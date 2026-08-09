"""CI bootstrap fires when a repo is connected or created, and never fails
the connect/create action even when the bootstrap push itself fails.
"""
import subprocess

import pytest

from s7_delivery.factory import scaffold as scaffold_mod
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


def _bare_remote_with_maven_seed(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "pom.xml").write_text("<project/>")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "init")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    return remote


def test_connect_repo_bootstraps_detected_maven_stack(tmp_path):
    remote = _bare_remote_with_maven_seed(tmp_path)
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(remote))
    repos = eng.state()["intake"]["repos"]
    assert repos[0]["ci_bootstrap_status"] == "bootstrapped:maven"
    # store.path() rejects dot-prefixed segments (path-traversal guard), and
    # ci_bootstrap writes .github/ via plain pathlib, not through the store —
    # build the assertion path the same way rather than through store.path().
    workflow = eng.store.path("repos", repos[0]["name"]) / ".github" / "workflows" / "s7-ci.yml"
    assert workflow.exists()


def test_connect_repo_records_unsupported_stack(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "index.html").write_text("<html></html>")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "init")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")

    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(remote))
    repos = eng.state()["intake"]["repos"]
    assert repos[0]["ci_bootstrap_status"] == "unsupported_stack"


def test_connect_repo_bootstrap_push_failure_does_not_fail_connect(tmp_path):
    # a plain non-bare repo with its branch checked out refuses the push —
    # connecting must still succeed
    checked_out = tmp_path / "checked_out"
    checked_out.mkdir()
    _git(checked_out, "init", "--initial-branch=main")
    (checked_out / "app.py").write_text("# app\n")
    _git(checked_out, "add", ".")
    _git(checked_out, "commit", "-m", "init")

    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(checked_out))
    repos = eng.state()["intake"]["repos"]
    assert repos[0]["ci_bootstrap_status"] == "push_failed"
    assert repos[0]["name"]  # connect itself still succeeded


def test_create_new_app_repo_bootstraps_from_declared_stack(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.store.write_json(
        {"transcript": [], "pending": [], "rounds_used": 2, "max_rounds": 2,
         "name": "advisor-portal-signin", "description": "Sign-in",
         "stack": "Java Spring Boot"},
        "intake", "new_app.json",
    )
    # a scaffold must already exist on disk for _scaffold_files() to find —
    # normally written by intake_generate_scaffold; write it directly here
    eng.store.write_text(
        "# arch\n\nWhat this application does NOT do\n- nothing yet\n",
        "intake", "scaffold", "advisor-portal-signin", "architecture.md",
    )
    eng.store.write_text(
        "# readme\n", "intake", "scaffold", "advisor-portal-signin", "README.md",
    )

    def fake_push(repo_path, name):
        # scaffold.write_scaffold_locally already committed architecture.md
        # + README.md; simulate the real push by making it its own remote
        _git(repo_path, "config", "receive.denyCurrentBranch", "updateInstead")
        return str(repo_path)

    monkeypatch.setattr(scaffold_mod, "push_new_repo", fake_push)
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)
    repos = eng.state()["intake"]["repos"]
    assert repos[0]["ci_bootstrap_status"] == "bootstrapped:maven"
