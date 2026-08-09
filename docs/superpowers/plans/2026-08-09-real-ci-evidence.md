# Real CI Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build & Test Evidence shows real GitHub Actions test results for a real developer push, instead of only the deterministic simulation engine's numbers — closing the gap found in the 2026-08-09 live test, and fixing the "Sync Now" button that currently does nothing.

**Architecture:** S7 bootstraps a `.github/workflows/s7-ci.yml` onto each repo's default branch once (at connect/create time), so a real push produces a real GitHub Actions run. `Engine.workspaces_sync_git` — the same action behind both "Sync from Git" and (once fixed) "Sync Now" — reads that run back via `gh` and stores it as `ci_evidence` on the workspace, which `_workspaces_view` surfaces alongside (never silently replacing) the existing simulated evidence.

**Tech Stack:** Python (`s7_delivery/factory/`), `gh` CLI, plain `git` subprocess calls (existing pattern in `git_sync.py`/`scaffold.py`), React/TypeScript frontend (`apps/control/web/src/`).

## Global Constraints

- No third-party Python libraries for parsing — plain regex over captured CI log text (hard rule 4: plain Python preferred, pin dependencies).
- No coverage tooling injected into target repos — `coverage_pct` stays `null` in v1, never fabricated.
- No AC-level test-to-criterion mapping for real tests in v1 — the Acceptance Criteria Coverage panel keeps showing only the simulated baseline.
- A `gh`/CI-bootstrap failure must never fail `intake_connect_repo`, `intake_create_new_app_repo`, or `workspaces_sync_git` — CI evidence is additive, never load-bearing (spec: "additive, not load-bearing").
- Every new/changed Python module follows the existing style in `git_sync.py`/`scaffold.py`: module-level `Error` class, plain `subprocess.run(..., capture_output=True, text=True)`, functions exercised for real against local git fixtures (not mocked) where no real network is involved.
- Frontend: keep `SIMULATED` badges on simulated data; new real evidence gets `HUMAN` provenance, per this project's badge vocabulary (`s7_delivery/factory/models.py: Provenance`).

Spec: `docs/superpowers/specs/2026-08-09-real-ci-evidence-design.md`

---

### Task 1: `ci_bootstrap.py` — stack detection + workflow templates

**Files:**
- Create: `s7_delivery/factory/ci_bootstrap.py`
- Test: `tests/test_factory_ci_bootstrap.py`

**Interfaces:**
- Produces: `CiBootstrapError(Exception)`; `detect_stack_from_files(repo_dir: Path) -> str | None`; `detect_stack_from_text(stack_hint: str) -> str | None`; `bootstrap(repo_dir: Path, default_branch: str, stack: str | None) -> str` (returns `"bootstrapped:<stack>"` or `"unsupported_stack"`, raises `CiBootstrapError` only on a real git failure once a supported stack is confirmed).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_ci_bootstrap.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 's7_delivery.factory.ci_bootstrap'`

- [ ] **Step 3: Write the implementation**

```python
"""CI workflow bootstrap — one real GitHub Actions workflow per repo, so a
developer's real push produces a real run for `ci_sync.py` to read back. S7
never executes the developer's code itself; GitHub's own runners do.

Committed straight to the repo's default branch, once, right after the repo
is cloned in `Engine.intake_connect_repo` / `Engine.intake_create_new_app_repo`.
A push failure here must never fail connecting/creating the repo — callers
catch `CiBootstrapError` and record a status, they don't propagate it.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

MAVEN_WORKFLOW = """name: S7 CI
on:
  push:
    branches: ['**']
  pull_request:
jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Run tests
        run: mvn -B test | tee test-output.log
      - name: Summarize results
        if: always()
        run: |
          python3 - <<'PY'
          import json, re
          text = open("test-output.log", encoding="utf-8", errors="replace").read()
          matches = re.findall(r"Tests run: (\\d+), Failures: (\\d+), Errors: (\\d+), Skipped: (\\d+)", text)
          if matches:
              run, fail, err, skip = (int(x) for x in matches[-1])
              total, failed = run, fail + err
          else:
              total, failed = 0, 0
          summary = {"tests_total": total, "tests_passed": total - failed, "tests_failed": failed, "coverage_pct": None}
          json.dump(summary, open("ci-summary.json", "w"))
          PY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ci-summary
          path: ci-summary.json
"""

PYTEST_WORKFLOW = """name: S7 CI
on:
  push:
    branches: ['**']
  pull_request:
jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
          pip install pytest
      - name: Run tests
        run: pytest | tee test-output.log
      - name: Summarize results
        if: always()
        run: |
          python3 - <<'PY'
          import json, re
          text = open("test-output.log", encoding="utf-8", errors="replace").read()
          passed_m = re.findall(r"(\\d+) passed", text)
          failed_m = re.findall(r"(\\d+) failed", text)
          passed = int(passed_m[-1]) if passed_m else 0
          failed = int(failed_m[-1]) if failed_m else 0
          summary = {"tests_total": passed + failed, "tests_passed": passed, "tests_failed": failed, "coverage_pct": None}
          json.dump(summary, open("ci-summary.json", "w"))
          PY
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: ci-summary
          path: ci-summary.json
