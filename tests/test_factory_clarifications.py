"""Analysis raises its own clarification round — no separate ask step.

The moment intake analysis completes, its open questions become the pending
clarification round for the Business Owner to answer (surfaced by the UI as
an auto-opening popup). Only the first round seeds this way; re-running the
analysis never re-opens questions already asked or answered.
"""

import pytest

from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture()
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def test_analysis_opens_the_clarification_round(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    analysis = eng.state()["intake"]["analysis"]
    assert clar["pending"] == analysis["clarification_questions"]
    assert clar["rounds_used"] == 1
    assert clar["provenance"] == analysis["provenance"]


def test_regenerating_analysis_never_reopens_the_round(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    n = len(eng.state()["intake"]["clarifications"]["pending"])
    eng.intake_clarify_answer(Role.BUSINESS_OWNER, ["answer"] * n)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == []
    assert clar["rounds_used"] == 1


def test_business_owner_answers_qa_lead_does_not(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    n = len(eng.state()["intake"]["clarifications"]["pending"])
    with pytest.raises(PermissionError_):
        eng.intake_clarify_answer(Role.QA_LEAD, ["answer"] * n)
    eng.intake_clarify_answer(Role.BUSINESS_OWNER, ["answer"] * n)
    transcript = eng.state()["intake"]["clarifications"]["transcript"]
    assert transcript[-1]["role"] == "user"
