"""Architecture pack: generated after G1, versioned, accepted by a human.

The blueprint is canonical — teams and task packs reference it by version and
never copy it. Revision creates a new immutable version directory and marks
downstream artifacts stale through the provenance chain.
"""

import pytest

from s7_delivery.factory import architecture as arch
from s7_delivery.factory.build_phases import PhaseError
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role, Stage
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture
def eng(tmp_path):
    e = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    e.intake_analyse(Role.PRODUCT_ANALYST)
    e.intake_create_epic(Role.PRODUCT_ANALYST)
    e.intake_pass_gate(Role.BUSINESS_OWNER)
    e.planning_generate(Role.PRODUCT_ANALYST)
    return e


def signed(e: Engine) -> Engine:
    e.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Blake", "approved")
    return e


def test_generate_requires_gate1(eng):
    with pytest.raises(PhaseError, match="pre-G1"):
        eng.architecture_generate(Role.ENGINEERING_LEAD)


def test_generate_writes_versioned_pack_and_meta(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    build = eng.state()["build"]
    meta = build["architecture"]
    assert meta["version"] == 1
    assert meta["status"] == "generated"
    assert meta["provenance"] == "simulated"
    assert build["phase"] == "architecture_ready"
    for name in arch.FILES:
        assert eng.store.exists("architecture", "v1", name), name
    md = eng.store.path("architecture", "v1", "architecture.md").read_text()
    for heading in ("# Application Landscape", "# Repository Mapping",
                    "# Integration Boundaries", "# Security Constraints",
                    "# Technology Standards", "# Operational Considerations"):
        assert heading.lstrip("# ") in md


def test_generate_twice_refused(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    with pytest.raises(EngineError, match="use revise"):
        eng.architecture_generate(Role.ENGINEERING_LEAD)


def test_generate_role_gated(eng):
    signed(eng)
    with pytest.raises(PermissionError_):
        eng.architecture_generate(Role.BUSINESS_OWNER)


def test_accept_is_a_human_checkpoint(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    eng.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    meta = eng.state()["build"]["architecture"]
    assert meta["status"] == "accepted"
    assert meta["accepted_by"] == "Sam Whitfield"
    assert eng.state()["build"]["phase"] == "architecture_accepted"
    with pytest.raises(EngineError, match="already accepted"):
        eng.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")


def test_accept_role_gated_to_engineering_lead(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    with pytest.raises(PermissionError_):
        eng.architecture_accept(Role.DELIVERY_LEAD)


def test_revise_creates_new_version_and_keeps_old(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    eng.architecture_accept(Role.ENGINEERING_LEAD, "Sam Whitfield")
    eng.architecture_revise(Role.ENGINEERING_LEAD, "Split the claims data flows")
    meta = eng.state()["build"]["architecture"]
    assert meta["version"] == 2
    assert meta["status"] == "generated"  # re-acceptance required
    assert meta["accepted_by"] == ""
    # both versions resolvable — immutable version directories
    assert eng.store.exists("architecture", "v1", "architecture.md")
    assert eng.store.exists("architecture", "v2", "architecture.md")
    assert "Split the claims data flows" in eng.store.path(
        "architecture", "v2", "architecture.md"
    ).read_text()
    assert eng.state()["build"]["phase"] == "architecture_ready"


def test_revise_requires_feedback(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    with pytest.raises(EngineError, match="feedback is empty"):
        eng.architecture_revise(Role.ENGINEERING_LEAD, "   ")


def test_provenance_chain_arch_from_plan(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    ledger = eng.store.read_ledger("provenance.jsonl")
    rec = next(r for r in ledger if r["artifact_id"] == "ARCH-001")
    assert rec["inputs"] == ["PLAN-001"]
    assert rec["artifact_type"] == "architecture"


def test_plan_change_marks_architecture_stale_semantics(eng):
    """The staleness walk covers ARCH-001 because its input is PLAN-001."""
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    # simulate an upstream plan re-record (version bump) via the engine's own
    # upstream-change trigger, which bumps design/requirement artifacts and
    # recomputes staleness — architecture must be caught by the same net once
    # its upstream (the plan) changes.
    eng._record(  # a plan amendment lands as a new PLAN-001 version
        artifact_id="PLAN-001", artifact_type="plan", payload={"v": 2},
        author="test", stage=Stage.PLANNING, action="amend",
        outcome="amended", version=2, previous_version=1,
    )
    stale = {s["artifact_id"] for s in eng.store.read_json_or([], "staleness.json")}
    assert "ARCH-001" in stale


def test_pure_renderers_are_deterministic():
    stories = [
        {"story_id": "US-001", "accountable_team": "Portal Team",
         "target_repository": "maplesure-sponsor-portal",
         "target_application": "Sponsor Portal", "target_component": "ClaimForm",
         "dependencies": []},
        {"story_id": "US-002", "accountable_team": "Services Team",
         "target_repository": "maplesure-claims-api",
         "target_application": "Claims API", "target_component": "SubmitEndpoint",
         "dependencies": ["US-001"]},
    ]
    a = arch.render_pack(epic=None, requirement=None, stories=stories,
                         analysis=None, repos=[], version=1)
    b = arch.render_pack(epic=None, requirement=None, stories=stories,
                         analysis=None, repos=[], version=1)
    assert a == b
    dep = a["dependency-map.json"]
    assert dep["edges"] == [{"from": "US-001", "to": "US-002"}]
    assert dep["integration_points"][0]["from_team"] == "Portal Team"
    rmap = a["repository-map.json"]["teams"]
    assert {r["repository"] for r in rmap} == {
        "maplesure-sponsor-portal", "maplesure-claims-api"
    }


# --- meta enrichment: validations, landscape, sizes, hash, plan version ------


def test_meta_carries_validations_landscape_sizes_hash_and_plan_version(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    meta = eng.state()["build"]["architecture"]
    assert meta["plan_version"] == eng.state()["planning"]["plan"]["plan_version"]
    assert len(meta["file_sizes"]) == 5
    assert all(size > 0 for size in meta["file_sizes"].values())
    assert len(meta["validations"]) == 9
    assert meta["content_hash"] and len(meta["content_hash"]) == 64
    assert meta["landscape"]["nodes"]


def test_revision_recomputes_hash_and_validations(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    h1 = eng.state()["build"]["architecture"]["content_hash"]
    eng.architecture_revise(Role.ENGINEERING_LEAD, "tighten integration boundaries")
    meta = eng.state()["build"]["architecture"]
    assert meta["version"] == 2
    assert meta["content_hash"] != h1
    assert len(meta["validations"]) == 9


def test_accept_blocked_while_mandatory_validation_fails(eng):
    signed(eng)
    stories = eng.store.read_json_or([], "planning", "stories.json")
    stories[0]["target_repository"] = ""
    eng.store.write_json(stories, "planning", "stories.json")
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    meta = eng.state()["build"]["architecture"]
    failed = [v for v in meta["validations"] if v["result"] == "failed"]
    assert failed
    with pytest.raises(EngineError, match="mandatory validation"):
        eng.architecture_accept(Role.ENGINEERING_LEAD, "A. Osei")


def test_accept_records_hash_and_still_passes_when_valid(eng):
    signed(eng)
    eng.architecture_generate(Role.ENGINEERING_LEAD)
    eng.architecture_accept(Role.ENGINEERING_LEAD, "A. Osei")
    meta = eng.state()["build"]["architecture"]
    assert meta["status"] == "accepted"
    assert meta["content_hash"] and len(meta["content_hash"]) == 64
