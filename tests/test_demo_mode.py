"""Demo mode — the fourth environment (spec 2026-08-10-demo-mode).

Demo behaves as simulation everywhere except: epic creation always presents
the seeded MapleSure epic, even when an upload has produced an extraction
record (the story-source decision), and the Sync surface runs the scripted
storyline (covered in test_demo_sync.py).
"""

from __future__ import annotations

from s7_delivery.factory import seed
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role

_EXTRACTION = {
    "epic_title": "Uploaded title",
    "business_objective": "x",
    "requirement_summary": "y",
    "extracted_requirements": ["a", "b"],
    "method": "rule_based",
    "provenance": "rule_based",
}


def test_demo_mode_exists_and_creates_run(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    assert eng.run().mode is DemoMode.DEMO


def test_demo_epic_ignores_extraction(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.store.write_json(_EXTRACTION, "intake", "extraction.json")
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    epic = eng.store.read_json("intake", "epic.json")
    assert epic["title"] == seed.EPIC.title


def test_simulation_epic_still_uses_extraction(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.store.write_json(_EXTRACTION, "intake", "extraction.json")
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    assert eng.store.read_json("intake", "epic.json")["title"] == "Uploaded title"


def test_demo_run_seeds_repo_grounding(tmp_path):
    """Demo intake shows connected-repo details and a routable verdict with
    no network and no clone (user request 2026-08-10: 'show repo details in
    the intake itself')."""
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    state = eng.state()
    repos = state["intake"]["repos"]
    assert {r["name"] for r in repos} == {
        "sponsorconnect-portal", "sponsorconnect-api", "sponsorconnect-db",
        "sponsorconnect-tests", "sponsorconnect-platform",
    }
    assert all(r["provenance"] == "simulated" for r in repos)
    # Honesty gate: never a github.com URL, so the UI cannot render a dead link
    assert all("github.com" not in r["url"] for r in repos)
    assert state["intake"]["routing"]["verdict"] == "routable"


def test_simulation_run_has_no_seeded_repos(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    assert eng.state()["intake"]["repos"] == []
    assert eng.state()["intake"]["routing"] is None


def test_demo_analysis_raises_clarification_questions(tmp_path):
    """The analysis's own questions become the pending round in demo mode —
    the auto-opening popup has content to show."""
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == seed.ANALYSIS.clarification_questions
    assert clar["rounds_used"] == 1
