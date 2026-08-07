"""Run lifecycle and stage actions for the governed factory.

Every mutation goes through an action method that:
1. checks the acting role (`roles.require`),
2. checks gate/stage preconditions (server-side, never the UI),
3. writes artifacts through the store (atomic JSON / append-only ledgers),
4. appends a provenance record (with content hash) and an activity event.

Phase 1 implements the run lifecycle and state assembly; stage actions land
phase by phase behind the same discipline.
"""

from __future__ import annotations

from typing import Any

from s7_delivery.factory import gates, roles, seed
from s7_delivery.factory.models import (
    Approval,
    ActivityEvent,
    DeliveryRun,
    DemoMode,
    GateId,
    GateRecord,
    ProvenanceRecord,
    Role,
    Stage,
    STAGE_ORDER,
    StageState,
    Status,
    now_iso,
)
from s7_delivery.factory.store import RunStore, StoreError, next_run_id, sha256_of


class EngineError(Exception):
    """A rule violation: bad transition, unmet gate, unknown id."""


GATE_LABELS = {
    GateId.INTAKE: "Intake complete",
    GateId.PLAN_SIGNOFF: "Plan sign-off",
    GateId.INDEPENDENT_REVIEW: "Independent review",
    GateId.QUALITY: "Quality",
    GateId.RELEASE: "Release",
}


