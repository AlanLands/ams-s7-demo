"""Rule-based (non-LLM) requirement extraction. Pure functions, offline."""

from pathlib import Path

import pytest

from s7_delivery.factory import extraction

EPIC_S7_001 = (Path(__file__).resolve().parent.parent / "crs" / "EPIC-S7-001.md").read_text()

PLAIN_TEXT = """Claims Deductible Handling

Apply policy deductible during claim intake to ensure valid claim processing
and accurate payable amount calculation.

Add a per-policy deductible and apply it during claim intake.

- Policy record must contain a deductible amount.
- Reject claim if claim amount is at or below the policy deductible.
- For accepted claims, calculate payable amount = claim amount - deductible
  and store it.
"""

NO_STRUCTURE_TEXT = "Sponsors need a way to submit claims online without calling support."


def test_extract_from_epic_s7_001_finds_real_title_and_objective():
    result = extraction.extract_requirement(EPIC_S7_001)
    assert result["epic_title"] == "Online disability claim submission for plan sponsors"
    assert "guided online way" in result["business_objective"]
    assert result["requirement_summary"]
    assert len(result["extracted_requirements"]) >= 1
    assert all(r["rule_id"].startswith("REQ-") for r in result["extracted_requirements"])


def test_extract_caps_at_twelve_and_dedupes():
    result = extraction.extract_requirement(EPIC_S7_001)
    assert len(result["extracted_requirements"]) <= 12
    texts = [r["text"] for r in result["extracted_requirements"]]
    assert len(texts) == len(set(texts))


def test_extract_from_plain_text_with_bullets():
    result = extraction.extract_requirement(PLAIN_TEXT)
    assert result["epic_title"] == "Claims Deductible Handling"
    assert "deductible" in result["business_objective"].lower()
    assert len(result["extracted_requirements"]) == 3
    assert result["extracted_requirements"][0]["rule_id"] == "REQ-01"
    assert "deductible amount" in result["extracted_requirements"][0]["text"]


def test_extract_wraps_multiline_bullets_into_one_item():
    result = extraction.extract_requirement(PLAIN_TEXT)
    payable = [r for r in result["extracted_requirements"] if "payable amount" in r["text"]][0]
    assert "and store it" in payable["text"]


def test_extract_falls_back_to_first_line_title_and_trigger_sentences():
    result = extraction.extract_requirement(NO_STRUCTURE_TEXT)
    assert result["epic_title"] == NO_STRUCTURE_TEXT
    assert result["extracted_requirements"]


def test_extract_never_returns_silently_empty_requirements():
    result = extraction.extract_requirement("A short requirement with no lists or trigger words at all here.")
    assert len(result["extracted_requirements"]) == 1
    assert "No discrete requirements detected" in result["extracted_requirements"][0]["text"]


def test_extract_rejects_empty_text():
    with pytest.raises(extraction.ExtractionError, match="empty"):
        extraction.extract_requirement("   ")
