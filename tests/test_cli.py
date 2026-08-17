"""The CLI surface: where an agent executes, and what makes the run ledger
assertable in pytest (the standing reason the docs give for a CLI).

Text output over the same engine the app uses — nothing rendered here that
the ledger does not hold.
"""

import pytest

from s7_delivery import cli
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def planned(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    return eng, tmp_path


def test_runs_lists_run_ids(planned, capsys):
    eng, root = planned
    assert cli.main(["runs", "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert eng.run_id in out
    assert "simulation" in out


def test_state_shows_stages_and_gates(planned, capsys):
    eng, root = planned
    assert cli.main(["state", eng.run_id, "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "planning" in out
    assert "G1" in out
    assert "passed" in out


def test_ledger_is_assertable_text(planned, capsys):
    eng, root = planned
    assert cli.main(["ledger", eng.run_id, "--root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "ai_workflows" in out
    assert "simulated_workflows" in out
    assert "velocity" in out
    assert "not evidenced" in out  # unevidenced KPIs say so, even here


def test_downstream_drives_a_story_to_review(planned, capsys):
    eng, root = planned
    assert cli.main([
        "downstream", eng.run_id, "--story", "US-001", "--root", str(root),
    ]) == 0
    out = capsys.readouterr().out
    assert "US-001" in out
    assert "review" in out.lower()
    reviews = eng.state()["build"]["reviews"]
    assert any(r["result"] == "passed" for r in reviews)


def test_downstream_blocked_review_reports_and_fails(planned, capsys):
    """The bounded-loop discipline: a blocked review is reported with its
    findings and a nonzero exit — never quietly presented as success."""
    eng, root = planned
    rc = cli.main(["downstream", eng.run_id, "--root", str(root)])
    out = capsys.readouterr().out
    assert rc == 1
    assert "blocked" in out.lower()
    assert "FND-001" in out  # US-003's deliberate boundary defect