class Engine:
    """All operations on one run. Stateless between calls — disk is truth."""

    def __init__(self, run_id: str, root=None):
        self.store = RunStore(run_id, root=root)
        self.run_id = self.store.run_id

    # --- lifecycle ----------------------------------------------------------

    @classmethod
    def create(cls, mode: DemoMode = DemoMode.SIMULATION, root=None) -> "Engine":
        run_id = next_run_id(root)
        eng = cls(run_id, root=root)
        run = DeliveryRun(
            run_id=run_id,
            scenario_id=seed.SCENARIO.scenario_id,
            mode=mode,
            status=Status.READY,
            stages=[StageState(stage=s) for s in STAGE_ORDER],
        )
        run.stage(Stage.INTAKE).status = Status.READY
        eng.store.write_json(run, "run.json")
        eng.store.write_json(seed.SCENARIO, "scenario.json")
        eng.store.write_json(seed.REQUIREMENT, "intake", "requirement.json")
        eng._gates_init()
        eng._record(
            artifact_id=seed.REQUIREMENT.request_id,
            artifact_type="requirement",
            payload=seed.REQUIREMENT,
            author=seed.REQUIREMENT.business_owner,
            stage=Stage.INTAKE,
            action="seed",
            outcome="created",
        )
        eng._activity(
            stage=Stage.INTAKE,
            actor="system",
            actor_type="service",
            workflow="run-lifecycle",
            outcome="run created",
            details=f"mode={mode.value}",
        )
        return eng

    def run(self) -> DeliveryRun:
        return DeliveryRun.model_validate(self.store.read_json("run.json"))

    def _save_run(self, run: DeliveryRun) -> None:
        self.store.write_json(run, "run.json")

    def reset(self, role: Role) -> None:
        """Restore the run to its seeded state. Ledgers are truncated too:
        a reset is a new rehearsal, not history to preserve (spec §20)."""
        roles.require("manage_run", role)
        import shutil

        root = self.store.root
        if root.exists():
            shutil.rmtree(root)
        run = DeliveryRun(
            run_id=self.run_id,
            scenario_id=seed.SCENARIO.scenario_id,
            mode=DemoMode.SIMULATION,
            status=Status.READY,
            stages=[StageState(stage=s) for s in STAGE_ORDER],
        )
        run.stage(Stage.INTAKE).status = Status.READY
        self.store.write_json(run, "run.json")
        self.store.write_json(seed.SCENARIO, "scenario.json")
        self.store.write_json(seed.REQUIREMENT, "intake", "requirement.json")
        self._gates_init()
        self._activity(
            stage=Stage.INTAKE, actor="system", actor_type="service",
            workflow="run-lifecycle", outcome="run reset to seed",
        )

    # --- gates --------------------------------------------------------------

    def _gates_init(self) -> None:
        gates = [
            GateRecord(gate_id=g, label=GATE_LABELS[g]).model_dump(mode="json")
            for g in GateId
        ]
        self.store.write_json(gates, "gates.json")

    def gates(self) -> list[GateRecord]:
        return [GateRecord.model_validate(g) for g in self.store.read_json("gates.json")]

    def _save_gate(self, gate: GateRecord) -> None:
        gates = self.gates()
        out = [gate if g.gate_id == gate.gate_id else g for g in gates]
        self.store.write_json([g.model_dump(mode="json") for g in out], "gates.json")

    def gate(self, gate_id: GateId) -> GateRecord:
        for g in self.gates():
            if g.gate_id == gate_id:
                return g
        raise EngineError(f"Unknown gate {gate_id}")

    # --- ledger plumbing ----------------------------------------------------

    def _record(
        self,
        *,
        artifact_id: str,
        artifact_type: str,
        payload: Any,
        author: str,
        stage: Stage,
        action: str,
        outcome: str,
        inputs: list[str] | None = None,
        version: int = 1,
        previous_version: int | None = None,
    ) -> ProvenanceRecord:
        existing = self.store.read_ledger("provenance.jsonl")
        rec = ProvenanceRecord(
            event_id=f"PRV-{len(existing) + 1:04d}",
            artifact_id=artifact_id,
            artifact_type=artifact_type,
            version=version,
            sha256=sha256_of(payload),
            author=author,
            inputs=inputs or [],
            previous_version=previous_version,
            run_id=self.run_id,
            stage=stage.value,
            action=action,
            outcome=outcome,
        )
        self.store.append(rec, "provenance.jsonl")
        return rec

    def _activity(
        self,
        *,
        stage: Stage,
        actor: str,
        actor_type: str,
        workflow: str = "",
        skill: str = "",
        artifact: str = "",
        duration_s: float = 0.0,
        outcome: str = "",
        details: str = "",
    ) -> None:
        self.store.append(
            ActivityEvent(
                run_id=self.run_id,
                stage=stage.value,
                actor=actor,
                actor_type=actor_type,
                workflow=workflow,
                skill=skill,
                artifact=artifact,
                duration_s=duration_s,
                outcome=outcome,
                details=details,
            ),
            "activity.jsonl",
        )

    # --- state assembly -----------------------------------------------------

    def state(self) -> dict[str, Any]:
        """Everything the Control Centre renders, in one payload."""
        run = self.run()
        provenance = self.store.read_ledger("provenance.jsonl")
        activity = self.store.read_ledger("activity.jsonl")
        current = self._latest_versions(provenance)
        stale = self.store.read_json_or([], "staleness.json")
        stale_ids = {s["artifact_id"] for s in stale}
        for row in current:
            row["stale"] = row["artifact_id"] in stale_ids
        return {
            "run": run.model_dump(mode="json"),
            "scenario": self.store.read_json("scenario.json"),
            "gates": [g.model_dump(mode="json") for g in self.gates()],
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
            },
            "planning": {
                "stories": self.store.read_json_or([], "planning", "stories.json"),
                "plan": self.store.read_json_or(None, "planning", "plan.json"),
            },
            "build": {
                "tasks": self.store.read_json_or([], "build", "tasks.json"),
                "reviews": self.store.read_json_or([], "review", "reviews.json"),
            },
            "quality": self.store.read_json_or(None, "quality", "quality-report.json"),
            "release": self.store.read_json_or(None, "release", "release-record.json"),
            "staleness": stale,
            "amendments": self.store.read_ledger("amendments.jsonl"),
            "approvals": self.store.read_ledger("approvals.jsonl"),
            "provenance": current,
            "provenance_ledger": provenance,
            "activity": activity,
            "activity_summary": self._activity_summary(activity),
        }

    @staticmethod
    def _latest_versions(provenance: list[dict]) -> list[dict]:
        """Current view of the ledger: one row per artifact, latest version."""
        latest: dict[str, dict] = {}
        for rec in provenance:
            latest[rec["artifact_id"]] = rec
        return sorted(latest.values(), key=lambda r: r["event_id"])

    @staticmethod
    def _activity_summary(activity: list[dict]) -> dict[str, Any]:
        by_outcome = {
            "ai_workflows": 0,
            "human_approvals": 0,
            "artifacts_created": 0,
            "artifacts_amended": 0,
            "gate_failures": 0,
            "gate_retries": 0,
        }
        stage_time: dict[str, float] = {}
        for ev in activity:
            if ev.get("actor_type") == "simulation":
                by_outcome["ai_workflows"] += 1
            if "approval" in ev.get("workflow", ""):
                by_outcome["human_approvals"] += 1
            if ev.get("outcome", "").startswith("created"):
                by_outcome["artifacts_created"] += 1
            if ev.get("outcome", "").startswith("amended"):
                by_outcome["artifacts_amended"] += 1
            if "gate" in ev.get("workflow", "") and ev.get("outcome") == "failed":
                by_outcome["gate_failures"] += 1
            if "gate" in ev.get("workflow", "") and ev.get("outcome") == "retried":
                by_outcome["gate_retries"] += 1
            stage_time[ev.get("stage", "?")] = (
                stage_time.get(ev.get("stage", "?"), 0.0) + float(ev.get("duration_s", 0))
            )
        return {"counters": by_outcome, "stage_time_s": stage_time,
                "total_events": len(activity)}

    # --- stage helpers ------------------------------------------------------

    def _advance_stage(self, run: DeliveryRun, done: Stage) -> None:
        """Mark a stage completed and ready the next one."""
        state = run.stage(done)
        state.status = Status.COMPLETED
        state.completed_at = now_iso()
        idx = STAGE_ORDER.index(done)
        if idx + 1 < len(STAGE_ORDER):
            nxt = run.stage(STAGE_ORDER[idx + 1])
            if nxt.status == Status.NOT_STARTED:
                nxt.status = Status.READY
        self._save_run(run)

    def _stage_in_progress(self, stage: Stage) -> None:
        run = self.run()
        state = run.stage(stage)
        if state.status == Status.NOT_STARTED:
            raise EngineError(
                f"Stage {stage.value} has not been opened by the preceding gate"
            )
        if state.status in (Status.READY, Status.WAITING_INPUT):
            state.status = Status.IN_PROGRESS
            if not state.started_at:
                state.started_at = now_iso()
            self._save_run(run)

    # --- intake (spec §7) ---------------------------------------------------

    def intake_analyse(self, role: Role) -> None:
        roles.require("run_intake_analysis", role)
        self._stage_in_progress(Stage.INTAKE)
        analysis = seed.ANALYSIS.model_copy(update={"generated_at": now_iso()})
        self.store.write_json(analysis, "intake", "analysis.json")
        self._record(
            artifact_id="ANL-001", artifact_type="intake_analysis",
            payload=analysis, author="intake-analysis (simulated)",
            stage=Stage.INTAKE, action="analyse",
            outcome="created", inputs=[seed.REQUIREMENT.request_id],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="intake-analysis", artifact="ANL-001", duration_s=6.0,
            outcome="created", details="requirement analysed; open questions surfaced",
        )

    def intake_create_epic(self, role: Role) -> None:
        roles.require("create_epic", role)
        if not self.store.exists("intake", "analysis.json"):
            raise EngineError("Run intake analysis before creating the epic")
        epic = seed.EPIC.model_copy(update={"created_at": now_iso()})
        self.store.write_json(epic, "intake", "epic.json")
        self._record(
            artifact_id=epic.epic_id, artifact_type="epic", payload=epic,
            author=epic.created_by, stage=Stage.INTAKE, action="create-epic",
            outcome="created", inputs=[seed.REQUIREMENT.request_id, "ANL-001"],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="epic-creation", artifact=epic.epic_id, duration_s=3.0,
            outcome="created",
        )

    def intake_pass_gate(self, role: Role) -> None:
        roles.require("pass_intake_gate", role)
        conditions = gates.intake_gate(
            self.store.read_json_or(None, "intake", "requirement.json"),
            self.store.read_json_or(None, "intake", "analysis.json"),
            self.store.read_json_or(None, "intake", "epic.json"),
        )
        gate = self.gate(GateId.INTAKE)
        gate.conditions = conditions
        if not gates.all_met(conditions):
            gate.status = Status.BLOCKED
            self._save_gate(gate)
            unmet = "; ".join(c["condition"] for c in conditions if not c["met"])
            self._activity(
                stage=Stage.INTAKE, actor=role.value, actor_type="human",
                workflow="intake-gate", outcome="failed", details=unmet,
            )
            raise EngineError(f"Intake gate blocked — unmet: {unmet}")
        gate.status = Status.PASSED
        gate.decided_by = role.value
        gate.decided_at = now_iso()
        self._save_gate(gate)
        run = self.run()
        self._advance_stage(run, Stage.INTAKE)
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="intake-gate", outcome="passed",
        )

    # --- planning (spec §8) -------------------------------------------------

    EDITABLE_STORY_FIELDS = {
        "accountable_team", "owner", "estimate", "sprint", "dependencies",
        "acceptance_criteria", "contributing_teams", "risk",
    }

    def _stories(self) -> list[dict]:
        return self.store.read_json_or([], "planning", "stories.json")

    def planning_generate(self, role: Role) -> None:
        roles.require("generate_plan", role)
        if self.gate(GateId.INTAKE).status != Status.PASSED:
            raise EngineError("Planning opens after the intake gate (G0) passes")
        if self.run().plan_locked:
            raise EngineError("The plan is locked; use an amendment to change it")
        self._stage_in_progress(Stage.PLANNING)
        stories = [s.model_dump(mode="json") for s in seed.build_stories()]
        self.store.write_json(stories, "planning", "stories.json")
        for s in stories:
            self._record(
                artifact_id=s["story_id"], artifact_type="story", payload=s,
                author="planning (simulated)", stage=Stage.PLANNING,
                action="decompose", outcome="created",
                inputs=[s["epic_id"], seed.REQUIREMENT.request_id],
            )
        self._activity(
            stage=Stage.PLANNING, actor="planning", actor_type="simulation",
            workflow="epic-decomposition", duration_s=12.0, outcome="created",
            details=f"{len(stories)} stories across "
            f"{len({s['accountable_team'] for s in stories})} teams",
        )

    def edit_story(self, role: Role, story_id: str, patch: dict) -> None:
        roles.require("edit_story", role)
        if self.run().plan_locked:
            raise EngineError(
                "The signed plan is locked; changes require an amendment"
            )
        stories = self._stories()
        target = next((s for s in stories if s["story_id"] == story_id), None)
        if target is None:
            raise EngineError(f"Unknown story {story_id}")
        illegal = set(patch) - self.EDITABLE_STORY_FIELDS
        if illegal:
            raise EngineError(f"Fields not editable: {', '.join(sorted(illegal))}")
        previous = target["version"]
        target.update(patch)
        target["version"] = previous + 1
        self.store.write_json(stories, "planning", "stories.json")
        self._record(
            artifact_id=story_id, artifact_type="story", payload=target,
            author=role.value, stage=Stage.PLANNING, action="edit",
            outcome=f"amended ({', '.join(sorted(patch))})",
            version=target["version"], previous_version=previous,
        )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="story-edit", artifact=story_id,
            outcome="amended", details=", ".join(sorted(patch)),
        )

    def planning_revise(self, role: Role, feedback: str) -> None:
        roles.require("request_plan_revision", role)
        if self.run().plan_locked:
            raise EngineError("The signed plan is locked; changes require an amendment")
        if not feedback.strip():
            raise EngineError("Revision feedback is required")
        notes = self.store.read_json_or([], "planning", "revision-notes.json")
        notes.append({"at": now_iso(), "by": role.value, "feedback": feedback.strip()})
        self.store.write_json(notes, "planning", "revision-notes.json")
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="plan-revision", outcome="requested", details=feedback.strip()[:200],
        )

    def planning_sign_off(self, role: Role, approver: str, note: str = "") -> None:
        roles.require("sign_off_plan", role)
        stories = self._stories()
        conditions = gates.plan_signoff_gate(stories, approver)
        gate = self.gate(GateId.PLAN_SIGNOFF)
        gate.conditions = conditions
        if not gates.all_met(conditions):
            gate.status = Status.BLOCKED
            self._save_gate(gate)
            unmet = "; ".join(c["condition"] for c in conditions if not c["met"])
            self._activity(
                stage=Stage.PLANNING, actor=approver or role.value,
                actor_type="human", workflow="plan-signoff-gate",
                outcome="failed", details=unmet,
            )
            raise EngineError(f"Plan sign-off blocked — unmet: {unmet}")

        run = self.run()
        run.plan_locked = True
        run.plan_version += 1
        self._save_run(run)

        plan = {
            "plan_version": run.plan_version,
            "signed_by": approver,
            "signed_at": now_iso(),
            "note": note,
            "story_ids": [s["story_id"] for s in stories],
            "story_versions": {s["story_id"]: s["version"] for s in stories},
        }
        self.store.write_json(plan, "planning", "plan.json")
        self.store.write_text(self._plan_markdown(plan, stories), "planning", "plan.md")

        gate.status = Status.PASSED
        gate.decided_by = approver
        gate.decided_at = now_iso()
        gate.note = note
        self._save_gate(gate)

        approvals = self.store.read_ledger("approvals.jsonl")
        self.store.append(
            Approval(
                approval_id=f"APR-{len(approvals) + 1:03d}",
                subject="plan",
                role=role,
                approver=approver,
                decision="approved",
                note=note,
            ),
            "approvals.jsonl",
        )
        self._record(
            artifact_id="PLAN-001", artifact_type="plan", payload=plan,
            author=approver, stage=Stage.PLANNING, action="sign-off",
            outcome="created", inputs=[s["story_id"] for s in stories],
            version=run.plan_version,
        )
        run = self.run()
        self._advance_stage(run, Stage.PLANNING)
        self._seed_tasks(stories)
        self._activity(
            stage=Stage.PLANNING, actor=approver, actor_type="human",
            workflow="plan-signoff-approval", outcome="passed",
            details=f"plan v{plan['plan_version']} locked; downstream work opened",
        )

    def _seed_tasks(self, stories: list[dict]) -> None:
        """Create the work queue from the signed plan — one task per
        implementation story, dependency order preserved. The demo processes
        one task at a time (spec §9A); US-003 carries the deliberate defect."""
        from s7_delivery.factory.models import TaskRecord

        tasks = []
        for i, s in enumerate(stories, start=1):
            tasks.append(
                TaskRecord(
                    task_id=f"TASK-{i:03d}",
                    story_id=s["story_id"],
                    summary=s["title"],
                    accountable_team=s["accountable_team"],
                    dependencies=s.get("dependencies", []),
                    status=Status.READY if not s.get("dependencies") else Status.NOT_STARTED,
                ).model_dump(mode="json")
            )
        self.store.write_json(tasks, "build", "tasks.json")

    @staticmethod
    def _plan_markdown(plan: dict, stories: list[dict]) -> str:
        lines = [
            "# Delivery plan — EPIC-S7-001",
            "",
            f"Version {plan['plan_version']}, signed by {plan['signed_by']} "
            f"at {plan['signed_at']}.",
            "",
            "This signed plan is the contract for downstream work. Changes "
            "after sign-off require an amendment with its own approval.",
            "",
            "| Story | Title | Team | Component | Depends on | Est | Sprint |",
            "|---|---|---|---|---|---|---|",
        ]
        for s in stories:
            lines.append(
                f"| {s['story_id']} | {s['title']} | {s['accountable_team']} "
                f"| {s['target_component']} | {', '.join(s.get('dependencies', [])) or '—'} "
                f"| {s['estimate']} | {s['sprint']} |"
            )
        lines += ["", "## Acceptance criteria", ""]
        for s in stories:
            lines.append(f"### {s['story_id']} — {s['title']}")
            for ac in s["acceptance_criteria"]:
                lines.append(f"- **{ac['ac_id']}** {ac['text']}")
            lines.append("")
        return "\n".join(lines)
