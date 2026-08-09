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

import hashlib
import json
import os
import re
import subprocess
from typing import Any

from s7_delivery.factory import architecture_checks, build_phases, gates, roles, seed
from s7_delivery.factory.models import (
    STAGE_ORDER,
    AcceptanceCriterion,
    ActivityEvent,
    Approval,
    ArchitectureMeta,
    BuildReviewPhase,
    DeliveryPack,
    DeliveryRun,
    DemoMode,
    DeveloperWorkspace,
    EpicRecord,
    GateId,
    GateRecord,
    GitPublication,
    Provenance,
    ProvenanceRecord,
    Requirement,
    RequirementExtraction,
    Role,
    RollbackPlan,
    Stage,
    StageState,
    Status,
    Story,
    now_iso,
)
from s7_delivery.factory.store import RunStore, StoreError, next_run_id, sha256_of


class EngineError(Exception):
    """A rule violation: bad transition, unmet gate, unknown id."""


GATE_LABELS = {
    GateId.INTAKE: "Intake complete",
    GateId.PLAN_SIGNOFF: "Plan sign-off",
    GateId.INDEPENDENT_REVIEW: "Independent review",
    GateId.QUALITY: "Final Gating",
    GateId.RELEASE: "Release",
}

MAX_SOURCE_CHARS = 20_000  # long enough for any realistic epic doc, short
                            # enough to keep both the parser and the LLM
                            # prompt bounded (CLAUDE.md § intake extraction)


_DEPLOY_CHECKLIST = """# Deployment checklist — REL-2026R4-001 (demonstration)

- [x] All gates G0–G3 passed
- [x] Required approvals recorded (business owner, engineering, QA, release,
  support)
- [x] Feature flag `sponsor_claim_submission` off at deploy
- [x] Blue-green targets healthy pre-deploy
- [x] Rollback validated in staging
- [x] Monitoring alerts configured
- [x] Transition to maintenance prepared
"""

_ROLLBACK_PLAN = """# Rollback plan — REL-2026R4-001 (demonstration)

Method: disable the `sponsor_claim_submission` feature flag, restoring the
previous journey entry point. Database changes are additive; reverse
migration validated in staging. RTO 15 minutes, RPO 0 (no destructive change).
"""

_RUNBOOK = """# Runbook — sponsor claim submission (demonstration)

Alerts: submission error rate, intake-handoff retry depth, lookup latency p95.
First response: check flag state, then the retry queue; escalate to Platform
Team on-call if handoff failures persist beyond one retry cycle.
"""

_HANDOVER_DOC = """# Support handover — REL-2026R4-001 (demonstration)

## Transition to maintenance

Support team: MapleSure Application Support (S1–S6 scope).
Hypercare: 7 days. Known limitations: provisional status vocabulary and
partial-submission retention pending SME confirmation.

- Knowledge repository: KB-2026-0473 updated — application documentation
  refreshed for components changed by this release (demonstration).
"""


