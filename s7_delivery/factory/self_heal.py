"""Self-healing: a human change after plan lock becomes a change record that a
versioned playbook runs to completion — mechanical steps automatically, human
gates never.

The shape (feature priorities #8 change management and #10 staleness, joined):

    human edit on a main page          architecture_revise / test_plan_amend /
            │                          trigger_upstream_change
            ▼
    change record  (SH-nnn)            governance/self_healing.json — one per change,
            │                          naming the playbook file and its recorded version
            ▼
    playbook steps, in order           s7_delivery/layers/playbooks/<change-type>.md
      mechanical → run now             assess impact, regenerate packs, re-validate stale
      gate       → wait for a role     accept, approve, publish, re-run quality, re-approve
            │
            ▼
    advance() after every hooked       the gate is observed as met from the run's own
    human action                       records, then the next mechanical step runs

Three disciplines this module holds to:

- **No phase self-approves.** A gate step is satisfied only by the named
  role performing the real engine action; this module evaluates the run's
  records and never signs anything itself.
- **Nothing is invented.** Impact is the staleness walk over the provenance
  ledger; mechanical outcomes are what the engine actually did, badged with
  the provenance the engine gives them (simulated in simulation runs).
- **The playbook that ran is named by version.** A change record carries the
  playbook id, ledger version and content hash, so a later edit to the file
  cannot rewrite what an earlier change followed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from s7_delivery.factory import layers
from s7_delivery.factory.models import Role, Stage, now_iso

if TYPE_CHECKING:  # pragma: no cover
    from s7_delivery.factory.engine import Engine

STATE = ("governance", "self_healing.json")

MECHANICAL_ACTIONS = ("assess_impact", "regenerate_delivery_packs", "revalidate_stale_artifacts")
GATE_ACTIONS = (
    "accept_architecture", "approve_test_plan", "publish_delivery_pack",
    "run_self_correction", "run_quality_checks", "approve_release",
)


def playbooks() -> list[dict[str, Any]]:
    return [
        layers.playbook(lf.id)
        for lf in layers.load_all().values() if lf.layer == "playbook"
    ]


def _read(engine: Engine) -> list[dict[str, Any]]:
    return engine.store.read_json_or([], *STATE)


def _write(engine: Engine, changes: list[dict[str, Any]]) -> None:
    engine.store.write_json(changes, *STATE)


def _stale_ids(engine: Engine) -> list[str]:
    return [s["artifact_id"] for s in engine.store.read_json_or([], "staleness.json")]


def _event(engine: Engine, change: dict, outcome: str, details: str) -> None:
    engine._activity(
        stage=Stage(change["stage"]), actor="self-healing", actor_type="service",
        workflow="self-healing", artifact=change["change_id"],
        outcome=outcome, details=details,
    )


# --- change intake ------------------------------------------------------------


def open_change(
    engine: Engine,
    *,
    change_type: str,
    initiator: Role,
    reason: str,
    trigger_artifact: str,
    trigger_version: int,
    pack_id: str | None = None,
    story_id: str | None = None,
    pack_version: int | None = None,
    amendment_id: str | None = None,
) -> dict[str, Any]:
    """Record the change, link (or create) its amendment, and run the playbook
    as far as the first human gate."""
    book = layers.playbook(change_type)
    changes = _read(engine)
    change_id = f"SH-{len(changes) + 1:03d}"  # SH-: CHG- is the ledger's change-request id
    steps = [
        {
            "step_id": s["step_id"], "kind": s["kind"], "action": s["action"],
            "role": s.get("role"), "as_role": s.get("as_role"),
            "label": s["label"], "detail": s.get("detail", ""),
            "status": "pending", "executed_at": None, "outcome": "", "provenance": None,
        }
        for s in book["steps"]
    ]
    if amendment_id is None:
        amendments = engine.store.read_ledger("amendments.jsonl")
        amendment_id = f"AMD-{len(amendments) + 1:03d}"
        engine.store.append(
            {
                "amendment_id": amendment_id,
                "change_id": change_id,
                "change_type": change_type,
                "reason": reason,
                "initiator": initiator.value,
                "affected_artifacts": _stale_ids(engine),
                "impact_assessment": "",
                "required_changes": [s["label"] for s in book["steps"]],
                "implementation_status": "not_started",
                "verification_status": "not_started",
                "review_status": "not_started",
                "approval": None,
                "created_at": now_iso(),
            },
            "amendments.jsonl",
        )
    rec: dict[str, Any] = {
        "change_id": change_id,
        "change_type": change_type,
        "title": book["title"],
        "stage": book.get("stage", "build_review"),
        "playbook_id": book["playbook_id"],
        "playbook_version": book["version"],
        "playbook_sha256": book["sha256"],
        "playbook_recorded": book["recorded"],
        "initiator": initiator.value,
        "reason": reason,
        "created_at": now_iso(),
        "trigger": {"artifact_id": trigger_artifact, "version": trigger_version},
        "scope": {"pack_id": pack_id, "story_id": story_id, "pack_version": pack_version},
        "amendment_id": amendment_id,
        "impact": {"stale": [], "count": 0, "assessed_at": None},
        "steps": steps,
        "status": "open",
        "completed_at": None,
    }
    changes.append(rec)
    _write(engine, changes)
    _event(
        engine, rec, "opened",
        f"{change_type} by {initiator.value} — playbook {book['playbook_id']}"
        f"@v{book['version']}: {reason[:140]}",
    )
    advance(engine)
    return next(c for c in _read(engine) if c["change_id"] == change_id)


# --- execution ------------------------------------------------------------------


def advance(engine: Engine) -> list[str]:
    """Move every open change forward: observe gates from the run's records,
    run the mechanical steps they unblock, stop at the next unmet gate.
    Re-entrant-safe — mechanical steps call engine actions whose own hooks
    call back here, and those inner calls are no-ops."""
    if getattr(engine, "_self_heal_active", False):
        return []
    from s7_delivery.factory.engine import EngineError

    engine._self_heal_active = True
    touched: list[str] = []
    try:
        changes = _read(engine)
        for change in changes:
            if change["status"] != "open":
                continue
            for step in change["steps"]:
                if step["status"] == "done":
                    continue
                if step["kind"] == "gate":
                    if _gate_met(engine, change, step):
                        step.update(
                            status="done", executed_at=now_iso(), provenance="human",
                            outcome=(f"observed — {step['role']} recorded the "
                                     f"{step['action']} action"),
                        )
                        _write(engine, changes)
                        _event(engine, change, "gate-met", f"{step['step_id']}: {step['label']}")
                        touched.append(f"{change['change_id']}:{step['step_id']}")
                        continue
                    step["status"] = "waiting"
                    _write(engine, changes)
                    break
                try:
                    outcome, prov = _run_mechanical(engine, change, step)
                except EngineError as exc:
                    step.update(status="failed", executed_at=now_iso(), outcome=str(exc),
                                provenance="rule_based")
                    _write(engine, changes)
                    _event(engine, change, "failed", f"{step['step_id']}: {exc}")
                    touched.append(f"{change['change_id']}:{step['step_id']}")
                    break
                step.update(status="done", executed_at=now_iso(), outcome=outcome, provenance=prov)
                _write(engine, changes)
                _event(engine, change, "step-done", f"{step['step_id']}: {outcome}")
                touched.append(f"{change['change_id']}:{step['step_id']}")
            if change["status"] == "open" and all(s["status"] == "done" for s in change["steps"]):
                change["status"] = "completed"
                change["completed_at"] = now_iso()
                _write(engine, changes)
                _close_amendment(engine, change)
                _event(engine, change, "completed",
                       f"all {len(change['steps'])} playbook steps done")
                touched.append(f"{change['change_id']}:completed")
        return touched
    finally:
        engine._self_heal_active = False


def _close_amendment(engine: Engine, change: dict) -> None:
    """Append the closing record for the change's amendment — the ledger is
    append-only, so completion is a new line, never an edit."""
    amendments = engine.store.read_ledger("amendments.jsonl")
    latest = next((a for a in reversed(amendments)
                   if a.get("amendment_id") == change.get("amendment_id")), None)
    if latest is None or latest.get("implementation_status") == "completed":
        return
    done = dict(latest)
    done.update(
        implementation_status="completed", verification_status="completed",
        review_status="completed", completed_at=change["completed_at"],
        change_id=change["change_id"],
        impact_assessment=latest.get("impact_assessment")
        or f"{change['impact']['count']} artifact(s) derived from "
           f"{change['trigger']['artifact_id']} v{change['trigger']['version']}",
    )
    engine.store.append(done, "amendments.jsonl")


def _gate_met(engine: Engine, change: dict, step: dict) -> bool:
    """A gate is met only when the run's own records show the named action
    happened after (or at) the change — never asserted."""
    action = step["action"]
    trig = change["trigger"]
    scope = change.get("scope") or {}
    since = change["created_at"]
    if action == "accept_architecture":
        meta = engine._architecture_meta()
        return bool(meta) and meta.get("status") == "accepted" \
            and int(meta.get("version", 0)) >= int(trig["version"])
    if action in ("approve_test_plan", "publish_delivery_pack"):
        packs = engine._packs()
        if scope.get("pack_id"):
            packs = [p for p in packs if p["delivery_pack_id"] == scope["pack_id"]]
            if not packs:
                return False
            floor = int(scope.get("pack_version") or 0)
            fresh = [p for p in packs if int(p.get("version", 0)) >= floor]
        else:
            fresh = [p for p in packs
                     if int(p.get("architecture_version", 0)) >= int(trig["version"])]
        if not fresh or len(fresh) != len(packs):
            return False
        if action == "approve_test_plan":
            return all(p.get("test_plan_status") == "approved" for p in fresh)
        return all(int(p.get("published_version", 0)) == int(p.get("version", 0))
                   for p in fresh)
    if action == "run_self_correction":
        recs = [a for a in engine.store.read_ledger("amendments.jsonl")
                if a.get("amendment_id") == change.get("amendment_id")]
        return bool(recs) and recs[-1].get("implementation_status") == "completed"
    if action == "run_quality_checks":
        report = engine.store.read_json_or(None, "quality", "quality-report.json")
        return bool(report) and str(report.get("generated_at", "")) > since
    if action == "approve_release":
        return any(
            a.get("subject") == "release" and a.get("decision") == "approved"
            and str(a.get("decided_at", "")) > since
            for a in engine.store.read_ledger("approvals.jsonl")
        )
    return False


def _run_mechanical(engine: Engine, change: dict, step: dict) -> tuple[str, str]:
    """Execute one mechanical step through the engine's own actions; return
    (outcome sentence, provenance label)."""
    from s7_delivery.factory.engine import EngineError

    action = step["action"]
    trig = change["trigger"]
    label = f"{trig['artifact_id']} v{trig['version']}"
    if action == "assess_impact":
        stale = _stale_ids(engine)
        change["impact"] = {"stale": stale, "count": len(stale), "assessed_at": now_iso()}
        if stale:
            return (f"{len(stale)} downstream artifact(s) derive from {label} and are stale: "
                    f"{', '.join(stale[:8])}{'…' if len(stale) > 8 else ''}"), "rule_based"
        return f"no downstream artifact derives from {label}", "rule_based"
    if action == "regenerate_delivery_packs":
        engine.delivery_packs_generate(Role(step["as_role"]))
        meta = engine._architecture_meta() or {}
        packs = engine._packs()
        return (f"{len(packs)} pack(s) regenerated at architecture v{meta.get('version', '?')};"
                " QA approval and publication reset"), engine._blueprint_provenance().value
    if action == "revalidate_stale_artifacts":
        stale = _stale_ids(engine)
        if not stale:
            return "nothing stale — no re-validation needed", "rule_based"
        engine.run_self_correction(Role(step["as_role"]), against=label)
        remaining = _stale_ids(engine)
        done = len(stale) - len(remaining)
        return (f"{done} artifact(s) re-validated as new versions against {label}"
                + (f"; {len(remaining)} still stale" if remaining else "")), "simulated"
    raise EngineError(f"unknown mechanical action {action!r}")


# --- the view --------------------------------------------------------------------


def view(engine: Engine) -> dict[str, Any]:
    """Everything the Self-Healing page renders. Derived from the change
    records, the activity ledger and the current staleness — never stored
    twice, never an AI claim."""
    changes = _read(engine)
    activity = engine.store.read_ledger("activity.jsonl")
    out = []
    summary = {"open": 0, "waiting_on_human": 0, "completed": 0, "failed": 0}
    for c in changes:
        pending = next((s for s in c["steps"] if s["status"] != "done"), None)
        waiting_on = pending["role"] if pending and pending["kind"] == "gate" else None
        failed = any(s["status"] == "failed" for s in c["steps"])
        if c["status"] == "completed":
            summary["completed"] += 1
        elif failed:
            summary["failed"] += 1
        else:
            summary["open"] += 1
            if waiting_on:
                summary["waiting_on_human"] += 1
        out.append({
            **c,
            "waiting_on": waiting_on,
            "blocked_step": pending["step_id"] if pending else None,
            "done_steps": sum(1 for s in c["steps"] if s["status"] == "done"),
            "events": [e for e in activity if e.get("artifact") == c["change_id"]],
        })
    return {
        "provenance": "rule_based",
        "summary": summary,
        "stale_now": _stale_ids(engine),
        "changes": list(reversed(out)),
        "playbooks": playbooks(),
    }
