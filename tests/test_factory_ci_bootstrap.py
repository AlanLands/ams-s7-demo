"""CI workflow bootstrap: a real GitHub Actions workflow, written once per
repo, so a real developer push produces a real run for ci_sync to read.
Git operations run for real against local bare remotes — no gh, no network.
"""
import json
import subprocess
import sys

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
    assert "shell: bash" in workflow.read_text()
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
    assert "shell: bash" in workflow.read_text()


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


def test_bootstrap_idempotent_on_repeated_calls(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    # First bootstrap call
    status1 = ci_bootstrap.bootstrap(clone, "main", "maven")
    assert status1 == "bootstrapped:maven"
    workflow = clone / ".github" / "workflows" / "s7-ci.yml"
    assert workflow.exists()
    first_content = workflow.read_text()

    # Second bootstrap call with same stack — must not fail despite nothing new to commit
    status2 = ci_bootstrap.bootstrap(clone, "main", "maven")
    assert status2 == "bootstrapped:maven"
    # Verify file unchanged
    assert workflow.read_text() == first_content


def test_pytest_workflow_collects_per_test_results():
    PYTEST_WORKFLOW = ci_bootstrap.workflow_for("pytest")
    assert "--junitxml=junit.xml" in PYTEST_WORKFLOW
    assert '"tests":' in PYTEST_WORKFLOW or "'tests'" in PYTEST_WORKFLOW


def test_maven_workflow_collects_per_test_results():
    MAVEN_WORKFLOW = ci_bootstrap.workflow_for("maven")
    assert "surefire-reports" in MAVEN_WORKFLOW


def test_maven_workflow_parses_jacoco_coverage():
    MAVEN_WORKFLOW = ci_bootstrap.workflow_for("maven")
    assert "target/site/jacoco/jacoco.xml" in MAVEN_WORKFLOW
    assert 'type") == "LINE"' in MAVEN_WORKFLOW


def test_pytest_workflow_parses_cobertura_coverage():
    PYTEST_WORKFLOW = ci_bootstrap.workflow_for("pytest")
    assert "coverage.xml" in PYTEST_WORKFLOW
    assert "line-rate" in PYTEST_WORKFLOW


def _extract_summarize_script(workflow: str) -> str:
    """Pull the embedded `python3 - <<'PY' ... PY` body out of a workflow
    template and de-indent it, so the actual summarize logic can be run and
    verified directly rather than trusted from a string search."""
    start = workflow.index("<<'PY'\n") + len("<<'PY'\n")
    end = workflow.index("\n          PY", start)
    body = workflow[start:end]
    return "\n".join(
        line[10:] if line.startswith(" " * 10) else line
        for line in body.splitlines()
    )


def test_maven_summarize_script_computes_jacoco_line_coverage(tmp_path):
    """The real embedded script, run against a real jacoco.xml: the report
    root's own LINE counter (not a package/class one) drives coverage_pct."""
    MAVEN_WORKFLOW = ci_bootstrap.workflow_for("maven")

    jacoco_dir = tmp_path / "target" / "site" / "jacoco"
    jacoco_dir.mkdir(parents=True)
    (jacoco_dir / "jacoco.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<report name="demo">\n'
        '  <package name="com/example">\n'
        '    <class name="com/example/Foo">\n'
        '      <counter type="LINE" missed="1" covered="9"/>\n'
        "    </class>\n"
        '    <counter type="LINE" missed="1" covered="9"/>\n'
        "  </package>\n"
        '  <counter type="INSTRUCTION" missed="10" covered="90"/>\n'
        '  <counter type="LINE" missed="5" covered="35"/>\n'
        "</report>\n"
    )
    script = _extract_summarize_script(MAVEN_WORKFLOW)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True,
                    capture_output=True, text=True)
    summary = json.loads((tmp_path / "ci-summary.json").read_text())
    # the report-root LINE counter (5 missed, 35 covered), not the nested
    # package/class-level ones with the same type
    assert summary["coverage_pct"] == 87.5


def test_maven_summarize_script_leaves_coverage_none_without_jacoco(tmp_path):
    MAVEN_WORKFLOW = ci_bootstrap.workflow_for("maven")

    script = _extract_summarize_script(MAVEN_WORKFLOW)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True,
                    capture_output=True, text=True)
    summary = json.loads((tmp_path / "ci-summary.json").read_text())
    assert summary["coverage_pct"] is None


