# Artifact Export & Delivery Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Once a plan is signed off, each story becomes a portable, per-team markdown package — not JSON — and that package reaches a developer's real local clone via a disposable git branch (or a no-side-effects zip), never by automating a merge into anyone's working branch.

**Architecture:** Sub-project C (artifact plane) and D (delivery handoff) from `docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md` §C–§D. A new pure-function module (`artifact_export.py`) renders story packages; three new engine actions move them through export → local commit → push, each its own explicit, human-triggered step with its own precondition, mirroring the mutation discipline every existing engine action already follows.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, plain `subprocess` git, stdlib `zipfile`, vanilla JS UI, pytest.

## Global Constraints

- **Hard rule 4, the load-bearing one for this plan: no `.claude/`-specific output.** No `skills/`, `agents/`, `hooks/`, `.mcp.json`, `settings.json`. Exported artifacts are plain markdown in this repo's own `AGENTS.md` convention — readable by any coding agent or any human, not bound to any one tool.
- **The delivery branch is always `delivery/<run_id>`, never a repo's default branch.** Enforced by construction (the branch name always carries the `delivery/` prefix) *and* by an explicit runtime assertion — not convention alone.
- **Merging the delivery branch into a developer's own working branch is never automated by this system.** UI copy states this plainly wherever a push happens.
- **`stories.json` stays the engine's internal state format.** Every existing renderer, validator, and gate keeps reading it unchanged. The export is additive — a new, human-facing deliverable — not a replacement.
- **No new dependencies.** `zipfile` is stdlib.
- **All tests offline.** No network, no real GitHub calls, ever. Local git fixtures via `git init`/local paths, exactly as `tests/test_factory_repos.py` already does. Pushing to a local non-bare repo on a different branch than the one it has checked out is safe and git-native — no bare repo needed for tests.
- **Run the full suite (`.venv/bin/pytest -q`) before every commit.**
- Every new engine action follows: role check → precondition → store write / git operation → provenance record + activity event.
- `CLAUDE.md` and `AGENTS.md` must be updated in the same commit (Task 7).

## File Structure

| File | Responsibility |
|---|---|
| `s7_delivery/factory/artifact_export.py` (create) | Pure rendering: `render_story_package`, `story_folder_name` |
| `s7_delivery/factory/engine.py` (modify) | `planning_export_artifacts`, `planning_write_to_clone`, `planning_push_delivery_branch`, `_story_target_architecture` |
| `s7_delivery/factory/roles.py` (modify) | Three new permissions |
| `apps/control/server.py` (modify) | Four new routes (export, write-to-clone, push, zip download) |
| `apps/control/static/app.js` (modify) | Export/write/push buttons and zip link on the Plan Sign-off page |
| `tests/test_artifact_export.py` (create) | Task 1 tests |
| `tests/test_planning_handoff.py` (create) | Task 2, 3, 4 tests |
| `tests/test_control_api.py` (modify) | Task 5 test |

---

### Task 1: Story package rendering — pure functions

**Files:**
- Create: `s7_delivery/factory/artifact_export.py`
- Test: `tests/test_artifact_export.py`

**Interfaces:**
- Produces: `story_folder_name(story: dict) -> str` (e.g. `"US-001-add-disability-claim-submission-endpoint"`); `render_story_package(story: dict, repo_architecture_md: str) -> dict[str, str]` returning exactly the keys `"AGENTS.md"`, `"acceptance-criteria.md"`, `"context.md"`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_artifact_export.py
"""Per-story artifact rendering — pure functions, offline."""
from s7_delivery.factory.artifact_export import (
    render_acceptance_criteria_md,
    render_agents_md,
    render_story_package,
    story_folder_name,
)

STORY = {
    "story_id": "US-1",
    "title": "Add disability claim submission endpoint",
    "purpose": "Introduce an endpoint for sponsors to submit disability claims.",
    "accountable_team": "Services Team",
    "target_application": "maplesure-claims-api",
    "target_repository": "maplesure-claims-api",
    "target_component": "main.py",
    "acceptance_criteria": [
        {"ac_id": "US-1-AC1", "text": "Given an authenticated sponsor, when they submit a claim, then it is stored."},
        {"ac_id": "US-1-AC2", "text": "Given a duplicate submission, when resubmitted, then it is rejected."},
    ],
    "dependencies": [],
    "feature_flag": {"name": "enable_claim_submission"},
    "rollback_plan": {"method": "Remove the new endpoint from main.py"},
    "task_type": "feature",
    "estimate": 5,
}


