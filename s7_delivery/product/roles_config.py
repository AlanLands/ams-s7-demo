"""Role and permission overrides (`config/roles.json`).

`factory/roles.py` keeps the committed defaults — `PERMISSIONS` and
`ROLE_PROFILES` — and every reader there (`require`, `allowed`,
`permitted_roles`, `actions_for`, `role_label`, `profile`) consults the
*effective* tables this module computes on every call, so a saved override
applies to the next request with no restart.

The override file is small and explicit:

    {
      "permissions": {"<action>": ["<role id>", ...]},   # complete replacement
      "profiles":    {"<role id>": {"label": ..., "summary": ..., "signs": [...]}}
    }

An action listed under `permissions` is *replaced* by the holder set given —
never merged — so what the operator sees in the file is what the engine
enforces. Two refusals keep the separation rules from being emptied by
accident: an unknown action or role is refused, and so is an action left
with no holder at all (a gate nobody can sign is a run nobody can finish).
"""

from __future__ import annotations

from typing import Any

from s7_delivery.factory.models import Role
from s7_delivery.factory.roles import PERMISSIONS, ROLE_PROFILES
from s7_delivery.product import config

FILE = "roles.json"
_PROFILE_KEYS = ("label", "summary", "signs")

# The section an action belongs to — the comments in `PERMISSIONS`, made
# explicit so the admin surface can group the table. `tests/test_roles_config`
# checks that every action in `PERMISSIONS` has a group here.
ACTION_GROUPS: dict[str, str] = {
    # intake
    "edit_requirement": "intake",
    "upload_intake_document": "intake",
    "run_intake_analysis": "intake",
    "create_epic": "intake",
    "connect_repository": "intake",
    "ask_clarification": "intake",
    "answer_clarification": "intake",
    "manage_business_rules": "intake",
    "route_requirement": "intake",
    "setup_new_application": "intake",
    "create_new_application_repo": "intake",
    "pass_intake_gate": "intake",
    # planning
    "generate_plan": "planning",
    "edit_story": "planning",
    "request_plan_revision": "planning",
    "sign_off_plan": "planning",
    "export_artifacts": "planning",
    "write_delivery_clone": "planning",
    "push_delivery_branch": "planning",
    # build & review
    "generate_architecture": "build_review",
    "revise_architecture": "build_review",
    "accept_architecture": "build_review",
    "generate_delivery_packs": "build_review",
    "approve_test_plan": "build_review",
    "amend_test_plan": "build_review",
    "publish_delivery_pack": "build_review",
    "assign_developer": "build_review",
    "override_dependency_gate": "build_review",
    "sync_git_evidence": "build_review",
    "start_task": "build_review",
    "run_development": "build_review",
    "submit_for_review": "build_review",
    "execute_review": "build_review",
    "return_to_development": "build_review",
    "approve_review": "build_review",
    # quality
    "run_quality_checks": "quality",
    "decide_quality_gate": "quality",
    # release
    "request_release_approval": "release",
    "approve_release": "release",
    "deploy": "release",
    "generate_release_document": "release",
    "complete_handover": "release",
    # governance
    "create_amendment": "governance",
    "trigger_upstream_change": "governance",
    "run_self_correction": "governance",
    # run lifecycle
    "manage_run": "run",
}
GROUPS = ("intake", "planning", "build_review", "quality", "release", "governance", "run")

_EMPTY: dict[str, Any] = {"permissions": {}, "profiles": {}}


def group_of(action: str) -> str:
    """The group of an action; an action added to `PERMISSIONS` without a
    group entry reports "ungrouped" rather than failing the whole table."""
    return ACTION_GROUPS.get(action, "ungrouped")


# --- the override file -------------------------------------------------------


def _role_ids() -> list[str]:
    return [r.value for r in Role]


