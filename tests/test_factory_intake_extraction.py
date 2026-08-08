"""intake_set_source / intake_extract — the upload/paste front door."""

import pytest

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
