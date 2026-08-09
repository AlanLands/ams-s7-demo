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
    that — it must not fail the repo connect/create action).

    Idempotent: if the workflow file already exists with identical content,
    returns immediately without git operations."""
    if stack is None or stack not in _WORKFLOWS:
        return "unsupported_stack"
    workflow_dir = repo_dir / ".github" / "workflows"
    workflow_path = workflow_dir / "s7-ci.yml"
    workflow_content = _WORKFLOWS[stack]

    # Idempotent short-circuit: if workflow already exists with identical content, return
    if workflow_path.exists():
        existing = workflow_path.read_text(encoding="utf-8")
        if existing == workflow_content:
            return f"bootstrapped:{stack}"

    workflow_dir.mkdir(parents=True, exist_ok=True)
    workflow_path.write_text(workflow_content, encoding="utf-8")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
    _git(repo_dir, "add", ".github/workflows/s7-ci.yml")
    _git(repo_dir, *ident, "commit", "-qm", "s7: bootstrap CI workflow")
    _git(repo_dir, "push", "-q", "origin", f"HEAD:refs/heads/{default_branch}")
    return f"bootstrapped:{stack}"