def test_story_folder_name_slugifies_title():
    assert story_folder_name(STORY) == "US-1-add-disability-claim-submission-endpoint"


def test_story_folder_name_handles_punctuation():
    messy = dict(STORY, title="Fix: claim's status (v2)!")
    assert story_folder_name(messy) == "US-1-fix-claim-s-status-v2"


def test_render_agents_md_contains_key_fields():
    text = render_agents_md(STORY)
    assert "US-1 — Add disability claim submission endpoint" in text
    assert "Repository: maplesure-claims-api" in text
    assert "Feature flag: enable_claim_submission" in text
    assert "Rollback plan: Remove the new endpoint from main.py" in text


def test_render_agents_md_handles_missing_flag_and_rollback():
    bare = dict(STORY, feature_flag=None, rollback_plan=None, dependencies=["US-0"])
    text = render_agents_md(bare)
    assert "Feature flag: none" in text
    assert "Rollback plan: none recorded" in text
    assert "Dependencies: US-0" in text


def test_render_acceptance_criteria_md_is_a_checklist():
    text = render_acceptance_criteria_md(STORY)
    assert "- [ ] US-1-AC1: Given an authenticated sponsor" in text
    assert "- [ ] US-1-AC2: Given a duplicate submission" in text


def test_render_story_package_has_three_files():
    pkg = render_story_package(STORY, "# Repository: maplesure-claims-api\n...")
    assert set(pkg) == {"AGENTS.md", "acceptance-criteria.md", "context.md"}
    assert pkg["context.md"] == "# Repository: maplesure-claims-api\n..."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_artifact_export.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 's7_delivery.factory.artifact_export'`

- [ ] **Step 3: Write the module**

```python
# s7_delivery/factory/artifact_export.py
"""Portable, per-story artifact export (spec: requirement-routing-and-
delivery-handoff-design.md §C).

One folder per story, in this repo's own AGENTS.md convention: AGENTS.md
(context), acceptance-criteria.md (checklist), context.md (the target
repo's architecture.md). Vendor-neutral markdown — no `.claude/`-specific
tooling (hard rule 4).
"""
from __future__ import annotations

import re


