"""Structured editing of the self-healing playbooks (`playbooks/<change-type>.md`).

A playbook is a layer file whose body is JSON: an ordered list of steps the
engine runs when a human change opens a change record
(`factory/self_heal.py`). The raw-text file routes already edit it as bytes;
this module edits it as *steps*, validated against the engine's own
catalogue — `MECHANICAL_ACTIONS` and `GATE_ACTIONS` — and the effective
permission table, so a saved playbook can never name a gate no role can
sign or an action the engine does not know.

Three things are held to:

- **The catalogue is the engine's.** Labels and descriptions below describe
  what `self_heal._run_mechanical` and `self_heal._gate_met` actually do;
  nothing is listed the engine will not execute or observe.
- **A playbook's id is the change type.** `layers.playbook(change_type)` is
  how the engine finds it, so ids are never renamed here; the body's
  `change_type` is always written equal to the file id.
- **Every save is a ledger line.** The body goes through `layers.write_body`
  — same ledger, snapshots, diff and rollback as any other layer file; an
  identical body is reported `unchanged` and records nothing.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from s7_delivery.factory import layers, roles, store
from s7_delivery.factory.layers import LayerError
from s7_delivery.factory.models import Role
from s7_delivery.factory.self_heal import GATE_ACTIONS, MECHANICAL_ACTIONS, STATE
from s7_delivery.product import config, prompt_sets

_STEP_ID_RE = re.compile(r"^[a-z][a-z0-9-]*$")
KINDS = ("mechanical", "gate")


class PlaybookValidationError(LayerError):
    """A playbook body was refused. `problems` lists every reason, so the
    editor can show them all at once rather than one per round trip."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems))
        self.problems = list(problems)


# --- the catalogue --------------------------------------------------------------

# What each action does, stated from `self_heal.py`. `engine_action` is the
# permission the step's `as_role` (mechanical) or `role` (gate) must hold in
# the effective table — `None` for the one step that calls no engine action.
_MECHANICAL: dict[str, dict[str, Any]] = {
    "assess_impact": {
        "label": "Assess impact",
        "description": "Walk the staleness ledger and list every artifact derived from "
                       "the trigger artifact on the change record. Rule-based; calls no "
                       "engine action and needs no role.",
        "engine_action": None,
    },
    "regenerate_delivery_packs": {
        "label": "Regenerate delivery packs",
        "description": "Run Engine.delivery_packs_generate as the step's `as_role`: new "
                       "pack versions against the accepted architecture, with QA test-plan "
                       "approval and publication reset on every pack.",
        "engine_action": "generate_delivery_packs",
    },
    "revalidate_stale_artifacts": {
        "label": "Re-validate stale artifacts",
        "description": "If anything is still stale, run Engine.run_self_correction as the "
                       "step's `as_role` against the trigger: each stale artifact gets a "
                       "new version. Reports 'nothing stale' and does nothing otherwise.",
        "engine_action": "run_self_correction",
    },
}

_GATE: dict[str, dict[str, Any]] = {
    "accept_architecture": {
        "label": "Architecture accepted",
        "description": "Observed met when the architecture record is `accepted` at a "
                       "version at or above the change's trigger version.",
    },
    "approve_test_plan": {
        "label": "Test plan approved",
        "description": "Observed met when every delivery pack in scope (the change's pack, "
                       "or all packs at or above the trigger architecture version) has "
                       "`test_plan_status` approved.",
    },
    "publish_delivery_pack": {
        "label": "Delivery pack published",
        "description": "Observed met when every delivery pack in scope has its current "
                       "version published (`published_version` equals `version`).",
    },
    "run_self_correction": {
        "label": "Self-correction run",
        "description": "Observed met when the change's amendment record reaches "
                       "`implementation_status` completed — the controlled correction ran.",
    },
    "run_quality_checks": {
        "label": "Quality checks re-run",
        "description": "Observed met when a quality report was generated after the change "
                       "opened.",
    },
    "approve_release": {
        "label": "Release re-approved",
        "description": "Observed met when a release approval was decided after the change "
                       "opened.",
    },
}

assert set(_MECHANICAL) == set(MECHANICAL_ACTIONS), "catalogue drifted from self_heal"
assert set(_GATE) == set(GATE_ACTIONS), "catalogue drifted from self_heal"


def _shipped_roles() -> dict[str, str]:
    """Action → the role the committed playbooks name for it (first
    occurrence, in file order). The default set is the convention."""
    out: dict[str, str] = {}
    for lf in layers.load_all(layers.LAYERS_ROOT).values():
        if lf.layer != "playbook":
            continue
        try:
            book = layers.playbook(lf.id, layers.LAYERS_ROOT)
        except LayerError:
            continue
        for step in book["steps"]:
            role = step.get("role") if step["kind"] == "gate" else step.get("as_role")
            if role and step["action"] not in out:
                out[step["action"]] = str(role)
    return out


