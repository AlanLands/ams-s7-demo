"""Editable architecture and test plans: leads propose, the system refines.

The invariants under test are the guardrails, not the editing itself:
- the proposal is recorded verbatim and the refinement is honestly badged
  (RULE_BASED in simulation — never presented as AI),
- an edit always resets the human checkpoint it feeds (architecture
  acceptance, QA test-plan approval),
- the AC-derived test names never move — QA cases append under governed
  `test_qa_*` names, so CI evidence keeps joining per AC,
- regeneration preserves a stored amendment instead of dropping QA's work.
"""

import pytest

from common.llm import LLMError
from s7_delivery.factory import refine, test_skeletons
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Provenance, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
    e.planning_generate(Role.PRODUCT_ANALYST)
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    e.architecture_generate(Role.ENGINEERING_LEAD)
    return e


def packs_ready(e: Engine) -> Engine:
    e.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    e.delivery_packs_generate(Role.ENGINEERING_LEAD)
    return e


# --- refine module -----------------------------------------------------------


def test_simulation_architecture_refinement_is_rule_based_and_verbatim():
    refined, prov = refine.refine_architecture_proposal(
        "Split the intake service. Add a queue between intake and indexing.",
        "# Architecture\n", DemoMode.SIMULATION,
    )
    assert prov is Provenance.RULE_BASED
    assert "Split the intake service" in refined  # verbatim proposal kept
    assert "rule-based" in refined.lower()
    assert "no AI" in refined  # honesty label, § Staged output


def test_simulation_test_refinement_yields_one_case_per_sentence():
    cases, prov = refine.refine_test_amendment(
        "Verify lockout resets after 15 minutes. Verify audit entry is masked.",
        {"story_id": "US-1"}, DemoMode.SIMULATION,
    )
    assert prov is Provenance.RULE_BASED
    assert [c["case_id"] for c in cases] == ["QA-1", "QA-2"]
    assert "lockout resets" in cases[0]["description"]


def test_empty_amendment_is_an_error():
    with pytest.raises(LLMError):
        refine.refine_test_amendment("   ", {"story_id": "US-1"}, DemoMode.SIMULATION)


def test_qa_names_are_governed_and_never_displace_base_names():
    story = {
        "story_id": "US-9",
        "provenance": "human",
        "acceptance_criteria": [{"ac_id": "AC-1", "text": "sponsor can submit"}],
    }
    amendment = {"cases": [{"case_id": "QA-1", "description": "sponsor can submit"}]}
    files, manifest = test_skeletons.render_story_tests(story, "pytest", amendment)
    body = next(iter(files.values()))
    base = manifest["tests"][0]["test_name"]
    qa = manifest["qa_tests"][0]["test_name"]
    assert base == "test_sponsor_can_submit"  # AC name unchanged
    assert qa.startswith("test_qa_1_") and qa != base
    assert f"def {base}(" in body and f"def {qa}(" in body


# --- architecture: propose → refine → new version → acceptance resets --------


def test_architecture_revision_embeds_refined_proposal(eng):
    eng.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    eng.architecture_revise(Role.ENGINEERING_LEAD, "Introduce an event bus")
    meta = eng.state()["build"]["architecture"]
    assert meta["version"] == 2
    assert meta["status"] == "generated"  # acceptance reset — must re-accept
    assert meta["revision_proposal"] == "Introduce an event bus"
    assert meta["refinement_provenance"] == "rule_based"
    assert "Introduce an event bus" in meta["revision_refined"]
    md = eng.store.path("architecture", "v2", "architecture.md").read_text()
    assert "## Revision v2 — Proposed Change" in md
    assert "Introduce an event bus" in md


# --- test plan: QA amendment overlay ----------------------------------------


def _first_pack(e: Engine) -> dict:
    return e.state()["build"]["delivery_packs"][0]


def test_qa_amendment_appends_cases_and_resets_approval(eng):
    packs_ready(eng)
    pack = _first_pack(eng)
    eng.test_plan_approve(Role.QA_LEAD, pack["delivery_pack_id"], "Riley Chen")
    story_id = pack["story_ids"][0]
    eng.test_plan_amend(
        Role.QA_LEAD, pack["delivery_pack_id"], story_id,
        "Verify duplicate submissions are rejected.",
    )
    fresh = _first_pack(eng)
    assert fresh["version"] == pack["version"] + 1
    assert fresh["test_plan_status"] != "approved"  # own edit re-enters the gate
    manifest = eng.store.read_json("build", "tests", story_id, "test-manifest.json")
    assert manifest["qa_tests"][0]["test_name"].startswith("test_qa_1_")
    assert manifest["qa_amendment"]["proposal"].startswith("Verify duplicate")
    assert manifest["qa_amendment"]["provenance"] == "rule_based"
    # base per-AC join untouched — no QA case leaks into the AC list
    assert all(not t["ac_id"].startswith("QA-") for t in manifest["tests"])
    story = next(
        s for s in eng.state()["planning"]["stories"] if s["story_id"] == story_id
    )
    assert len(manifest["tests"]) == len(story["acceptance_criteria"])


def test_amendment_survives_pack_regeneration(eng):
    packs_ready(eng)
    pack = _first_pack(eng)
    story_id = pack["story_ids"][0]
    eng.test_plan_amend(
        Role.QA_LEAD, pack["delivery_pack_id"], story_id, "Verify masked logging."
    )
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    manifest = eng.store.read_json("build", "tests", story_id, "test-manifest.json")
    assert manifest["qa_tests"], "regeneration dropped the QA amendment"


def test_amendment_is_qa_lead_only(eng):
    packs_ready(eng)
    pack = _first_pack(eng)
    with pytest.raises(PermissionError_):
        eng.test_plan_amend(
            Role.ENGINEERING_LEAD, pack["delivery_pack_id"],
            pack["story_ids"][0], "Verify something.",
        )


def test_amendment_rejects_foreign_story(eng):
    packs_ready(eng)
    packs = eng.state()["build"]["delivery_packs"]
    if len(packs) < 2:
        pytest.skip("scenario yields a single team pack")
    with pytest.raises(EngineError, match="not part of"):
        eng.test_plan_amend(
            Role.QA_LEAD, packs[0]["delivery_pack_id"],
            packs[1]["story_ids"][0], "Verify something.",
        )
