"""Human business rules: storage, permissions, immutability, merge."""

import pytest

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture()
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def run_intake(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)


def test_add_business_rule_assigns_human_ids(eng):
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Claims must be sponsor-scoped.")
    assert rid == "BR-H1"
    rid2 = eng.intake_add_business_rule(Role.PRODUCT_ANALYST, "Uploads are AV-scanned.")
    assert rid2 == "BR-H2"
    rules = eng.state()["intake"]["human_business_rules"]
    assert [r["rule_id"] for r in rules] == ["BR-H1", "BR-H2"]
    assert rules[0]["provenance"] == "human"
    assert rules[0]["added_by"] == Role.BUSINESS_OWNER.value


def test_add_business_rule_rejects_blank(eng):
    with pytest.raises(EngineError, match="empty"):
        eng.intake_add_business_rule(Role.BUSINESS_OWNER, "   ")


def test_add_business_rule_permission(eng):
    with pytest.raises(PermissionError_):
        eng.intake_add_business_rule(Role.INDEPENDENT_REVIEWER, "No.")


def test_edit_and_remove_own_rules(eng):
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Draft text")
    eng.intake_edit_business_rule(Role.BUSINESS_OWNER, rid, "Final text")
    rules = eng.state()["intake"]["human_business_rules"]
    assert rules[0]["text"] == "Final text"
    eng.intake_remove_business_rule(Role.BUSINESS_OWNER, rid)
    assert eng.state()["intake"]["human_business_rules"] == []


def test_ai_rules_are_immutable(eng):
    run_intake(eng)  # seeds analysis with BR-<n> rules
    ai_id = eng.state()["intake"]["analysis"]["business_rules"][0]["rule_id"]
    with pytest.raises(EngineError, match="immutable"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, ai_id, "rewrite")
    with pytest.raises(EngineError, match="immutable"):
        eng.intake_remove_business_rule(Role.BUSINESS_OWNER, ai_id)


def test_unknown_rule_id_refused(eng):
    with pytest.raises(EngineError, match="Unknown"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, "BR-H9", "x")


def test_rules_locked_after_plan_sign_off(eng):
    run_intake(eng)
    eng.planning_generate(Role.DELIVERY_LEAD)
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Pre-sign rule")
    eng.planning_sign_off(Role.BUSINESS_OWNER, approver="business owner")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Too late")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, rid, "Too late")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_remove_business_rule(Role.BUSINESS_OWNER, rid)


def test_human_rules_survive_reanalysis(eng):
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Survives re-analysis")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    rules = eng.state()["intake"]["human_business_rules"]
    assert [r["rule_id"] for r in rules] == ["BR-H1"]


def test_merged_rules_are_ai_then_human(eng):
    run_intake(eng)
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Human rule")
    merged = eng.merged_business_rules()
    ai_count = len(eng.state()["intake"]["analysis"]["business_rules"])
    assert len(merged) == ai_count + 1
    assert merged[-1]["rule_id"] == "BR-H1"


def test_live_planning_receives_merged_rules(eng, monkeypatch):
    """The analysis dict handed to run_plan must carry human rules too."""
    run_intake(eng)
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Human rule for planning")

    seen = {}

    def fake_run_plan(epic, analysis, packs, transcript, teams):
        seen["rule_ids"] = [r["rule_id"] for r in analysis["business_rules"]]
        raise RuntimeError("stop here")

    monkeypatch.setattr(
        "s7_delivery.factory.live_intake.run_plan", fake_run_plan
    )
    # Force the live branch without a real repo/context pack.
    monkeypatch.setattr(
        type(eng), "_context_packs", lambda self: {"fake-repo": "# pack"},
        raising=True,
    )
    run = eng.run()
    run.mode = DemoMode.LIVE
    monkeypatch.setattr(type(eng), "run", lambda self: run, raising=True)

    with pytest.raises(RuntimeError, match="stop here"):
        eng.planning_generate(Role.DELIVERY_LEAD)
    assert "BR-H1" in seen["rule_ids"]