def _permitted(action: str | None) -> list[str]:
    if action is None:
        return []
    return [r.value for r in roles.permitted_roles(action)]


def _action_info(action: str, kind: str, shipped: dict[str, str]) -> dict[str, Any]:
    meta = _MECHANICAL[action] if kind == "mechanical" else _GATE[action]
    engine_action = meta.get("engine_action", action) if kind == "mechanical" else action
    return {
        "action": action,
        "kind": kind,
        "label": meta["label"],
        "description": meta["description"],
        "default_role": shipped.get(action),
        "permitted_roles": _permitted(engine_action),
        "engine_action": engine_action,
    }


def catalogue(set_name: str = prompt_sets.DEFAULT) -> dict[str, Any]:
    """The payload the editor needs: every action the engine can run or
    observe, the roles it may name, and the change types the set carries."""
    shipped = _shipped_roles()
    root = prompt_sets.root_of(set_name)
    return {
        "mechanical": [_action_info(a, "mechanical", shipped) for a in MECHANICAL_ACTIONS],
        "gate": [_action_info(a, "gate", shipped) for a in GATE_ACTIONS],
        "roles": [{"id": r.value, "label": roles.role_label(r)} for r in Role],
        "change_types": [lf.id for lf in layers.load_all(root).values()
                         if lf.layer == "playbook"],
    }


def action_info(action: str) -> dict[str, Any] | None:
    """One `ActionInfo`, or `None` for an action the engine does not know."""
    shipped = _shipped_roles()
    if action in _MECHANICAL:
        return _action_info(action, "mechanical", shipped)
    if action in _GATE:
        return _action_info(action, "gate", shipped)
    return None


# --- validation -------------------------------------------------------------------


def validate_steps(steps: Any, set_name: str = prompt_sets.DEFAULT) -> dict[str, Any]:
    """Dry run. Returns `{"ok", "problems", "warnings"}` — every refusal
    listed, and the conventions the shipped playbooks follow as warnings.
    `set_name` only has to exist: the permission table is product-wide."""
    prompt_sets.root_of(set_name)
    problems: list[str] = []
    warnings: list[str] = []
    if not isinstance(steps, list):
        return {"ok": False, "problems": ["steps must be a list"], "warnings": []}
    if not steps:
        problems.append("at least one step is required")
    perms = {a: set(roles.permitted_roles(a)) for a in roles.PERMISSIONS}
    role_ids = {r.value for r in Role}
    seen: set[str] = set()
    for i, step in enumerate(steps, start=1):
        if not isinstance(step, dict):
            problems.append(f"step {i}: must be an object")
            continue
        sid = str(step.get("step_id") or "").strip()
        where = f"step {i} ({sid or 'no id'})"
        if not sid:
            problems.append(f"{where}: step_id is required")
        elif not _STEP_ID_RE.match(sid):
            problems.append(f"{where}: step_id must be kebab-case (a-z, 0-9, -)")
        elif sid in seen:
            problems.append(f"{where}: duplicate step_id")
        seen.add(sid)
        kind = step.get("kind")
        action = str(step.get("action") or "")
        if kind not in KINDS:
            problems.append(f"{where}: kind must be mechanical or gate, got {kind!r}")
            continue
        catalogue_for_kind = _MECHANICAL if kind == "mechanical" else _GATE
        if action not in catalogue_for_kind:
            problems.append(
                f"{where}: {kind} action {action!r} is not in the engine's catalogue "
                f"(expected one of {', '.join(catalogue_for_kind)})"
            )
            continue
        if not str(step.get("label") or "").strip():
            problems.append(f"{where}: label is required")
        if kind == "gate":
            role = step.get("role")
            if not role:
                problems.append(f"{where}: a gate step needs a role")
            elif role not in role_ids:
                problems.append(f"{where}: unknown role {role!r}")
            elif Role(role) not in perms.get(action, set()):
                holders = ", ".join(r.value for r in roles.permitted_roles(action)) or "nobody"
                problems.append(
                    f"{where}: role {role!r} does not hold {action!r} in the effective "
                    f"permission table (holders: {holders})"
                )
            if step.get("as_role"):
                problems.append(f"{where}: as_role belongs on mechanical steps only")
        else:
            engine_action = _MECHANICAL[action]["engine_action"]
            as_role = step.get("as_role")
            if step.get("role"):
                problems.append(f"{where}: role belongs on gate steps only")
            if as_role and as_role not in role_ids:
                problems.append(f"{where}: unknown as_role {as_role!r}")
            elif engine_action is not None and not as_role:
                problems.append(
                    f"{where}: {action!r} runs Engine.{engine_action} and needs an as_role"
                )
            elif as_role and engine_action is not None \
                    and Role(as_role) not in perms.get(engine_action, set()):
                holders = ", ".join(r.value for r in roles.permitted_roles(engine_action))
                problems.append(
                    f"{where}: as_role {as_role!r} does not hold {engine_action!r} "
                    f"(holders: {holders or 'nobody'})"
                )
            elif as_role and engine_action is None:
                warnings.append(f"{where}: {action!r} calls no engine action; as_role is "
                                "recorded but unused")
    if steps and isinstance(steps[0], dict) and steps[0].get("action") != "assess_impact":
        warnings.append("the first step is normally assess_impact so the change record "
                        "carries its impact before any gate is waited on")
    return {"ok": not problems, "problems": problems, "warnings": warnings}