def test_pytest_summarize_script_computes_cobertura_line_coverage(tmp_path):
    PYTEST_WORKFLOW = ci_bootstrap.workflow_for("pytest")

    (tmp_path / "coverage.xml").write_text(
        '<?xml version="1.0"?>\n'
        '<coverage line-rate="0.875" branch-rate="0.5">\n'
        "  <packages/>\n"
        "</coverage>\n"
    )
    script = _extract_summarize_script(PYTEST_WORKFLOW)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True,
                    capture_output=True, text=True)
    summary = json.loads((tmp_path / "ci-summary.json").read_text())
    assert summary["coverage_pct"] == 87.5


def test_pytest_summarize_script_leaves_coverage_none_without_report(tmp_path):
    PYTEST_WORKFLOW = ci_bootstrap.workflow_for("pytest")

    script = _extract_summarize_script(PYTEST_WORKFLOW)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True,
                    capture_output=True, text=True)
    summary = json.loads((tmp_path / "ci-summary.json").read_text())
    assert summary["coverage_pct"] is None


# --- new-application build scaffold ----------------------------------------
# A repository S7 creates has no build file, so the workflow alone fails
# before running a test and every run is red for a reason unrelated to the
# published red baseline. Scaffolding is creation-only and never overwrites.


def test_scaffold_files_maven_render_from_templates(tmp_path):
    repo = tmp_path / "sponsor-login-enhancement"
    repo.mkdir()
    files = ci_bootstrap.scaffold_files("maven", repo)
    assert set(files) == {"pom.xml", "src/test/java/smoke/BuildSmokeTest.java"}
    assert "<artifactId>sponsor-login-enhancement</artifactId>" in files["pom.xml"]
    assert "jacoco-maven-plugin" in files["pom.xml"]
    assert "class BuildSmokeTest" in files["src/test/java/smoke/BuildSmokeTest.java"]


def test_scaffold_files_pytest_render_from_templates(tmp_path):
    files = ci_bootstrap.scaffold_files("pytest", tmp_path)
    assert set(files) == {
        "requirements.txt", "pyproject.toml", "tests/test_build_smoke.py",
    }
    assert "pytest==" in files["requirements.txt"]
    assert "--cov-report=xml" in files["pyproject.toml"]


def test_scaffold_files_unknown_stack_is_empty(tmp_path):
    assert ci_bootstrap.scaffold_files(None, tmp_path) == {}
    assert ci_bootstrap.scaffold_files("cobol", tmp_path) == {}


def test_artifact_id_is_maven_safe(tmp_path):
    assert ci_bootstrap.artifact_id_for(tmp_path / "MapleSure_Claims API") == "maplesure-claims-api"
    assert ci_bootstrap.artifact_id_for(tmp_path / "___") == "application"


def test_bootstrap_scaffold_commits_a_buildable_project(bare_remote_and_clone):
    remote, clone = bare_remote_and_clone
    status = ci_bootstrap.bootstrap(clone, "main", "maven", scaffold=True)
    assert status == "bootstrapped:maven+scaffold"
    fresh = remote.parent / "fresh_scaffold"
    subprocess.run(["git", "clone", "-q", str(remote), str(fresh)],
                    check=True, capture_output=True)
    # the workflow is useless without these two: `mvn -B test` would exit
    # before any test runs and CI would be red from the first commit
    assert (fresh / "pom.xml").exists()
    assert (fresh / "src/test/java/smoke/BuildSmokeTest.java").exists()
    assert (fresh / ".github" / "workflows" / "s7-ci.yml").exists()