def _slug(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return slug or "story"


def story_folder_name(story: dict) -> str:
    return f"{story['story_id']}-{_slug(story['title'])}"


def render_agents_md(story: dict) -> str:
    flag = story.get("feature_flag")
    flag_line = flag["name"] if isinstance(flag, dict) and flag.get("name") else "none"
    rollback = story.get("rollback_plan")
    rollback_line = (
        rollback["method"] if isinstance(rollback, dict) and rollback.get("method")
        else "none recorded"
    )
    deps = ", ".join(story.get("dependencies") or []) or "none"
    lines = [
        f"# {story['story_id']} — {story['title']}",
        "",
        "## Purpose",
        story.get("purpose", ""),
        "",
        "## Target",
        f"- Application: {story.get('target_application', '')}",
        f"- Repository: {story.get('target_repository', '')}",
        f"- Component: {story.get('target_component', '')}",
        "",
        "## Delivery details",
        f"- Accountable team: {story.get('accountable_team', '')}",
        f"- Task type: {story.get('task_type', '')}",
        f"- Estimate: {story.get('estimate', 0)} points",
        f"- Dependencies: {deps}",
        f"- Feature flag: {flag_line}",
        f"- Rollback plan: {rollback_line}",
    ]
    return "\n".join(lines) + "\n"


def render_acceptance_criteria_md(story: dict) -> str:
    lines = [f"# Acceptance criteria — {story['story_id']}", ""]
    for ac in story.get("acceptance_criteria", []):
        lines.append(f"- [ ] {ac['ac_id']}: {ac['text']}")
    return "\n".join(lines) + "\n"


def render_story_package(story: dict, repo_architecture_md: str) -> dict[str, str]:
    return {
        "AGENTS.md": render_agents_md(story),
        "acceptance-criteria.md": render_acceptance_criteria_md(story),
        "context.md": repo_architecture_md,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_artifact_export.py -v`
Expected: 6 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/artifact_export.py tests/test_artifact_export.py
git commit -m "feat: portable per-story artifact rendering (AGENTS.md convention)"
```

---

### Task 2: `planning_export_artifacts` — write packages into the run's own tree

**Files:**
- Modify: `s7_delivery/factory/engine.py` (add `_story_target_architecture`, `planning_export_artifacts`, after `edit_story`, ~line 699)
- Modify: `s7_delivery/factory/roles.py` (add `export_artifacts`)
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_planning_handoff.py` (create)

**Interfaces:**
- Consumes: `artifact_export.render_story_package`, `story_folder_name` (Task 1).
- Produces: `Engine.planning_export_artifacts(role)`. Files land at `planning/export/<team-with-dashes>/<story_id>-<slug>/{AGENTS.md,acceptance-criteria.md,context.md}`. No external side effects.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_planning_handoff.py
"""Export → write-to-clone → push, offline. Fixtures are local git repos."""
import subprocess
from pathlib import Path

import pytest

from demo.create_target_repos import API_FILES, write_repo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, IntakeAnalysis, Provenance, Role
from s7_delivery.factory import live_intake


def _fake_analysis(repo_name: str) -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True, business_impact="impact",
        affected_applications=[repo_name],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=[], assumptions=[],
        business_rules=[], risk_register=[], confidence=80,
        provenance=Provenance.LIVE_AI,
    )


def _signed_off_run_with_repo(tmp_path, monkeypatch, repo_name="maplesure-claims-api"):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    src = write_repo(repo_name, API_FILES, tmp_path / "src")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=demo"]
    subprocess.run(["git", "-C", str(src), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(src), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(src), *ident, "commit", "-qm", "init"], check=True)
    eng.intake_connect_repo(Role.DELIVERY_LEAD, str(src))
    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (_fake_analysis(repo_name), {}),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.DELIVERY_LEAD)
    eng.planning_add_story(Role.DELIVERY_LEAD, {
        "title": "Add disability claim submission endpoint",
        "accountable_team": "Services Team",
        "target_component": "main.py",
        "target_repository": repo_name,
        "acceptance_criteria": [
            "Given a sponsor, when they submit a claim, then it is stored."
        ],
    })
    eng.planning_sign_off(Role.BUSINESS_OWNER, "Jordan Hale")
    return eng


STORY_FOLDER = "US-001-add-disability-claim-submission-endpoint"


def test_export_artifacts_writes_team_shaped_folders(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    folder = eng.store.path("planning", "export", "Services-Team", STORY_FOLDER)
    assert (folder / "AGENTS.md").is_file()
    assert (folder / "acceptance-criteria.md").is_file()
    assert (folder / "context.md").is_file()
    assert "What this application does NOT do" in (folder / "context.md").read_text()


def test_export_artifacts_before_signoff_is_an_error(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="sign"):
        eng.planning_export_artifacts(Role.DELIVERY_LEAD)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -v`
Expected: FAIL — `planning_export_artifacts` does not exist.

- [ ] **Step 3: Implement**

`roles.py` — under `# planning`:

```python
    "export_artifacts": {Role.DELIVERY_LEAD, Role.PRODUCT_ANALYST, Role.ENGINEERING_LEAD},
```

`engine.py` — after `edit_story` (before `_planning_generate_live`):

```python
    def _story_target_architecture(self, story: dict) -> str:
        """Read architecture.md straight from the story's target repo's own
        clone — not parsed out of the merged context pack (spec §C1)."""
        path = self.store.path("repos", story["target_repository"], "architecture.md")
        if not path.is_file():
            raise EngineError(
                f"No architecture.md found for {story['target_repository']!r} — "
                "is it connected?"
            )
        return path.read_text(encoding="utf-8")

    def planning_export_artifacts(self, role: Role) -> None:
        """§C2: write each signed-off story's portable package into the
        run's own artifact tree. No external side effects."""
        roles.require("export_artifacts", role)
        if not self.run().plan_locked:
            raise EngineError("Export artifacts after the plan is signed off")
        from s7_delivery.factory.artifact_export import render_story_package, story_folder_name

        exported = 0
        for story in self._stories():
            arch = self._story_target_architecture(story)
            package = render_story_package(story, arch)
            folder = story_folder_name(story)
            team_dir = story["accountable_team"].replace(" ", "-")
            for filename, content in package.items():
                self.store.write_text(content, "planning", "export", team_dir, folder, filename)
            self._record(
                artifact_id=f"EXPORT-{story['story_id']}", artifact_type="export",
                payload={"files": sorted(package)}, author=role.value,
                stage=Stage.PLANNING, action="export", outcome="created",
                inputs=[story["story_id"]],
            )
            exported += 1
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="artifact-export", outcome="created",
            details=f"{exported} story packages exported",
        )
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/planning/export-artifacts")
def post_export_artifacts(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.planning_export_artifacts(_role(body.role))
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -v`
Expected: 2 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_planning_handoff.py
git commit -m "feat: planning_export_artifacts — team-shaped portable packages"
```

---

### Task 3: `planning_write_to_clone` — local commit into the target repo

**Files:**
- Modify: `s7_delivery/factory/engine.py` (add `planning_write_to_clone`, after `planning_export_artifacts`)
- Modify: `s7_delivery/factory/roles.py` (add `write_delivery_clone`)
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_planning_handoff.py` (append)

**Interfaces:**
- Produces: `Engine.planning_write_to_clone(role)`. Copies each story's exported folder into `<clone>/delivery/<story_id>-<slug>/`, commits locally (idempotent — a re-run with no changes does not fail), and records `planning/delivery/<repo-name>.json`: `{"committed": true, "commit_sha": "<sha>"}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planning_handoff.py`:

```python
def test_write_to_clone_commits_locally_no_push(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)

    clone_dir = eng.store.path("repos", "maplesure-claims-api")
    assert (clone_dir / "delivery" / STORY_FOLDER / "AGENTS.md").is_file()
    log = subprocess.run(
        ["git", "-C", str(clone_dir), "log", "--oneline", "-1"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Delivery artifacts" in log

    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["committed"] is True
    assert marker["commit_sha"]


def test_write_to_clone_before_export_is_an_error(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    with pytest.raises(EngineError, match="export"):
        eng.planning_write_to_clone(Role.DELIVERY_LEAD)


def test_write_to_clone_is_idempotent(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    first = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)  # re-run, no new changes
    second = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert first["commit_sha"] == second["commit_sha"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -k write_to_clone -v`
Expected: FAIL — `planning_write_to_clone` does not exist.

- [ ] **Step 3: Implement**

`roles.py` — under `# planning`:

```python
    "write_delivery_clone": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
```

`engine.py` — after `planning_export_artifacts`:

```python
    def planning_write_to_clone(self, role: Role) -> None:
        """§D1: copy each story's exported folder into its target repo's
        own clone and commit locally. No push — fully reversible."""
        roles.require("write_delivery_clone", role)
        import subprocess

        from s7_delivery.factory.artifact_export import story_folder_name

        stories = self._stories()
        by_repo: dict[str, list[dict]] = {}
        for story in stories:
            by_repo.setdefault(story["target_repository"], []).append(story)

        for repo_name, repo_stories in by_repo.items():
            clone_dir = self.store.path("repos", repo_name)
            if not clone_dir.is_dir():
                raise EngineError(f"No clone found for {repo_name!r}")
            delivery_dir = clone_dir / "delivery"
            for story in repo_stories:
                team_dir = story["accountable_team"].replace(" ", "-")
                folder = story_folder_name(story)
                export_dir = self.store.path("planning", "export", team_dir, folder)
                if not export_dir.is_dir():
                    raise EngineError(
                        f"Story {story['story_id']} has no exported package — "
                        "run export-artifacts first"
                    )
                target = delivery_dir / folder
                target.mkdir(parents=True, exist_ok=True)
                for src_file in export_dir.iterdir():
                    (target / src_file.name).write_text(
                        src_file.read_text(encoding="utf-8"), encoding="utf-8"
                    )
            ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
            status = subprocess.run(
                ["git", "-C", str(clone_dir), "status", "--porcelain"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            if status:
                subprocess.run(
                    ["git", "-C", str(clone_dir), "add", "-A"],
                    check=True, capture_output=True,
                )
                subprocess.run(
                    ["git", "-C", str(clone_dir), *ident, "commit", "-qm",
                     f"Delivery artifacts for {self.run_id}"],
                    check=True, capture_output=True,
                )
            commit_sha = subprocess.run(
                ["git", "-C", str(clone_dir), "rev-parse", "HEAD"],
                check=True, capture_output=True, text=True,
            ).stdout.strip()
            self.store.write_json(
                {"committed": True, "commit_sha": commit_sha},
                "planning", "delivery", f"{repo_name}.json",
            )
            self._record(
                artifact_id=f"DELIVERY-{repo_name}", artifact_type="delivery_commit",
                payload={"repo": repo_name, "commit_sha": commit_sha},
                author=role.value, stage=Stage.PLANNING, action="write-to-clone",
                outcome="created", inputs=[s["story_id"] for s in repo_stories],
            )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="delivery-write-to-clone", outcome="created",
            details=f"{len(by_repo)} repositories committed locally",
        )
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/planning/write-to-clone")
def post_write_to_clone(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.planning_write_to_clone(_role(body.role))
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -k write_to_clone -v`
Expected: 3 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_planning_handoff.py
git commit -m "feat: planning_write_to_clone — local, idempotent, reversible delivery commit"
```

---

### Task 4: `planning_push_delivery_branch` — the approval-gated push

**Files:**
- Modify: `s7_delivery/factory/engine.py` (add `planning_push_delivery_branch`, after `planning_write_to_clone`)
- Modify: `s7_delivery/factory/roles.py` (add `push_delivery_branch`)
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_planning_handoff.py` (append)

**Interfaces:**
- Produces: `Engine.planning_push_delivery_branch(role, repo_name: str)`. Pushes `HEAD:refs/heads/delivery/<run_id>` to `origin`; updates the repo's `planning/delivery/<repo>.json` marker with `pushed: true`, `branch`, `pushed_at`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_planning_handoff.py`:

```python
def test_push_delivery_branch_creates_new_branch_never_default(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")

    src = tmp_path / "src" / "maplesure-claims-api"
    branch = f"delivery/{eng.run_id}"
    branches = subprocess.run(
        ["git", "-C", str(src), "branch", "--list", branch],
        check=True, capture_output=True, text=True,
    ).stdout
    assert branch in branches

    # The default branch's own log is untouched — the push never landed there.
    default_log = subprocess.run(
        ["git", "-C", str(src), "log", "--oneline", "-1"],
        check=True, capture_output=True, text=True,
    ).stdout
    assert "Delivery artifacts" not in default_log

    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["pushed"] is True
    assert marker["branch"] == branch


def test_push_delivery_branch_without_local_commit_is_an_error(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    with pytest.raises(EngineError, match="write to the clone"):
        eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")


def test_push_delivery_branch_failure_is_reported_and_retry_safe(tmp_path, monkeypatch):
    eng = _signed_off_run_with_repo(tmp_path, monkeypatch)
    eng.planning_export_artifacts(Role.DELIVERY_LEAD)
    eng.planning_write_to_clone(Role.DELIVERY_LEAD)
    # Break the remote to force a push failure.
    clone_dir = eng.store.path("repos", "maplesure-claims-api")
    subprocess.run(
        ["git", "-C", str(clone_dir), "remote", "set-url", "origin", "/no/such/path"],
        check=True,
    )
    with pytest.raises(EngineError, match="[Pp]ush"):
        eng.planning_push_delivery_branch(Role.DELIVERY_LEAD, "maplesure-claims-api")
    # The local commit from write-to-clone is untouched — retry-safe.
    marker = eng.store.read_json("planning", "delivery", "maplesure-claims-api.json")
    assert marker["committed"] is True
    assert "pushed" not in marker
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -k push_delivery -v`
Expected: FAIL — `planning_push_delivery_branch` does not exist.

- [ ] **Step 3: Implement**

`roles.py` — under `# planning`:

```python
    "push_delivery_branch": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
```

`engine.py` — after `planning_write_to_clone`:

```python
    def planning_push_delivery_branch(self, role: Role, repo_name: str) -> None:
        """§D2: push this run's committed delivery branch to the real
        remote. Never the default branch — the ref is always
        refs/heads/delivery/<run_id>, asserted below, not just implied by
        the f-string. Merging it into a developer's own working branch is
        never automated by this system."""
        roles.require("push_delivery_branch", role)
        import subprocess

        marker = self.store.read_json_or(None, "planning", "delivery", f"{repo_name}.json")
        if marker is None or not marker.get("committed"):
            raise EngineError(
                f"No local delivery commit for {repo_name!r} — write to the clone first"
            )
        clone_dir = self.store.path("repos", repo_name)
        branch = f"delivery/{self.run_id}"
        assert branch.startswith("delivery/"), "delivery branch must never be a bare/default branch name"
        try:
            subprocess.run(
                ["git", "-C", str(clone_dir), "push", "origin", f"HEAD:refs/heads/{branch}"],
                check=True, capture_output=True, text=True,
            )
        except subprocess.CalledProcessError as exc:
            raise EngineError(
                f"Push to {repo_name} failed: {(exc.stderr or str(exc)).strip()}"
            ) from exc
        self.store.write_json(
            {**marker, "pushed": True, "branch": branch, "pushed_at": now_iso()},
            "planning", "delivery", f"{repo_name}.json",
        )
        self._record(
            artifact_id=f"DELIVERY-PUSH-{repo_name}", artifact_type="delivery_push",
            payload={"repo": repo_name, "branch": branch}, author=role.value,
            stage=Stage.PLANNING, action="push", outcome="created",
        )
        self._activity(
            stage=Stage.PLANNING, actor=role.value, actor_type="human",
            workflow="delivery-push", outcome="created",
            details=f"pushed {branch} to {repo_name}",
        )
```

`server.py`:

```python
class PushDeliveryBody(BaseModel):
    role: str
    repo_name: str


@app.post("/api/runs/{run_id}/planning/push-delivery-branch")
def post_push_delivery_branch(run_id: str, body: PushDeliveryBody) -> dict:
    eng = _engine(run_id)
    eng.planning_push_delivery_branch(_role(body.role), body.repo_name)
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_planning_handoff.py -k push_delivery -v`
Expected: 3 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_planning_handoff.py
git commit -m "feat: planning_push_delivery_branch — gated, never the default branch"
```

---

### Task 5: Zip download — the no-side-effects fallback

**Files:**
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_control_api.py` (append)

**Interfaces:**
- Produces: `GET /api/runs/{run_id}/planning/export.zip` — streams a zip of everything under `planning/export/`, preserving the team/story folder structure. Works whether or not §D1/§D2 ever ran.

**Scope note:** this task tests only the zip-serving mechanism (directory → zip stream). Export *content* correctness against a real connected repo is already covered by Task 2's tests — the seeded simulation-mode stories reference fictional repo names (e.g. `sponsorconnect-db`) that are never actually cloned in a simulation run, so running the full `analyse → epic → gate → generate → sign-off → export` pipeline here would fail on `_story_target_architecture`'s "is it connected?" check before writing anything. Seed the export directory directly instead.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_control_api.py`:

```python
def test_export_zip_contains_previously_exported_packages(client, run_id):
    from s7_delivery.factory.engine import Engine

    eng = Engine(run_id)
    eng.store.write_text(
        "# AGENTS.md content\n", "planning", "export", "Services-Team",
        "US-001-story", "AGENTS.md",
    )
    eng.store.write_text(
        "- [ ] AC-1: text\n", "planning", "export", "Services-Team",
        "US-001-story", "acceptance-criteria.md",
    )

    res = client.get(f"/api/runs/{run_id}/planning/export.zip")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/zip"

    import io
    import zipfile
    names = zipfile.ZipFile(io.BytesIO(res.content)).namelist()
    assert "Services-Team/US-001-story/AGENTS.md" in names
    assert "Services-Team/US-001-story/acceptance-criteria.md" in names


def test_export_zip_empty_before_export_is_a_valid_empty_zip(client, run_id):
    res = client.get(f"/api/runs/{run_id}/planning/export.zip")
    assert res.status_code == 200
    import io
    import zipfile
    assert zipfile.ZipFile(io.BytesIO(res.content)).namelist() == []
```

`Engine(run_id)` here relies on the same monkeypatched `store_module.RUNS_ROOT` the `client` fixture already sets — the identical mechanism `apps.control.server._engine()` itself uses.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_control_api.py -k export_zip -v`
Expected: FAIL — 404, no such route.

- [ ] **Step 3: Implement**

`server.py` — add to the imports:

```python
import io
import zipfile

from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
```

(This replaces the existing `from fastapi.responses import FileResponse, JSONResponse` line — add `StreamingResponse` to it.)

Add the route after the sign-off route:

```python
@app.get("/api/runs/{run_id}/planning/export.zip")
def get_export_zip(run_id: str) -> StreamingResponse:
    eng = _engine(run_id)
    root = eng.store.path("planning", "export")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if root.is_dir():
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root))
    buf.seek(0)
    return StreamingResponse(
        buf, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}-delivery-export.zip"'},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_control_api.py -k export_zip -v`
Expected: 2 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add apps/control/server.py tests/test_control_api.py
git commit -m "feat: zip download — no-side-effects delivery handoff fallback"
```

---

### Task 6: UI — export, write-to-clone, push, and zip download on Plan Sign-off

No JS test harness exists in this repo; verified by driving the app in Chrome/curl (Step 4). Follow the existing style: `el()` builders, `act(path, body, okMessage)`.

**Files:**
- Modify: `apps/control/static/app.js` (`renderPlanSignoff`, ~lines 1516–1584)

**Interfaces:**
- Consumes: `run.plan_locked`, `planning.stories` (for repo names to push per), routes from Tasks 2–5.

- [ ] **Step 1: Add a delivery-handoff card**

`renderPlanSignoff` already declares `const stories = planningStories();` near its top (do not redeclare it — a second `const stories` in the same function is a `SyntaxError`). After the `history` card is built and before the `return el("section", ...)`, add:

```js
    const repoNames = [...new Set(stories.map((s) => s.target_repository))];
    const handoffCard = plan ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Delivery Handoff" }),
        el("span", { class: "hint", text: "Portable, per-team packages — no .claude/ tooling" })),
      el("div", { class: "actions-row", style: "gap:8px; flex-wrap:wrap" },
        el("button", {
          class: "outline", text: "Export Artifacts",
          onclick: () => act("/planning/export-artifacts", {}, "Artifacts exported"),
        }),
        el("button", {
          class: "outline", text: "Write to Clone",
          onclick: () => act("/planning/write-to-clone", {}, "Committed locally to each target repo"),
        }),
        el("button", {
          class: "outline", text: "⬇ Download Zip",
          onclick: () => { window.location.href = `${API}/api/runs/${state.runId}/planning/export.zip`; },
        })),
      el("p", { class: "hint", style: "margin-top:10px", text:
        "Pushing creates delivery/" + state.runId + " on each target repo — a fresh, disposable branch, never the default branch. Merging it into your own working branch is a manual step; nothing here does that for you." }),
      el("div", { class: "actions-row", style: "gap:8px; flex-wrap:wrap; margin-top:8px" },
        ...repoNames.map((repo) => el("button", {
          class: "primary sq", text: `Push delivery branch → ${repo}`,
          onclick: () => act("/planning/push-delivery-branch", { repo_name: repo }, `Pushed to ${repo}`),
        }))),
    ) : null;