def _normalise_step(step: dict[str, Any]) -> dict[str, Any]:
    """The step as the file carries it: the contract's keys, in a fixed
    order, and only the role key its kind uses."""
    out: dict[str, Any] = {
        "step_id": str(step["step_id"]).strip(),
        "kind": step["kind"],
        "action": step["action"],
        "label": str(step["label"]).strip(),
        "detail": str(step.get("detail") or "").strip(),
    }
    if step["kind"] == "gate":
        out["role"] = step["role"]
    elif step.get("as_role"):
        out["as_role"] = step["as_role"]
    return out


# --- read ---------------------------------------------------------------------------


def _usage(playbook_id: str, runs_root: Path | None) -> dict[str, int]:
    """How many runs, and how many change records, pin this playbook id in
    their `governance/self_healing.json`. Counted from files, never stored."""
    base = Path(runs_root) if runs_root is not None else store.RUNS_ROOT
    runs = changes = 0
    for run_id in store.list_runs(base):
        path = base / run_id / Path(*STATE)
        if not path.exists():
            continue
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        hits = sum(1 for c in records if isinstance(c, dict)
                   and c.get("playbook_id") == playbook_id)
        if hits:
            runs += 1
            changes += hits
    return {"runs": runs, "changes": changes}


def _row(root: Path, playbook_id: str) -> dict[str, Any]:
    for row in layers.describe(root)["playbooks"]:
        if row["id"] == playbook_id:
            return row
    lf = layers.get(playbook_id, root)  # raises "no layer file" for an unknown id
    raise LayerError(f"{playbook_id!r} is a {lf.layer} file, not a playbook")


def get_playbook(set_name: str, playbook_id: str,
                 *, runs_root: Path | None = None) -> dict[str, Any]:
    root = prompt_sets.root_of(set_name)
    row = _row(root, playbook_id)
    lf = layers.get(playbook_id, root)
    book = layers.playbook(playbook_id, root)
    return {
        **row,
        "body": lf.body,
        "frontmatter_stage": row["stage"],
        "change_type": book["change_type"],
        "trigger": book.get("trigger", ""),
        "stage": book.get("stage", row["stage"]),
        "steps": book["steps"],
        "versions": layers.versions_of(playbook_id, root),
        "usage": _usage(playbook_id, runs_root),
    }


def list_playbooks(set_name: str, *, runs_root: Path | None = None) -> list[dict[str, Any]]:
    root = prompt_sets.root_of(set_name)
    ids = [lf.id for lf in layers.load_all(root).values() if lf.layer == "playbook"]
    return [get_playbook(set_name, pid, runs_root=runs_root) for pid in ids]


# --- write ---------------------------------------------------------------------------


def save_playbook(
    set_name: str, playbook_id: str, *, steps: Any, note: str,
    trigger: str | None = None, stage: str | None = None, actor: str = "",
    runs_root: Path | None = None,
) -> dict[str, Any]:
    """Validate, render the body, write it through the layer ledger, audit.
    Returns `{"record": LedgerLine | None, "unchanged": bool, "playbook": detail}`."""
    root = prompt_sets.root_of(set_name)
    before = get_playbook(set_name, playbook_id, runs_root=runs_root)
    result = validate_steps(steps, set_name)
    if not result["ok"]:
        raise PlaybookValidationError(result["problems"])
    body = json.dumps(
        {
            "change_type": playbook_id,
            "trigger": (trigger if trigger is not None else before["trigger"]).strip(),
            "stage": (stage if stage is not None else before["stage"]).strip(),
            "steps": [_normalise_step(s) for s in steps],
        },
        indent=2, ensure_ascii=False,
    )
    record = layers.write_body(playbook_id, body, note=note, author=actor, root=root)
    if record is not None:
        config.audit(
            actor, "playbook.write", f"{set_name}/{playbook_id}",
            detail=f"v{record['version']}: {record['note']}",
            before={"sha256": before["sha256"]}, after={"sha256": record["sha256"]},
        )
    return {
        "record": record,
        "unchanged": record is None,
        "warnings": result["warnings"],
        "playbook": get_playbook(set_name, playbook_id, runs_root=runs_root),
    }
