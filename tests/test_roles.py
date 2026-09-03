"""Role profiles and the structured permission error."""

import pytest

from s7_delivery.factory.models import Role
from s7_delivery.factory.roles import (
    PERMISSIONS,
    ROLE_PROFILES,
    PermissionError_,
    permitted_roles,
    require,
    role_label,
)


def test_every_role_has_a_profile():
    assert set(ROLE_PROFILES) == set(Role)
    for profile in ROLE_PROFILES.values():
        assert profile["label"] and profile["summary"]
        assert isinstance(profile["signs"], list)


def test_role_label_falls_back_to_humanised_id():
    assert role_label(Role.QA_LEAD) == "QA Lead"
    assert role_label("business_owner") == "Business Owner"
    assert role_label("someone_new") == "Someone New"


def test_permitted_roles_follow_enum_order():
    assert permitted_roles("sign_off_plan") == (Role.BUSINESS_OWNER,)
    assert permitted_roles("approve_release") == (
        Role.BUSINESS_OWNER, Role.ENGINEERING_LEAD, Role.QA_LEAD,
        Role.RELEASE_MANAGER, Role.SUPPORT_LEAD)
    assert permitted_roles("no_such_action") == ()


def test_require_carries_structured_facts():
    with pytest.raises(PermissionError_) as exc:
        require("deploy", Role.ENGINEERING_LEAD)
    err = exc.value
    assert err.action == "deploy"
    assert err.role is Role.ENGINEERING_LEAD
    assert err.permitted == (Role.RELEASE_MANAGER,)
    assert "release_manager" in str(err)


def test_unknown_action_has_no_permitted_roles():
    with pytest.raises(PermissionError_) as exc:
        require("teleport", Role.DELIVERY_LEAD)
    assert exc.value.action == "teleport"
    assert exc.value.permitted == ()


def test_separation_rules_still_hold():
    """The profiles describe the table; they must not drift from it."""
    assert PERMISSIONS["sign_off_plan"] == {Role.BUSINESS_OWNER}
    assert PERMISSIONS["deploy"] == {Role.RELEASE_MANAGER}
    assert PERMISSIONS["approve_review"] == {Role.INDEPENDENT_REVIEWER}
    assert PERMISSIONS["accept_architecture"] == {Role.ENGINEERING_LEAD}
    assert PERMISSIONS["decide_quality_gate"] == {Role.QA_LEAD}


# --- the effective tables (product overrides, added 2026-09-03) --------------


def test_require_honours_a_saved_override_without_restart(tmp_path, monkeypatch):
    """`config/roles.json` is consulted on every call: a saved override
    applies to the next `require`, and the committed table is untouched."""
    from s7_delivery.factory import roles
    from s7_delivery.product import roles_config

    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path))
    with pytest.raises(PermissionError_):
        require("sign_off_plan", Role.DELIVERY_LEAD)
    roles_config.save({"permissions": {"sign_off_plan": ["delivery_lead"]}}, actor="t")
    require("sign_off_plan", Role.DELIVERY_LEAD)
    with pytest.raises(PermissionError_) as exc:
        require("sign_off_plan", Role.BUSINESS_OWNER)
    assert exc.value.permitted == (Role.DELIVERY_LEAD,)
    assert permitted_roles("sign_off_plan") == (Role.DELIVERY_LEAD,)
    assert roles.allowed("sign_off_plan", Role.DELIVERY_LEAD)
    assert PERMISSIONS["sign_off_plan"] == {Role.BUSINESS_OWNER}
    roles_config.reset(actor="t")
    require("sign_off_plan", Role.BUSINESS_OWNER)


def test_zero_holder_override_is_refused(tmp_path, monkeypatch):
    from s7_delivery.product import config, roles_config

    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path))
    with pytest.raises(config.ConfigError, match="at least one holder"):
        roles_config.save({"permissions": {"deploy": []}}, actor="t")
    require("deploy", Role.RELEASE_MANAGER)


def test_role_label_reads_the_effective_profile(tmp_path, monkeypatch):
    from s7_delivery.factory import roles
    from s7_delivery.product import roles_config

    monkeypatch.setenv("S7_CONFIG_DIR", str(tmp_path))
    roles_config.save({"profiles": {"support_lead": {"label": "Ops Lead"}}}, actor="t")
    assert role_label(Role.SUPPORT_LEAD) == "Ops Lead"
    assert roles.profile(Role.SUPPORT_LEAD)["label"] == "Ops Lead"
    assert ROLE_PROFILES[Role.SUPPORT_LEAD]["label"] == "Support Lead"