```

- [ ] **Step 2: Insert into the returned layout**

The current return statement reads:

```js
    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Plan Sign-off (Gate 1)" }),
          el("span", { class: "hint", text: "Review and approve the plan to lock it and proceed to execution." })),
        readiness,
        el("div", { style: "margin-top:14px" }, history),
        el("div", { style: "margin-top:14px" }, artifactsCard(true)),
      ),
      el("aside", { class: "rail" }, gate1Rail()),
    );
```

Add `handoffCard` after `history`, before `artifactsCard`:

```js
    return el("section", { class: "page-with-rail" },
      el("div", {},
        el("div", { class: "page-head", style: "margin-bottom:16px" },
          el("h2", { text: "Plan Sign-off (Gate 1)" }),
          el("span", { class: "hint", text: "Review and approve the plan to lock it and proceed to execution." })),
        readiness,
        el("div", { style: "margin-top:14px" }, history),
        handoffCard ? el("div", { style: "margin-top:14px" }, handoffCard) : null,
        el("div", { style: "margin-top:14px" }, artifactsCard(true)),
      ),
      el("aside", { class: "rail" }, gate1Rail()),
    );
```

- [ ] **Step 3: Verify by driving the app**

```bash
lsof -ti:8720 | xargs -r kill 2>/dev/null
set -a; source .env 2>/dev/null; set +a
LLM_MODE=replay .venv/bin/uvicorn apps.control.server:app --port 8720 &
```

1. Create a run, sign off a plan (simulation mode is fine — the handoff mechanics don't require live mode).
2. On Plan Sign-off, click "Export Artifacts" → "Write to Clone" (this requires a connected repo clone to exist under the run's artifact tree, which simulation mode never creates — this beat needs a **live** run with at least one connected repo; verify with a live run instead, following the same repo-connect steps as the prior plan's rehearsal). Confirm the delivery folder appears under the clone and no error is raised on a second click (idempotency).
3. Click "⬇ Download Zip" → confirm a zip downloads with `AGENTS.md`/`acceptance-criteria.md` files inside.
4. Click "Push delivery branch → \<repo\>" only against a repo you are prepared to see a real branch pushed to (Task 7's rehearsal covers this deliberately; for this UI smoke test it is enough to confirm the button fires the request and a specific, readable error/success message renders — a real push is not required to verify the UI wiring).
5. Kill the server.

- [ ] **Step 4: Commit**

```bash
git add apps/control/static/app.js
git commit -m "feat(ui): delivery handoff — export, write-to-clone, push, zip download"
```

---

### Task 7: Docs and rehearsal

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md` (mirrored, same commit), `README.md`, `docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md` (status line, this plan's sections only)

- [ ] **Step 1: Update the docs**

- `CLAUDE.md`/`AGENTS.md`: one paragraph noting that signed-off plans now export a portable, per-team, per-story markdown package (`AGENTS.md` convention, no `.claude/` tooling — hard rule 4 held deliberately) and can reach a real developer clone via a disposable `delivery/<run_id>` branch push or a no-side-effects zip download; merging into a working branch stays a manual, human action.
- `README.md`: extend the "Live mode" / rehearsal section with the export → write-to-clone → push beats.
- Spec file: mark §C and §D as `implemented`.

- [ ] **Step 2: Rehearsal (manual, one real branch push against an already-connected repo)**

⚠️ This step pushes one real, disposable branch (`delivery/<run_id>`) to one of the two already-connected MapleSure repos on GitHub. It is genuinely disposable — a fresh branch, never the default branch — and can be deleted from GitHub afterward if not wanted.

With `LLM_MODE=record` (or simulation mode, since the handoff mechanics do not depend on live analysis): create a run through a signed-off plan against `maplesure-claims-api`, export artifacts, write to clone, and push the delivery branch for real. Confirm on GitHub that `delivery/<run_id>` exists on `maplesure-claims-api` and that the repo's default branch is untouched. Then confirm the zip download works identically regardless of mode.

- [ ] **Step 3: Full suite + ruff, commit**

```bash
.venv/bin/pytest -q
ruff check s7_delivery/factory/artifact_export.py s7_delivery/factory/engine.py apps/control/server.py tests/test_artifact_export.py tests/test_planning_handoff.py tests/test_control_api.py
git add CLAUDE.md AGENTS.md README.md docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md
git commit -m "docs: artifact export and delivery handoff — status, runbook"
```