"""

_WORKFLOWS = {"maven": MAVEN_WORKFLOW, "pytest": PYTEST_WORKFLOW}


class CiBootstrapError(Exception):
    """A git command failed while bootstrapping the CI workflow."""


def detect_stack_from_files(repo_dir: Path) -> str | None:
    """Inspect an already-cloned repo's files to pick a known stack, or
    None if nothing recognized is present yet (used for connect-by-URL,
    where real code already exists)."""
    if (repo_dir / "pom.xml").exists():
        return "maven"
    if (repo_dir / "requirements.txt").exists() or (repo_dir / "pyproject.toml").exists():
        return "pytest"
    if any(repo_dir.rglob("*.py")):
        return "pytest"
    return None


def detect_stack_from_text(stack_hint: str) -> str | None:
    """Keyword-match a human-typed stack description from the new-app setup
    conversation, before any code exists."""
    text = stack_hint.lower()
    if any(kw in text for kw in ("java", "spring", "maven")):
        return "maven"
    if any(kw in text for kw in ("python", "flask", "fastapi", "django")):
        return "pytest"
    return None


def _git(repo_dir: Path, *args: str) -> None:
    proc = subprocess.run(
        ["git", *args], cwd=repo_dir, capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CiBootstrapError(
            f"git {' '.join(args)} failed in {repo_dir}: {proc.stderr.strip()}"
        )


def bootstrap(repo_dir: Path, default_branch: str, stack: str | None) -> str:
    """Write, commit and push the workflow for `stack` onto the repo's
    default branch. Returns "unsupported_stack" (no-op, no git touched) when
    `stack` is None or unrecognized; otherwise "bootstrapped:<stack>" or
    raises CiBootstrapError if the push fails (caller decides how to record
    that — it must not fail the repo connect/create action)."""
    if stack is None or stack not in _WORKFLOWS:
        return "unsupported_stack"
    workflow_dir = repo_dir / ".github" / "workflows"
    workflow_dir.mkdir(parents=True, exist_ok=True)
    (workflow_dir / "s7-ci.yml").write_text(_WORKFLOWS[stack], encoding="utf-8")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
    _git(repo_dir, "add", ".github/workflows/s7-ci.yml")
    _git(repo_dir, *ident, "commit", "-qm", "s7: bootstrap CI workflow")
    _git(repo_dir, "push", "-q", "origin", f"HEAD:refs/heads/{default_branch}")
    return f"bootstrapped:{stack}"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_ci_bootstrap.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/ci_bootstrap.py tests/test_factory_ci_bootstrap.py
git commit -m "feat: CI workflow bootstrap for real GitHub Actions evidence

Writes a real .github/workflows/s7-ci.yml (Maven or pytest) onto a
target repo's default branch, once, so a developer's real push produces
a real run for ci_sync.py to read back. Push failures raise, and callers
must catch them — connecting/creating a repo must never fail because CI
bootstrap failed.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `ci_sync.py` — read real GitHub Actions results via `gh`

**Files:**
- Create: `s7_delivery/factory/ci_sync.py`
- Test: `tests/test_factory_ci_sync.py`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `CiSyncError(Exception)`; `owner_repo_from_url(url: str) -> str | None`; `latest_run(owner_repo: str, sha: str) -> dict | None` (keys: `databaseId, status, conclusion, url, workflowName`); `download_summary(owner_repo: str, run_id: int) -> dict | None` (keys: `tests_total, tests_passed, tests_failed, coverage_pct`).

- [ ] **Step 1: Write the failing tests**

```python
"""Real CI evidence: reading GitHub Actions run results via `gh`. All `gh`
calls are monkeypatched — no network, no real GitHub access in tests.
"""
import json
import subprocess

import pytest

from s7_delivery.factory import ci_sync


def test_owner_repo_from_url_github():
    assert ci_sync.owner_repo_from_url(
        "https://github.com/AlanLands/advisor-portal-signin"
    ) == "AlanLands/advisor-portal-signin"


def test_owner_repo_from_url_github_with_git_suffix():
    assert ci_sync.owner_repo_from_url(
        "https://github.com/AlanLands/advisor-portal-signin.git"
    ) == "AlanLands/advisor-portal-signin"


def test_owner_repo_from_url_non_github_returns_none():
    assert ci_sync.owner_repo_from_url("local") is None
    assert ci_sync.owner_repo_from_url("/tmp/some/local/path") is None


def _fake_run(returncode=0, stdout="", stderr=""):
    def _run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, returncode, stdout=stdout, stderr=stderr)
    return _run


def test_latest_run_returns_none_when_no_runs(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(stdout="[]"))
    assert ci_sync.latest_run("owner/repo", "abc123") is None


def test_latest_run_returns_first_row(monkeypatch):
    rows = [{"databaseId": 42, "status": "completed", "conclusion": "success",
              "url": "https://github.com/owner/repo/actions/runs/42",
              "workflowName": "S7 CI"}]
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(stdout=json.dumps(rows)))
    run = ci_sync.latest_run("owner/repo", "abc123")
    assert run["databaseId"] == 42
    assert run["conclusion"] == "success"


def test_latest_run_raises_on_gh_failure(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run",
                         _fake_run(returncode=1, stderr="not found"))
    with pytest.raises(ci_sync.CiSyncError, match="not found"):
        ci_sync.latest_run("owner/repo", "abc123")


def test_download_summary_returns_none_on_gh_failure(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(returncode=1, stderr="no artifact"))
    assert ci_sync.download_summary("owner/repo", 42) is None


def test_download_summary_parses_artifact(monkeypatch, tmp_path):
    summary = {"tests_total": 2, "tests_passed": 2, "tests_failed": 0, "coverage_pct": None}

    def fake_run(cmd, **kwargs):
        # emulate `gh run download ... -D <tmp>` writing ci-summary.json there
        dest_dir = cmd[cmd.index("-D") + 1]
        (__import__("pathlib").Path(dest_dir) / "ci-summary.json").write_text(json.dumps(summary))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(ci_sync.subprocess, "run", fake_run)
    result = ci_sync.download_summary("owner/repo", 42)
    assert result == summary


def test_download_summary_returns_none_when_artifact_missing(monkeypatch):
    monkeypatch.setattr(ci_sync.subprocess, "run", _fake_run(returncode=0, stdout=""))
    assert ci_sync.download_summary("owner/repo", 42) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_ci_sync.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 's7_delivery.factory.ci_sync'`

- [ ] **Step 3: Write the implementation**

```python
"""Real CI evidence — read GitHub Actions run results for a real pushed
commit via `gh`. Read-only: nothing here executes the developer's code or
writes to any remote. A failure here is always recoverable by the caller —
"no evidence yet" and "gh call failed" are both non-fatal to git evidence
sync (see Engine._sync_ci_evidence)."""
from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


class CiSyncError(Exception):
    """A `gh` command failed — the message carries stderr."""


def owner_repo_from_url(url: str) -> str | None:
    """'https://github.com/AlanLands/advisor-portal-signin(.git)' ->
    'AlanLands/advisor-portal-signin'. None for anything that isn't a
    github.com URL (e.g. the local paths used by test fixtures)."""
    marker = "github.com/"
    if marker not in url:
        return None
    tail = url.split(marker, 1)[1]
    parts = tail.removesuffix(".git").split("/")
    if len(parts) < 2 or not parts[0] or not parts[1]:
        return None
    return f"{parts[0]}/{parts[1]}"


def latest_run(owner_repo: str, sha: str) -> dict | None:
    """The most recent GitHub Actions run for `sha`, or None if nothing has
    run yet — a normal, expected outcome, not an error. Raises CiSyncError
    only when `gh` itself fails (auth, repo not found)."""
    proc = subprocess.run(
        ["gh", "run", "list", "--repo", owner_repo, "--commit", sha,
         "--json", "databaseId,status,conclusion,url,workflowName", "--limit", "1"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise CiSyncError(
            f"gh run list failed for {owner_repo}@{sha}: {proc.stderr.strip()}"
        )
    rows = json.loads(proc.stdout or "[]")
    return rows[0] if rows else None


def download_summary(owner_repo: str, run_id: int) -> dict | None:
    """The `ci-summary.json` artifact the S7-bootstrapped workflow produces,
    or None if the run hasn't finished, produced nothing (e.g. it failed
    before the summarize step), or predates the CI bootstrap. A `gh`
    failure here is treated the same as "no artifact" — not raised."""
    with tempfile.TemporaryDirectory() as tmp:
        proc = subprocess.run(
            ["gh", "run", "download", str(run_id), "--repo", owner_repo,
             "-n", "ci-summary", "-D", tmp],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            return None
        summary_path = Path(tmp) / "ci-summary.json"
        if not summary_path.exists():
            return None
        return json.loads(summary_path.read_text(encoding="utf-8"))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_ci_sync.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/ci_sync.py tests/test_factory_ci_sync.py
git commit -m "feat: read real GitHub Actions run results via gh

Pure functions over gh run list/download — no network in tests, all gh
calls monkeypatched. A gh failure or 'no run yet' both return None/raise
CiSyncError; callers in engine.py decide these are never fatal to sync.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `DeveloperWorkspace.ci_evidence` model field

**Files:**
- Modify: `s7_delivery/factory/models.py:373` (right after `git_evidence`)

**Interfaces:**
- Produces: `DeveloperWorkspace.ci_evidence: dict | None` — same shape as `git_evidence`, a plain optional dict (not a nested Pydantic model, matching how `git_evidence` is already typed).

- [ ] **Step 1: Make the change**

In `s7_delivery/factory/models.py`, immediately after the existing `git_evidence` line (models.py:373):

```python
    # real evidence from the repository remote (git fetch + ref inspection);
    # None until a live-run "Sync from Git" has run. HUMAN work, read-only.
    git_evidence: dict | None = None
    # real GitHub Actions run result for git_evidence's latest commit, when
    # the repo's CI workflow has been bootstrapped and has run. None until
    # a live-run sync finds a run. Additive: never overwrites git_evidence.
    ci_evidence: dict | None = None
```

- [ ] **Step 2: Verify the model still imports cleanly**

Run: `.venv/bin/python -c "from s7_delivery.factory.models import DeveloperWorkspace; print(DeveloperWorkspace(workspace_id='w', run_id='r', team='t', story_id='s').ci_evidence)"`
Expected: prints `None`

- [ ] **Step 3: Commit**

```bash
git add s7_delivery/factory/models.py
git commit -m "feat: add ci_evidence field to DeveloperWorkspace model

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: Wire CI sync into `workspaces_sync_git` and `_workspaces_view`

**Files:**
- Modify: `s7_delivery/factory/engine.py:2046` (`_DEV_STATUS`, add `_CI_CONCLUSION_MAP` after it)
- Modify: `s7_delivery/factory/engine.py:2062-2097` (`_workspaces_view`)
- Modify: `s7_delivery/factory/engine.py:2099-2154` (`workspaces_sync_git`)
- Test: `tests/test_factory_ci_sync_engine.py`

**Interfaces:**
- Consumes: `ci_sync.owner_repo_from_url`, `ci_sync.latest_run`, `ci_sync.download_summary`, `ci_sync.CiSyncError` (Task 2); `DeveloperWorkspace.ci_evidence` (Task 3).
- Produces: `Engine._sync_ci_evidence(repo: dict, git_evidence: dict) -> dict | None`; `Engine._refresh_task_evidence_files(workspaces: list[dict], tasks_by_story: dict[str, dict]) -> None`. `_workspaces_view()` output gains `ci_run_url`, `ci_tests_total`, `ci_tests_passed`, `ci_tests_failed` (all present, possibly `None`, whenever `ci_evidence` exists on the record) and may now set `ci_status` to a real value instead of leaving it blank.

- [ ] **Step 1: Write the failing tests**

```python
"""CI evidence sync: real GitHub Actions results layered onto real git
evidence. `gh` is always monkeypatched via ci_sync — no network.
"""
import json
import subprocess

import pytest

from s7_delivery.factory import ci_sync
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role


def _git(cwd, *args):
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True,
        env={"GIT_AUTHOR_NAME": "Dev", "GIT_AUTHOR_EMAIL": "dev@test",
             "GIT_COMMITTER_NAME": "Dev", "GIT_COMMITTER_EMAIL": "dev@test",
             "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd)},
    )


@pytest.fixture
def live_eng_with_github_repo(tmp_path):
    """A live engine whose workspace repository looks like a real GitHub
    repo (a github.com URL) but is actually a local bare remote — git
    operations are real, gh calls are monkeypatched per-test."""
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
    _git(seed, "checkout", "-B", "feature/us-1")
    (seed / "login.py").write_text("# login\n")
    _git(seed, "add", ".")
    _git(seed, "commit", "-m", "US-1: implement sign-in page")
    _git(seed, "push", "-q", "-u", "origin", "feature/us-1")

    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    dest = e.store.path("repos", "advisor-portal-signin")
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(remote), str(dest)],
                    check=True, capture_output=True)
    e.store.write_json(
        [{"url": "https://github.com/AlanLands/advisor-portal-signin",
          "name": "advisor-portal-signin", "head_sha": "", "default_branch": "main",
          "file_count": 1, "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-1", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-1", "repository": "advisor-portal-signin",
          "branch": "s7/x-platform-team", "developer": "Alan Lands",
          "delivery_pack_id": "PACK-platform-team", "delivery_pack_version": 1,
          "base_commit": "", "development_status": "provisioned",
          "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json(
        [{"task_id": "TASK-001", "story_id": "US-1", "status": "ready",
          "commit_ref": "", "pr_ref": "", "ci_status": ""}],
        "build", "tasks.json",
    )
    return e


def test_sync_with_no_github_url_leaves_ci_evidence_none(tmp_path, monkeypatch):
    """Non-github repos (e.g. this codebase's own local-path test fixtures)
    never attempt a gh call at all."""
    def boom(*a, **k):
        raise AssertionError("gh should never be called for a non-github url")
    monkeypatch.setattr(ci_sync, "latest_run", boom)

    import subprocess as sp
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "--initial-branch=main")
    e = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    dest = e.store.path("repos", "advisor-portal-signin")
    dest.parent.mkdir(parents=True, exist_ok=True)
    sp.run(["git", "clone", "-q", str(remote), str(dest)], check=True, capture_output=True)
    e.store.write_json(
        [{"url": "local", "name": "advisor-portal-signin", "head_sha": "",
          "default_branch": "main", "file_count": 1, "cloned_at": "", "provenance": "human"}],
        "intake", "repos.json",
    )
    e.store.write_json(
        [{"workspace_id": "WS-US-1", "run_id": e.run_id, "team": "Platform Team",
          "story_id": "US-1", "repository": "advisor-portal-signin",
          "branch": "b", "developer": "Alan", "delivery_pack_id": "PACK-1",
          "delivery_pack_version": 1, "base_commit": "",
          "development_status": "provisioned", "provenance": "human"}],
        "build", "workspaces.json",
    )
    e.store.write_json([{"task_id": "TASK-001", "story_id": "US-1", "status": "ready"}],
                        "build", "tasks.json")
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws.get("ci_evidence") is None
    assert ws["ci_status"] == ""


def test_sync_populates_real_ci_status_and_test_counts(live_eng_with_github_repo, monkeypatch):
    e = live_eng_with_github_repo

    def fake_latest_run(owner_repo, sha):
        assert owner_repo == "AlanLands/advisor-portal-signin"
        return {"databaseId": 42, "status": "completed", "conclusion": "success",
                "url": "https://github.com/AlanLands/advisor-portal-signin/actions/runs/42",
                "workflowName": "S7 CI"}

    def fake_download_summary(owner_repo, run_id):
        assert run_id == 42
        return {"tests_total": 2, "tests_passed": 2, "tests_failed": 0, "coverage_pct": None}

    monkeypatch.setattr(ci_sync, "latest_run", fake_latest_run)
    monkeypatch.setattr(ci_sync, "download_summary", fake_download_summary)

    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["ci_status"] == "passed"
    assert ws["ci_tests_total"] == 2
    assert ws["ci_tests_passed"] == 2
    assert ws["ci_tests_failed"] == 0
    assert ws["ci_run_url"].endswith("/actions/runs/42")

    # the exported task-evidence.json is refreshed to match (only if the
    # delivery pack directory already exists — simulate that it does)
    task_evidence_path = e.store.path("build", "tasks", "TASK-001", "task-evidence.json")
    task_evidence_path.parent.mkdir(parents=True, exist_ok=True)
    task_evidence_path.write_text(json.dumps({"task_id": "TASK-001"}))
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    refreshed = json.loads(task_evidence_path.read_text())
    assert refreshed["ci_evidence"]["conclusion"] == "success"


def test_sync_ci_run_still_queued_maps_to_running(live_eng_with_github_repo, monkeypatch):
    e = live_eng_with_github_repo
    monkeypatch.setattr(
        ci_sync, "latest_run",
        lambda owner_repo, sha: {"databaseId": 7, "status": "queued", "conclusion": None,
                                  "url": "https://x/actions/runs/7", "workflowName": "S7 CI"},
    )
    monkeypatch.setattr(ci_sync, "download_summary", lambda *a: (_ for _ in ()).throw(
        AssertionError("must not download an artifact for a run that hasn't completed")))
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["ci_status"] == "running"
    assert ws.get("ci_tests_total") is None


def test_sync_gh_failure_does_not_break_git_sync(live_eng_with_github_repo, monkeypatch):
    def boom(owner_repo, sha):
        raise ci_sync.CiSyncError("gh auth failure")
    monkeypatch.setattr(ci_sync, "latest_run", boom)
    e = live_eng_with_github_repo
    e.workspaces_sync_git(Role.DELIVERY_LEAD)
    ws = e.state()["build"]["workspaces"][0]
    assert ws["git_evidence"]["commit_count"] == 1
    assert ws.get("ci_evidence") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_ci_sync_engine.py -v`
Expected: FAIL — `ws["ci_status"]` stays `""` in the populate test (feature not wired yet); `ci_run_url`/`ci_tests_total` KeyErrors.

- [ ] **Step 3: Implement — add `_CI_CONCLUSION_MAP`**

In `s7_delivery/factory/engine.py`, immediately after `_DEV_STATUS` (engine.py:2054):

```python
    _CI_CONCLUSION_MAP = {
        "success": "passed",
        "failure": "failed",
        "queued": "running",
        "in_progress": "running",
    }
```

- [ ] **Step 4: Implement — extend `_workspaces_view`**

Replace the existing block in `_workspaces_view` (engine.py:2084-2093):

```python
            ev = ws.get("git_evidence")
            if ev and ev.get("commit_count"):
                # real pushed work wins over the simulated task lifecycle;
                # what git cannot prove (CI, PR) stays blank, never invented
                ws["current_commit"] = ev["latest"]["sha"][:7]
                ws["development_status"] = (
                    "complete" if ev["merged"] else "in_development"
                )
                ws["pull_request"] = ""
                ws["ci_status"] = ""
```

with:

```python
            ev = ws.get("git_evidence")
            if ev and ev.get("commit_count"):
                # real pushed work wins over the simulated task lifecycle;
                # what git cannot prove (PR) stays blank, never invented
                ws["current_commit"] = ev["latest"]["sha"][:7]
                ws["development_status"] = (
                    "complete" if ev["merged"] else "in_development"
                )
                ws["pull_request"] = ""
                ws["ci_status"] = ""
            ci_ev = ws.get("ci_evidence")
            if ci_ev:
                # CI is no longer unprovable once a real run exists — this
                # overrides the blank set above, never invents a status the
                # run itself didn't report
                mapped = self._CI_CONCLUSION_MAP.get(
                    ci_ev.get("conclusion") or ci_ev.get("status") or "", ""
                )
                if mapped:
                    ws["ci_status"] = mapped
                ws["ci_run_url"] = ci_ev.get("url", "")
                ws["ci_tests_total"] = ci_ev.get("tests_total")
                ws["ci_tests_passed"] = ci_ev.get("tests_passed")
                ws["ci_tests_failed"] = ci_ev.get("tests_failed")
```

- [ ] **Step 5: Implement — extend `workspaces_sync_git` and add helpers**

Replace the body of `workspaces_sync_git` (engine.py:2099-2154) with:

```python
    def workspaces_sync_git(self, role: Role) -> int:
        """Read real developer progress from each workspace repository:
        `git fetch` + local ref inspection, plus (when the commit resolves
        to a real GitHub repo) the real GitHub Actions run for that commit.
        Nothing written to any remote here — the one-time CI workflow
        commit happens at connect/create time, in ci_bootstrap.bootstrap.
        Live runs only — a simulation run has no real clone, and mixing
        real git evidence into simulated provenance would muddy the
        badging."""
        roles.require("sync_git_evidence", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError(
                "Git evidence sync needs a live run — simulation has no real"
                " repository clone"
            )
        from s7_delivery.factory import git_sync

        workspaces = self._workspaces()
        if not workspaces:
            raise EngineError("No developer workspaces to sync")
        repos = {r["name"]: r for r in self._connected_repos()}
        task_ids_by_story: dict[str, list[str]] = {}
        tasks_by_story: dict[str, dict] = {}
        for t in self._tasks():
            task_ids_by_story.setdefault(t["story_id"], []).append(t["task_id"])
            tasks_by_story[t["story_id"]] = t
        fetched: set[str] = set()
        synced = 0
        for ws in workspaces:
            repo = repos.get(ws["repository"])
            repo_dir = self.store.path("repos", ws["repository"])
            if repo is None or not (repo_dir / ".git").exists():
                continue
            try:
                if ws["repository"] not in fetched:
                    git_sync.fetch(repo_dir)
                    fetched.add(ws["repository"])
                ws["git_evidence"] = git_sync.story_evidence(
                    repo_dir, ws["story_id"],
                    task_ids_by_story.get(ws["story_id"], []),
                    repo.get("default_branch", ""),
                )
            except git_sync.GitSyncError as exc:
                raise EngineError(str(exc)) from exc
            ws["ci_evidence"] = self._sync_ci_evidence(repo, ws["git_evidence"])
            ws["last_sync_at"] = now_iso()
            synced += 1
        if not synced:
            raise EngineError(
                "No workspace repository has a local clone to sync from"
            )
        self._save_workspaces(workspaces)
        self._refresh_task_evidence_files(workspaces, tasks_by_story)
        with_commits = sum(
            1 for w in workspaces
            if (w.get("git_evidence") or {}).get("commit_count")
        )
        with_ci = sum(1 for w in workspaces if w.get("ci_evidence"))
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=role.value, actor_type="human",
            workflow="git-evidence-sync", artifact="workspaces",
            outcome="synced",
            details=f"{synced} workspaces synced from git; {with_commits}"
                    f" with developer commits, {with_ci} with real CI"
                    " results (real pushed work, read-only)",
        )
        return synced

    def _sync_ci_evidence(self, repo: dict, git_evidence: dict) -> dict | None:
        """Best-effort real CI lookup for the latest matching commit. Never
        raises: a gh failure, an unresolvable owner/repo, or no run yet all
        mean "no CI evidence yet", not a sync failure."""
        from s7_delivery.factory import ci_sync

        latest = git_evidence.get("latest")
        if not latest:
            return None
        owner_repo = ci_sync.owner_repo_from_url(repo.get("url", ""))
        if owner_repo is None:
            return None
        try:
            run = ci_sync.latest_run(owner_repo, latest["sha"])
        except ci_sync.CiSyncError:
            return None
        if run is None:
            return None
        evidence: dict = {
            "run_id": run.get("databaseId"),
            "status": run.get("status", ""),
            "conclusion": run.get("conclusion") or "",
            "url": run.get("url", ""),
            "checked_at": now_iso(),
        }
        if run.get("status") == "completed":
            try:
                summary = ci_sync.download_summary(owner_repo, run["databaseId"])
            except ci_sync.CiSyncError:
                summary = None
            if summary:
                evidence["tests_total"] = summary.get("tests_total")
                evidence["tests_passed"] = summary.get("tests_passed")
                evidence["tests_failed"] = summary.get("tests_failed")
        return evidence

    def _refresh_task_evidence_files(
        self, workspaces: list[dict], tasks_by_story: dict[str, dict]
    ) -> None:
        """Keep build/tasks/{id}/task-evidence.json — what
        GET .../tasks/{id}/evidence.zip actually exports — in step with
        real sync results, so the download matches what the app shows.
        No-op for a task whose delivery pack hasn't been generated yet."""
        for ws in workspaces:
            task = tasks_by_story.get(ws["story_id"])
            if task is None:
                continue
            path = self.store.path(
                "build", "tasks", task["task_id"], "task-evidence.json"
            )
            if not path.exists():
                continue
            evidence = {
                "task_id": task["task_id"],
                "status": task.get("status", "not_started"),
                "commit_ref": task.get("commit_ref", ""),
                "pr_ref": task.get("pr_ref", ""),
                "ci_status": task.get("ci_status", ""),
            }
            if ws.get("git_evidence"):
                evidence["git_evidence"] = ws["git_evidence"]
            if ws.get("ci_evidence"):
                evidence["ci_evidence"] = ws["ci_evidence"]
            self.store.write_json(
                evidence, "build", "tasks", task["task_id"], "task-evidence.json"
            )
```

- [ ] **Step 6: Run the new tests, then the full existing git-sync suite**

Run: `.venv/bin/pytest tests/test_factory_ci_sync_engine.py tests/test_factory_git_sync.py -v`
Expected: PASS, all tests including the pre-existing `test_sync_records_real_commits_on_workspace` (its `ws["ci_status"] == ""` assertion still holds: that test's repo URL is `"local"`, so `owner_repo_from_url` returns `None` and `_sync_ci_evidence` short-circuits to `None`).

- [ ] **Step 7: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, no regressions

- [ ] **Step 8: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_ci_sync_engine.py
git commit -m "feat: sync real CI evidence into workspaces_sync_git

_workspaces_view now reports a real ci_status/tests once a workspace's
commit has a real GitHub Actions run, instead of leaving CI blank the
way 'git cannot prove it' correctly did before CI existed. Also
refreshes build/tasks/{id}/task-evidence.json so the exported evidence
ZIP matches what the app shows.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: Bootstrap the CI workflow at repo connect/create time

**Files:**
- Modify: `s7_delivery/factory/engine.py:845-874` (`intake_connect_repo`)
- Modify: `s7_delivery/factory/engine.py:1056-1104` (`intake_create_new_app_repo`)
- Test: `tests/test_factory_ci_bootstrap_engine.py`

**Interfaces:**
- Consumes: `ci_bootstrap.detect_stack_from_files`, `ci_bootstrap.detect_stack_from_text`, `ci_bootstrap.bootstrap`, `ci_bootstrap.CiBootstrapError` (Task 1).
- Produces: each entry in `intake/repos.json` gains `ci_bootstrap_status: str` (`"bootstrapped:<stack>"`, `"unsupported_stack"`, or `"push_failed"`).

- [ ] **Step 1: Write the failing tests**

```python
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
    workflow = eng.store.path("repos", repos[0]["name"], ".github", "workflows", "s7-ci.yml")
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
    eng._set_new_app_setup_for_test(  # see Step 3a below for this test seam
        name="advisor-portal-signin", description="Sign-in", stack="Java Spring Boot",
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_ci_bootstrap_engine.py -v`
Expected: FAIL — `KeyError: 'ci_bootstrap_status'` on the first three; the fourth fails at `_set_new_app_setup_for_test` (doesn't exist yet).

- [ ] **Step 3: Add a small test seam for new-app setup state**

`Engine._new_app()` (engine.py:947-952) reads
`self.store.read_json_or({"transcript": [], "pending": [], "rounds_used": 0, "max_rounds": 2, "name": None, "description": None, "stack": None}, "intake", "new_app.json")`.
No test-only method needed — write that same shape directly. Replace the
`eng._set_new_app_setup_for_test(...)` call in Step 1's last test with:

```python
    eng.store.write_json(
        {"transcript": [], "pending": [], "rounds_used": 2, "max_rounds": 2,
         "name": "advisor-portal-signin", "description": "Sign-in",
         "stack": "Java Spring Boot"},
        "intake", "new_app.json",
    )
```

- [ ] **Step 4: Implement — `intake_connect_repo`**

In `s7_delivery/factory/engine.py`, replace (engine.py:852-859):

```python
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            raise EngineError(f"Repository clone failed: {exc}") from exc

        repos = self.store.read_json_or([], "intake", "repos.json")
        repos.append(rec.model_dump(mode="json"))
        self.store.write_json(repos, "intake", "repos.json")
```

with:

```python
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            raise EngineError(f"Repository clone failed: {exc}") from exc

        from s7_delivery.factory import ci_bootstrap
        repo_dir = self.store.path("repos", rec.name)
        stack = ci_bootstrap.detect_stack_from_files(repo_dir)
        try:
            bootstrap_status = ci_bootstrap.bootstrap(repo_dir, rec.default_branch, stack)
        except ci_bootstrap.CiBootstrapError:
            bootstrap_status = "push_failed"

        repos = self.store.read_json_or([], "intake", "repos.json")
        rec_dict = rec.model_dump(mode="json")
        rec_dict["ci_bootstrap_status"] = bootstrap_status
        repos.append(rec_dict)
        self.store.write_json(repos, "intake", "repos.json")
```

- [ ] **Step 5: Implement — `intake_create_new_app_repo`**

In `s7_delivery/factory/engine.py`, replace (engine.py:1083-1091):

```python
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            shutil.rmtree(repo_path, ignore_errors=True)
            raise EngineError(f"Cloning the newly created repo failed: {exc}") from exc

        repos = self.store.read_json_or([], "intake", "repos.json")
        repos.append(rec.model_dump(mode="json"))
        self.store.write_json(repos, "intake", "repos.json")
```

with:

```python
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            shutil.rmtree(repo_path, ignore_errors=True)
            raise EngineError(f"Cloning the newly created repo failed: {exc}") from exc

        from s7_delivery.factory import ci_bootstrap
        repo_dir = self.store.path("repos", rec.name)
        stack = ci_bootstrap.detect_stack_from_text(setup["stack"])
        try:
            bootstrap_status = ci_bootstrap.bootstrap(repo_dir, rec.default_branch, stack)
        except ci_bootstrap.CiBootstrapError:
            bootstrap_status = "push_failed"

        repos = self.store.read_json_or([], "intake", "repos.json")
        rec_dict = rec.model_dump(mode="json")
        rec_dict["ci_bootstrap_status"] = bootstrap_status
        repos.append(rec_dict)
        self.store.write_json(repos, "intake", "repos.json")
```

- [ ] **Step 6: Run the new tests, then the full existing intake test suites**

Run: `.venv/bin/pytest tests/test_factory_ci_bootstrap_engine.py tests/test_factory_live_engine.py tests/test_planning_handoff.py -v`
Expected: PASS. In particular `test_connect_repo_records_and_builds_pack` still passes — that fixture's repo contains loose `.py` files (detected as `pytest`), attempts a push against a checked-out non-bare repo, which fails and is caught as `"push_failed"`; the test doesn't assert on `ci_bootstrap_status` so it's unaffected.

- [ ] **Step 7: Run the full test suite**

Run: `.venv/bin/pytest -q`
Expected: PASS, no regressions

- [ ] **Step 8: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_ci_bootstrap_engine.py
git commit -m "feat: bootstrap CI workflow on repo connect/create

Connect-by-URL detects the stack from files already in the repo;
create-new-app uses the stack the human typed into the setup
conversation, since no code exists yet at creation time. Either way a
bootstrap push failure is recorded (ci_bootstrap_status), never raised —
connecting/creating a repo must not fail because of it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Frontend types — `ci_evidence` on `DeveloperWorkspace`

**Files:**
- Modify: `apps/control/web/src/types.ts:512-538`

**Interfaces:**
- Produces: `DeveloperWorkspace.ci_evidence`, `.ci_run_url`, `.ci_tests_total`, `.ci_tests_passed`, `.ci_tests_failed` — all optional, consumed by Task 7.

- [ ] **Step 1: Make the change**

In `apps/control/web/src/types.ts`, after the existing `git_evidence` block (types.ts:528-533):

```typescript
  git_evidence?: {
    commit_count: number
    latest: { sha: string; author: string; when: string; subject: string } | null
    branches: string[]
    merged: boolean
  } | null
  ci_evidence?: {
    run_id: number
    status: string
    conclusion: string
    url: string
    checked_at: string
    tests_total?: number | null
    tests_passed?: number | null
    tests_failed?: number | null
  } | null
  ci_run_url?: string
  ci_tests_total?: number | null
  ci_tests_passed?: number | null
  ci_tests_failed?: number | null
```

- [ ] **Step 2: Typecheck**

Run: `cd apps/control/web && npm run build`
Expected: builds cleanly (this only adds optional fields, nothing consumes them yet)

- [ ] **Step 3: Commit**

```bash
git add apps/control/web/src/types.ts
git commit -m "feat: type ci_evidence on DeveloperWorkspace

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 7: Build & Test Evidence — real CI Run block, fix Sync Now

**Files:**
- Modify: `apps/control/web/src/pages/build/TestEvidence.tsx`

**Interfaces:**
- Consumes: `DeveloperWorkspace.ci_evidence`/`ci_run_url`/`ci_tests_total`/`ci_tests_passed`/`ci_tests_failed` (Task 6); `useRun().act` (already imported in this file).

- [ ] **Step 1: Fix the "Sync Now" no-op**

Replace (TestEvidence.tsx:151-155):

```typescript
  const doSync = async () => {
    setSyncing(true)
    await refresh()
    setSyncing(false)
  }
```

with:

```typescript
  const doSync = async () => {
    setSyncing(true)
    await act('/workspaces/sync-git', {}, 'Synced — real commits and CI results, where available')
    setSyncing(false)
  }
```

(`refresh` stays imported/used elsewhere on this page if referenced; if this was its only use, remove `refresh` from the `useRun()` destructure at TestEvidence.tsx:51 to avoid an unused-variable lint error — check before removing.)

- [ ] **Step 2: Switch CI System / Pipeline / Open CI Pipeline to real evidence when present**

Replace the "Build Information" block's CI System/Pipeline rows (TestEvidence.tsx:363-364):

```typescript
              <b>Pipeline</b><span className="mono">{task.task_id.replace('TASK', 'BUILD')}</span>
              <b>CI System</b><span>Simulated CI <Prov provenance="simulated" /></span>
```

with:

```typescript
              <b>Pipeline</b><span className="mono">
                {ws?.ci_evidence ? `Run #${ws.ci_evidence.run_id}` : task.task_id.replace('TASK', 'BUILD')}
              </span>
              <b>CI System</b><span>
                {ws?.ci_evidence
                  ? <>GitHub Actions <Prov provenance="human" /></>
                  : <>Simulated CI <Prov provenance="simulated" /></>}
              </span>
```

Replace the disabled "Open CI Pipeline" button (TestEvidence.tsx:449-451):

```typescript
            <button className="outline block" disabled title="No external CI to open in simulation">
              <ExternalLink className="btn-ico" /> Open CI Pipeline
            </button>
```

with:

```typescript
            <button className="outline block" disabled={!ws?.ci_run_url}
              title={ws?.ci_run_url ? undefined : 'No external CI run recorded yet'}
              onClick={() => ws?.ci_run_url && window.open(ws.ci_run_url, '_blank')}>
              <ExternalLink className="btn-ico" /> Open CI Pipeline
            </button>
```

- [ ] **Step 3: Add the "Real CI Run" block, relabel the simulated Test Summary**

Insert a new `dp-ins-block` immediately before the existing "Test Summary" block (before TestEvidence.tsx:369), and relabel that existing block:

```typescript
          {ws?.ci_evidence ? (
            <div className="dp-ins-block">
              <span className="as-label">Real CI Run <Prov provenance="human" /></span>
              <div className="dp-ins-metrics">
                <span><span className="as-label">Passed</span>
                  <b style={{ color: 'var(--green)' }}>{String(ws.ci_tests_passed ?? '—')}</b></span>
                <span><span className="as-label">Failed</span>
                  <b style={{ color: (ws.ci_tests_failed ?? 0) > 0 ? 'var(--red-dark)' : 'inherit' }}>
                    {String(ws.ci_tests_failed ?? '—')}</b></span>
                <span><span className="as-label">Total</span><b>{String(ws.ci_tests_total ?? '—')}</b></span>
                <span><span className="as-label">Conclusion</span><b>{ws.ci_evidence.conclusion || ws.ci_evidence.status}</b></span>
              </div>
            </div>
          ) : null}

          <div className="dp-ins-block">
            <span className="as-label">
              {ws?.ci_evidence ? 'Simulated Test Plan (baseline)' : 'Test Summary'}
              {ws?.ci_evidence ? <Prov provenance="simulated" /> : null}
            </span>
```

(This changes the opening `<span className="as-label">Test Summary</span>` line of the existing block — keep everything below it in that block unchanged.)

- [ ] **Step 4: Table row — real Tests/Build columns when evidence exists**

Replace the table row's Build and Tests cells (TestEvidence.tsx:258-270):

```typescript
                      <td>
                        <span className="repo-cell"><Workflow /><span className="mono">{t.task_id.replace('TASK', 'BUILD')}</span></span>
                        <span className="hint dp-sub">Simulated CI</span>
                      </td>
                      <td><CiBadge ci={w?.ci_status} /></td>
                      <td>
                        {tt.length ? (
                          <>
                            <span className="mono">{`${p} / ${tt.length}`}</span>
                            <span className="hint dp-sub">{`${Math.round((p / tt.length) * 100)}%`}</span>
                          </>
                        ) : <span className="hint">—</span>}
                      </td>
```

with:

```typescript
                      <td>
                        <span className="repo-cell"><Workflow /><span className="mono">
                          {w?.ci_evidence ? `Run #${w.ci_evidence.run_id}` : t.task_id.replace('TASK', 'BUILD')}
                        </span></span>
                        <span className="hint dp-sub">{w?.ci_evidence ? 'GitHub Actions' : 'Simulated CI'}</span>
                      </td>
                      <td><CiBadge ci={w?.ci_status} /></td>
                      <td>
                        {w?.ci_evidence && w.ci_tests_total != null ? (
                          <>
                            <span className="mono">{`${w.ci_tests_passed ?? 0} / ${w.ci_tests_total}`}</span>
                            <span className="hint dp-sub">real</span>
                          </>
                        ) : tt.length ? (
                          <>
                            <span className="mono">{`${p} / ${tt.length}`}</span>
                            <span className="hint dp-sub">{`${Math.round((p / tt.length) * 100)}%`}</span>
                          </>
                        ) : <span className="hint">—</span>}
                      </td>
```

- [ ] **Step 5: Build the frontend**

Run: `cd apps/control/web && npm run build`
Expected: builds cleanly with no type errors

- [ ] **Step 6: Run the full backend test suite one more time**

Run: `.venv/bin/pytest -q`
Expected: PASS (frontend changes don't touch Python, but this confirms nothing upstream broke across the whole plan)

- [ ] **Step 7: Commit**

```bash
git add apps/control/web/src/pages/build/TestEvidence.tsx apps/control/web/dist
git commit -m "fix: Build & Test Evidence shows real CI results, fix dead Sync Now

Sync Now called refresh() only — it never actually synced anything.
Now calls the same /workspaces/sync-git endpoint Developer Workspaces
already used. Once a workspace has real ci_evidence, CI System/Pipeline/
Open CI Pipeline point at the real GitHub Actions run, and a new 'Real
CI Run' block shows real pass/fail counts above the simulated baseline
panel (relabeled, not removed — both stay visible and clearly badged).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 8: End-to-end verification against the real `advisor-portal-signin` repo

**Files:** none (verification only)

- [ ] **Step 1: Restart the Control Centre server** so it serves the rebuilt frontend

Run: `lsof -ti tcp:8720 | xargs -r kill; ./demo/run_control.sh &`

- [ ] **Step 2: In the browser, open run S7-00003 → Build & Review → Developer Workspaces, click "Sync from Git"**

Expected: toast confirms sync; TASK-001's workspace now carries `ci_evidence` if `advisor-portal-signin`'s `main` branch has the bootstrapped `.github/workflows/s7-ci.yml` (it won't yet, since this repo predates Task 5 — run `gh workflow list --repo AlanLands/advisor-portal-signin` to check; if absent, manually invoke `ci_bootstrap.bootstrap` once via a short Python one-liner against that repo's clone under `artifacts/runs/S7-00003/repos/advisor-portal-signin`, matching what Task 5 will do automatically for every repo connected/created from now on).

- [ ] **Step 3: Push a trivial commit to `advisor-portal-signin`'s `feature/us-1-...` branch** (or wait for the existing push's Actions run to finish) and click "Sync from Git" again

Expected: Developer Workspaces' CI Status column shows the real GitHub Actions conclusion.

- [ ] **Step 4: Open Build & Test Evidence, click "Sync Now"**

Expected: page shows a "Real CI Run" block with real pass/fail counts for TASK-001, "GitHub Actions" in place of "Simulated CI", "Open CI Pipeline" enabled and linking to the real run, and the existing simulated Test Summary panel still visible below, relabeled "Simulated Test Plan (baseline)".

- [ ] **Step 5: Download the Export Evidence ZIP for TASK-001** and confirm `task-evidence.json` inside it now contains a `ci_evidence` key matching what the page showed.

- [ ] **Step 6: Report back** — screenshot both pages, confirm to the user whether the real CI run reflects the actual `advisor-portal-signin` test suite outcome (pass/fail), since this is the first time this exact workflow has run against that repo's real code.