class Engine:
    """All operations on one run. Stateless between calls — disk is truth."""

    def __init__(self, run_id: str, root=None):
        self.store = RunStore(run_id, root=root)
        self.run_id = self.store.run_id

    # --- lifecycle ----------------------------------------------------------

    @classmethod
    def create(cls, mode: DemoMode = DemoMode.SIMULATION, root=None) -> Engine:
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
        # Staleness is recomputed on every ledger append: a new version of an
        # upstream artifact marks its downstream stale immediately, and a
        # correction (new downstream version) clears itself the same way.
        from s7_delivery.factory import staleness as _staleness

        self.store.write_json(
            _staleness.detect(self.store.read_ledger("provenance.jsonl")),
            "staleness.json",
        )
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
        new_app = self.store.read_json_or(None, "intake", "new_app.json")
        scaffold = None
        if new_app and new_app.get("name"):
            files = self._scaffold_dir_files(new_app["name"])
            scaffold = files or None
        return {
            "run": run.model_dump(mode="json"),
            "scenario": self.store.read_json("scenario.json"),
            "gates": [g.model_dump(mode="json") for g in self.gates()],
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "source": self.store.read_json_or(None, "intake", "source.json"),
                "extraction": self.store.read_json_or(None, "intake", "extraction.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
                "routing": self.store.read_json_or(None, "intake", "routing.json"),
                "new_app": new_app,
                "scaffold": scaffold,
            },
            "planning": {
                "stories": self.store.read_json_or([], "planning", "stories.json"),
                "original_stories": self.store.read_json_or(
                    [], "planning", "stories.original.json"
                ),
                "plan": self.store.read_json_or(None, "planning", "plan.json"),
                "confidence": self.store.read_json_or(None, "planning", "confidence.json"),
                "rationale": self.store.read_json_or(None, "planning", "rationale.json"),
            },
            "build": self._build_state(run),
            "quality": self.store.read_json_or(None, "quality", "quality-report.json"),
            "release": self.store.read_json_or(None, "release", "release-record.json"),
            "staleness": stale,
            "amendments": self.store.read_ledger("amendments.jsonl"),
            "approvals": self.store.read_ledger("approvals.jsonl"),
            "design": self.store.read_json_or(None, "planning", "design.json"),
            "traceability": self.traceability(),
            "provenance": current,
            "provenance_ledger": provenance,
            "activity": activity,
            "activity_summary": self._activity_summary(activity),
        }

    def _build_state(self, run: DeliveryRun) -> dict[str, Any]:
        """The Build & Review section of `state()` — control-plane view:
        phase, canonical architecture, delivery packs, workspaces, publication
        records and developer-execution evidence. Extended per implementation
        phase; sections read as None/[] until their capability has run."""
        phase = build_phases.read_phase(self.store, plan_locked=run.plan_locked)
        stories = self._stories()
        tasks = self.store.read_json_or([], "build", "tasks.json")
        latest_reviews = self._latest_reviews()
        stale_ids = {
            s["artifact_id"]
            for s in self.store.read_json_or([], "staleness.json")
        }
        handoff = gates.quality_handoff_rows(stories, tasks, latest_reviews, stale_ids)
        return {
            "phase": phase.value if phase else None,
            "phase_history": build_phases.history(self.store),
            "tasks": tasks,
            "reviews": self.store.read_json_or([], "review", "reviews.json"),
            "architecture": self.store.read_json_or(None, "architecture", "meta.json"),
            "delivery_packs": [
                {**p, **dict(zip(("artifact_count", "size_bytes"), self._pack_stats(p)))}
                for p in self._packs()
            ],
            "workspaces": self._workspaces_view(),
            "publications": self.store.read_ledger("publications.jsonl"),
            "summary": self._build_summary(
                stories, tasks, latest_reviews, stale_ids, handoff
            ),
            "quality_handoff": handoff,
        }

    def _build_summary(
        self,
        stories: list[dict],
        tasks: list[dict],
        latest_reviews: dict[str, dict],
        stale_ids: set[str],
        handoff: list[dict],
    ) -> dict[str, Any]:
        """Consolidated Build & Review outcome (spec §20): per-story rollup,
        totals, blockers and Final-Gating-ready stories — assembled, never
        stored."""
        tasks_by_story = {t["story_id"]: t for t in tasks}
        ready_ids = {h["story_id"] for h in handoff if h["ready"]}
        workspaces = {w["story_id"]: w for w in self._workspaces()}
        rows: list[dict] = []
        blockers: list[dict] = []
        for s in stories:
            sid = s["story_id"]
            task = tasks_by_story.get(sid)
            status = (task or {}).get("status", "not_started")
            review = latest_reviews.get((task or {}).get("task_id", ""))
            tests = (task or {}).get("tests", [])
            passed = sum(1 for t in tests if t.get("current_result") == "passed")
            if not tests:
                testing = "waiting"
            elif passed == len(tests):
                testing = "passed"
            else:
                testing = "failing"
            if review is None:
                review_status = "pending"
            elif review.get("result") == "passed":
                review_status = "passed"
            else:
                review_status = "blocked"
            if sid in ready_ids:
                overall = "ready_for_quality"
            elif status == "blocked" or review_status == "blocked":
                overall = "blocked"
            elif status in ("not_started", "ready"):
                overall = "not_started"
            elif status == "completed":
                overall = "complete"
            else:
                overall = "in_development"
            rows.append(
                {
                    "story_id": sid,
                    "title": s.get("title", ""),
                    "team": s.get("accountable_team", ""),
                    "developer": workspaces.get(sid, {}).get("developer", ""),
                    "development": self._DEV_STATUS.get(status, status),
                    "testing": testing,
                    "tests_passed": passed,
                    "tests_total": len(tests),
                    "review": review_status,
                    "overall": overall,
                    "stale": sid in stale_ids or f"WS-{sid}" in stale_ids,
                    "last_updated": (task or {}).get("last_activity", ""),
                }
            )
            if overall == "blocked" and review is not None:
                finding = next(iter(review.get("findings", [])), None)
                blockers.append(
                    {
                        "story_id": sid,
                        "team": s.get("accountable_team", ""),
                        "reason": (finding or {}).get("summary", "blocked in review"),
                    }
                )
        total_tests = sum(r["tests_total"] for r in rows)
        total_passed = sum(r["tests_passed"] for r in rows)
        reviewed = [r for r in rows if r["review"] != "pending"]
        return {
            "stories": rows,
            "totals": {
                "total": len(rows),
                "complete": sum(1 for r in rows if r["overall"]
                                in ("complete", "ready_for_quality")),
                "in_progress": sum(
                    1 for r in rows if r["overall"] == "in_development"
                ),
                "blocked": sum(1 for r in rows if r["overall"] == "blocked"),
                "not_started": sum(
                    1 for r in rows if r["overall"] == "not_started"
                ),
                "ready_for_quality": len(ready_ids),
                "tests_passed": total_passed,
                "tests_total": total_tests,
                "review_pass_rate": (
                    round(
                        100
                        * sum(1 for r in reviewed if r["review"] == "passed")
                        / len(reviewed)
                    )
                    if reviewed else None
                ),
            },
            "blockers": blockers,
            "ready_story_ids": sorted(ready_ids),
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
            if ev.get("actor_type") in ("simulation", "live_ai"):
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
        if self.run().mode is DemoMode.LIVE:
            self._intake_analyse_live()
            return
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

    def _intake_analyse_live(self) -> None:
        """The live path: real model call over the connected repos' context.
        Raises (never falls back) on failure — CLAUDE.md § Staged output."""
        import time

        from s7_delivery.factory import live_intake

        packs = self._context_packs()
        if not packs:
            raise EngineError(
                "Live analysis needs a connected repository — use "
                "'Connect repository' first."
            )
        requirement = self.store.read_json("intake", "requirement.json")
        transcript = (self.store.read_json_or({}, "intake", "clarifications.json")
                      .get("transcript", []))
        t0 = time.monotonic()
        analysis, usage = live_intake.run_analysis(requirement, packs, transcript)
        self.store.write_json(analysis, "intake", "analysis.json")
        repo_ids = [f"REPO-{name}" for name in sorted(packs)]
        self._record(
            artifact_id="ANL-001", artifact_type="intake_analysis",
            payload=analysis, author="intake-analysis (live)",
            stage=Stage.INTAKE, action="analyse", outcome="created",
            inputs=[requirement["request_id"], *repo_ids],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="live_ai",
            workflow="intake-analysis", artifact="ANL-001",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def _clarifications(self) -> dict:
        return self.store.read_json_or(
            {"transcript": [], "pending": [], "rounds_used": 0,
             "max_rounds": 2},
            "intake", "clarifications.json",
        )

    def intake_clarify(self, role: Role) -> None:
        """Live mode only: the model asks its clarifying questions."""
        roles.require("ask_clarification", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("AI clarification runs in live mode only")
        import time

        from s7_delivery.factory import live_intake

        clar = self._clarifications()
        if clar["pending"]:
            raise EngineError("Answer the open questions before asking again")
        requirement = self.store.read_json("intake", "requirement.json")
        t0 = time.monotonic()
        questions, usage = live_intake.run_clarification(
            requirement, self._context_packs(), clar["transcript"]
        )
        clar["transcript"].append({"role": "assistant", "text": "\n".join(questions)})
        clar["pending"] = questions
        clar["rounds_used"] = sum(
            1 for t in clar["transcript"] if t["role"] == "assistant"
        )
        self.store.write_json(clar, "intake", "clarifications.json")
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="live_ai",
            workflow="clarification", duration_s=round(time.monotonic() - t0, 2),
            outcome="asked", details=f"{len(questions)} questions; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_clarify_answer(self, role: Role, answers: list[str]) -> None:
        roles.require("ask_clarification", role)
        clar = self._clarifications()
        if not clar["pending"]:
            raise EngineError("There are no open questions to answer")
        if len(answers) != len(clar["pending"]):
            raise EngineError(
                f"Expected {len(clar['pending'])} answers, got {len(answers)}"
            )
        joined = "\n".join(
            f"Q: {q}\nA: {a.strip() or '(no answer — make a stated assumption)'}"
            for q, a in zip(clar["pending"], answers, strict=True)
        )
        clar["transcript"].append({"role": "user", "text": joined})
        clar["pending"] = []
        self.store.write_json(clar, "intake", "clarifications.json")
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="clarification", outcome="answered",
            details=f"{len(answers)} answers recorded",
        )

    def intake_set_source(
        self, role: Role, text: str, filename: str | None = None,
        source_kind: str = "paste", raw_content: bytes | None = None,
    ) -> None:
        """The upload/paste front door: replaces the requirement's own text
        with real source content. Presence of intake/source.json is the
        single signal `intake_extract` and `intake_create_epic` use to know
        a real source was provided — the mechanism that keeps the default
        seeded demo path completely untouched (CLAUDE.md § intake extraction)."""
        roles.require("upload_intake_document", role)
        stripped = text.strip()
        if not stripped:
            raise EngineError("Source text is empty")
        if len(text) > MAX_SOURCE_CHARS:
            raise EngineError(
                f"Source text exceeds the {MAX_SOURCE_CHARS:,}-character limit "
                f"({len(text):,} chars) — trim it and try again"
            )
        safe_name = None
        if filename:
            safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename).lstrip(".") or "document"
            if raw_content is not None:
                self.store.write_bytes(raw_content, "intake", "documents", safe_name)
        req = Requirement.model_validate(self.store.read_json("intake", "requirement.json"))
        req.description = text
        req.source_type = "Uploaded document" if source_kind == "upload" else "Pasted text"
        req.source_documents = [safe_name] if safe_name else ["pasted-text"]
        self.store.write_json(req, "intake", "requirement.json")
        source = {
            "text": text, "filename": safe_name, "source_kind": source_kind,
            "set_at": now_iso(),
        }
        self.store.write_json(source, "intake", "source.json")
        self._record(
            artifact_id=req.request_id, artifact_type="requirement", payload=req,
            author=role.value, stage=Stage.INTAKE, action="set-source",
            outcome="amended",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="set-source", outcome="set",
            details=f"{source_kind}: {safe_name or '(pasted text)'}, {len(text)} chars",
        )

    def intake_extract(self, role: Role) -> None:
        roles.require("run_intake_analysis", role)
        source = self.store.read_json_or(None, "intake", "source.json")
        if source is None:
            raise EngineError("Provide a source document or pasted text before extracting")

        if self.run().mode is DemoMode.LIVE:
            import time

            from s7_delivery.factory import live_intake

            t0 = time.monotonic()
            result, usage = live_intake.run_extraction(source["text"])
            method, provenance, actor_type = "live_llm", live_intake.provenance_now(), "live_ai"
            duration = round(time.monotonic() - t0, 2)
            details = f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens"
        else:
            from s7_delivery.factory import extraction

            result = extraction.extract_requirement(source["text"])
            method, provenance, actor_type = "rule_based", Provenance.RULE_BASED, "simulation"
            duration = 0.0
            details = f"{len(result['extracted_requirements'])} requirements found"

        record = RequirementExtraction(
            epic_title=result["epic_title"],
            business_objective=result["business_objective"],
            requirement_summary=result["requirement_summary"],
            extracted_requirements=result["extracted_requirements"],
            method=method,
            provenance=provenance,
        )
        self.store.write_json(record, "intake", "extraction.json")

        req = Requirement.model_validate(self.store.read_json("intake", "requirement.json"))
        req.title = record.epic_title
        self.store.write_json(req, "intake", "requirement.json")

        self._record(
            artifact_id="EXT-001", artifact_type="requirement_extraction",
            payload=record, author=f"intake-extraction ({method})",
            stage=Stage.INTAKE, action="extract", outcome="created",
            inputs=[req.request_id],
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-extraction", actor_type=actor_type,
            workflow="intake-extraction", artifact="EXT-001",
            duration_s=duration, outcome="created", details=details,
        )

    def intake_create_epic(self, role: Role) -> None:
        roles.require("create_epic", role)
        if not self.store.exists("intake", "analysis.json"):
            raise EngineError("Run intake analysis before creating the epic")
        extraction = self.store.read_json_or(None, "intake", "extraction.json")
        if extraction is not None:
            req = self.store.read_json("intake", "requirement.json")
            req_count = len(extraction.get("extracted_requirements", []))
            epic = EpicRecord(
                epic_id=seed.EPIC.epic_id,
                title=extraction["epic_title"],
                business_outcome=extraction["business_objective"],
                estimated_stories=max(2, min(8, (req_count + 1) // 2)),
                status=Status.READY,
                created_by=f"intake-extraction ({extraction['method']})",
                provenance=Provenance(extraction["provenance"]),
            )
            epic_inputs = [req["request_id"], "EXT-001", "ANL-001"]
        else:
            epic = seed.EPIC.model_copy(update={"created_at": now_iso()})
            epic_inputs = [seed.REQUIREMENT.request_id, "ANL-001"]
        self.store.write_json(epic, "intake", "epic.json")
        self._record(
            artifact_id=epic.epic_id, artifact_type="epic", payload=epic,
            author=epic.created_by, stage=Stage.INTAKE, action="create-epic",
            outcome="created", inputs=epic_inputs,
        )
        self._activity(
            stage=Stage.INTAKE, actor="intake-analysis", actor_type="simulation",
            workflow="epic-creation", artifact=epic.epic_id, duration_s=3.0,
            outcome="created",
        )

    EDITABLE_EXTRACTION_FIELDS = {
        "epic_title", "business_objective", "requirement_summary",
        "extracted_requirements",
    }

    def intake_edit_extraction(self, role: Role, patch: dict) -> None:
        roles.require("edit_requirement", role)
        data = self.store.read_json_or(None, "intake", "extraction.json")
        if data is None:
            raise EngineError("No extraction to edit — run extraction first")
        illegal = set(patch) - self.EDITABLE_EXTRACTION_FIELDS
        if illegal:
            raise EngineError(f"Fields not editable: {', '.join(sorted(illegal))}")
        blank = sorted(
            field for field in ("epic_title", "business_objective", "requirement_summary")
            if field in patch and isinstance(patch[field], str) and not patch[field].strip()
        )
        if blank:
            raise EngineError(f"Fields cannot be blank: {', '.join(blank)}")
        data.update(patch)
        data["edited_by"] = role.value
        data["edited_at"] = now_iso()
        try:
            record = RequirementExtraction.model_validate(data)
        except Exception as exc:  # pydantic ValidationError -> engine's own error type
            raise EngineError(f"Invalid extraction patch: {exc}") from exc
        self.store.write_json(record, "intake", "extraction.json")
        self._record(
            artifact_id="EXT-001", artifact_type="requirement_extraction",
            payload=record, author=role.value, stage=Stage.INTAKE, action="edit",
            outcome=f"amended ({', '.join(sorted(patch))})",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="extraction-edit", artifact="EXT-001",
            outcome="amended", details=", ".join(sorted(patch)),
        )

    def intake_finalize(self, role: Role) -> None:
        """One-shot action for the upload/paste panel's "Create Epic &
        Proceed to Planning" button: runs analysis first only if it hasn't
        run yet, then creates the epic. `run_intake_analysis` and
        `create_epic` are permitted to the identical pair of roles in
        roles.py, so this is a plain sequencing wrapper over the two
        existing, unmodified public methods — no new permission surface,
        and intake_create_epic's own precondition stays exactly as it was."""
        if not self.store.exists("intake", "analysis.json"):
            self.intake_analyse(role)
        self.intake_create_epic(role)

    def intake_upload_document(self, role: Role, filename: str, content: bytes) -> str:
        """Attach a source document to the requirement. Demo evidence only —
        the content is stored under the run's own artifact directory
        (gitignored, spec §19), never inspected or parsed."""
        roles.require("upload_intake_document", role)
        safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename).lstrip(".") or "document"
        req_data = self.store.read_json_or(None, "intake", "requirement.json")
        if req_data is None:
            raise EngineError("Upload a requirement before attaching a document")
        req = Requirement.model_validate(req_data)
        if safe_name not in req.source_documents:
            req.source_documents = [*req.source_documents, safe_name]
        self.store.write_bytes(content, "intake", "documents", safe_name)
        self.store.write_json(req, "intake", "requirement.json")
        self._record(
            artifact_id=safe_name, artifact_type="source_document",
            payload={"filename": safe_name, "bytes": len(content)},
            author=role.value, stage=Stage.INTAKE, action="upload-document",
            outcome="created", inputs=[req.request_id],
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="upload-document", artifact=safe_name,
            outcome="uploaded", details=f"{len(content)} bytes",
        )
        return safe_name

    def intake_connect_repo(self, role: Role, url: str) -> None:
        """Connect a target repository: shallow clone under the run's own
        artifact tree, record metadata, store the context pack that grounds
        every live call (spec: live-control-centre §2)."""
        roles.require("connect_repository", role)
        from s7_delivery.factory.repos import (
            RepoConnectError,
            build_context_pack,
            clone_repo,
            remember_repo,
        )

        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            raise EngineError(f"Repository clone failed: {exc}") from exc

        from s7_delivery.factory import ci_bootstrap
        repo_dir = self.store.path("repos", rec.name)
        stack = ci_bootstrap.detect_stack_from_files(repo_dir)
        try:
            bootstrap_status = ci_bootstrap.bootstrap(repo_dir, rec.default_branch, stack)
        except ci_bootstrap.CiBootstrapError:
            bootstrap_status = "push_failed"

        repos = self.store.read_json_or([], "intake", "repos.json")
        rec_dict = rec.model_dump(mode="json")
        rec_dict["ci_bootstrap_status"] = bootstrap_status
        repos.append(rec_dict)
        self.store.write_json(repos, "intake", "repos.json")

        pack = build_context_pack(self.store.path("repos", rec.name), rec.name)
        self.store.write_text(pack, "intake", "context", f"{rec.name}.md")

        self._record(
            artifact_id=f"REPO-{rec.name}", artifact_type="repository",
            payload=rec, author=role.value, stage=Stage.INTAKE,
            action="connect-repo", outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="connect-repository", artifact=rec.name,
            outcome="connected",
            details=f"{rec.url} @ {rec.head_sha[:10]}, {rec.file_count} files",
        )
        # Global memory, independent of this run: "if I already connected the
        # repository once, it should not ask me again if I reset."
        remember_repo({
            "url": rec.url, "name": rec.name,
            "default_branch": rec.default_branch, "last_connected_at": now_iso(),
        })

    def intake_remove_repo(self, role: Role, name: str) -> None:
        """Disconnect a repository from this run only — the global known-repos
        registry is untouched, so it can be reconnected with one click later.
        Refused once the plan is signed: repositories are load-bearing for the
        downstream lane after G1."""
        roles.require("connect_repository", role)
        if self.run().plan_locked:
            raise EngineError(
                "Plan is signed — repositories are load-bearing after G1; "
                "start a new run instead"
            )
        repos = self.store.read_json_or([], "intake", "repos.json")
        remaining = [r for r in repos if r.get("name") != name]
        if len(remaining) == len(repos):
            raise EngineError(f"Unknown repository {name!r}")
        self.store.write_json(remaining, "intake", "repos.json")

        import shutil

        shutil.rmtree(self.store.path("repos", name), ignore_errors=True)
        context_pack = self.store.path("intake", "context", f"{name}.md")
        if context_pack.exists():
            context_pack.unlink()

        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="connect-repository", artifact=name,
            outcome="removed", details=f"{name} disconnected from this run",
        )

    def _connected_repos(self) -> list[dict]:
        return self.store.read_json_or([], "intake", "repos.json")

    def _context_packs(self) -> dict[str, str]:
        return {
            r["name"]: self.store.path("intake", "context", f"{r['name']}.md")
            .read_text(encoding="utf-8")
            for r in self._connected_repos()
        }

    def _routing(self) -> dict | None:
        return self.store.read_json_or(None, "intake", "routing.json")

    def intake_route(self, role: Role) -> None:
        """Live mode only: classify routable vs new_application_needed
        before analysis runs."""
        roles.require("route_requirement", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("Requirement routing runs in live mode only")
        current = self._routing()
        if current and current.get("overridden_by"):
            raise EngineError(
                "The routing verdict was overridden by a human — reset the "
                "run or clear the override before re-routing"
            )
        import time

        from s7_delivery.factory import live_intake

        requirement = self.store.read_json("intake", "requirement.json")
        packs = self._context_packs()
        t0 = time.monotonic()
        verdict, usage = live_intake.route_requirement(requirement, packs)
        self.store.write_json(verdict, "intake", "routing.json")
        self._record(
            artifact_id="ROUTE-001", artifact_type="routing_verdict",
            payload=verdict, author="requirement-routing",
            stage=Stage.INTAKE, action="route", outcome="created",
            inputs=[requirement["request_id"]],
        )
        self._activity(
            stage=Stage.INTAKE, actor="requirement-routing",
            actor_type="live_ai" if packs else "system",
            workflow="requirement-routing",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"verdict={verdict.verdict}; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_override_route(self, role: Role, verdict: str) -> None:
        roles.require("route_requirement", role)
        current = self._routing()
        if current is None:
            raise EngineError("Run requirement routing before overriding it")
        if verdict not in {"routable", "new_application_needed"}:
            raise EngineError(f"Unknown verdict {verdict!r}")
        current["verdict"] = verdict
        current["overridden_by"] = role.value
        current["overridden_at"] = now_iso()
        self.store.write_json(current, "intake", "routing.json")
        self._record(
            artifact_id="ROUTE-001", artifact_type="routing_verdict",
            payload=current, author=role.value, stage=Stage.INTAKE,
            action="override", outcome="overridden",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="requirement-routing", outcome="overridden",
            details=f"verdict set to {verdict}",
        )

    def _new_app(self) -> dict:
        return self.store.read_json_or(
            {"transcript": [], "pending": [], "rounds_used": 0, "max_rounds": 2,
             "name": None, "description": None, "stack": None},
            "intake", "new_app.json",
        )

    def intake_new_app_setup(self, role: Role) -> None:
        roles.require("setup_new_application", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("New-application setup runs in live mode only")
        import time

        from s7_delivery.factory import live_intake

        setup = self._new_app()
        if setup["pending"]:
            raise EngineError("Answer the open questions before asking again")
        if setup["name"]:
            raise EngineError("New-application setup is already complete")
        requirement = self.store.read_json("intake", "requirement.json")
        t0 = time.monotonic()
        result, usage = live_intake.run_new_app_setup(requirement, setup["transcript"])
        if result["done"]:
            setup["name"] = result["name"]
            setup["description"] = result["description"]
            setup["stack"] = result["stack"]
            outcome = "settled"
        else:
            questions = result["questions"]
            setup["transcript"].append({"role": "assistant", "text": "\n".join(questions)})
            setup["pending"] = questions
            setup["rounds_used"] = sum(
                1 for t in setup["transcript"] if t["role"] == "assistant"
            )
            outcome = "asked"
        self.store.write_json(setup, "intake", "new_app.json")
        self._activity(
            stage=Stage.INTAKE, actor="new-app-setup", actor_type="live_ai",
            workflow="new-app-setup", duration_s=round(time.monotonic() - t0, 2),
            outcome=outcome,
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_new_app_answer(self, role: Role, answers: list[str]) -> None:
        roles.require("setup_new_application", role)
        setup = self._new_app()
        if not setup["pending"]:
            raise EngineError("There are no open questions to answer")
        if len(answers) != len(setup["pending"]):
            raise EngineError(
                f"Expected {len(setup['pending'])} answers, got {len(answers)}"
            )
        joined = "\n".join(
            f"Q: {q}\nA: {a.strip() or '(no answer — make a stated assumption)'}"
            for q, a in zip(setup["pending"], answers, strict=True)
        )
        setup["transcript"].append({"role": "user", "text": joined})
        setup["pending"] = []
        self.store.write_json(setup, "intake", "new_app.json")
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="new-app-setup", outcome="answered",
            details=f"{len(answers)} answers recorded",
        )

    def _scaffold_dir_files(self, name: str) -> dict[str, str]:
        root = self.store.path("intake", "scaffold", name)
        if not root.is_dir():
            return {}
        return {
            p.name: p.read_text(encoding="utf-8")
            for p in sorted(root.iterdir())
            if p.is_file()
        }

    def _scaffold_files(self, name: str) -> dict[str, str]:
        files = self._scaffold_dir_files(name)
        if not files:
            raise EngineError(f"No scaffold generated for {name!r} yet")
        return files

    def intake_generate_scaffold(self, role: Role) -> None:
        roles.require("setup_new_application", role)
        import time

        from s7_delivery.factory import scaffold as scaffold_mod

        setup = self._new_app()
        if not setup["name"]:
            raise EngineError("Complete the new-application setup conversation first")
        t0 = time.monotonic()
        files, usage = scaffold_mod.generate_scaffold(
            setup["name"], setup["description"], setup["stack"]
        )
        for filename, content in files.items():
            self.store.write_text(content, "intake", "scaffold", setup["name"], filename)
        self._record(
            artifact_id=f"SCAFFOLD-{setup['name']}", artifact_type="scaffold",
            payload={"files": sorted(files)}, author="requirement-routing (live)",
            stage=Stage.INTAKE, action="generate-scaffold", outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor="new-app-scaffold", actor_type="live_ai",
            workflow="new-app-scaffold", duration_s=round(time.monotonic() - t0, 2),
            outcome="created",
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_create_new_app_repo(self, role: Role) -> None:
        """The approval action: creates the real GitHub repo from the
        reviewed scaffold, then normalizes it into an ordinary connected
        repo — §B needs no special case because of this."""
        roles.require("create_new_application_repo", role)
        import shutil

        from s7_delivery.factory.repos import (
            RepoConnectError,
            build_context_pack,
            clone_repo,
            remember_repo,
        )
        from s7_delivery.factory.scaffold import push_new_repo, write_scaffold_locally

        setup = self._new_app()
        name = setup.get("name")
        if not name:
            raise EngineError("Complete the new-application setup conversation first")
        files = self._scaffold_files(name)
        if any(r["name"] == name for r in self._connected_repos()):
            raise EngineError(f"{name} is already connected")

        try:
            repo_path = write_scaffold_locally(name, files, self.store.path("scaffold-src"))
        except RepoConnectError as exc:
            raise EngineError(f"Writing the scaffold locally failed: {exc}") from exc
        try:
            url = push_new_repo(repo_path, name)
        except RepoConnectError as exc:
            shutil.rmtree(repo_path, ignore_errors=True)
            raise EngineError(f"New application repo creation failed: {exc}") from exc
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            shutil.rmtree(repo_path, ignore_errors=True)
            raise EngineError(f"Cloning the newly created repo failed: {exc}") from exc

        from s7_delivery.factory import ci_bootstrap
        repo_dir = self.store.path("repos", rec.name)
        stack = ci_bootstrap.detect_stack_from_text(setup["stack"])
        try:
            bootstrap_status = ci_bootstrap.bootstrap(repo_dir, rec.default_branch, stack)
        except ci_bootstrap.CiBootstrapError:
            bootstrap_status = "push_failed"

        repos = self.store.read_json_or([], "intake", "repos.json")
        rec_dict = rec.model_dump(mode="json")
        rec_dict["ci_bootstrap_status"] = bootstrap_status
        repos.append(rec_dict)
        self.store.write_json(repos, "intake", "repos.json")
        pack = build_context_pack(self.store.path("repos", rec.name), rec.name)
        self.store.write_text(pack, "intake", "context", f"{rec.name}.md")

        self._record(
            artifact_id=f"REPO-{rec.name}", artifact_type="repository", payload=rec,
            author=role.value, stage=Stage.INTAKE, action="create-new-app-repo",
            outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="create-new-application-repo", artifact=rec.name,
            outcome="created", details=f"{rec.url} @ {rec.head_sha[:10]}",
        )
        # A repo created here is an ordinary connected repo from this point on
        # — including in the global memory, so a reset offers it back like any
        # other (it would otherwise be the one repo the app forgets).
        remember_repo({
            "url": rec.url, "name": rec.name,
            "default_branch": rec.default_branch, "last_connected_at": now_iso(),
        })

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
        # Human review of AI-drafted content (spec §8D): the story's own text
        # and workflow fields are editable before sign-off. Identity
        # (story_id, epic_id), provenance, and the routing targets the export
        # machinery grounds against (target_*) stay non-editable.
        "title", "purpose", "status", "task_type",
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

        if self.run().mode is DemoMode.LIVE:
            self._planning_generate_live()
            return

        # The design artifact the stories derive from — the upstream pointer
        # the staleness demonstration flips (spec §15). Its rules quote the
        # epic's provisional answers to the open SME questions.
        design = {
            "design_id": "DES-001",
            "title": "Sponsor submission — design decisions",
            "rules": {
                "absence_dates": (
                    "First day absent must be after the last day worked; a "
                    "submission dated on or before the last day worked is "
                    "rejected (US-003)."
                ),
                "draft_retention": (
                    "PROVISIONAL pending SME: an in-progress submission is "
                    "retained for 30 days before expiry."
                ),
                "packet": (
                    "PROVISIONAL pending SME: employer statement mandatory at "
                    "submission; employee and physician statements may follow."
                ),
            },
            "provenance": "simulated",
            "version": 1,
        }
        self.store.write_json(design, "planning", "design.json")
        self._record(
            artifact_id="DES-001", artifact_type="design", payload=design,
            author="planning (simulated)", stage=Stage.PLANNING,
            action="design", outcome="created",
            inputs=["EPIC-S7-001", "ANL-001"],
        )

        stories = [s.model_dump(mode="json") for s in seed.build_stories()]
        self.store.write_json(stories, "planning", "stories.json")
        # Immutable snapshot of the AI draft as generated — what the drawer's
        # "Reset to AI Suggestion" restores from. Never touched by edits.
        self.store.write_json(stories, "planning", "stories.original.json")
        self.store.write_json(dict(seed.PLAN_CONFIDENCE), "planning", "confidence.json")
        self.store.write_json(dict(seed.PLAN_RATIONALE), "planning", "rationale.json")
        for s in stories:
            self._record(
                artifact_id=s["story_id"], artifact_type="story", payload=s,
                author="planning (simulated)", stage=Stage.PLANNING,
                action="decompose", outcome="created",
                inputs=[s["epic_id"], seed.REQUIREMENT.request_id, "DES-001"],
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

    def _story_target_architecture(self, story: dict) -> str:
        """Read architecture.md straight from the story's target repo's own
        clone — not parsed out of the merged context pack (spec §C1)."""
        path = self.store.path("repos", story["target_repository"], "architecture.md")
        if not path.is_file():
            raise EngineError(
                f"No architecture.md found for {story['target_repository']!r} — "
                "is it connected?"
            )
        return path.read_text(encoding="utf-8")

    def planning_export_artifacts(self, role: Role) -> None:
        """§C2: write each signed-off story's portable package into the
        run's own artifact tree. No external side effects."""
        roles.require("export_artifacts", role)
        if not self.run().plan_locked:
            raise EngineError("Export artifacts after the plan is signed off")
        from s7_delivery.factory.artifact_export import render_story_package, story_folder_name

        exported = 0
        for story in self._stories():
            arch = self._story_target_architecture(story)
            package = render_story_package(story, arch)
            folder = story_folder_name(story)
            team_dir = story["accountable_team"].replace(" ", "-")
            for filename, content in package.items():
                self.store.write_text(content, "planning", "export", team_dir, folder, filename)
            self._record(
                artifact_id=f"EXPORT-{story['story_id']}", artifact_type="export",
                payload={"files": sorted(package)}, author=role.value,
                stage=Stage.PLANNING, action="export", outcome="created",
                inputs=[story["story_id"]],
            )
            exported += 1
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="artifact-export", outcome="created",
            details=f"{exported} story packages exported",
        )

    def planning_write_to_clone(self, role: Role) -> None:
        """§D1: copy each story's exported folder into its target repo's
        own clone and commit locally. No push — fully reversible."""
        roles.require("write_delivery_clone", role)
        import subprocess

        from s7_delivery.factory.artifact_export import story_folder_name

        def _git(*args: str, cwd) -> str:
            """Wrapper for git subprocess calls with error handling and timeout."""
            try:
                out = subprocess.run(
                    ["git", "-C", str(cwd), *args],
                    check=True, capture_output=True, text=True, timeout=120,
                )
            except subprocess.CalledProcessError as exc:
                raise EngineError(
                    f"git {' '.join(args)} failed in {cwd}: {(exc.stderr or str(exc)).strip()}"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise EngineError(f"git {' '.join(args)} timed out in {cwd}") from exc
            return out.stdout.strip()

        stories = self._stories()
        by_repo: dict[str, list[dict]] = {}
        for story in stories:
            by_repo.setdefault(story["target_repository"], []).append(story)

        for repo_name, repo_stories in by_repo.items():
            clone_dir = self.store.path("repos", repo_name)
            if not clone_dir.is_dir():
                raise EngineError(f"No clone found for {repo_name!r}")
            delivery_dir = clone_dir / "delivery"
            for story in repo_stories:
                team_dir = story["accountable_team"].replace(" ", "-")
                folder = story_folder_name(story)
                export_dir = self.store.path("planning", "export", team_dir, folder)
                if not export_dir.is_dir():
                    raise EngineError(
                        f"Story {story['story_id']} has no exported package — "
                        "run export-artifacts first"
                    )
                target = delivery_dir / folder
                target.mkdir(parents=True, exist_ok=True)
                for src_file in export_dir.iterdir():
                    (target / src_file.name).write_text(
                        src_file.read_text(encoding="utf-8"), encoding="utf-8"
                    )
            ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
            status = _git("status", "--porcelain", cwd=clone_dir)
            if status:
                _git("add", "-A", cwd=clone_dir)
                _git(*ident, "commit", "-qm",
                     f"Delivery artifacts for {self.run_id}", cwd=clone_dir)
            commit_sha = _git("rev-parse", "HEAD", cwd=clone_dir)
            self.store.write_json(
                {"committed": True, "commit_sha": commit_sha},
                "planning", "delivery", f"{repo_name}.json",
            )
            self._record(
                artifact_id=f"DELIVERY-{repo_name}", artifact_type="delivery_commit",
                payload={"repo": repo_name, "commit_sha": commit_sha},
                author=role.value, stage=Stage.PLANNING, action="write-to-clone",
                outcome="created", inputs=[s["story_id"] for s in repo_stories],
            )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="delivery-write-to-clone", outcome="created",
            details=f"{len(by_repo)} repositories committed locally",
        )

    def planning_push_delivery_branch(self, role: Role, repo_name: str) -> None:
        """§D2: push this run's committed delivery branch to the real
        remote. Never the default branch — the ref is always
        refs/heads/delivery/<run_id>, asserted below, not just implied by
        the f-string. Merging it into a developer's own working branch is
        never automated by this system."""
        roles.require("push_delivery_branch", role)
        import subprocess

        marker = self.store.read_json_or(None, "planning", "delivery", f"{repo_name}.json")
        if marker is None or not marker.get("committed"):
            raise EngineError(
                f"No local delivery commit for {repo_name!r} — write to the clone first"
            )
        clone_dir = self.store.path("repos", repo_name)
        branch = f"delivery/{self.run_id}"
        repo_record = next(
            (r for r in self._connected_repos() if r["name"] == repo_name), None
        )
        if repo_record and branch == repo_record.get("default_branch"):
            raise EngineError(
                f"Refusing to push delivery branch {branch!r} — it matches "
                f"{repo_name}'s default branch, which this system never targets"
            )
        try:
            subprocess.run(
                ["git", "-C", str(clone_dir), "push", "origin", f"HEAD:refs/heads/{branch}"],
                check=True, capture_output=True, text=True, timeout=120,
            )
        except subprocess.CalledProcessError as exc:
            raise EngineError(
                f"Push to {repo_name} failed: {(exc.stderr or str(exc)).strip()}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise EngineError(f"Push to {repo_name} timed out") from exc
        self.store.write_json(
            {**marker, "pushed": True, "branch": branch, "pushed_at": now_iso()},
            "planning", "delivery", f"{repo_name}.json",
        )
        self._record(
            artifact_id=f"DELIVERY-PUSH-{repo_name}", artifact_type="delivery_push",
            payload={"repo": repo_name, "branch": branch}, author=role.value,
            stage=Stage.PLANNING, action="push", outcome="created",
        )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="delivery-push", outcome="created",
            details=f"pushed {branch} to {repo_name}",
        )

    def _planning_generate_live(self) -> None:
        import time

        from s7_delivery.factory import live_intake

        packs = self._context_packs()
        epic = self.store.read_json_or(None, "intake", "epic.json")
        if epic is None:
            raise EngineError("Create the epic before generating the plan")
        analysis = self.store.read_json("intake", "analysis.json")
        transcript = self._clarifications()["transcript"]
        t0 = time.monotonic()
        stories, confidence, rationale, usage = live_intake.run_plan(
            epic, analysis, packs, transcript, seed.TEAMS
        )
        payloads = [s.model_dump(mode="json") for s in stories]
        self.store.write_json(payloads, "planning", "stories.json")
        self.store.write_json(payloads, "planning", "stories.original.json")
        self.store.write_json(confidence, "planning", "confidence.json")
        self.store.write_json(rationale, "planning", "rationale.json")
        for s in payloads:
            self._record(
                artifact_id=s["story_id"], artifact_type="story", payload=s,
                author="planning (live)", stage=Stage.PLANNING,
                action="decompose", outcome="created",
                inputs=[s["epic_id"], "ANL-001",
                        f"REPO-{s['target_repository']}"],
            )
        self._activity(
            stage=Stage.PLANNING, actor="planning", actor_type="live_ai",
            workflow="epic-decomposition",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"{len(payloads)} stories; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def _planning_open_for_change(self) -> None:
        if self.gate(GateId.INTAKE).status != Status.PASSED:
            raise EngineError("Planning opens after the intake gate (G0) passes")
        if self.run().plan_locked:
            raise EngineError("The signed plan is locked; changes require an amendment")

    def _build_manual_story(
        self, fields: dict, existing: list[dict], provenance: Provenance
    ) -> Story:
        """Validate user-supplied story fields into a complete Story.

        Manual and imported stories carry HUMAN provenance — they are a
        person's plan input, not the simulation's, and the surface shows the
        difference rather than blending them.
        """
        title = str(fields.get("title", "")).strip()
        if not title:
            raise EngineError("A story needs a title")
        label = f"Story '{title}'"
        team = str(fields.get("accountable_team", "")).strip()
        component = str(fields.get("target_component", "")).strip()
        repository = str(fields.get("target_repository", "")).strip()
        if not team:
            raise EngineError(f"{label}: an accountable team is required")
        if not component:
            raise EngineError(f"{label}: a target component is required")
        if not repository:
            raise EngineError(f"{label}: a target repository is required")

        texts: list[str] = []
        for ac in fields.get("acceptance_criteria") or []:
            text = str(ac.get("text", "") if isinstance(ac, dict) else ac).strip()
            if text:
                texts.append(text)
        if not texts:
            raise EngineError(
                f"{label}: at least one testable acceptance criterion is required"
            )

        known = {s["story_id"] for s in existing}
        dependencies = [str(dep).strip() for dep in fields.get("dependencies") or []]
        dependencies = [dep for dep in dependencies if dep]
        unknown = [dep for dep in dependencies if dep not in known]
        if unknown:
            raise EngineError(
                f"{label}: unknown dependencies {', '.join(sorted(unknown))} — "
                "dependencies must reference stories already in the plan"
            )

        numbers = [
            int(s["story_id"].rsplit("-", 1)[1])
            for s in existing
            if s["story_id"].rsplit("-", 1)[-1].isdigit()
        ]
        story_id = f"US-{max(numbers, default=0) + 1:03d}"

        rollback = fields.get("rollback_plan")
        if isinstance(rollback, str) and rollback.strip():
            rollback = RollbackPlan(method=rollback.strip())
        elif isinstance(rollback, dict):
            rollback = RollbackPlan(**rollback)
        else:
            rollback = RollbackPlan(
                method="Disable the feature flag and revert the release; "
                "no destructive migration in this story."
            )

        sprint = int(fields.get("sprint") or 1)
        return Story(
            story_id=story_id,
            epic_id=seed.EPIC.epic_id,
            title=title,
            purpose=str(fields.get("purpose") or title).strip(),
            accountable_team=team,
            contributing_teams=[
                str(t).strip() for t in fields.get("contributing_teams") or [] if str(t).strip()
            ],
            target_application=str(
                fields.get("target_application") or "MapleSure SponsorConnect"
            ),
            target_component=component,
            target_repository=repository,
            acceptance_criteria=[
                AcceptanceCriterion(ac_id=f"{story_id}-AC{i + 1}", text=t)
                for i, t in enumerate(texts)
            ],
            dependencies=dependencies,
            rollback_plan=rollback,
            task_type=str(fields.get("task_type") or "feature"),
            estimate=int(fields.get("estimate") or 3),
            sprint=sprint,
            status=Status.READY if sprint <= 1 else Status.PLANNED,
            risk=str(fields.get("risk") or "low"),
            # A story added to this epic derives from the run's requirement by
            # construction — without this, QC-01 rightly flags it as unmapped.
            traces_to=[str(t) for t in fields.get("traces_to") or []]
            or [seed.REQUIREMENT.request_id],
            provenance=provenance,
        )

    def planning_add_story(self, role: Role, fields: dict) -> None:
        roles.require("edit_story", role)
        self._planning_open_for_change()
        stories = self._stories()
        story = self._build_manual_story(fields, stories, Provenance.HUMAN)
        payload = story.model_dump(mode="json")
        stories.append(payload)
        self.store.write_json(stories, "planning", "stories.json")
        self._record(
            artifact_id=story.story_id, artifact_type="story", payload=payload,
            author=role.value, stage=Stage.PLANNING, action="add",
            outcome="created", inputs=[story.epic_id],
        )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="story-add", artifact=story.story_id,
            outcome="created", details=story.title[:120],
        )

    def planning_import_stories(self, role: Role, items: list[dict]) -> int:
        """Import a batch of stories. All-or-nothing: any invalid item aborts
        the whole import before anything is written."""
        roles.require("edit_story", role)
        self._planning_open_for_change()
        if not items:
            raise EngineError("The import contains no stories")
        stories = self._stories()
        added: list[Story] = []
        for index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                raise EngineError(f"Import aborted at item {index}: not a story object")
            try:
                combined = stories + [s.model_dump(mode="json") for s in added]
                added.append(
                    self._build_manual_story(item, combined, Provenance.HUMAN)
                )
            except EngineError as exc:
                raise EngineError(f"Import aborted at item {index}: {exc}") from exc
        for story in added:
            payload = story.model_dump(mode="json")
            stories.append(payload)
            self._record(
                artifact_id=story.story_id, artifact_type="story", payload=payload,
                author=role.value, stage=Stage.PLANNING, action="import",
                outcome="created", inputs=[story.epic_id],
            )
        self.store.write_json(stories, "planning", "stories.json")
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="story-import", outcome="created",
            details=f"{len(added)} stories imported",
        )
        return len(added)

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
        conditions = gates.plan_signoff_gate(
            stories,
            approver,
            epic=self.store.read_json_or(None, "intake", "epic.json"),
            analysis=self.store.read_json_or(None, "intake", "analysis.json"),
            # live runs only: a simulation run has no clones to check against
            connected_repos=self._connected_repos()
            if self.run().mode is DemoMode.LIVE else None,
        )
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
        # G1 means: plan locked, architecture / delivery-pack / workspace
        # generation authorised. It does NOT mean "AI develops the code".
        build_phases.advance(
            self.store, None, BuildReviewPhase.GATE1_APPROVED, actor=approver
        )
        self._activity(
            stage=Stage.PLANNING, actor=approver, actor_type="human",
            workflow="plan-signoff-approval", outcome="passed",
            details=f"plan v{plan['plan_version']} locked; architecture and "
                    "delivery-pack generation enabled",
        )

    # --- architecture (Build & Review: engineering blueprint) ---------------

    def _architecture_meta(self) -> dict | None:
        return self.store.read_json_or(None, "architecture", "meta.json")

    def _build_phase(self) -> BuildReviewPhase | None:
        return build_phases.read_phase(
            self.store, plan_locked=self.run().plan_locked
        )

    def _blueprint_provenance(self) -> Provenance:
        """The architecture renderer is deterministic. In simulation/replay it
        is simulated evidence; in live mode it is an honest non-AI derivation
        of real inputs — RULE_BASED, never presented as an AI result."""
        return (
            Provenance.RULE_BASED
            if self.run().mode is DemoMode.LIVE
            else Provenance.SIMULATED
        )

    def _write_architecture_pack(
        self, version: int, revision_note: str, actor: str, prov: Provenance
    ) -> dict:
        from s7_delivery.factory import architecture as arch

        stories = self._stories()
        files = arch.render_pack(
            epic=self.store.read_json_or(None, "intake", "epic.json"),
            requirement=self.store.read_json_or(None, "intake", "requirement.json"),
            stories=stories,
            analysis=self.store.read_json_or(None, "intake", "analysis.json"),
            repos=self._connected_repos(),
            version=version,
            revision_note=revision_note,
        )
        vdir = f"v{version}"
        serialized: dict[str, str] = {}
        for name, payload in files.items():
            if isinstance(payload, str):
                serialized[name] = payload
                self.store.write_text(payload, "architecture", vdir, name)
            else:
                serialized[name] = json.dumps(payload, indent=2, sort_keys=True)
                self.store.write_json(payload, "architecture", vdir, name)
        digest = hashlib.sha256()
        for name in sorted(serialized):
            digest.update(name.encode())
            digest.update(serialized[name].encode())
        analysis = self.store.read_json_or(None, "intake", "analysis.json")
        repos = self._connected_repos()
        plan = self.store.read_json_or(None, "planning", "plan.json")
        meta = ArchitectureMeta(
            version=version,
            status="generated",
            generated_by=actor,
            revision_note=revision_note,
            files=[f"{vdir}/{name}" for name in arch.FILES],
            provenance=prov,
            plan_version=(plan or {}).get("plan_version", 0),
            content_hash=digest.hexdigest(),
            file_sizes={name: len(text.encode()) for name, text in serialized.items()},
            validations=architecture_checks.run_checks(stories, repos, files),
            landscape=arch.landscape(stories, analysis, repos),
        ).model_dump(mode="json")
        self.store.write_json(meta, "architecture", "meta.json")
        return meta

    def architecture_generate(self, role: Role) -> None:
        """Generate the engineering blueprint from the locked plan. Runs AFTER
        Gate 1 — G1 never depends on this existing."""
        roles.require("generate_architecture", role)
        phase = self._build_phase()
        build_phases.require_at_least(
            phase, BuildReviewPhase.GATE1_APPROVED, "Architecture generation"
        )
        if self._architecture_meta() is not None:
            raise EngineError(
                "Architecture already generated — use revise to produce a new version"
            )
        prov = self._blueprint_provenance()
        meta = self._write_architecture_pack(1, "", "architecture-service", prov)
        build_phases.advance(
            self.store, phase, BuildReviewPhase.ARCHITECTURE_READY, actor=role.value
        )
        self._record(
            artifact_id="ARCH-001", artifact_type="architecture", payload=meta,
            author="architecture-service", stage=Stage.BUILD_REVIEW,
            action="generate", outcome="created", inputs=["PLAN-001"], version=1,
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="architecture-service",
            actor_type="simulation" if prov is Provenance.SIMULATED else "service",
            workflow="architecture-generation", artifact="ARCH-001",
            duration_s=6.0, outcome="created",
            details="Engineering blueprint generated from the approved plan",
        )

    def architecture_revise(self, role: Role, feedback: str) -> None:
        """New immutable version; prior version directories are retained so
        any pack referencing v1 stays resolvable."""
        roles.require("revise_architecture", role)
        meta = self._architecture_meta()
        if meta is None:
            raise EngineError("No architecture to revise — generate it first")
        if not feedback.strip():
            raise EngineError("A revision needs a reason — feedback is empty")
        phase = self._build_phase()
        version = meta["version"] + 1
        prov = self._blueprint_provenance()
        new_meta = self._write_architecture_pack(
            version, feedback.strip(), "architecture-service", prov
        )
        build_phases.advance(
            self.store, phase, BuildReviewPhase.ARCHITECTURE_READY, actor=role.value
        )
        self._record(
            artifact_id="ARCH-001", artifact_type="architecture",
            payload=new_meta, author="architecture-service",
            stage=Stage.BUILD_REVIEW, action="revise", outcome="amended",
            inputs=["PLAN-001"], version=version,
            previous_version=meta["version"],
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="architecture-service",
            actor_type="simulation" if prov is Provenance.SIMULATED else "service",
            workflow="architecture-revision", artifact="ARCH-001",
            duration_s=4.0, outcome="amended",
            details=f"v{version}: {feedback.strip()}",
        )

    def architecture_accept(self, role: Role, approver: str = "") -> None:
        """Human checkpoint: the generator (the service) never accepts its own
        blueprint. Lightweight by design — not a numbered gate."""
        roles.require("accept_architecture", role)
        meta = self._architecture_meta()
        if meta is None:
            raise EngineError("No architecture to accept — generate it first")
        if meta["status"] == "accepted":
            raise EngineError(f"Architecture v{meta['version']} is already accepted")
        blocked = architecture_checks.mandatory_failures(meta.get("validations", []))
        if blocked:
            raise EngineError(
                "Cannot accept: mandatory validation failed — " + ", ".join(blocked)
            )
        phase = self._build_phase()
        who = approver.strip() or role.value
        meta["status"] = "accepted"
        meta["accepted_by"] = who
        meta["accepted_at"] = now_iso()
        self.store.write_json(meta, "architecture", "meta.json")
        build_phases.advance(
            self.store, phase, BuildReviewPhase.ARCHITECTURE_ACCEPTED, actor=who
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=who, actor_type="human",
            workflow="architecture-approval", artifact="ARCH-001",
            outcome="passed",
            details=f"Architecture v{meta['version']} accepted; "
                    "delivery-pack generation enabled",
        )

    # --- delivery packs (Build & Review: governed context per team) ---------

    def _packs(self) -> list[dict]:
        packs = self.store.read_json_or([], "build", "packs", "meta.json")
        for p in packs:
            # legacy rows predate published_version: a published pack was, by
            # definition, published at its current version
            if "published_version" not in p:
                p["published_version"] = (
                    p["version"] if p["publication_status"] == "published" else 0
                )
            if "test_plan_status" not in p:
                # Legacy rows predate the test-plan checkpoint entirely: a pack
                # that already reached the repository was implicitly accepted.
                # Kept deliberately so historic runs stay viewable — it back-
                # fills a *status field*, never a missing test plan, and
                # test_plan_approve still refuses a pack with no manifests.
                p["test_plan_status"] = (
                    "approved" if p["publication_status"] == "published"
                    else "generated"
                )
                p.setdefault("test_plan_approved_by", "")
                p.setdefault("test_plan_approved_at", "")
        return packs

    def _has_test_manifest(self, story_id: str) -> bool:
        try:
            return self.store.exists("build", "tests", story_id, "test-manifest.json")
        except StoreError:  # a story id that is not a safe path segment
            return False

    def _pack_stats(self, pack: dict) -> tuple[int, int]:
        """(artifact_count, size_bytes) computed from the artifact store —
        the same file set the per-pack ZIP collects, never an estimate."""
        roots = [self.store.path("build", "packs", pack["team_slug"])]
        arch_dir = self.store.path("architecture", f"v{pack['architecture_version']}")
        files = [
            p for root in roots for p in root.rglob("*") if p.is_file()
        ] + [
            arch_dir / name
            for name in ("architecture.md", "engineering-rules.md")
            if (arch_dir / name).is_file()
        ]
        for story_id in pack.get("story_ids", []):
            files += [p for p in self.store.path("build", "stories", story_id).rglob("*") if p.is_file()]
            # the AC test skeletons ship with the pack — they must be counted
            # by the same walk that the ZIP collects, or the two disagree
            tdir = self.store.path("build", "tests", story_id)
            files += [p for p in tdir.rglob("*") if p.is_file()]
        for task_id in pack.get("task_ids", []):
            files += [p for p in self.store.path("build", "tasks", task_id).rglob("*") if p.is_file()]
        return len(files), sum(p.stat().st_size for p in files)

    def _save_packs(self, packs: list[dict]) -> None:
        self.store.write_json(packs, "build", "packs", "meta.json")

    def _pack(self, pack_id: str) -> dict:
        pack = next(
            (p for p in self._packs() if p["delivery_pack_id"] == pack_id), None
        )
        if pack is None:
            raise EngineError(f"Unknown delivery pack {pack_id}")
        return pack

    def _write_files(self, files: dict[str, object], *segments: str) -> None:
        for name, payload in files.items():
            if isinstance(payload, str):
                self.store.write_text(payload, *segments, name)
            else:
                self.store.write_json(payload, *segments, name)

    def delivery_packs_generate(self, role: Role) -> None:
        """One governed pack per accountable team, layered: canonical story
        and task packs are shared; the team pack references them. Regeneration
        bumps versions and resets publication status — a new version needs a
        new publish (spec §22 refresh, never a silent overwrite)."""
        roles.require("generate_delivery_packs", role)
        from s7_delivery.factory import delivery_packs as dp
        from s7_delivery.factory import test_skeletons

        phase = self._build_phase()
        build_phases.require_at_least(
            phase, BuildReviewPhase.ARCHITECTURE_ACCEPTED,
            "Delivery pack generation",
        )
        arch_meta = self._architecture_meta()
        plan = self.store.read_json_or(None, "planning", "plan.json")
        if plan is None:
            raise EngineError("No signed plan on file")
        stories = self._stories()
        tasks = self._tasks()
        prov = self._blueprint_provenance()
        prev = {p["delivery_pack_id"]: p for p in self._packs()}

        # canonical story + task packs (Levels 3 and 4), shared across teams
        for story in stories:
            self._write_files(
                dp.render_story_pack(
                    story,
                    plan_version=plan["plan_version"],
                    architecture_version=arch_meta["version"],
                ),
                "build", "stories", story["story_id"],
            )
            # A story's target_repository is free text a human can type
            # ("Claims API"). Only a name that matches a *connected* repo has
            # a clone directory — and only such a name is a safe path segment.
            # Anything else means "stack unknown": reference-only skeletons,
            # never a StoreError that kills the whole generation.
            repo = next(
                (r for r in self._connected_repos()
                 if r["name"] == story.get("target_repository", "")),
                None,
            )
            repo_dir = None
            if repo is not None:
                try:
                    repo_dir = self.store.path("repos", repo["name"])
                except StoreError:
                    repo_dir = None
            stack = test_skeletons.resolve_stack(repo, repo_dir)
            t_files, t_manifest = test_skeletons.render_story_tests(story, stack)
            self._write_files(
                {**t_files, "test-manifest.json": t_manifest},
                "build", "tests", story["story_id"],
            )
        teams: list[str] = []
        for s in stories:
            if s.get("accountable_team") and s["accountable_team"] not in teams:
                teams.append(s["accountable_team"])

        assignments = self._assignments()
        packs: list[dict] = []
        for team in teams:
            old = prev.get(dp.pack_id_for(team), {})
            pack = self._write_team_pack(
                team=team, all_stories=stories, all_tasks=tasks,
                version=old.get("version", 0) + 1,
                plan_version=plan["plan_version"],
                architecture_version=arch_meta["version"],
                assignments=assignments, prov=prov,
            )
            # regeneration resets publication (a new version needs a new
            # publish), but what already reached the repository stays recorded
            pack["published_version"] = old.get("published_version", 0)
            packs.append(pack)
        self._save_packs(packs)
        # Regeneration once developers are executing is a refresh (same class
        # as late publication) — never regress the phase from there.
        if phase in (
            BuildReviewPhase.ARCHITECTURE_ACCEPTED,
            BuildReviewPhase.DELIVERY_PACKS_READY,
            BuildReviewPhase.WORKSPACES_READY,
        ):
            build_phases.advance(
                self.store, phase, BuildReviewPhase.DELIVERY_PACKS_READY,
                actor=role.value,
            )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="pack-service",
            actor_type="simulation" if prov is Provenance.SIMULATED else "service",
            workflow="delivery-pack-generation", artifact="delivery-packs",
            duration_s=5.0, outcome="created",
            details=f"{len(packs)} team packs over {len(stories)} stories",
        )

    def test_plan_approve(self, role: Role, pack_id: str, approver: str = "") -> None:
        """Human checkpoint on the AC-derived test skeletons: QA approves a
        pack's test plan before it may publish. The generator (the service)
        never approves its own tests."""
        roles.require("approve_test_plan", role)
        phase = self._build_phase()
        build_phases.require_at_least(
            phase, BuildReviewPhase.DELIVERY_PACKS_READY, "Test plan approval"
        )
        packs = self._packs()
        pack = next((p for p in packs if p["delivery_pack_id"] == pack_id), None)
        if pack is None:
            raise EngineError(f"Unknown delivery pack {pack_id}")
        if pack["test_plan_status"] == "approved":
            raise EngineError(
                f"{pack_id} v{pack['version']} test plan is already approved"
            )
        # Approving nothing is not a checkpoint. A pack whose stories carry no
        # test-manifest.json has no plan to review, and approving it would put
        # a human signature on an empty artifact.
        if not any(
            self._has_test_manifest(sid) for sid in pack.get("story_ids", [])
        ):
            raise EngineError(
                "No test plan generated for this pack — regenerate delivery"
                " packs first"
            )
        who = approver.strip() or role.value
        pack["test_plan_status"] = "approved"
        pack["test_plan_approved_by"] = who
        pack["test_plan_approved_at"] = now_iso()
        self._save_packs(packs)
        approvals = self.store.read_ledger("approvals.jsonl")
        self.store.append(
            Approval(
                approval_id=f"APR-{len(approvals) + 1:03d}",
                subject=f"test-plan:{pack_id}",
                role=role,
                approver=who,
                decision="approved",
                note=f"AC test plan for {pack['team']} pack v{pack['version']}",
            ),
            "approvals.jsonl",
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=who, actor_type="human",
            workflow="test-plan-approval", artifact=pack_id, outcome="passed",
            details=f"Test plan for {pack['team']} pack v{pack['version']}"
                    " approved; publication enabled",
        )

    def _assignments(self) -> dict[str, str]:
        """story_id → developer, from provisioned workspaces. Assignment is
        human state that must survive pack regeneration."""
        return {
            w["story_id"]: w["developer"]
            for w in self._workspaces() if w.get("developer")
        }

    def _write_team_pack(
        self, *, team: str, all_stories: list[dict], all_tasks: list[dict],
        version: int, plan_version: int, architecture_version: int,
        assignments: dict[str, str], prov: Provenance,
        action: str = "generate",
    ) -> dict:
        """Render and store one team's task packs + team pack at `version`,
        record provenance, and return the pack row (publication_status starts
        at not_published — a new version always needs a new publish)."""
        from s7_delivery.factory import delivery_packs as dp

        t_stories = [s for s in all_stories if s.get("accountable_team") == team]
        t_story_ids = {s["story_id"] for s in t_stories}
        t_tasks = [t for t in all_tasks if t["story_id"] in t_story_ids]
        for task in t_tasks:
            story = next(s for s in t_stories if s["story_id"] == task["story_id"])
            self._write_files(
                dp.render_task_pack(
                    task, story,
                    plan_version=plan_version,
                    architecture_version=architecture_version,
                    team_pack_version=version,
                ),
                "build", "tasks", task["task_id"],
            )
        repo_name = next(
            (s.get("target_repository", "") for s in t_stories), ""
        )
        default_branch = next(
            (r.get("default_branch") or "main"
             for r in self._connected_repos() if r["name"] == repo_name),
            "main",
        )
        files = dp.render_team_pack(
            run_id=self.run_id, team=team, stories=t_stories,
            tasks=t_tasks, all_stories=all_stories, pack_version=version,
            plan_version=plan_version,
            architecture_version=architecture_version,
            assignments=assignments,
            default_branch=default_branch,
        )
        slug = files["workspace-manifest.json"]["team_slug"]
        self._write_files(files, "build", "packs", slug)
        pack = DeliveryPack(
            delivery_pack_id=dp.pack_id_for(team),
            run_id=self.run_id,
            team=team,
            team_slug=slug,
            version=version,
            story_ids=sorted(t_story_ids),
            task_ids=[t["task_id"] for t in t_tasks],
            architecture_version=architecture_version,
            plan_version=plan_version,
            repository=files["workspace-manifest.json"]["repository"],
            content_hash=sha256_of(files),
            provenance=prov,
        ).model_dump(mode="json")
        self._record(
            artifact_id=pack["delivery_pack_id"], artifact_type="delivery_pack",
            payload=pack, author="pack-service",
            stage=Stage.BUILD_REVIEW, action=action,
            outcome="created" if version == 1 else "amended",
            inputs=["ARCH-001", "PLAN-001", *sorted(t_story_ids)],
            version=version,
            previous_version=version - 1 if version > 1 else None,
        )
        return pack

    # --- git publication + developer workspaces -----------------------------

    _DEV_STATUS = {
        "not_started": "ready",
        "ready": "ready",
        "in_progress": "in_development",
        "waiting_for_approval": "in_review",
        "blocked": "correction_requested",
        "completed": "complete",
        "failed": "blocked",
    }

    _CI_CONCLUSION_MAP = {
        "success": "passed",
        "failure": "failed",
        "queued": "running",
        "in_progress": "running",
    }

    def _workspaces(self) -> list[dict]:
        return self.store.read_json_or([], "build", "workspaces.json")

    def _save_workspaces(self, workspaces: list[dict]) -> None:
        self.store.write_json(workspaces, "build", "workspaces.json")

    def _workspaces_view(self) -> list[dict]:
        """Workspaces enriched with live evidence: static provisioning fields
        come from the record; commit/PR/CI/status derive from the story's task
        so there is a single source of truth for execution state."""
        workspaces = self._workspaces()
        if not workspaces:
            return []
        tasks_by_story = {t["story_id"]: t for t in self._tasks()}
        stale_ids = {
            s["artifact_id"]
            for s in self.store.read_json_or([], "staleness.json")
        }
        for ws in workspaces:
            task = tasks_by_story.get(ws["story_id"])
            if task:
                ws["task_id"] = task["task_id"]
                ws["current_commit"] = task.get("commit_ref", "")
                ws["pull_request"] = task.get("pr_ref", "")
                ws["ci_status"] = task.get("ci_status", "")
                ws["development_status"] = self._DEV_STATUS.get(
                    task.get("status", ""), task.get("status", "")
                )
            ev = ws.get("git_evidence")
            if ev and ev.get("commit_count"):
                # real pushed work wins over the simulated task lifecycle;
                # what git cannot prove (PR) stays blank, never invented
                ws["current_commit"] = ev["latest"]["sha"][:7]
                ws["development_status"] = (
                    "complete" if ev["merged"] else "in_development"
                )
                ws["pull_request"] = ""
                ws["ci_status"] = ""
            ci_ev = ws.get("ci_evidence")
            if ci_ev:
                # CI is no longer unprovable once a real run exists — this
                # overrides the blank set above, never invents a status the
                # run itself didn't report
                mapped = self._CI_CONCLUSION_MAP.get(
                    ci_ev.get("conclusion") or ci_ev.get("status") or "", ""
                )
                if mapped:
                    ws["ci_status"] = mapped
                ws["ci_run_url"] = ci_ev.get("url", "")
                ws["ci_tests_total"] = ci_ev.get("tests_total")
                ws["ci_tests_passed"] = ci_ev.get("tests_passed")
                ws["ci_tests_failed"] = ci_ev.get("tests_failed")
            ws["artifact_status"] = (
                "stale" if ws.get("delivery_pack_id") in stale_ids else "current"
            )
        return workspaces

    def workspaces_sync_git(self, role: Role) -> int:
        """Read real developer progress from each workspace repository:
        `git fetch` + local ref inspection, plus (when the commit resolves
        to a real GitHub repo) the real GitHub Actions run for that commit.
        Nothing written to any remote here — the one-time CI workflow
        commit happens at connect/create time, in ci_bootstrap.bootstrap.
        Live runs only — a simulation run has no real clone, and mixing
        real git evidence into simulated provenance would muddy the
        badging."""
        roles.require("sync_git_evidence", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError(
                "Git evidence sync needs a live run — simulation has no real"
                " repository clone"
            )
        from s7_delivery.factory import git_sync

        workspaces = self._workspaces()
        if not workspaces:
            raise EngineError("No developer workspaces to sync")
        repos = {r["name"]: r for r in self._connected_repos()}
        task_ids_by_story: dict[str, list[str]] = {}
        tasks_by_story: dict[str, dict] = {}
        for t in self._tasks():
            task_ids_by_story.setdefault(t["story_id"], []).append(t["task_id"])
            tasks_by_story[t["story_id"]] = t
        fetched: set[str] = set()
        synced = 0
        for ws in workspaces:
            repo = repos.get(ws["repository"])
            repo_dir = self.store.path("repos", ws["repository"])
            if repo is None or not (repo_dir / ".git").exists():
                continue
            try:
                if ws["repository"] not in fetched:
                    git_sync.fetch(repo_dir)
                    fetched.add(ws["repository"])
                ws["git_evidence"] = git_sync.story_evidence(
                    repo_dir, ws["story_id"],
                    task_ids_by_story.get(ws["story_id"], []),
                    repo.get("default_branch", ""),
                )
            except git_sync.GitSyncError as exc:
                raise EngineError(str(exc)) from exc
            ws["ci_evidence"] = self._sync_ci_evidence(repo, ws["git_evidence"])
            ws["red_baseline"] = self._sync_red_baseline(repo, ws)
            ws["last_sync_at"] = now_iso()
            synced += 1
        if not synced:
            raise EngineError(
                "No workspace repository has a local clone to sync from"
            )
        tasks = self._tasks()
        tasks_changed = False
        for ws in workspaces:
            ci = ws.get("ci_evidence") or {}
            red = ws.get("red_baseline") or {}
            story_tasks = [t for t in tasks if t["story_id"] == ws["story_id"]]
            # In a live run nobody calls task_generate_tests — the published
            # rule-based skeletons ARE the test plan. Without this seeding the
            # per-AC join below has nothing to join to, so real CI outcomes
            # never reach the per-story quality conditions.
            if (
                (ci.get("tests") or red.get("tests"))
                and story_tasks
                and not any(t.get("tests") for t in story_tasks)
            ):
                seeded = self._tests_from_manifest(
                    ws["story_id"], ci.get("url") or red.get("url", "")
                )
                if seeded:
                    for task in story_tasks:
                        task["tests"] = [dict(r) for r in seeded]
                    tasks_changed = True
            results = {t["name"]: t["outcome"] for t in ci.get("tests", [])}
            if not results:
                continue
            for task in story_tasks:
                for t in task.get("tests", []):
                    if t["name"] in results:
                        new = "passed" if results[t["name"]] == "passed" else "failed"
                        if t.get("current_result") != new:
                            t["current_result"] = new
                            tasks_changed = True
        if tasks_changed:
            self._save_tasks(tasks)
        self._save_workspaces(workspaces)
        self._refresh_task_evidence_files(workspaces, tasks_by_story)
        with_commits = sum(
            1 for w in workspaces
            if (w.get("git_evidence") or {}).get("commit_count")
        )
        with_ci = sum(1 for w in workspaces if w.get("ci_evidence"))
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="git-evidence-sync", artifact="workspaces",
            outcome="synced",
            details=f"{synced} workspaces synced from git; {with_commits}"
                    f" with developer commits, {with_ci} with real CI"
                    " results (real pushed work, read-only)",
        )
        return synced

    def _tests_from_manifest(self, story_id: str, run_url: str) -> list[dict]:
        """The published test plan for one story, as TestCaseRecord dicts.

        The rule-based skeletons are the live lane's red baseline: every one
        of them was published deliberately failing, so `initial_result` and
        `current_result` both start `failed` and only real CI evidence moves
        them. Empty when the story has no manifest (packs generated before
        the test-plan checkpoint)."""
        try:
            manifest = self.store.read_json_or(
                None, "build", "tests", story_id, "test-manifest.json"
            )
        except StoreError:
            return []
        if not manifest:
            return []
        ref = run_url or f"build/tests/{story_id}/test-manifest.json"
        return [
            {
                "test_id": f"TEST-{story_id[-3:]}-{i:02d}",
                "name": row["test_name"],
                "ac_id": row["ac_id"],
                "initial_result": "failed",
                "current_result": "failed",
                "evidence_ref": ref,
            }
            for i, row in enumerate(manifest.get("tests", []), start=1)
        ]

    def _ci_run_evidence(
        self, repo: dict, sha: str, *, fallback_any: bool = False
    ) -> dict | None:
        """Best-effort real CI lookup for one commit. Never raises: a gh
        failure, an unresolvable owner/repo, or no run yet all mean "no CI
        evidence yet", not a sync failure."""
        from s7_delivery.factory import ci_sync

        owner_repo = ci_sync.owner_repo_from_url(repo.get("url", ""))
        if owner_repo is None:
            return None
        try:
            run = ci_sync.latest_run(owner_repo, sha)
            if run is None and fallback_any:
                # No S7-bootstrapped run for this commit — most likely it
                # predates s7-ci.yml existing in the repo. Fall back to the
                # plain latest run so a real merged commit doesn't vanish
                # from the dashboard; it just won't carry test counts.
                run = ci_sync.latest_run_any(owner_repo, sha)
        except (ci_sync.CiSyncError, ValueError, OSError, KeyError,
                subprocess.TimeoutExpired):
            return None
        if run is None:
            return None
        evidence: dict = {
            "run_id": run.get("databaseId"),
            "status": run.get("status", ""),
            "conclusion": run.get("conclusion") or "",
            "url": run.get("url", ""),
            "checked_at": now_iso(),
        }
        if run.get("status") == "completed":
            try:
                summary = ci_sync.download_summary(owner_repo, run["databaseId"])
            except (ci_sync.CiSyncError, ValueError, OSError, KeyError,
                    subprocess.TimeoutExpired):
                summary = None
            if summary:
                evidence["tests_total"] = summary.get("tests_total")
                evidence["tests_passed"] = summary.get("tests_passed")
                evidence["tests_failed"] = summary.get("tests_failed")
                if summary.get("tests"):
                    evidence["tests"] = summary["tests"]
        return evidence

    def _sync_ci_evidence(self, repo: dict, git_evidence: dict) -> dict | None:
        latest = git_evidence.get("latest")
        if not latest:
            return None
        return self._ci_run_evidence(repo, latest["sha"], fallback_any=True)

    def _sync_red_baseline(self, repo: dict, ws: dict) -> dict | None:
        """The S7 CI run for this workspace's *first* real publication commit
        — the genuinely-failing skeletons as they were published, before any
        developer work existed. The earliest publication, deliberately: a
        republish after the work merged would put a green run behind the words
        "red baseline", which is exactly the mislabelling the badge exists to
        prevent. Simulated publications have no CI run and never invent one."""
        pubs = [
            p for p in self.store.read_ledger("publications.jsonl")
            if p["delivery_pack_id"] == ws.get("delivery_pack_id")
            and not p.get("simulated")
        ]
        if not pubs:
            return None
        return self._ci_run_evidence(repo, pubs[0]["commit"])

    def _refresh_task_evidence_files(
        self, workspaces: list[dict], tasks_by_story: dict[str, dict]
    ) -> None:
        """Keep build/tasks/{id}/task-evidence.json — what
        GET .../tasks/{id}/evidence.zip actually exports — in step with
        real sync results, so the download matches what the app shows.
        No-op for a task whose delivery pack hasn't been generated yet."""
        for ws in workspaces:
            task = tasks_by_story.get(ws["story_id"])
            if task is None:
                continue
            path = self.store.path(
                "build", "tasks", task["task_id"], "task-evidence.json"
            )
            if not path.exists():
                continue
            evidence = {
                "task_id": task["task_id"],
                "status": task.get("status", "not_started"),
                "commit_ref": task.get("commit_ref", ""),
                "pr_ref": task.get("pr_ref", ""),
                "ci_status": task.get("ci_status", ""),
            }
            if ws.get("git_evidence"):
                evidence["git_evidence"] = ws["git_evidence"]
            if ws.get("ci_evidence"):
                evidence["ci_evidence"] = ws["ci_evidence"]
            self.store.write_json(
                evidence, "build", "tasks", task["task_id"], "task-evidence.json"
            )

    def delivery_pack_publish(self, role: Role, pack_id: str) -> None:
        """Publish a team pack into its developer repository as S7-managed
        context (AGENTS.md + .s7/** only). Canonical artifacts stay in the
        artifact store — published, not moved. Simulation/replay never touch
        git; only a live run writes to the connected clone."""
        roles.require("publish_delivery_pack", role)
        from s7_delivery.factory import delivery_packs as dp
        from s7_delivery.factory import publication as pub

        phase = self._build_phase()
        build_phases.require_at_least(
            phase, BuildReviewPhase.DELIVERY_PACKS_READY, "Publication"
        )
        packs = self._packs()
        pack = next((p for p in packs if p["delivery_pack_id"] == pack_id), None)
        if pack is None:
            raise EngineError(f"Unknown delivery pack {pack_id}")
        if (
            pack["publication_status"] == "published"
            and pack.get("published_version", 0) >= pack["version"]
        ):
            raise EngineError(
                f"{pack_id} v{pack['version']} is already published — regenerate"
                " packs to produce a new version first"
            )
        stale_ids = {
            s["artifact_id"] for s in self.store.read_json_or([], "staleness.json")
        }
        if pack_id in stale_ids:
            raise EngineError(
                f"{pack_id} is stale (its architecture or plan moved on) —"
                " regenerate delivery packs before publishing"
            )
        if pack.get("test_plan_status") != "approved":
            raise EngineError(
                f"{pack_id} test plan is not approved — the QA Lead must"
                " approve the acceptance-criteria test plan before this pack"
                " can publish"
            )
        branch = dp.branch_name(self.run_id, pack["team"])
        files = pub.file_plan(self.store, pack)
        publications = self.store.read_ledger("publications.jsonl")
        prior = [
            p for p in publications
            if p["repository"] == pack["repository"] and p["status"] == "published"
        ]
        republish = bool(prior)
        # Exactly what this run has written into that repository before —
        # anything else under a managed root is somebody else's file.
        prior_paths = {path for p in prior for path in p.get("published_paths", [])}
        live = self.run().mode is DemoMode.LIVE
        if live:
            repo = next(
                (r for r in self._connected_repos() if r["name"] == pack["repository"]),
                None,
            )
            if repo is None:
                raise EngineError(
                    f"Repository {pack['repository']!r} is not connected —"
                    " connect it at intake before publishing"
                )
            repo_dir = self.store.path("repos", pack["repository"])
            try:
                commit = pub.publish_to_clone(
                    repo_dir, files, branch=branch,
                    default_branch=repo.get("default_branch", ""),
                    republish=republish, published_paths=prior_paths,
                )
                if pub.has_remote(repo_dir):
                    pub.push_branch(repo_dir, branch, repo.get("default_branch", ""))
            except pub.PublicationConflict as exc:
                raise EngineError(str(exc)) from exc
        else:
            try:
                pub.check_branch(branch, "")
            except pub.PublicationConflict as exc:  # defence in depth
                raise EngineError(str(exc)) from exc
            commit = pub.simulated_commit(pack["content_hash"])

        record = GitPublication(
            publication_id=f"PUB-{len(publications) + 1:03d}",
            delivery_pack_id=pack_id,
            repository=pack["repository"],
            branch=branch,
            commit=commit,
            published_paths=sorted(files),
            status="published",
            simulated=not live,
            published_at=now_iso(),
            provenance=Provenance.HUMAN if live else Provenance.SIMULATED,
        ).model_dump(mode="json")
        self.store.append(record, "publications.jsonl")
        pack["publication_status"] = "published"
        pack["published_version"] = pack["version"]
        pack["published_at"] = record["published_at"]
        self._save_packs(packs)
        self._record(
            artifact_id=f"PUB-{pack['team_slug']}", artifact_type="git_publication",
            payload=record, author=role.value, stage=Stage.BUILD_REVIEW,
            action="publish", outcome="published", inputs=[pack_id],
            version=pack["version"],
            previous_version=pack["version"] - 1 if pack["version"] > 1 else None,
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="delivery-pack-publication", artifact=pack_id,
            outcome="published",
            details=f"{pack['team']} pack v{pack['version']} → "
                    f"{pack['repository']}@{branch} ({commit[:7]}"
                    f"{', simulated' if not live else ''})",
        )
        self._provision_workspaces(pack, branch, commit)
        # Late publications are legal once developers are executing — never
        # regress the phase back to workspaces_ready from there.
        phase = self._build_phase()
        if phase in (
            BuildReviewPhase.DELIVERY_PACKS_READY,
            BuildReviewPhase.WORKSPACES_READY,
        ):
            build_phases.advance(
                self.store, phase, BuildReviewPhase.WORKSPACES_READY,
                actor=role.value,
            )

    def _provision_workspaces(self, pack: dict, branch: str, commit: str) -> None:
        """One workspace per story in the pack. The developer field survives
        republication — assignment is a human decision, not pack state."""
        workspaces = self._workspaces()
        by_story = {w["story_id"]: w for w in workspaces}
        for story_id in pack["story_ids"]:
            existing = by_story.get(story_id)
            ws = DeveloperWorkspace(
                workspace_id=f"WS-{story_id}",
                run_id=self.run_id,
                team=pack["team"],
                story_id=story_id,
                repository=pack["repository"],
                branch=branch,
                developer=(existing or {}).get("developer", ""),
                delivery_pack_id=pack["delivery_pack_id"],
                delivery_pack_version=pack["version"],
                base_commit=commit,
                development_status="provisioned",
                provenance=Provenance.SIMULATED
                if pack.get("provenance") != "human" else Provenance.HUMAN,
            ).model_dump(mode="json")
            if existing:
                workspaces[workspaces.index(existing)] = ws
                by_story[story_id] = ws
            else:
                workspaces.append(ws)
                by_story[story_id] = ws
            self._record(
                artifact_id=f"WS-{story_id}", artifact_type="developer_workspace",
                payload=ws, author="workspace-service", stage=Stage.BUILD_REVIEW,
                action="provision", outcome="ready",
                inputs=[pack["delivery_pack_id"]],
                version=pack["version"],
                previous_version=pack["version"] - 1 if pack["version"] > 1 else None,
            )
            self._activity(
                stage=Stage.BUILD_REVIEW, actor="workspace-service",
                actor_type="service", workflow="workspace-provisioning",
                artifact=f"WS-{story_id}", outcome="ready",
                details=f"{pack['team']} · {story_id} · {pack['repository']}@{branch}",
            )
        self._save_workspaces(workspaces)

    def delivery_packs_publish_all(self, role: Role) -> int:
        """Publish every pending pack — all of them or none of them.

        The preflight below is not belt-and-braces over `delivery_pack_publish`:
        without it the batch publishes packs one by one until the first
        refusal, leaving half the teams' repositories written to and the run in
        a state nobody asked for. Every failure it checks is *foreseeable*
        before any mutation, so it is checked before any mutation."""
        roles.require("publish_delivery_pack", role)
        pending = [
            p for p in self._packs()
            if p["publication_status"] != "published"
            or p.get("published_version", 0) < p["version"]
        ]
        if not pending:
            raise EngineError("Every delivery pack is already published")
        stale_ids = {
            s["artifact_id"] for s in self.store.read_json_or([], "staleness.json")
        }
        problems: list[str] = []
        for pack in pending:
            pid = pack["delivery_pack_id"]
            if pack.get("test_plan_status") != "approved":
                problems.append(f"{pid}: test plan not approved by the QA Lead")
            if pid in stale_ids:
                problems.append(
                    f"{pid}: stale — regenerate delivery packs before publishing"
                )
            if not any(
                self._has_test_manifest(sid) for sid in pack.get("story_ids", [])
            ):
                problems.append(f"{pid}: no test plan generated")
        if problems:
            raise EngineError(
                "Nothing published — the batch is refused whole: "
                + "; ".join(problems)
            )
        for pack in pending:
            self.delivery_pack_publish(role, pack["delivery_pack_id"])
        return len(pending)

    def workspace_assign_developer(
        self, role: Role, workspace_id: str, developer: str
    ) -> None:
        roles.require("assign_developer", role)
        if not developer.strip():
            raise EngineError("Developer name is empty")
        workspaces = self._workspaces()
        ws = next(
            (w for w in workspaces if w["workspace_id"] == workspace_id), None
        )
        if ws is None:
            raise EngineError(f"Unknown workspace {workspace_id}")
        ws["developer"] = developer.strip()
        ws["last_sync_at"] = now_iso()
        self._save_workspaces(workspaces)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="developer-assignment", artifact=workspace_id,
            outcome="assigned",
            details=f"{developer.strip()} owns {ws['story_id']} "
                    "(Human Controlled · AI Assisted)",
        )
        self._refresh_pack_after_assignment(ws)

    def _refresh_pack_after_assignment(self, ws: dict) -> None:
        """Assignment is pack content (`assigned-stories.json`, AGENTS.md), so
        the affected team pack gets a new version and needs a new, explicit
        publish to reach the repository — assigning never touches git."""
        packs = self._packs()
        idx = next(
            (i for i, p in enumerate(packs)
             if p["delivery_pack_id"] == ws["delivery_pack_id"]), None,
        )
        if idx is None:  # defensive: workspaces only exist once packs do
            return
        old = packs[idx]
        plan = self.store.read_json_or(None, "planning", "plan.json")
        arch_meta = self._architecture_meta()
        pack = self._write_team_pack(
            team=old["team"], all_stories=self._stories(),
            all_tasks=self._tasks(), version=old["version"] + 1,
            plan_version=plan["plan_version"],
            architecture_version=arch_meta["version"],
            assignments=self._assignments(),
            prov=self._blueprint_provenance(),
            action="assign",  # metadata-only: never marks downstream stale
        )
        # The published branch still carries what it carried — assignment only
        # makes a newer version *pending*. Development against the published
        # version continues; the update ships on the next explicit publish.
        pack["publication_status"] = old["publication_status"]
        pack["published_version"] = old.get("published_version", 0)
        pack["published_at"] = old.get("published_at", "")
        # Assignment is human metadata (who is on the story), never test-plan
        # content — it doesn't touch acceptance criteria or the rendered test
        # skeletons. So unlike a real content regeneration (which always
        # resets test_plan_status to force re-approval), carry the QA
        # approval forward here as long as nothing the test plan actually
        # covers moved: same stories, same plan, same architecture.
        if (
            old.get("test_plan_status") == "approved"
            and old.get("story_ids") == pack.get("story_ids")
            and old.get("plan_version") == pack.get("plan_version")
            and old.get("architecture_version") == pack.get("architecture_version")
        ):
            pack["test_plan_status"] = old["test_plan_status"]
            pack["test_plan_approved_by"] = old.get("test_plan_approved_by", "")
            pack["test_plan_approved_at"] = old.get("test_plan_approved_at", "")
        packs[idx] = pack
        self._save_packs(packs)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="pack-service",
            actor_type="service", workflow="delivery-pack-refresh",
            artifact=old["delivery_pack_id"], outcome="amended",
            details=f"{old['team']} pack v{old['version'] + 1} carries the"
                    " assignment — republish to sync it to the repository",
        )

    # --- build & independent review (spec §9) ------------------------------

    def _tasks(self) -> list[dict]:
        return self.store.read_json_or([], "build", "tasks.json")

    def _save_tasks(self, tasks: list[dict]) -> None:
        self.store.write_json(tasks, "build", "tasks.json")

    def _task(self, tasks: list[dict], task_id: str) -> dict:
        target = next((t for t in tasks if t["task_id"] == task_id), None)
        if target is None:
            raise EngineError(f"Unknown task {task_id}")
        return target

    def _story(self, story_id: str) -> dict:
        story = next(
            (s for s in self._stories() if s["story_id"] == story_id), None
        )
        if story is None:
            raise EngineError(f"Unknown story {story_id}")
        return story

    def _reviews(self) -> list[dict]:
        return self.store.read_json_or([], "review", "reviews.json")

    def _latest_reviews(self) -> dict[str, dict]:
        latest: dict[str, dict] = {}
        for r in self._reviews():
            latest[r["task_id"]] = r
        return latest

    def _was_blocked(self, task_id: str) -> bool:
        return any(
            r["task_id"] == task_id and r["result"] == "blocked"
            for r in self._reviews()
        )

    def task_start(self, role: Role, task_id: str) -> None:
        roles.require("start_task", role)
        if not self.run().plan_locked:
            raise EngineError("Build opens after the plan is signed (G1)")
        tasks = self._tasks()
        task = self._task(tasks, task_id)
        # Entity-level guard: once delivery packs exist, execution evidence
        # only flows for stories whose team pack reached a developer
        # workspace. (Runs that never generate packs — the pre-existing demo
        # macros and tests — keep the legacy direct path.)
        packs = self._packs()
        if packs:
            pack = next(
                (p for p in packs if task["story_id"] in p.get("story_ids", [])),
                None,
            )
            if pack is not None and pack["publication_status"] != "published":
                raise EngineError(
                    f"{task_id} belongs to {pack['delivery_pack_id']}, which"
                    " has not been published to its developer workspace yet"
                )
        if task["status"] not in (Status.READY, "ready", Status.IN_PROGRESS, "in_progress"):
            raise EngineError(
                f"{task_id} is {task['status']}; only a ready task can start "
                "(dependencies must be complete)"
            )
        task["status"] = Status.IN_PROGRESS.value
        task["progress_pct"] = 10
        task["owner"] = "delivery-worker (simulated)"
        task["current_activity"] = (
            "Workspace created; signed plan validated; upstream artifacts "
            "checked for staleness"
        )
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self._stage_in_progress(Stage.BUILD_REVIEW)
        phase = self._build_phase()
        if phase is BuildReviewPhase.WORKSPACES_READY:
            build_phases.advance(
                self.store, phase, BuildReviewPhase.DEVELOPER_EXECUTION,
                actor=role.value,
            )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="delivery-worker",
            actor_type="simulation", workflow="task-start", artifact=task_id,
            duration_s=2.0, outcome="started", details=task["summary"],
        )

    def task_generate_tests(self, role: Role, task_id: str) -> None:
        roles.require("run_development", role)
        from s7_delivery.factory import simulate

        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if task["status"] != Status.IN_PROGRESS.value:
            raise EngineError(f"{task_id} is not in progress")
        story = self._story(task["story_id"])
        corrected = self._was_blocked(task_id)
        tests = [t.model_dump(mode="json")
                 for t in simulate.tests_for(story, corrected=corrected)]
        task["tests"] = tests
        task["progress_pct"] = 35
        task["current_activity"] = (
            "Test scenarios generated from acceptance criteria; red baseline "
            "recorded — every test fails before implementation"
        )
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self.store.write_json(
            {"task_id": task_id, "baseline": "red", "tests": tests},
            "build", "test-baselines", f"{task['story_id']}.json",
        )
        baseline_version = 2 if corrected else 1
        self._record(
            artifact_id=f"TSTB-{task_id[-3:]}", artifact_type="test_baseline",
            payload=tests, author="delivery-worker (simulated)",
            stage=Stage.BUILD_REVIEW, action="generate-tests",
            outcome="amended (corrected baseline)" if corrected
            else "created (red baseline)",
            inputs=[task["story_id"]],
            version=baseline_version,
            previous_version=1 if corrected else None,
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="delivery-worker",
            actor_type="simulation", workflow="test-first", artifact=task_id,
            duration_s=8.0, outcome="created",
            details=f"{len(tests)} tests, all initially failing",
        )

    def task_develop(self, role: Role, task_id: str) -> None:
        roles.require("run_development", role)
        from s7_delivery.factory import simulate

        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if not task.get("tests"):
            raise EngineError(
                f"{task_id} has no red test baseline; generate tests first "
                "(test-first is the demonstrated workflow)"
            )
        corrected = self._was_blocked(task_id)
        story = self._story(task["story_id"])
        prov = story.get("provenance", "simulated")

        # Opt-in escape hatch: one story's build/test/review runs for real,
        # over `common.llm`, instead of the fixed simulated evidence. See
        # `s7_delivery/factory/live.py`. Everything else stays simulated.
        if os.environ.get("S7_LIVE_STORY") == task["story_id"]:
            self._task_develop_live(task, tasks, story, task_id)
            return

        ev = simulate.dev_evidence(task["story_id"], prov)
        previous = task["version"]
        task["files_changed"] = len(ev["files"])
        task["changed_files"] = ev["files"]
        task["lines_added"] = ev["lines_added"]
        task["lines_removed"] = ev["lines_removed"]
        task["coverage_pct"] = ev["coverage"]
        task["change_summary"] = simulate.change_summary(
            task["story_id"], corrected=corrected, provenance=prov
        )
        task["commit_ref"] = f"c{abs(hash((task_id, corrected))) % 10**7:07d}"
        task["pr_ref"] = f"PR-{int(task_id[-3:]) + 20}"
        task["ci_status"] = "running"
        if corrected:
            task["version"] = previous + 1
            task["tests"] = [
                t.model_dump(mode="json")
                for t in simulate.tests_for(self._story(task["story_id"]), corrected=True)
            ]
        for t in task["tests"]:
            t["current_result"] = "passed"
        task["progress_pct"] = 80
        task["current_activity"] = (
            "Correction applied per independent review; targeted tests green"
            if corrected
            else "Smallest compliant change implemented; targeted tests green"
        )
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self._record(
            artifact_id=f"CHG-{task_id[-3:]}", artifact_type="code_change",
            payload={"files": ev["files"], "summary": task["change_summary"]},
            author="delivery-worker (simulated)", stage=Stage.BUILD_REVIEW,
            action="correct" if corrected else "develop",
            outcome="amended" if corrected else "created",
            inputs=[task["story_id"], f"TSTB-{task_id[-3:]}"],
            version=task["version"],
            previous_version=previous if corrected else None,
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="delivery-worker",
            actor_type="simulation", workflow="development", artifact=task_id,
            duration_s=45.0, outcome="amended" if corrected else "created",
            details=task["change_summary"][:160],
        )

    def _task_develop_live(
        self, task: dict, tasks: list[dict], story: dict, task_id: str
    ) -> None:
        """The `S7_LIVE_STORY` path for `task_develop`: real Developer/Tester/
        Reviewer calls over `common.llm` via `s7_delivery.factory.live`,
        instead of `simulate.dev_evidence`. Coverage isn't measured for a
        live run (the lane doesn't compute it), so it's left at 0 rather than
        invented — the caveat is in `current_activity`, not hidden."""
        from s7_delivery.factory import live

        root = self.store.path("build", "live", task_id)
        result = live.run(task, story, root)
        files = sorted(
            str(p.relative_to(result.app_dir))
            for p in result.app_dir.rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and ".pytest_cache" not in p.parts
        )
        lines_added = sum(
            len((result.app_dir / f).read_text(encoding="utf-8").splitlines())
            for f in files
        )
        verdict = result.review.get("verdict", "unknown")
        previous = task["version"]
        task["files_changed"] = len(files)
        task["changed_files"] = files
        task["lines_added"] = lines_added
        task["lines_removed"] = 0
        task["coverage_pct"] = 0
        task["change_summary"] = (
            f"Live model run for {task['story_id']}: Developer wrote "
            f"{len(files)} file(s), Tester wrote tests, independent Reviewer "
            f"verdict '{verdict}'"
            + (" after a bounded revision pass" if result.revised else "")
            + "."
        )
        task["commit_ref"] = f"c{abs(hash((task_id, 'live'))) % 10**7:07d}"
        task["pr_ref"] = f"PR-{int(task_id[-3:]) + 20}"
        for t in task["tests"]:
            t["current_result"] = "passed" if result.ok else "failed"
        task["progress_pct"] = 80
        task["current_activity"] = (
            f"Live run complete: pytest {'green' if result.ok else 'red'}, "
            f"reviewer verdict '{verdict}'. Coverage not measured for live "
            "runs (0 shown, not invented)."
        )
        task["last_activity"] = now_iso()
        task["version"] = previous + 1 if self._was_blocked(task_id) else previous
        self._save_tasks(tasks)
        self.store.write_json(result.review, "build", "live", task_id, "review.json")
        self._record(
            artifact_id=f"CHG-{task_id[-3:]}", artifact_type="code_change",
            payload={"files": files, "summary": task["change_summary"]},
            author="delivery-worker (live model)", stage=Stage.BUILD_REVIEW,
            action="develop", outcome="created",
            inputs=[task["story_id"], f"TSTB-{task_id[-3:]}"],
            version=task["version"],
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="delivery-worker",
            actor_type="live_ai", workflow="development", artifact=task_id,
            duration_s=0.0, outcome="created",
            details=task["change_summary"][:160],
        )

    def task_verify(self, role: Role, task_id: str) -> None:
        roles.require("run_development", role)
        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if not task.get("files_changed"):
            raise EngineError(f"{task_id} has no implementation to verify")
        task["progress_pct"] = 90
        task["ci_status"] = "passed"
        task["current_activity"] = (
            "Developer verification complete: build valid, targeted tests "
            "green, change summary produced"
        )
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="delivery-worker",
            actor_type="simulation", workflow="developer-verification",
            artifact=task_id, duration_s=6.0, outcome="passed",
        )

    def task_submit_review(self, role: Role, task_id: str) -> None:
        roles.require("submit_for_review", role)
        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if task.get("progress_pct", 0) < 90:
            raise EngineError(
                f"{task_id} has not completed developer verification"
            )
        task["status"] = Status.WAITING_APPROVAL.value
        task["current_activity"] = "Evidence submitted for independent review"
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="submit-review", artifact=task_id, outcome="submitted",
        )

    def task_run_to_review(self, role: Role, task_id: str) -> None:
        """Convenience for the demo: start → tests → develop → verify →
        submit, each step logged individually. The reviewer is still a
        separate role and a separate action — this never reviews."""
        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if task["status"] in (Status.READY.value, Status.BLOCKED.value):
            if task["status"] == Status.BLOCKED.value:
                raise EngineError(
                    f"{task_id} is blocked by review; return it to "
                    "development first"
                )
            self.task_start(role, task_id)
        self.task_generate_tests(role, task_id)
        self.task_develop(role, task_id)
        self.task_verify(role, task_id)
        self.task_submit_review(role, task_id)

    # --- independent review -------------------------------------------------

    @staticmethod
    def _findings_from_live_review(live_review: dict) -> list[dict]:
        """Adapt `downstream.py`'s reviewer JSON
        (`{"criteria": [{"id", "met", "note"}], "notes": [...]}`) into the
        `ReviewFinding` shape the factory renders."""
        findings = []
        for i, c in enumerate(live_review.get("criteria", []), start=1):
            if c.get("met"):
                continue
            findings.append({
                "finding_id": f"FND-{i:03d}",
                "severity": "major",
                "ac_id": c.get("id", ""),
                "summary": (c.get("note") or "Criterion not met")[:80],
                "detail": c.get("note", ""),
                "expected": "", "observed": "", "impact": "",
                "recommendation": "", "evidence": [],
            })
        return findings

    def review_execute(self, role: Role, task_id: str) -> dict:
        roles.require("execute_review", role)
        from s7_delivery.factory import simulate

        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if task["status"] != Status.WAITING_APPROVAL.value:
            raise EngineError(f"{task_id} has not been submitted for review")
        corrected = self._was_blocked(task_id)
        story = self._story(task["story_id"])
        live_review = self.store.read_json_or(None, "build", "live", task_id, "review.json")
        if live_review is not None:
            findings = self._findings_from_live_review(live_review)
            verdict = {
                "result": "passed" if live_review.get("verdict") == "pass" else "blocked",
                "critical_gaps": 0,
                "major_gaps": len(findings),
                "minor_gaps": 0,
                "findings": findings,
            }
            reviewer_label = "independent-reviewer (live model, isolated from development)"
            provenance = "live_ai"
        else:
            verdict = simulate.review_findings(
                task["story_id"], corrected=corrected,
                provenance=story.get("provenance", "simulated"),
            )
            reviewer_label = "independent-reviewer (simulated, isolated from development)"
            provenance = "simulated"
        reviews = self._reviews()
        report = {
            "review_id": f"REV-{len(reviews) + 1:03d}",
            "task_id": task_id,
            "reviewer": reviewer_label,
            "result": verdict["result"],
            "critical_gaps": verdict["critical_gaps"],
            "major_gaps": verdict["major_gaps"],
            "minor_gaps": verdict["minor_gaps"],
            "findings": verdict["findings"],
            "verified_against": [
                "signed plan v" + str(self.run().plan_version),
                task["story_id"],
                *[ac["ac_id"] for ac in story["acceptance_criteria"]],
                "change summary", "test evidence",
            ],
            "created_at": now_iso(),
            "version": sum(1 for r in reviews if r["task_id"] == task_id) + 1,
            "provenance": provenance,
        }
        reviews.append(report)
        self.store.write_json(reviews, "review", "reviews.json")
        # The ledger tracks one review artifact per task (stable id), so a
        # re-review is a new *version* of the same artifact — the display id
        # REV-00N stays unique per execution.
        self._record(
            artifact_id=f"REV-{task_id[-3:]}", artifact_type="review_report",
            payload=report, author=report["reviewer"],
            stage=Stage.BUILD_REVIEW, action="independent-review",
            outcome=report["result"],
            inputs=[task["story_id"], f"CHG-{task_id[-3:]}", f"TSTB-{task_id[-3:]}"],
            version=report["version"],
            previous_version=report["version"] - 1 if report["version"] > 1 else None,
        )

        gate = self.gate(GateId.INDEPENDENT_REVIEW)
        if report["result"] == "blocked":
            task["status"] = Status.BLOCKED.value
            task["current_activity"] = (
                f"Blocked by independent review — {report['major_gaps']} major "
                "gap(s); return to development"
            )
            gate.status = Status.BLOCKED
            outcome = "failed"
        else:
            task["status"] = Status.COMPLETED.value
            task["progress_pct"] = 100
            task["current_activity"] = "Independent review passed"
            self._unlock_dependents(tasks, task)
            outcome = "passed"
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)

        gate.conditions = gates.independent_review_gate(
            list(self._latest_reviews().values()), tasks
        )
        all_done = all(t["status"] == Status.COMPLETED.value for t in tasks)
        if all_done and gates.all_met(gate.conditions):
            gate.status = Status.PASSED
            gate.decided_by = report["reviewer"]
            gate.decided_at = now_iso()
            run = self.run()
            self._advance_stage(run, Stage.BUILD_REVIEW)
            phase = self._build_phase()
            if phase is BuildReviewPhase.DEVELOPER_EXECUTION:
                build_phases.advance(
                    self.store, phase, BuildReviewPhase.BUILD_COMPLETE,
                    actor=report["reviewer"],
                )
        self._save_gate(gate)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor="independent-reviewer",
            actor_type="simulation", workflow="independent-review-gate",
            artifact=task_id, duration_s=20.0, outcome=outcome,
            details="; ".join(f["summary"] for f in report["findings"]) or
            "verified against acceptance criteria — no gaps",
        )
        return report

    def review_return_to_development(self, role: Role, task_id: str) -> None:
        roles.require("return_to_development", role)
        tasks = self._tasks()
        task = self._task(tasks, task_id)
        if task["status"] != Status.BLOCKED.value:
            raise EngineError(f"{task_id} is not blocked by review")
        task["status"] = Status.IN_PROGRESS.value
        task["progress_pct"] = 40
        task["current_activity"] = (
            "Returned to development with review findings attached"
        )
        task["last_activity"] = now_iso()
        self._save_tasks(tasks)
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="return-to-development", artifact=task_id,
            outcome="returned",
        )

    def _unlock_dependents(self, tasks: list[dict], completed: dict) -> None:
        done_stories = {
            t["story_id"] for t in tasks
            if t["status"] == Status.COMPLETED.value
        }
        for t in tasks:
            if t["status"] == Status.NOT_STARTED.value and all(
                dep in done_stories for dep in t.get("dependencies", [])
            ):
                t["status"] = Status.READY.value
                t["last_activity"] = now_iso()

    # --- quality (spec §10) -------------------------------------------------

    COVERAGE_THRESHOLD = 80

    def quality_run(self, role: Role) -> None:
        roles.require("run_quality_checks", role)
        if self.gate(GateId.INDEPENDENT_REVIEW).status != Status.PASSED:
            raise EngineError(
                "Quality aggregation opens after the independent-review gate "
                "(G2) passes for every task"
            )
        self._stage_in_progress(Stage.QUALITY)
        stories = self._stories()
        tasks = self._tasks()
        latest = self._latest_reviews()
        checks = self._compute_checks(stories, tasks, latest)
        passed = sum(1 for c in checks if c["status"] == "passed")
        applicable = sum(1 for c in checks if c["status"] != "not_applicable")
        report = {
            "checks": checks,
            "risks": [
                {
                    "risk_id": "RSK-001", "severity": "medium",
                    "description": (
                        "Status vocabulary and packet-completeness rules rest "
                        "on unresolved SME questions; implemented against "
                        "provisional definitions."
                    ),
                    "status": "open",
                },
            ],
            "exceptions": [
                {
                    "exception_id": "EXC-001",
                    "description": (
                        "US-007 (deployment/operations) carries no code "
                        "coverage; excluded from the coverage threshold as an "
                        "operational task."
                    ),
                    "approved_by": role.value,
                    "approved_at": now_iso(),
                },
            ],
            "quality_score": round(100 * passed / applicable) if applicable else 0,
            "score_note": (
                "Informational only. The gate is the explicit conditions "
                "below, never this number."
            ),
            "recommendation": "",
            "generated_at": now_iso(),
            "provenance": "simulated",
        }
        stale = self.store.read_json_or([], "staleness.json")
        conditions = gates.quality_gate(report, stale)
        report["recommendation"] = (
            "Ready for release" if gates.all_met(conditions)
            else "Not ready — unmet conditions listed on the gate"
        )
        self.store.write_json(report, "quality", "quality-report.json")
        self._record(
            artifact_id="QRPT-001", artifact_type="quality_report",
            payload=report, author="quality-aggregation (simulated)",
            stage=Stage.QUALITY, action="aggregate", outcome="created",
            inputs=sorted({f"REV-{t['task_id'][-3:]}" for t in tasks}
                          | {f"CHG-{t['task_id'][-3:]}" for t in tasks}),
        )
        self._activity(
            stage=Stage.QUALITY, actor="quality-aggregation",
            actor_type="simulation", workflow="quality-checks",
            duration_s=15.0, outcome="created",
            details=f"{passed}/{applicable} checks passed",
        )

    def _compute_checks(
        self, stories: list[dict], tasks: list[dict], latest: dict[str, dict]
    ) -> list[dict]:
        """Each row computed from run evidence, never asserted."""
        done = {t["story_id"]: t for t in tasks
                if t["status"] == Status.COMPLETED.value}
        all_acs = [(s, ac) for s in stories for ac in s["acceptance_criteria"]]
        tested_acs = {
            t["ac_id"] for task in tasks for t in task.get("tests", [])
        }
        tests = [t for task in tasks for t in task.get("tests", [])]
        green = [t for t in tests if t["current_result"] == "passed"]
        by_type = {s["story_id"]: s.get("task_type", "feature") for s in stories}
        code_cov = [t["coverage_pct"] for t in tasks
                    if by_type.get(t["story_id"]) != "operational"
                    and t.get("coverage_pct")]
        majors = sum(r["major_gaps"] for r in latest.values()
                     if r["result"] != "passed")

        def row(check_id, name, ok, evidence, owner="quality-aggregation",
                status=None):
            return {
                "check_id": check_id, "name": name,
                "status": status or ("passed" if ok else "failed"),
                "evidence": evidence, "owner": owner,
                "completed_at": now_iso(), "exception": "",
            }

        unmapped = [s["story_id"] for s in stories if not s.get("traces_to")]
        uncoded = [ac["ac_id"] for s, ac in all_acs if s["story_id"] not in done]
        untested = [ac["ac_id"] for _s, ac in all_acs if ac["ac_id"] not in tested_acs]
        return [
            row("QC-01", "Requirement-to-story mapping", not unmapped,
                f"{len(stories)} stories trace to REQ-2026-114"
                if not unmapped else f"unmapped: {', '.join(unmapped)}"),
            row("QC-02", "AC-to-code mapping", not uncoded,
                f"{len(all_acs)} criteria covered by completed tasks"
                if not uncoded else f"uncovered: {', '.join(uncoded)}"),
            row("QC-03", "AC-to-test mapping", not untested,
                f"{len(all_acs)} criteria each carry a test"
                if not untested else f"untested: {', '.join(untested)}"),
            row("QC-04", "Test execution", len(green) == len(tests) and tests,
                f"{len(green)}/{len(tests)} tests passing"),
            row("QC-05", "Code coverage",
                bool(code_cov) and min(code_cov) >= self.COVERAGE_THRESHOLD,
                f"minimum {min(code_cov)}% across implementation tasks "
                f"(threshold {self.COVERAGE_THRESHOLD}%)" if code_cov else "no data"),
            row("QC-06", "Security scan", True,
                "0 critical, 1 medium (tracked) — simulated scan"),
            row("QC-09", "Dependency scan", True,
                "no known-vulnerable dependencies — simulated scan"),
            row("QC-10", "Standards check", True,
                "27/27 engineering standards checks — simulated"),
            row("QC-07", "Independent-review gaps", majors == 0,
                "0 unresolved major gaps" if majors == 0
                else f"{majors} major gaps open"),
            self._typed_story_check(
                "QC-11", "Regression & integration hand-off", "test", stories,
                done, row,
                done_msg="in-scope integration scenarios passed — full "
                "regression & integration executes in the organisation's "
                "existing integration test suite, initiated from this gate "
                "(not executed in this demonstration)",
                missing_msg="the plan contains no dedicated regression story — "
                "verification is the per-task targeted tests (QC-03/QC-04); "
                "full regression & integration executes in the organisation's "
                "existing integration test suite, initiated from this gate "
                "(not executed in this demonstration)"),
            row("QC-12", "Performance test hand-off", True,
                "not exercised in this demonstration — the performance test "
                "suite is initiated from this gate against the organisation's "
                "existing performance environment", status="not_applicable"),
            self._typed_story_check(
                "QC-08", "Operational readiness", "operational", stories, done, row,
                done_msg="deployment, monitoring, runbook and handover prepared",
                missing_msg="the plan contains no dedicated operational-readiness "
                "story — release checklist artifacts are generated at deployment"),
        ]

    @staticmethod
    def _typed_story_check(check_id, name, task_type, stories, done, row, *,
                           done_msg, missing_msg):
        """A check keyed to whether the plan *planned* this kind of story.

        The seeded plan carries dedicated test/operational stories, so the
        check evaluates them. A smaller plan that never planned one gets an
        honest not_applicable stating so — not a failure against a story that
        was never in the plan, and not a silent pass."""
        typed = [s["story_id"] for s in stories
                 if s.get("task_type", "feature") == task_type]
        if not typed:
            return row(check_id, name, True, missing_msg, status="not_applicable")
        incomplete = [sid for sid in typed if sid not in done]
        return row(check_id, name, not incomplete,
                   f"{', '.join(typed)} {done_msg}" if not incomplete
                   else f"{', '.join(incomplete)} not complete")

    def quality_decide(self, role: Role) -> None:
        roles.require("decide_quality_gate", role)
        report = self.store.read_json_or(None, "quality", "quality-report.json")
        stale = self.store.read_json_or([], "staleness.json")
        conditions = gates.quality_gate(report, stale)
        gate = self.gate(GateId.QUALITY)
        gate.conditions = conditions
        if not gates.all_met(conditions):
            gate.status = Status.BLOCKED
            self._save_gate(gate)
            unmet = "; ".join(c["condition"] for c in conditions if not c["met"])
            self._activity(
                stage=Stage.QUALITY, actor=role.value, actor_type="human",
                workflow="quality-gate", outcome="failed", details=unmet,
            )
            raise EngineError(f"Final gate blocked — unmet: {unmet}")
        gate.status = Status.PASSED
        gate.decided_by = role.value
        gate.decided_at = now_iso()
        self._save_gate(gate)
        run = self.run()
        self._advance_stage(run, Stage.QUALITY)
        self._activity(
            stage=Stage.QUALITY, actor=role.value, actor_type="human",
            workflow="quality-gate", outcome="passed",
        )

    # --- release (spec §11) -------------------------------------------------

    RELEASE_APPROVER_ROLES = (
        "business_owner", "engineering_lead", "qa_lead", "release_manager",
        "support_lead",
    )

    def _release(self) -> dict | None:
        return self.store.read_json_or(None, "release", "release-record.json")

    def release_request_approval(self, role: Role) -> None:
        roles.require("request_release_approval", role)
        if self.gate(GateId.QUALITY).status != Status.PASSED:
            raise EngineError("Release opens after the final gate (G3) passes")
        self._stage_in_progress(Stage.RELEASE)
        if self._release() is not None:
            raise EngineError("Release approval has already been requested")
        record = {
            "release_id": "REL-2026R4-001",
            "epic_id": "EPIC-S7-001",
            "version": "1.0.0",
            "environment": "Production",
            "release_window": "2026-08-21 20:00–23:00 ET",
            "release_manager": "unassigned until approval",
            "feature_flag": "sponsor_claim_submission (off at deploy)",
            "rollback_plan": (
                "Disable the feature flag and restore the previous journey "
                "entry point; database changes are additive with a reverse "
                "migration. Validated in staging."
            ),
            "status": Status.WAITING_APPROVAL.value,
            "deployment": None,
            "handover": None,
            "created_at": now_iso(),
            "provenance": "simulated",
        }
        self.store.write_json(record, "release", "release-record.json")
        self.store.write_text(_DEPLOY_CHECKLIST, "release", "deployment-checklist.md")
        self.store.write_text(_ROLLBACK_PLAN, "release", "rollback-plan.md")
        self.store.write_text(_RUNBOOK, "release", "runbook.md")
        self._record(
            artifact_id=record["release_id"], artifact_type="release_record",
            payload=record, author=role.value, stage=Stage.RELEASE,
            action="request-approval", outcome="created",
            inputs=["QRPT-001", "PLAN-001"],
        )
        self._activity(
            stage=Stage.RELEASE, actor=role.value, actor_type="human",
            workflow="release-approval", outcome="requested",
        )

    def release_approve(
        self, role: Role, approver: str, note: str = "", decision: str = "approved"
    ) -> None:
        roles.require("approve_release", role)
        if self._release() is None:
            raise EngineError("Request release approval first")
        if decision not in ("approved", "rejected"):
            raise EngineError("Decision must be 'approved' or 'rejected'")
        if not approver.strip():
            raise EngineError("A named approver is required")
        approvals = self.store.read_ledger("approvals.jsonl")
        self.store.append(
            Approval(
                approval_id=f"APR-{len(approvals) + 1:03d}",
                subject="release",
                role=role,
                approver=approver.strip(),
                decision=decision,
                note=note,
            ),
            "approvals.jsonl",
        )
        gate = self.gate(GateId.RELEASE)
        if decision == "rejected":
            gate.status = Status.BLOCKED
            gate.note = note
            self._save_gate(gate)
            record = self._release()
            record["status"] = Status.BLOCKED.value
            self.store.write_json(record, "release", "release-record.json")
            self._activity(
                stage=Stage.RELEASE, actor=approver, actor_type="human",
                workflow="release-approval", outcome="rejected", details=note,
            )
            return
        self._activity(
            stage=Stage.RELEASE, actor=approver, actor_type="human",
            workflow="release-approval", outcome="approved",
            details=f"as {role.value}",
        )

    def release_deploy(self, role: Role) -> None:
        roles.require("deploy", role)
        record = self._release()
        if record is None:
            raise EngineError("Request release approval first")
        stale = self.store.read_json_or([], "staleness.json")
        approvals = self.store.read_ledger("approvals.jsonl")
        conditions = gates.release_gate(
            [g.model_dump(mode="json") for g in self.gates()],
            approvals, stale, self.RELEASE_APPROVER_ROLES,
        )
        gate = self.gate(GateId.RELEASE)
        gate.conditions = conditions
        if not gates.all_met(conditions):
            gate.status = Status.BLOCKED
            self._save_gate(gate)
            unmet = "; ".join(c["condition"] for c in conditions if not c["met"])
            self._activity(
                stage=Stage.RELEASE, actor=role.value, actor_type="human",
                workflow="release-gate", outcome="failed", details=unmet,
            )
            raise EngineError(f"Release gate blocked — unmet: {unmet}")
        gate.status = Status.PASSED
        gate.decided_by = role.value
        gate.decided_at = now_iso()
        self._save_gate(gate)

        record["status"] = Status.IN_PROGRESS.value
        record["release_manager"] = role.value
        deployment = {
            "deployment_id": "DEP-001",
            "environment": "Production",
            "pipeline_ref": "pipeline #126 (simulated)",
            "artifact_count": 14,
            "strategy": "blue-green behind sponsor_claim_submission flag",
            "status": Status.COMPLETED.value,
            "smoke_test_status": "passed (8/8 checks)",
            "post_checks": [
                "health endpoints green in both colours",
                "error rate within baseline",
                "no elevated latency on lookup service",
            ],
            "deployed_at": now_iso(),
        }
        record["deployment"] = deployment
        record["status"] = Status.COMPLETED.value
        self.store.write_json(record, "release", "release-record.json")
        self._record(
            artifact_id=deployment["deployment_id"], artifact_type="deployment",
            payload=deployment, author="deployment-pipeline (simulated)",
            stage=Stage.RELEASE, action="deploy", outcome="completed",
            inputs=[record["release_id"]],
        )
        for step, secs in [
            ("pre-deployment checks", 4.0), ("deploy to production", 9.0),
            ("smoke tests", 5.0), ("post-deployment checks", 4.0),
        ]:
            self._activity(
                stage=Stage.RELEASE, actor="deployment-pipeline",
                actor_type="simulation", workflow="deployment",
                artifact="DEP-001", duration_s=secs, outcome="passed",
                details=step,
            )

    def release_handover(self, role: Role) -> None:
        """Post-deploy transition to maintenance (spec §11): support accepts
        the release, the knowledge repository update is recorded — a
        labelled demonstration line, not a real repository write — and the
        run completes."""
        roles.require("complete_handover", role)
        record = self._release()
        if not record or not record.get("deployment"):
            raise EngineError(
                "Deployment must complete before transition to maintenance"
            )
        handover = {
            "support_team": "MapleSure Application Support (S1–S6 scope)",
            "runbook_ref": "release/runbook.md",
            "knowledge_article_ref": "KB-2026-0473 (demonstration)",
            "knowledge_repository_update": (
                "KB-2026-0473 updated — application documentation refreshed "
                "for components changed by this release (demonstration)"
            ),
            "monitoring_alerts": [
                "submission-error-rate above baseline",
                "intake-handoff retry queue depth",
                "lookup-service latency p95",
            ],
            "escalation_path": "Support → Platform Team → Services Team on-call",
            "known_limitations": [
                "Status vocabulary provisional pending SME confirmation",
                "Partial-submission retention period unconfirmed",
            ],
            "hypercare_days": 7,
            "accepted_by": role.value,
            "accepted_at": now_iso(),
        }
        record["handover"] = handover
        self.store.write_json(record, "release", "release-record.json")
        self.store.write_text(_HANDOVER_DOC, "release", "support-handover.md")
        self._record(
            artifact_id="HND-001", artifact_type="support_handover",
            payload=handover, author=role.value, stage=Stage.RELEASE,
            action="handover", outcome="accepted", inputs=["DEP-001"],
        )
        run = self.run()
        self._advance_stage(run, Stage.RELEASE)
        run = self.run()
        run.status = Status.COMPLETED
        self._save_run(run)
        self._activity(
            stage=Stage.RELEASE, actor=role.value, actor_type="human",
            workflow="transition-to-maintenance", outcome="accepted",
            details="transition to maintenance accepted; hypercare 7 days; "
                    "run complete",
        )

    # --- staleness & self-correction (spec §15, §16) ------------------------

    def trigger_upstream_change(self, role: Role) -> None:
        """The demonstration's upstream change: an SME ruling amends the
        design after downstream work exists. Nothing downstream is touched —
        the ledger marks it stale, and the release gate blocks on it."""
        roles.require("trigger_upstream_change", role)
        design = self.store.read_json_or(None, "planning", "design.json")
        if design is None:
            raise EngineError("No design artifact yet; generate the plan first")
        if design["version"] > 1:
            raise EngineError("The upstream change has already been applied")
        design["version"] = 2
        design["rules"]["draft_retention"] = (
            "SME CONFIRMED: an in-progress submission is retained for 14 days "
            "before expiry, and the sponsor is notified at day 10."
        )
        self.store.write_json(design, "planning", "design.json")
        self._record(
            artifact_id="DES-001", artifact_type="design", payload=design,
            author=f"{role.value} (SME ruling)", stage=Stage.PLANNING,
            action="sme-ruling", outcome="amended", version=2,
            previous_version=1, inputs=["EPIC-S7-001", "ANL-001"],
        )
        stale = self.store.read_json_or([], "staleness.json")
        amendments = self.store.read_ledger("amendments.jsonl")
        self.store.append(
            {
                "amendment_id": f"AMD-{len(amendments) + 1:03d}",
                "reason": (
                    "SME ruling: draft retention is 14 days with a day-10 "
                    "notification — the provisional 30-day assumption in "
                    "DES-001 v1 is wrong."
                ),
                "initiator": role.value,
                "affected_artifacts": [s["artifact_id"] for s in stale],
                "impact_assessment": (
                    f"{len(stale)} downstream artifacts derive from DES-001 "
                    "and must be re-validated; release is blocked until they "
                    "are corrected."
                ),
                "required_changes": [
                    "Amend affected stories against DES-001 v2",
                    "Update implementation and test evidence",
                    "Re-run independent review",
                    "Re-evaluate quality and release gates",
                ],
                "implementation_status": "not_started",
                "verification_status": "not_started",
                "review_status": "not_started",
                "approval": None,
                "created_at": now_iso(),
            },
            "amendments.jsonl",
        )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="upstream-change", artifact="DES-001",
            outcome="amended",
            details=f"SME ruling on draft retention; {len(stale)} artifacts stale",
        )

    def run_self_correction(self, role: Role) -> None:
        """Controlled amendment execution: every stale artifact gets a **new
        version** re-validated against the changed upstream — never a silent
        update. Corrections land in original creation order so the ledger
        clears the staleness chain naturally."""
        roles.require("run_self_correction", role)
        stale = self.store.read_json_or([], "staleness.json")
        if not stale:
            raise EngineError("Nothing is stale; no correction to run")
        ledger = self.store.read_ledger("provenance.jsonl")
        order = {rec["artifact_id"]: i for i, rec in enumerate(ledger)}
        latest: dict[str, dict] = {}
        for rec in ledger:
            latest[rec["artifact_id"]] = rec

        self._activity(
            stage=Stage.QUALITY, actor=role.value, actor_type="human",
            workflow="self-correction", outcome="started",
            details=f"impact assessment: {len(stale)} artifacts to re-validate",
        )
        for item in sorted(stale, key=lambda s: order.get(s["artifact_id"], 0)):
            rec = latest[item["artifact_id"]]
            payload = {
                "artifact_id": rec["artifact_id"],
                "revalidated_against": "DES-001 v2 (14-day draft retention)",
                "previous_sha256": rec["sha256"],
            }
            if rec["artifact_type"] == "story":
                stories = self._stories()
                target = next(
                    (s for s in stories if s["story_id"] == rec["artifact_id"]), None
                )
                if target is not None:
                    target["version"] += 1
                    self.store.write_json(stories, "planning", "stories.json")
            if rec["artifact_type"] == "review_report":
                # Stable ledger id REV-<suffix> maps to the task's reviews.
                suffix = rec["artifact_id"].split("-")[-1]
                reviews = self._reviews()
                base = [r for r in reviews
                        if r["task_id"].endswith(suffix)][-1]
                reviews.append({
                    **base,
                    "review_id": f"REV-{len(reviews) + 1:03d}",
                    "result": "passed",
                    "version": base["version"] + 1,
                    "created_at": now_iso(),
                })
                self.store.write_json(reviews, "review", "reviews.json")
            self._record(
                artifact_id=rec["artifact_id"],
                artifact_type=rec["artifact_type"],
                payload=payload,
                author="self-correction (simulated)",
                stage=Stage.QUALITY,
                action="re-validate",
                outcome="amended",
                inputs=rec.get("inputs", []),
                version=rec["version"] + 1,
                previous_version=rec["version"],
            )
            self._activity(
                stage=Stage.QUALITY, actor="self-correction",
                actor_type="simulation", workflow="self-correction",
                artifact=rec["artifact_id"], duration_s=8.0,
                outcome="amended",
                details=f"re-validated against DES-001 v2 as v{rec['version'] + 1}",
            )

        remaining = self.store.read_json_or([], "staleness.json")
        amendments = self.store.read_ledger("amendments.jsonl")
        if amendments:
            done = dict(amendments[-1])
            done.update(
                implementation_status="completed",
                verification_status="completed" if not remaining else "failed",
                review_status="completed",
                completed_at=now_iso(),
            )
            self.store.append(done, "amendments.jsonl")
        self._activity(
            stage=Stage.QUALITY, actor="self-correction",
            actor_type="simulation", workflow="self-correction",
            outcome="completed" if not remaining else "failed",
            details="all stale artifacts re-validated" if not remaining
            else f"{len(remaining)} artifacts still stale",
        )

    # --- traceability (spec §12) --------------------------------------------

    def traceability(self) -> list[dict]:
        """One row per acceptance criterion: the full chain from requirement
        to handover, from model fields — never descriptive text."""
        stories = self._stories()
        tasks = {t["story_id"]: t for t in self._tasks()}
        latest_reviews = self._latest_reviews()
        quality = self.store.read_json_or(None, "quality", "quality-report.json")
        release = self._release()
        rows: list[dict] = []
        for s in stories:
            task = tasks.get(s["story_id"])
            review = latest_reviews.get(task["task_id"]) if task else None
            for ac in s["acceptance_criteria"]:
                tests = [
                    t["test_id"] for t in (task or {}).get("tests", [])
                    if t["ac_id"] == ac["ac_id"]
                ]
                rows.append({
                    "requirement": seed.REQUIREMENT.request_id,
                    "design": "DES-001",
                    "epic": s["epic_id"],
                    "story": s["story_id"],
                    "ac": ac["ac_id"],
                    "task": task["task_id"] if task else None,
                    "change": f"CHG-{task['task_id'][-3:]}"
                    if task and task.get("files_changed") else None,
                    "pr": task.get("pr_ref") if task else None,
                    "tests": tests,
                    "review": review["review_id"] if review else None,
                    "review_result": review["result"] if review else None,
                    "quality": "QRPT-001" if quality else None,
                    "deployment": release["deployment"]["deployment_id"]
                    if release and release.get("deployment") else None,
                    "handover": "HND-001"
                    if release and release.get("handover") else None,
                })
        return rows

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
