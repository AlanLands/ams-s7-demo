"""Role and permission overrides: the effective tables the engine consults."""

from __future__ import annotations

import pytest

from s7_delivery.factory import roles
from s7_delivery.factory.models import Role
from s7_delivery.factory.roles import PERMISSIONS, ROLE_PROFILES, PermissionError_
from s7_delivery.product import config, roles_config


@pytest.fixture(autouse=True)
def _cfg(tmp_path, monkeypatch):
    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path / "config"))


def test_every_action_has_a_group():
    assert set(PERMISSIONS) == set(roles_config.ACTION_GROUPS), (
        "an action was added to PERMISSIONS without a group in ACTION_GROUPS"
    )
    assert set(roles_config.ACTION_GROUPS.values()) <= set(roles_config.GROUPS)
    assert {a["group"] for a in roles_config.describe()["actions"]} == set(roles_config.GROUPS)


def test_defaults_are_the_committed_tables():
    assert roles_config.load() == {"permissions": {}, "profiles": {}}
    assert roles_config.effective_permissions() == PERMISSIONS
    assert roles_config.effective_profiles() == ROLE_PROFILES
    d = roles_config.describe()
    assert d["overrides"] == {"permissions": {}, "profiles": {}}
    assert all(not r["overridden"] for r in d["roles"])
    assert all(not a["overridden"] for a in d["actions"])
    deploy = next(a for a in d["actions"] if a["action"] == "deploy")
    assert deploy == {"action": "deploy", "group": "release", "roles": ["release_manager"],
                      "default_roles": ["release_manager"], "overridden": False}


def test_validate_refuses_unknown_action_and_role_and_zero_holders():
    with pytest.raises(config.ConfigError, match="unknown action"):
        roles_config.validate({"permissions": {"teleport": ["delivery_lead"]}})
    with pytest.raises(config.ConfigError, match="unknown role"):
        roles_config.validate({"permissions": {"deploy": ["wizard"]}})
    with pytest.raises(config.ConfigError, match="every action needs at least one holder"):
        roles_config.validate({"permissions": {"deploy": []}})
    with pytest.raises(config.ConfigError, match="unknown role"):
        roles_config.validate({"profiles": {"wizard": {"label": "W"}}})
    with pytest.raises(config.ConfigError, match="unknown keys"):
        roles_config.validate({"profiles": {"qa_lead": {"colour": "red"}}})


def test_permission_override_is_a_complete_replacement_and_the_engine_honours_it():
    # Before: only the Release Manager deploys.
    with pytest.raises(PermissionError_):
        roles.require("deploy", Role.ENGINEERING_LEAD)
    roles_config.save({"permissions": {"deploy": ["engineering_lead"]}}, actor="ops")
    # After: the given list *is* the holder set — the old holder is gone.
    roles.require("deploy", Role.ENGINEERING_LEAD)
    with pytest.raises(PermissionError_) as exc:
        roles.require("deploy", Role.RELEASE_MANAGER)
    assert exc.value.permitted == (Role.ENGINEERING_LEAD,)
    assert roles.allowed("deploy", Role.ENGINEERING_LEAD)
    assert not roles.allowed("deploy", Role.RELEASE_MANAGER)
    assert roles.permitted_roles("deploy") == (Role.ENGINEERING_LEAD,)
    assert "deploy" in roles.actions_for(Role.ENGINEERING_LEAD)
    assert "deploy" not in roles.actions_for(Role.RELEASE_MANAGER)
    # The committed default is untouched.
    assert PERMISSIONS["deploy"] == {Role.RELEASE_MANAGER}
    d = roles_config.describe()
    deploy = next(a for a in d["actions"] if a["action"] == "deploy")
    assert deploy["roles"] == ["engineering_lead"]
    assert deploy["default_roles"] == ["release_manager"]
    assert deploy["overridden"] is True
    # Every other action is exactly as committed.
    assert all(not a["overridden"] for a in d["actions"] if a["action"] != "deploy")


def test_zero_holder_override_is_refused_and_nothing_is_saved():
    with pytest.raises(config.ConfigError, match="at least one holder"):
        roles_config.save({"permissions": {"sign_off_plan": []}}, actor="ops")
    assert roles_config.load() == {"permissions": {}, "profiles": {}}
    roles.require("sign_off_plan", Role.BUSINESS_OWNER)
    assert config.audit_log(action="roles.save") == []


def test_profile_override_reaches_role_label_and_profile():
    roles_config.save(
        {"profiles": {"qa_lead": {"label": "Quality Lead", "signs": ["G3 quality gate"]}}},
        actor="ops",
    )
    assert roles.role_label(Role.QA_LEAD) == "Quality Lead"
    prof = roles.profile("qa_lead")
    assert prof["label"] == "Quality Lead"
    assert prof["signs"] == ["G3 quality gate"]
    assert prof["summary"] == ROLE_PROFILES[Role.QA_LEAD]["summary"]  # untouched field
    assert roles.profiles()[Role.QA_LEAD]["label"] == "Quality Lead"
    assert ROLE_PROFILES[Role.QA_LEAD]["label"] == "QA Lead"
    row = next(r for r in roles_config.describe()["roles"] if r["id"] == "qa_lead")
    assert row["overridden"] is True and row["label"] == "Quality Lead"
    assert "decide_quality_gate" in row["actions"]


def test_reset_clears_overrides_and_both_actions_are_audited():
    roles_config.save({"permissions": {"deploy": ["engineering_lead", "release_manager"]}},
                      actor="ops")
    assert roles.permitted_roles("deploy") == (Role.ENGINEERING_LEAD, Role.RELEASE_MANAGER)
    roles_config.reset(actor="ops")
    assert roles.permitted_roles("deploy") == (Role.RELEASE_MANAGER,)
    assert roles_config.load() == {"permissions": {}, "profiles": {}}
    actions = [r["action"] for r in config.audit_log()]
    assert actions == ["roles.reset", "roles.save"]
    assert all(r["actor"] == "ops" for r in config.audit_log())


def test_holders_are_stored_in_enum_order_and_deduplicated():
    saved = roles_config.save(
        {"permissions": {"deploy": ["support_lead", "business_owner", "support_lead"]}},
        actor="ops",
    )
    assert saved["permissions"]["deploy"] == ["business_owner", "support_lead"]
