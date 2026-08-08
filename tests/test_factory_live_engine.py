"""Live-mode engine behaviour. All offline; LLM and git are local/fake."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import PORTAL_FILES, write_repo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


def fixture_repo(tmp_path: Path, name: str = "maplesure-sponsor-portal") -> Path:
    repo = write_repo(name, PORTAL_FILES, tmp_path / "src")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), *ident, "commit", "-qm", "init"], check=True)
    return repo


def test_connect_repo_records_and_builds_pack(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    state = eng.state()
    repos = state["intake"]["repos"]
    assert [r["name"] for r in repos] == ["maplesure-sponsor-portal"]
    assert repos[0]["provenance"] == "human"
    assert eng.store.exists("intake", "context", "maplesure-sponsor-portal.md")
    # Provenance ledger carries the connect event.
    assert any(r["artifact_type"] == "repository" for r in state["provenance_ledger"])


def test_connect_repo_bad_url_is_engine_error(tmp_path: Path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="clone"):
        eng.intake_connect_repo(Role.DELIVERY_LEAD, str(tmp_path / "nope"))
    assert eng.state()["intake"]["repos"] == []


# --- live analysis tests -------------------------------------------------------


from common.llm import LLMError
from s7_delivery.factory import live_intake
from s7_delivery.factory.models import IntakeAnalysis, Provenance


def _fake_analysis() -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True,
        business_impact="impact",
        affected_applications=["maplesure-sponsor-portal"],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=["q1"], assumptions=["a1"],
        business_rules=[{"rule_id": "BR-01", "text": "rule"}],
        risk_register=[{"text": "r", "severity": "high"}],
        confidence=80, provenance=Provenance.LIVE_AI,
    )


def _live_engine_with_repo(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = fixture_repo(tmp_path)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    return eng


def test_live_analyse_calls_model_and_badges(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(), {"input_tokens": 10, "output_tokens": 5}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    analysis = eng.state()["intake"]["analysis"]
    assert analysis["provenance"] == "live_ai"
    events = eng.state()["activity"]
    assert any(e["actor_type"] == "live_ai" and e["workflow"] == "intake-analysis"
               for e in events)


def test_live_analyse_without_repos_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Cc]onnect"):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None


def test_live_analyse_llm_failure_leaves_state_unchanged(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    def boom(req, packs, transcript):
        raise LLMError("model returned garbage")
    monkeypatch.setattr(live_intake, "run_analysis", boom)
    with pytest.raises(LLMError):
        eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"] is None  # no silent fallback


def test_simulation_mode_never_touches_live(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    def forbidden(*a, **kw):
        raise AssertionError("live path called in simulation mode")
    monkeypatch.setattr(live_intake, "run_analysis", forbidden)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    assert eng.state()["intake"]["analysis"]["provenance"] == "simulated"


# --- clarification tests -------------------------------------------------------


def test_clarify_roundtrip(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "run_clarification",
        lambda req, packs, transcript: (["Which attachments are mandatory?"], {}),
    )
    eng.intake_clarify(Role.PRODUCT_ANALYST)
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == ["Which attachments are mandatory?"]
    assert clar["rounds_used"] == 1

    eng.intake_clarify_answer(Role.PRODUCT_ANALYST, ["Employer statement only."])
    clar = eng.state()["intake"]["clarifications"]
    assert clar["pending"] == []
    assert clar["transcript"][-1]["role"] == "user"
    assert "Employer statement" in clar["transcript"][-1]["text"]


def test_clarify_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_clarify(Role.PRODUCT_ANALYST)
