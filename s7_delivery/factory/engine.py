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

from s7_delivery.factory import roles, seed
from s7_delivery.factory.models import (
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
