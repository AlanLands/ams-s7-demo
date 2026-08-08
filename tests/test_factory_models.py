"""New model additions for intake extraction."""

from s7_delivery.factory.models import Provenance, RequirementExtraction


def test_rule_based_provenance_value():
    assert Provenance.RULE_BASED.value == "rule_based"


def test_requirement_extraction_defaults():
    rec = RequirementExtraction(
        epic_title="Claims Deductible Handling",
        business_objective="Apply policy deductible during claim intake.",
        requirement_summary="Add a per-policy deductible and apply it during intake.",
        extracted_requirements=[{"rule_id": "REQ-01", "text": "Reject claims at or below the deductible."}],
        method="rule_based",
        provenance=Provenance.RULE_BASED,
    )
    assert rec.edited_by is None
    assert rec.edited_at is None
    assert rec.generated_at  # auto-stamped
