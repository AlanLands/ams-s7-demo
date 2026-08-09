"""CI workflow bootstrap: a real GitHub Actions workflow, written once per
repo, so a real developer push produces a real run for ci_sync to read.
Git operations run for real against local bare remotes — no gh, no network.
"""
import subprocess

import pytest

from s7_delivery.factory import ci_bootstrap


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def bare_remote_and_clone(tmp_path):
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "--initial-branch=main")
    (seed / "README.md").write_text("seed\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "initial scaffold")
    _git(seed, "remote", "add", "origin", str(remote))
    _git(seed, "push", "-q", "origin", "main")
    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(remote), str(clone)],
                    check=True, capture_output=True)
    return remote, clone


def test_detect_stack_from_files_maven(tmp_path):
    (tmp_path / "pom.xml").write_text("<project/>")
    assert ci_bootstrap.detect_stack_from_files(tmp_path) == "maven"


def test_detect_stack_from_files_python_requirements(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    assert ci_bootstrap.detect_stack_from_files(tmp_path) == "pytest"


def test_detect_stack_from_files_loose_python(tmp_path):
    (tmp_path / "app.py").write_text("# app\n")
    assert ci_bootstrap.detect_stack_from_files(tmp_path) == "pytest"


def test_detect_stack_from_files_unknown(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    assert ci_bootstrap.detect_stack_from_files(tmp_path) is None


def test_detect_stack_from_text_java():
    assert ci_bootstrap.detect_stack_from_text("Java Spring Boot") == "maven"


def test_detect_stack_from_text_python():
    assert ci_bootstrap.detect_stack_from_text("Python FastAPI") == "pytest"


def test_detect_stack_from_text_unknown():
    assert ci_bootstrap.detect_stack_from_text("Node Express") is None


def test_bootstrap_unsupported_stack_is_noop(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    status = ci_bootstrap.bootstrap(clone, "main", None)
    assert status == "unsupported_stack"
    assert not (clone / ".github").exists()


def test_bootstrap_maven_writes_commits_and_pushes(bare_remote_and_clone):
    remote, clone = bare_remote_and_clone
    status = ci_bootstrap.bootstrap(clone, "main", "maven")
    assert status == "bootstrapped:maven"
    workflow = clone / ".github" / "workflows" / "s7-ci.yml"
    assert workflow.exists()
    assert "mvn -B test" in workflow.read_text()
    # pushed for real: a fresh clone of the bare remote has it too
    fresh = remote.parent / "fresh"
    subprocess.run(["git", "clone", "-q", str(remote), str(fresh)],
                    check=True, capture_output=True)
    assert (fresh / ".github" / "workflows" / "s7-ci.yml").exists()


def test_bootstrap_pytest_workflow_content(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    ci_bootstrap.bootstrap(clone, "main", "pytest")
    workflow = clone / ".github" / "workflows" / "s7-ci.yml"
    assert "pytest" in workflow.read_text()


def test_bootstrap_push_failure_raises(tmp_path):
    # a plain non-bare repo with its branch checked out refuses the push
    checked_out = tmp_path / "checked_out"
    checked_out.mkdir()
    _git(checked_out, "init", "--initial-branch=main")
    (checked_out / "pom.xml").write_text("<project/>")
    _git(checked_out, "add", ".")
    _git(checked_out, "commit", "-m", "init")
    clone = tmp_path / "clone2"
    subprocess.run(["git", "clone", "-q", str(checked_out), str(clone)],
                    check=True, capture_output=True)
    with pytest.raises(ci_bootstrap.CiBootstrapError):
        ci_bootstrap.bootstrap(clone, "main", "maven")
