"""The design step the client named ('through design'): DFD + relationship
diagrams as first-class planning artifacts in every mode.

Simulation/demo carry the curated MapleSure diagrams (SIMULATED — scripted
content, labelled). Live/replay derive both diagrams from the run's own
stories and repositories (RULE_BASED — a real derivation, never an AI
claim). No mode makes a model call for design.
"""

import pytest

from s7_delivery.factory import design
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def engine(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def _run_planning(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)
    eng.planning_generate(Role.DELIVERY_LEAD)


def test_curated_diagrams_are_valid_mermaid():
    d = design.curated_diagrams()
    assert d["dfd"]["mermaid"].startswith("flowchart")
    assert d["relationship"]["mermaid"].startswith("erDiagram")
    assert d["dfd"]["notes"]


def test_derived_dfd_names_teams_and_repos():
    stories = [{"story_id": "US-001", "title": "Lookup",
                "accountable_team": "Portal Team",
                "target_repository": "maplesure-sponsor-portal", "estimate": 5}]
    repos = [{"name": "maplesure-sponsor-portal"}]
    d = design.derived_diagrams(stories, repos)
    assert d["dfd"]["mermaid"].startswith("flowchart")
    assert "Portal Team" in d["dfd"]["mermaid"]
    assert "maplesure-sponsor-portal" in d["dfd"]["mermaid"]


def test_derived_relationship_diagram_traces_stories():
    stories = [{"story_id": "US-001", "title": "Lookup",
                "accountable_team": "Portal Team",
                "target_repository": "maplesure-sponsor-portal", "estimate": 5}]
    d = design.derived_diagrams(stories, [{"name": "maplesure-sponsor-portal"}])
    assert d["relationship"]["mermaid"].startswith("erDiagram")
    assert "STORY" in d["relationship"]["mermaid"]


def test_simulated_planning_writes_design_with_diagrams(engine):
    _run_planning(engine)
    d = engine.state()["design"]
    assert d["version"] == 1
    assert d["provenance"] == "simulated"
    assert d["diagrams"]["dfd"]["mermaid"].startswith("flowchart")
    assert d["diagrams"]["relationship"]["mermaid"].startswith("erDiagram")


def test_staleness_flip_survives_diagrams(engine):
    """The staleness demo bumps the design version; the diagrams must not
    break that path."""
    _run_planning(engine)
    engine.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    # The upstream-change trigger reads and rewrites design.json.
    d = engine.store.read_json("planning", "design.json")
    assert "diagrams" in d