def test_bootstrap_without_scaffold_writes_workflow_only(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    status = ci_bootstrap.bootstrap(clone, "main", "maven")
    assert status == "bootstrapped:maven"
    assert not (clone / "pom.xml").exists()


def test_scaffold_never_overwrites_the_repositorys_own_files(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    (clone / "pom.xml").write_text("<project>mine</project>", encoding="utf-8")
    _git(clone, "add", "pom.xml")
    _git(clone, "commit", "-m", "own build file")
    ci_bootstrap.bootstrap(clone, "main", "maven", scaffold=True)
    assert (clone / "pom.xml").read_text() == "<project>mine</project>"


def test_bootstrap_scaffold_is_idempotent(bare_remote_and_clone):
    _, clone = bare_remote_and_clone
    ci_bootstrap.bootstrap(clone, "main", "pytest", scaffold=True)
    before = (clone / "pyproject.toml").read_text()
    # second call has nothing to write and must not fail on an empty commit
    status = ci_bootstrap.bootstrap(clone, "main", "pytest", scaffold=True)
    assert status == "bootstrapped:pytest"
    assert (clone / "pyproject.toml").read_text() == before


# --- build failure is not a test result ------------------------------------
# `mvn test` with no pom, or pytest with an unimportable suite, produces no
# report at all. Reporting that as "0 failing tests" is a false green in the
# one place the evidence chain exists to prevent one.


def _run_summarizer(stack: str, tmp_path, exit_code: str | None = None,
                    log: str | None = None) -> dict:
    script = _extract_summarize_script(ci_bootstrap.workflow_for(stack))
    if exit_code is not None:
        (tmp_path / "test-exit-code").write_text(exit_code)
    if log is not None:
        (tmp_path / "test-output.log").write_text(log)
    subprocess.run([sys.executable, "-c", script], cwd=tmp_path, check=True,
                    capture_output=True, text=True)
    return json.loads((tmp_path / "ci-summary.json").read_text())


@pytest.mark.parametrize("stack", ["maven", "pytest"])
def test_summary_reports_build_failure_with_null_counts(stack, tmp_path):
    summary = _run_summarizer(
        stack, tmp_path, exit_code="1\n",
        log="[ERROR] there is no POM in this directory\n",
    )
    assert summary["build"] == "failed"
    assert summary["exit_code"] == 1
    # null, never zero: a build that never compiled found no failures
    # because it never looked, and 0 reads as a clean run
    assert summary["tests_total"] is None
    assert summary["tests_passed"] is None
    assert summary["tests_failed"] is None
    assert "no POM" in summary["build_error"]


@pytest.mark.parametrize("stack", ["maven", "pytest"])
def test_summary_reports_no_tests_when_the_build_succeeded(stack, tmp_path):
    summary = _run_summarizer(stack, tmp_path, exit_code="0\n")
    assert summary["build"] == "no_tests"
    assert summary["tests_total"] == 0
    assert "build_error" not in summary


def test_pytest_exit_five_is_no_tests_not_a_build_failure(tmp_path):
    # pytest exits 5 when it collects nothing — the interpreter and the
    # suite are fine, there is simply nothing to run
    summary = _run_summarizer("pytest", tmp_path, exit_code="5\n")
    assert summary["build"] == "no_tests"


def test_maven_summary_reports_succeeded_with_real_counts(tmp_path):
    reports = tmp_path / "target" / "surefire-reports"
    reports.mkdir(parents=True)
    (reports / "TEST-smoke.xml").write_text(
        '<testsuite><testcase name="test_a"/>'
        '<testcase name="test_b"><failure/></testcase></testsuite>'
    )
    summary = _run_summarizer("maven", tmp_path, exit_code="1\n")
    assert summary["build"] == "succeeded"
    assert (summary["tests_total"], summary["tests_failed"]) == (2, 1)
    assert "build_error" not in summary


def test_pytest_summary_reports_succeeded_with_real_counts(tmp_path):
    (tmp_path / "junit.xml").write_text(
        '<testsuite><testcase name="test_a"/>'
        '<testcase name="test_b"><failure/></testcase></testsuite>'
    )
    summary = _run_summarizer("pytest", tmp_path, exit_code="1\n")
    assert summary["build"] == "succeeded"
    assert (summary["tests_total"], summary["tests_failed"]) == (2, 1)


@pytest.mark.parametrize("stack", ["maven", "pytest"])
def test_run_step_records_the_exit_code_without_hiding_it(stack):
    workflow = ci_bootstrap.workflow_for(stack)
    # the step still fails the job (exit "$code") — the recorded code is for
    # the summary, not a way to make a red run look green
    assert 'echo "$code" > test-exit-code' in workflow
    assert 'exit "$code"' in workflow
