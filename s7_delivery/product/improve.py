"""Correction learning: propose a revised prompt file from human corrections,
and let an operator accept or reject it (added 2026-09-03).

The loop, in this repo's own terms:

    model output (prompt set + skill + task)
      → a person edits it (Control Centre, recorded in the run's
        corrections ledger — `product/corrections.py`)
      → `propose()` makes ONE real model call with the current file body
        and the corrections, asking for a revised body (skill
        `prompt-improve`, task `prompt-improve-task`, both editable layer
        files themselves)
      → the proposal is stored as a *draft*, never applied
      → an operator reads the diff in the admin panel and `accept()`s it,
        which records a new version through the ordinary ledger, or
        `reject()`s it.

Three disciplines: no self-approval (the model proposes, a person records
the version); the proposal is a genuine call, badged LIVE_AI or REPLAYED_AI
like every other — there is no simulated proposal; and an accepted body is
a new version that misses the old recordings, which `re_record_status`
reports rather than hides.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import secrets
from pathlib import Path
from typing import Any

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory import layers
from s7_delivery.product import config, llm_settings, prompt_sets

STAGE_KEY = "prompt-improve"
RULES_ID = "delivery-assistant"
SKILL_ID = "prompt-improve"
TASK_ID = "prompt-improve-task"
MAX_CORRECTIONS = 40
MAX_VALUE_CHARS = 4000


class ImproveError(config.ConfigError):
    pass


def _dir(set_name: str) -> Path:
    return config.config_root() / "proposals" / set_name


def _path(set_name: str, proposal_id: str) -> Path:
    if not proposal_id.startswith("PRP-") or "/" in proposal_id or "\\" in proposal_id:
        raise ImproveError(f"bad proposal id {proposal_id!r}")
    return _dir(set_name) / f"{proposal_id}.json"


def _root_for(set_name: str) -> Path | None:
    return None if set_name == prompt_sets.DEFAULT else prompt_sets.root_of(set_name)


def _provenance_now() -> str:
    mode = os.environ.get("LLM_MODE", "replay").lower()
    return "live_ai" if mode in {"live", "record"} else "replayed_ai"


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    if len(text) > MAX_VALUE_CHARS:
        return text[:MAX_VALUE_CHARS] + " …[truncated]"
    return value


def _corrections_payload(corrections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "correction_id": c["correction_id"], "run_id": c["run_id"],
            "stage": c.get("stage"), "artifact_type": c.get("artifact_type"),
            "field": c.get("field"), "before": _clip(c.get("before")),
            "after": _clip(c.get("after")), "author": c.get("author"),
        }
        for c in corrections[:MAX_CORRECTIONS]
    ]


def _validate_revision(lf: layers.LayerFile, body: str) -> tuple[str, list[str]]:
    body = body.replace("\r\n", "\n").strip("\n")
    if not body.strip():
        raise LLMError("the proposal's revised_body is empty")
    warnings: list[str] = []
    if lf.layer == "task":
        used = set(layers.placeholders_of(body))
        undeclared = sorted(used - set(lf.variables))
        if undeclared:
            raise LLMError(
                f"the proposal introduced undeclared placeholders {undeclared}; "
                "a template may only use its declared variables"
            )
        dropped = sorted(set(layers.placeholders_of(lf.body)) - used)
        if dropped:
            warnings.append(
                f"the revision drops placeholder(s) {dropped}; the workflow still "
                "supplies them, but the prompt will no longer show that data"
            )
    return body, warnings


def propose(
    set_name: str, target_id: str, corrections: list[dict[str, Any]], *,
    actor: str = "", note: str = "",
) -> dict[str, Any]:
    """One model call → one stored draft proposal. Raises LLMError (a missing
    replay recording, a malformed response) rather than fabricating."""
    if not corrections:
        raise ImproveError("no corrections to learn from")
    root = None if set_name == prompt_sets.DEFAULT else prompt_sets.root_of(set_name)
    lf = layers.get(target_id, root)
    if lf.layer not in ("skill", "task"):
        raise ImproveError(
            f"{target_id!r} is a {lf.layer} file; only skills and tasks are learnable"
        )
    payload = _corrections_payload(corrections)
    task = layers.render_task(
        TASK_ID, root,
        target_layer=lf.layer, target_id=lf.id,
        variables=", ".join(lf.variables) or "none",
        current_body=lf.body,
        corrections=json.dumps(payload, indent=2, ensure_ascii=False),
    )
    digest = hashlib.sha256(
        (lf.sha256 + json.dumps(payload, sort_keys=True)).encode("utf-8")
    ).hexdigest()[:16]
    usage: dict[str, Any] = {}
    kwargs = llm_settings.for_stage(STAGE_KEY)
    response = complete(
        PromptLayers(rules=layers.rules(RULES_ID, root), role=layers.skill(SKILL_ID, root),
                     task=task),
        json_mode=True, cache_key=f"s7_admin_improve:{digest}", usage_out=usage, **kwargs,
    )
    data = parse_json_response(response, required_keys={"revised_body", "rationale"})
    revised, warnings = _validate_revision(lf, str(data["revised_body"]))
    learned = [str(x).strip() for x in (data.get("learned") or []) if str(x).strip()]
    if revised == lf.body:
        raise LLMError("the proposal is identical to the current body — nothing learned")
    proposal = {
        "proposal_id": f"PRP-{secrets.token_hex(4)}",
        "prompt_set": set_name,
        "target_id": lf.id, "target_layer": lf.layer,
        "base_version": layers.version_of(lf.id, root)["version"],
        "base_sha256": lf.sha256,
        "corrections": [c["correction_id"] for c in corrections[:MAX_CORRECTIONS]],
        "revised_body": revised,
        "rationale": str(data["rationale"]).strip(),
        "learned": learned,
        "warnings": warnings,
        "provenance": _provenance_now(),
        "skill": layers.skill_ref(SKILL_ID, root),
        "llm": {"provider": kwargs.get("provider"), "model": kwargs.get("model"),
                "usage": usage},
        "status": "proposed",
        "created_at": config.now_iso(), "created_by": actor or "unknown",
        "note": note.strip(),
        "decided_at": None, "decided_by": None, "decision_note": None,
        "resulting_version": None,
    }
    target = _path(set_name, proposal["proposal_id"])
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(proposal, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    config.audit(actor, "prompt.propose", f"{set_name}/{lf.id}",
                 detail=f"{len(payload)} corrections → {proposal['proposal_id']}",
                 after=proposal)
    return proposal


def list_proposals(set_name: str | None = None, status: str | None = None) -> list[dict[str, Any]]:
    base = config.config_root() / "proposals"
    if not base.is_dir():
        return []
    out = []
    for set_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        if set_name and set_dir.name != set_name:
            continue
        for path in sorted(set_dir.glob("PRP-*.json")):
            rec = json.loads(path.read_text(encoding="utf-8"))
            if status and rec.get("status") != status:
                continue
            out.append(rec)
    out.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return out


def get(set_name: str, proposal_id: str) -> dict[str, Any]:
    path = _path(set_name, proposal_id)
    if not path.exists():
        raise KeyError(proposal_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _save(rec: dict[str, Any]) -> None:
    _path(rec["prompt_set"], rec["proposal_id"]).write_text(
        json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def current_state(rec: dict[str, Any]) -> dict[str, Any]:
    """Whether the proposal still applies to the file as it is now, and —
    after acceptance — whether committed recordings carry the new text."""
    from s7_delivery.product import recordings

    root = _root_for(rec["prompt_set"])
    try:
        lf = layers.get(rec["target_id"], root)
    except layers.LayerError:
        return {"file_exists": False, "stale": True, "re_record": "file missing"}
    stale = lf.sha256 != rec["base_sha256"] and rec["status"] == "proposed"
    if rec["status"] == "accepted":
        pinned = recordings.pinned_count(rec["revised_body"])
        re_record = "re-recorded" if pinned else "awaiting re-record (LLM_MODE=record)"
    else:
        re_record = None
    return {
        "file_exists": True, "stale": stale,
        "current_version": layers.version_of(lf.id, root)["version"],
        "current_sha256": lf.sha256, "re_record": re_record,
        "old_recordings_pinned": recordings.pinned_count(rec.get("base_body") or "")
        if rec.get("base_body") else None,
    }


def diff(rec: dict[str, Any]) -> str:
    root = _root_for(rec["prompt_set"])
    current = layers.get(rec["target_id"], root).body
    return "".join(difflib.unified_diff(
        current.splitlines(keepends=True), rec["revised_body"].splitlines(keepends=True),
        fromfile=f"{rec['target_id']} (current)", tofile=f"{rec['target_id']} (proposed)",
    ))


def accept(set_name: str, proposal_id: str, *, note: str, actor: str = "") -> dict[str, Any]:
    rec = get(set_name, proposal_id)
    if rec["status"] != "proposed":
        raise ImproveError(f"proposal {proposal_id} is already {rec['status']}")
    root = None if set_name == prompt_sets.DEFAULT else prompt_sets.root_of(set_name)
    lf = layers.get(rec["target_id"], root)
    if lf.sha256 != rec["base_sha256"]:
        raise ImproveError(
            f"{rec['target_id']} changed since this proposal was made "
            f"(v{rec['base_version']} → v{layers.version_of(lf.id, root)['version']}); "
            "propose again from the current text"
        )
    if not note.strip():
        raise ImproveError("accepting a proposal needs a note — it becomes the ledger line")
    ledger_note = f"correction learning {proposal_id}: {note.strip()} — {rec['rationale']}"
    line = layers.write_body(rec["target_id"], rec["revised_body"], note=ledger_note,
                             author=actor, root=root)
    rec.update({
        "status": "accepted", "decided_at": config.now_iso(),
        "decided_by": actor or "unknown", "decision_note": note.strip(),
        "resulting_version": line["version"] if line else None,
    })
    _save(rec)
    config.audit(actor, "prompt.accept_proposal", f"{set_name}/{rec['target_id']}",
                 detail=f"{proposal_id} → v{rec['resulting_version']}", after=rec)
    return rec


def reject(set_name: str, proposal_id: str, *, note: str, actor: str = "") -> dict[str, Any]:
    rec = get(set_name, proposal_id)
    if rec["status"] != "proposed":
        raise ImproveError(f"proposal {proposal_id} is already {rec['status']}")
    rec.update({
        "status": "rejected", "decided_at": config.now_iso(),
        "decided_by": actor or "unknown", "decision_note": note.strip(),
    })
    _save(rec)
    config.audit(actor, "prompt.reject_proposal", f"{set_name}/{rec['target_id']}",
                 detail=proposal_id, after=rec)
    return rec
