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