def validate(data: Any) -> dict[str, Any]:
    """Normalise and refuse: unknown action, unknown role, a profile that is
    not an object, or an action with zero holders."""
    if data is None:
        data = {}
    if not isinstance(data, dict):
        raise config.ConfigError("roles overrides must be an object")
    out: dict[str, Any] = {"permissions": {}, "profiles": {}}

    permissions = data.get("permissions") or {}
    if not isinstance(permissions, dict):
        raise config.ConfigError("permissions must be an object keyed by action")
    for action, holders in permissions.items():
        if action not in PERMISSIONS:
            raise config.ConfigError(
                f"unknown action {action!r}; expected one of {', '.join(sorted(PERMISSIONS))}"
            )
        if holders is None:
            continue
        if isinstance(holders, str):
            holders = [holders]
        if not isinstance(holders, list):
            raise config.ConfigError(f"permissions.{action}: expected a list of role ids")
        cleaned: list[str] = []
        for rid in holders:
            try:
                value = Role(str(rid)).value
            except ValueError as exc:
                raise config.ConfigError(
                    f"permissions.{action}: unknown role {rid!r}; expected one of "
                    f"{', '.join(_role_ids())}"
                ) from exc
            if value not in cleaned:
                cleaned.append(value)
        if not cleaned:
            raise config.ConfigError(
                f"permissions.{action}: every action needs at least one holder"
            )
        # Stored in the Role enum's declared order, like `permitted_roles`.
        out["permissions"][action] = [r for r in _role_ids() if r in cleaned]

    profiles = data.get("profiles") or {}
    if not isinstance(profiles, dict):
        raise config.ConfigError("profiles must be an object keyed by role id")
    for rid, prof in profiles.items():
        try:
            value = Role(str(rid)).value
        except ValueError as exc:
            raise config.ConfigError(
                f"profiles: unknown role {rid!r}; expected one of {', '.join(_role_ids())}"
            ) from exc
        if prof is None:
            continue
        if not isinstance(prof, dict):
            raise config.ConfigError(f"profiles.{rid}: expected an object")
        unknown = sorted(set(prof) - set(_PROFILE_KEYS))
        if unknown:
            raise config.ConfigError(
                f"profiles.{rid}: unknown keys {unknown}; allowed: {', '.join(_PROFILE_KEYS)}"
            )
        entry: dict[str, Any] = {}
        for key in ("label", "summary"):
            if key in prof and prof[key] is not None:
                text = str(prof[key]).strip()
                if not text:
                    raise config.ConfigError(f"profiles.{rid}.{key} cannot be empty")
                entry[key] = text
        if "signs" in prof and prof["signs"] is not None:
            signs = prof["signs"]
            if isinstance(signs, str):
                signs = [signs]
            if not isinstance(signs, list):
                raise config.ConfigError(f"profiles.{rid}.signs: expected a list of strings")
            entry["signs"] = [str(s).strip() for s in signs if str(s).strip()]
        if entry:
            out["profiles"][value] = entry
    return out


def load() -> dict[str, Any]:
    return validate(config.read_json(FILE, _EMPTY))


def save(data: Any, *, actor: str = "") -> dict[str, Any]:
    before = load()
    cleaned = validate(data)
    config.write_json(FILE, cleaned)
    config.audit(actor, "roles.save", FILE, before=before, after=cleaned)
    return cleaned


def reset(*, actor: str = "") -> dict[str, Any]:
    """Clear every override — back to the committed tables."""
    before = load()
    config.write_json(FILE, _EMPTY)
    config.audit(actor, "roles.reset", FILE, before=before, after=_EMPTY)
    return dict(_EMPTY)


# --- the effective tables ----------------------------------------------------


def effective_permissions() -> dict[str, set[Role]]:
    """`PERMISSIONS` with each overridden action replaced by its holder set."""
    table = {action: set(holders) for action, holders in PERMISSIONS.items()}
    for action, holders in load()["permissions"].items():
        table[action] = {Role(r) for r in holders}
    return table


def effective_profiles() -> dict[Role, dict[str, Any]]:
    """`ROLE_PROFILES` with the overridden fields replaced per role."""
    table = {role: dict(prof) for role, prof in ROLE_PROFILES.items()}
    for rid, entry in load()["profiles"].items():
        table[Role(rid)] = {**table[Role(rid)], **entry}
    return table


def describe() -> dict[str, Any]:
    """The payload the admin surface renders and the UI sends back on PUT."""
    overrides = load()
    perms = effective_permissions()
    profiles = effective_profiles()
    roles_rows = []
    for role in Role:
        prof = profiles[role]
        roles_rows.append({
            "id": role.value,
            "label": str(prof["label"]),
            "summary": str(prof["summary"]),
            "signs": list(prof["signs"]),
            "actions": sorted(a for a, holders in perms.items() if role in holders),
            "overridden": role.value in overrides["profiles"],
        })
    actions_rows = []
    for action in PERMISSIONS:
        actions_rows.append({
            "action": action,
            "group": group_of(action),
            "roles": [r.value for r in Role if r in perms[action]],
            "default_roles": [r.value for r in Role if r in PERMISSIONS[action]],
            "overridden": action in overrides["permissions"],
        })
    return {"roles": roles_rows, "actions": actions_rows, "overrides": overrides}
