"""intake_set_source / intake_extract — the upload/paste front door."""

import pytest

from s7_delivery.factory import seed
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role

SOURCE_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
"""


@pytest.fixture()
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def test_set_source_updates_requirement(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    req = eng.state()["intake"]["requirement"]
    assert req["description"] == SOURCE_TEXT
    assert req["source_type"] == "Uploaded document"
    assert req["source_documents"] == ["epic.md"]


def test_set_source_paste_uses_placeholder_source_document(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, source_kind="paste")
    req = eng.state()["intake"]["requirement"]
    assert req["source_type"] == "Pasted text"
    assert req["source_documents"] == ["pasted-text"]


def test_set_source_rejects_empty_text(eng):
    with pytest.raises(EngineError, match="empty"):
        eng.intake_set_source(Role.PRODUCT_ANALYST, "   ")


def test_set_source_rejects_oversized_text(eng):
    with pytest.raises(EngineError, match="20,000"):
        eng.intake_set_source(Role.PRODUCT_ANALYST, "x" * 20_001)


def test_set_source_rejects_oversized_text_with_trailing_whitespace(eng):
    # 20,000 non-whitespace chars + 200 trailing spaces: stripped length is
    # exactly at the cap (20,000), but the raw stored/used text is 20,200 —
    # over the cap. The check must reject based on the raw text, since that
    # is what is stored in requirement.description / source.json and later
    # fed to the parser/LLM by intake_extract, not the stripped copy.
    text = ("a" * 20_000) + (" " * 200)
    with pytest.raises(EngineError, match="20,000"):
        eng.intake_set_source(Role.PRODUCT_ANALYST, text)


def test_set_source_persists_raw_upload_bytes(eng, tmp_path):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md",
                           source_kind="upload", raw_content=SOURCE_TEXT.encode())
    assert eng.store.exists("intake", "documents", "epic.md")


def test_extract_requires_source_first(eng):
    with pytest.raises(EngineError, match="Provide a source"):
        eng.intake_extract(Role.PRODUCT_ANALYST)


def test_extract_produces_rule_based_extraction_in_simulation(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    state = eng.state()
    ext = state["intake"]["extraction"]
    assert ext["method"] == "rule_based"
    assert ext["provenance"] == "rule_based"
    assert ext["epic_title"] == "Claims Deductible Handling"
    assert len(ext["extracted_requirements"]) == 2


def test_extract_patches_requirement_title(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["requirement"]["title"] == "Claims Deductible Handling"


def test_extract_records_provenance_and_activity(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    state = eng.state()
    assert any(r["artifact_id"] == "EXT-001" for r in state["provenance_ledger"])
    assert any(a["workflow"] == "intake-extraction" for a in state["activity"])


def test_state_exposes_source_and_extraction_as_none_by_default(eng):
    intake = eng.state()["intake"]
    assert intake["source"] is None
    assert intake["extraction"] is None


def _seeded_epic_only(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    return eng.state()["intake"]["epic"]


def test_create_epic_without_extraction_matches_seed_exactly(eng):
    """The regression test that protects the rehearsed demo path: a run
    where nobody ever uploads or pastes anything must keep producing the
    exact seeded epic, unchanged."""
    epic = _seeded_epic_only(eng)
    assert epic["epic_id"] == "EPIC-S7-001"
    assert epic["title"] == seed.EPIC.title
    assert epic["business_outcome"] == seed.EPIC.business_outcome
    assert epic["estimated_stories"] == seed.EPIC.estimated_stories


def test_create_epic_still_requires_analysis_first(eng):
    """test_epic_requires_analysis in test_factory_planning.py already
    covers this for the untouched path; this re-confirms it here too so a
    future edit to this file can't silently regress it."""
    with pytest.raises(EngineError):
        eng.intake_create_epic(Role.PRODUCT_ANALYST)


def test_create_epic_from_extraction_uses_extracted_content(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    epic = eng.state()["intake"]["epic"]
    assert epic["epic_id"] != "EPIC-S7-001"
    assert epic["epic_id"] == f"EPIC-{eng.run_id}"
    assert epic["title"] == "Claims Deductible Handling"
    assert epic["provenance"] == "rule_based"


def test_edit_extraction_updates_fields_and_stamps_editor(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"epic_title": "Corrected Title"})
    ext = eng.state()["intake"]["extraction"]
    assert ext["epic_title"] == "Corrected Title"
    assert ext["edited_by"] == "business_owner"
    assert ext["edited_at"]


def test_edit_extraction_rejects_unknown_fields(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="not editable"):
        eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"method": "live_llm"})


def test_edit_extraction_requires_extraction_first(eng):
    with pytest.raises(EngineError, match="No extraction"):
        eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"epic_title": "x"})


def test_edit_extraction_rejects_malformed_requirements_as_engine_error(eng):
    """A pydantic ValidationError (extracted_requirements must be a list of
    {rule_id, text} dicts, not plain strings) must surface as EngineError,
    not escape as a raw pydantic exception (final review finding 2)."""
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="Invalid extraction patch"):
        eng.intake_edit_extraction(
            Role.BUSINESS_OWNER, {"extracted_requirements": ["just a string"]}
        )


def test_edit_extraction_rejects_blank_title(eng):
    """A blank epic_title is valid `str` for pydantic and would otherwise be
    silently accepted (final review finding 2) — reject it explicitly."""
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    with pytest.raises(EngineError, match="blank"):
        eng.intake_edit_extraction(Role.BUSINESS_OWNER, {"epic_title": ""})


def test_finalize_runs_analysis_when_missing_then_creates_epic(eng):
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_finalize(Role.PRODUCT_ANALYST)
    state = eng.state()
    assert state["intake"]["analysis"] is not None
    assert state["intake"]["epic"]["title"] == "Claims Deductible Handling"


def test_finalize_does_not_rerun_existing_analysis(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    first_generated_at = eng.state()["intake"]["analysis"]["generated_at"]
    eng.intake_set_source(Role.PRODUCT_ANALYST, SOURCE_TEXT, filename="epic.md", source_kind="upload")
    eng.intake_extract(Role.PRODUCT_ANALYST)
    eng.intake_finalize(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"]["generated_at"] == first_generated_at
