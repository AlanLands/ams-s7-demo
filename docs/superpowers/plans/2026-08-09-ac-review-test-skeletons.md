# AC Review Checkpoint + Stack-Aware Test Skeletons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before a delivery pack can be published, generate rule-based test skeletons from each story's acceptance criteria, require a QA Lead approval of the test plan, publish the skeletons at a governed runnable path so S7 CI produces a real red baseline, and sync per-test CI results back into per-AC evidence.

**Architecture:** A new `factory/test_skeletons.py` module renders deterministic pytest/JUnit skeletons (one test per AC, shared name-derivation with `simulate.py`). The `DeliveryPack` record gains `test_plan_status`; `delivery_pack_publish` 409s until a new `test_plan_approve` engine action (QA Lead) approves it. `publication.py` gains two governed test roots. The bootstrapped CI workflows emit per-test results; `workspaces_sync_git` captures the publication commit's CI run as a red baseline and joins per-test outcomes into task test records.

**Tech Stack:** Python 3.11, pydantic models, FastAPI (`apps/control/server.py`), React+TS+Vite (`apps/control/web`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-09-ac-review-test-skeletons-design.md`

## Global Constraints

- Skeleton generation is **rule-based, deterministic, no LLM call** — badged/labelled `RULE_BASED`, never "AI" (spec; CLAUDE.md § Staged output).
- Simulation mode must stay fully offline: all existing tests green with no API key; simulation publish stays a pseudo-commit.
- Publication may only ever write under managed roots: `AGENTS.md`, `.s7/`, `tests/s7/`, `src/test/java/s7/` — never developer source.
- Any change under `apps/control/web/src/` must be followed by `npm run build` and the regenerated `apps/control/web/dist/` committed **in the same commit** (CLAUDE.md hard rule 4).
- CLAUDE.md and AGENTS.md must be updated **in the same commit** when scope/behavior descriptions change.
- No client names anywhere; fiction is MapleSure (hard rule 2).
- Commits end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

---

### Task 1: `test_skeletons.py` — shared test names + pytest renderer + manifest

**Files:**
- Create: `s7_delivery/factory/test_skeletons.py`
- Test: `tests/test_factory_test_skeletons.py`

**Interfaces:**
- Produces (used by Tasks 2–4, 7, 9):
  - `slug_test_name(text: str) -> str` — `"test_<slug>"`, exact same slugging as today's `simulate._test_name` fallback (lowercase, non-alnum→`_`, first 48 chars of the slugged AC text, collapse `__`, strip `_`).
  - `pytest_file_name(story_id: str) -> str` — `"test_us_1.py"` for `"US-1"`.
  - `render_pytest(story: dict) -> dict[str, str]` — `{filename: content}`, one failing test per AC.
  - `render_story_tests(story: dict, stack: str | None) -> tuple[dict[str, str], dict]` — `(files, manifest)`; manifest is `{"story_id", "stack", "runnable", "provenance": "rule_based", "generated_at", "tests": [{"ac_id", "test_name", "file"}]}`. (JUnit branch lands in Task 2; for now any non-`"pytest"` stack renders pytest files with `runnable=False`.)
- Story dict shape (existing): `{"story_id": "US-1", "title": ..., "acceptance_criteria": [{"ac_id": "US-1-AC1", "text": "..."}], ...}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_factory_test_skeletons.py
"""Rule-based test skeletons: deterministic, one failing test per AC,
names shared with the simulated lane so evidence joins by name."""

from s7_delivery.factory import test_skeletons as ts

STORY = {
    "story_id": "US-1",
    "title": "Establish project with initial build pipeline",
    "acceptance_criteria": [
        {"ac_id": "US-1-AC1", "text": "Given the repository, when checked, then it should build"},
        {"ac_id": "US-1-AC2", "text": "Given a push to the main branch, when checked, then CI runs"},
    ],
}


def test_slug_name_matches_simulate_fallback():
    from s7_delivery.factory.simulate import _test_name
    text = "Given the repository, when checked, then it should build"
    assert ts.slug_test_name(text) == _test_name("US-9", "US-9-AC1", text, scripted=False)


def test_pytest_file_name():
    assert ts.pytest_file_name("US-1") == "test_us_1.py"


def test_render_pytest_one_failing_test_per_ac():
    files = ts.render_pytest(STORY)
    assert list(files) == ["test_us_1.py"]
    content = files["test_us_1.py"]
    assert content.count("def test_") == 2
    assert "US-1-AC1" in content and "US-1-AC2" in content
    assert content.count('pytest.fail("Not implemented:') == 2


def test_render_pytest_is_deterministic():
    assert ts.render_pytest(STORY) == ts.render_pytest(STORY)


def test_render_story_tests_manifest():
    files, manifest = ts.render_story_tests(STORY, "pytest")
    assert manifest["story_id"] == "US-1"
    assert manifest["stack"] == "pytest"
    assert manifest["runnable"] is True
    assert manifest["provenance"] == "rule_based"
    assert [t["ac_id"] for t in manifest["tests"]] == ["US-1-AC1", "US-1-AC2"]
    assert all(t["file"] == "test_us_1.py" for t in manifest["tests"])
    assert all(t["test_name"].startswith("test_") for t in manifest["tests"])
    assert set(files) == {"test_us_1.py"}


def test_unknown_stack_renders_reference_only():
    files, manifest = ts.render_story_tests(STORY, None)
    assert manifest["runnable"] is False
    assert manifest["stack"] == ""
    assert set(files) == {"test_us_1.py"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/alanlands/Documents/ams-s7-demo && python -m pytest tests/test_factory_test_skeletons.py -v`
Expected: FAIL — `ModuleNotFoundError` / `AttributeError` (module doesn't exist).

- [ ] **Step 3: Write the implementation**

```python
# s7_delivery/factory/test_skeletons.py
"""Rule-based test skeletons derived from acceptance criteria.

Deterministic and non-AI by design: the skeleton is a red baseline —
one failing test per acceptance criterion — that publishes with the
delivery pack so the developer starts from real red and CI evidence
joins per-AC by test name. Badged RULE_BASED wherever shown; presenting
a heuristic as AI output is the mislabelling CLAUDE.md § Staged output
forbids. Name derivation is shared with simulate.py so simulated and
real evidence always agree on names.
"""

from __future__ import annotations

from s7_delivery.factory.models import now_iso

RULE_BASED = "rule_based"


def slug_test_name(text: str) -> str:
    """`test_<slug>` from AC text — the single source of truth for
    AC-derived test names (simulate.py delegates here)."""
    slug = "".join(c if c.isalnum() else "_" for c in text.lower())[:48].strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"test_{slug}"


def _story_slug(story_id: str) -> str:
    return story_id.lower().replace("-", "_")


def pytest_file_name(story_id: str) -> str:
    return f"test_{_story_slug(story_id)}.py"


def render_pytest(story: dict) -> dict[str, str]:
    """One pytest file per story, one deliberately-failing test per AC."""
    lines = [
        f'"""Acceptance tests for {story["story_id"]} — {story.get("title", "")}',
        "",
        "Generated by S7 (rule-based) as the red baseline. Implement the",
        "behaviour, then replace each pytest.fail with real assertions —",
        "keep the test names: CI evidence joins to acceptance criteria by",
        'name."""',
        "import pytest",
        "",
    ]
    for ac in story.get("acceptance_criteria", []):
        lines += [
            "",
            f"def {slug_test_name(ac['text'])}():",
            f'    """{ac["ac_id"]}: {ac["text"]}"""',
            f'    pytest.fail("Not implemented: {ac["ac_id"]}")',
        ]
    return {pytest_file_name(story["story_id"]): "\n".join(lines) + "\n"}


def render_story_tests(story: dict, stack: str | None) -> tuple[dict[str, str], dict]:
    """(files, manifest) for one story. Unknown stacks still render
    pytest-style files, marked non-runnable (reference only)."""
    runnable = stack == "pytest"
    files = render_pytest(story)
    manifest = {
        "story_id": story["story_id"],
        "stack": stack or "",
        "runnable": runnable,
        "provenance": RULE_BASED,
        "generated_at": now_iso(),
        "tests": [
            {
                "ac_id": ac["ac_id"],
                "test_name": slug_test_name(ac["text"]),
                "file": next(iter(files)),
            }
            for ac in story.get("acceptance_criteria", [])
        ],
    }
    return files, manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factory_test_skeletons.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/test_skeletons.py tests/test_factory_test_skeletons.py
git commit -m "feat: rule-based test skeletons from acceptance criteria (pytest)

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: JUnit renderer + stack resolution

**Files:**
- Modify: `s7_delivery/factory/test_skeletons.py`
- Test: `tests/test_factory_test_skeletons.py` (append)

**Interfaces:**
- Produces (used by Tasks 4, 7):
  - `junit_class_name(story_id: str) -> str` — `"US1AcceptanceTest"` for `"US-1"`.
  - `render_junit(story: dict) -> dict[str, str]` — `{"US1AcceptanceTest.java": content}`, package `s7`, one failing `@Test` per AC, **method names identical to the pytest names** (snake_case is legal Java; identical names are what makes CI-evidence joins stack-agnostic).
  - `resolve_stack(repo: dict | None, repo_dir) -> str | None` — `"pytest"`/`"maven"` from the repo record's `ci_bootstrap_status` (`"bootstrapped:pytest"`), falling back to `ci_bootstrap.detect_stack_from_files(repo_dir)` when the dir exists, else `None`.
  - `runnable_root(stack: str) -> str` — `"tests/s7"` for pytest, `"src/test/java/s7"` for maven.
  - `render_story_tests` now returns JUnit files for `stack == "maven"` (runnable), pytest files otherwise (runnable only for `"pytest"`).
- Consumes: `ci_bootstrap.detect_stack_from_files(repo_dir: Path) -> str | None` (exists).

- [ ] **Step 1: Write the failing tests (append to the test file)**

```python
def test_junit_class_name():
    assert ts.junit_class_name("US-1") == "US1AcceptanceTest"


def test_render_junit_one_failing_test_per_ac():
    files = ts.render_junit(STORY)
    assert list(files) == ["US1AcceptanceTest.java"]
    content = files["US1AcceptanceTest.java"]
    assert "package s7;" in content
    assert content.count("@Test") == 2
    assert content.count('fail("Not implemented:') == 2
    # method names identical to the pytest names — the join key
    assert ts.slug_test_name(STORY["acceptance_criteria"][0]["text"]) in content


def test_render_story_tests_maven_is_runnable_junit():
    files, manifest = ts.render_story_tests(STORY, "maven")
    assert set(files) == {"US1AcceptanceTest.java"}
    assert manifest["runnable"] is True and manifest["stack"] == "maven"


def test_runnable_root():
    assert ts.runnable_root("pytest") == "tests/s7"
    assert ts.runnable_root("maven") == "src/test/java/s7"


def test_resolve_stack_prefers_bootstrap_record(tmp_path):
    assert ts.resolve_stack({"ci_bootstrap_status": "bootstrapped:maven"}, tmp_path) == "maven"
    assert ts.resolve_stack({"ci_bootstrap_status": "unsupported_stack"}, tmp_path) is None
    (tmp_path / "requirements.txt").write_text("pytest\n")
    assert ts.resolve_stack({}, tmp_path) == "pytest"
    assert ts.resolve_stack(None, tmp_path / "missing") is None
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `python -m pytest tests/test_factory_test_skeletons.py -v`
Expected: the six new tests FAIL (`AttributeError`), Task 1's still pass.

- [ ] **Step 3: Implement (add to `test_skeletons.py`)**

```python
from pathlib import Path


def junit_class_name(story_id: str) -> str:
    return "".join(p for p in story_id.split("-") if p) + "AcceptanceTest"


def render_junit(story: dict) -> dict[str, str]:
    """One JUnit 5 class per story, package `s7`, one failing @Test per AC.
    Method names deliberately match the pytest names (snake_case) so CI
    evidence joins per-AC identically on both stacks."""
    name = junit_class_name(story["story_id"])
    lines = [
        "package s7;",
        "",
        "import org.junit.jupiter.api.Test;",
        "import static org.junit.jupiter.api.Assertions.fail;",
        "",
        f"/** Acceptance tests for {story['story_id']} — {story.get('title', '')}.",
        " * Generated by S7 (rule-based) as the red baseline. Implement the",
        " * behaviour, then replace each fail(...) with real assertions —",
        " * keep the method names: CI evidence joins to acceptance criteria",
        " * by name. */",
        f"class {name} {{",
    ]
    for ac in story.get("acceptance_criteria", []):
        lines += [
            "",
            "    @Test",
            f"    void {slug_test_name(ac['text'])}() {{",
            f"        // {ac['ac_id']}: {ac['text']}",
            f'        fail("Not implemented: {ac["ac_id"]}");',
            "    }",
        ]
    lines += ["}", ""]
    return {f"{name}.java": "\n".join(lines)}


def runnable_root(stack: str) -> str:
    return {"pytest": "tests/s7", "maven": "src/test/java/s7"}[stack]


def resolve_stack(repo: dict | None, repo_dir: Path | None) -> str | None:
    """The connected repo's stack: the bootstrap record first (it already
    made this call at connect time), file detection second, None when
    neither knows — never a guess."""
    status = (repo or {}).get("ci_bootstrap_status", "")
    if status.startswith("bootstrapped:"):
        stack = status.split(":", 1)[1]
        return stack if stack in ("pytest", "maven") else None
    if repo_dir is not None and Path(repo_dir).is_dir():
        from s7_delivery.factory.ci_bootstrap import detect_stack_from_files
        return detect_stack_from_files(Path(repo_dir))
    return None
```

Then change `render_story_tests` to use JUnit for maven:

```python
def render_story_tests(story: dict, stack: str | None) -> tuple[dict[str, str], dict]:
    """(files, manifest) for one story. Unknown stacks still render
    pytest-style files, marked non-runnable (reference only)."""
    runnable = stack in ("pytest", "maven")
    files = render_junit(story) if stack == "maven" else render_pytest(story)
    manifest = {
        "story_id": story["story_id"],
        "stack": stack or "",
        "runnable": runnable,
        "provenance": RULE_BASED,
        "generated_at": now_iso(),
        "tests": [
            {
                "ac_id": ac["ac_id"],
                "test_name": slug_test_name(ac["text"]),
                "file": next(iter(files)),
            }
            for ac in story.get("acceptance_criteria", [])
        ],
    }
    return files, manifest
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_factory_test_skeletons.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/test_skeletons.py tests/test_factory_test_skeletons.py
git commit -m "feat: JUnit skeleton renderer + repo stack resolution

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: `simulate.py` delegates name derivation to the shared function

**Files:**
- Modify: `s7_delivery/factory/simulate.py:130-140` (`_test_name`)
- Test: `tests/test_factory_test_skeletons.py` (already covers parity); existing suite guards regressions

**Interfaces:**
- Consumes: `test_skeletons.slug_test_name` (Task 1).
- Produces: `simulate._test_name` unchanged signature and unchanged output — the scripted US-003 special cases stay; only the fallback slug logic is replaced by the shared call.

- [ ] **Step 1: Replace the fallback body**

In `s7_delivery/factory/simulate.py`, change `_test_name` to:

```python
def _test_name(story_id: str, ac_id: str, text: str, *, scripted: bool = True) -> str:
    if scripted and ac_id == "US-003-AC2":
        return "test_accepts_first_day_absent_after_last_day_worked"
    if scripted and ac_id == "US-003-AC3":
        # The defective first version only checks strictly-before — the name
        # honestly reflects what it asserts, which is how the reviewer spots it.
        return "test_rejects_first_day_absent_before_last_day_worked"
    from s7_delivery.factory.test_skeletons import slug_test_name
    return slug_test_name(text)
```

- [ ] **Step 2: Run the full simulated-lane tests**

Run: `python -m pytest tests/test_factory_test_skeletons.py tests/test_factory_build_review.py tests/test_factory_engine.py -q`
Expected: all PASS (names byte-identical to before).

- [ ] **Step 3: Commit**

```bash
git add s7_delivery/factory/simulate.py
git commit -m "refactor: simulate test names delegate to shared slug function

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: `DeliveryPack.test_plan_status` + skeleton generation in `delivery_packs_generate`

**Files:**
- Modify: `s7_delivery/factory/models.py:328-348` (`DeliveryPack`)
- Modify: `s7_delivery/factory/engine.py:1877-1886` (`_packs` legacy default), `engine.py:1924-1994` (`delivery_packs_generate`)
- Test: `tests/test_factory_delivery_packs.py` (append)

**Interfaces:**
- Produces (used by Tasks 5, 6, 10):
  - `DeliveryPack` fields: `test_plan_status: str = "generated"` (`generated | approved`), `test_plan_approved_by: str = ""`, `test_plan_approved_at: str = ""`.
  - Artifact store: `build/tests/<story_id>/<skeleton file>` and `build/tests/<story_id>/test-manifest.json` written on every pack generation.
- Consumes: `test_skeletons.resolve_stack`, `test_skeletons.render_story_tests` (Tasks 1–2); existing `self._write_files`, `self._connected_repos()`.

- [ ] **Step 1: Write the failing tests (append to `tests/test_factory_delivery_packs.py`, reusing its existing `eng` fixture that reaches `delivery_packs_generate`)**

```python
def test_generation_writes_test_skeletons_and_manifest(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    stories = eng.state()["planning"]["stories"]
    for s in stories:
        mpath = eng.store.path("build", "tests", s["story_id"], "test-manifest.json")
        assert mpath.is_file(), s["story_id"]
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        assert manifest["provenance"] == "rule_based"
        assert [t["ac_id"] for t in manifest["tests"]] == [
            ac["ac_id"] for ac in s["acceptance_criteria"]
        ]
        for t in manifest["tests"]:
            assert eng.store.path("build", "tests", s["story_id"], t["file"]).is_file()


def test_new_pack_test_plan_starts_generated(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    packs = eng.state()["build"]["delivery_packs"]
    assert packs and all(p["test_plan_status"] == "generated" for p in packs)
```

(Add `import json` to the test file's imports if missing.)

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_factory_delivery_packs.py -v -k "test_plan or skeleton"`
Expected: FAIL (`KeyError: 'test_plan_status'` / missing manifest file).

- [ ] **Step 3: Implement**

(a) `models.py` — add to `DeliveryPack` after `publication_status`/`published_version`:

```python
    test_plan_status: str = "generated"  # generated | approved
    test_plan_approved_by: str = ""
    test_plan_approved_at: str = ""
```

(b) `engine.py` `_packs()` — extend the legacy-row block (same pattern as `published_version`):

```python
            if "test_plan_status" not in p:
                # legacy rows predate the test-plan checkpoint: a pack that
                # already reached the repository was implicitly accepted
                p["test_plan_status"] = (
                    "approved" if p["publication_status"] == "published"
                    else "generated"
                )
                p.setdefault("test_plan_approved_by", "")
                p.setdefault("test_plan_approved_at", "")
```

(c) `engine.py` `delivery_packs_generate` — inside the existing `for story in stories:` loop (after the `self._write_files(dp.render_story_pack(...), ...)` call), add:

```python
            repo = next(
                (r for r in self._connected_repos()
                 if r["name"] == story.get("target_repository", "")),
                None,
            )
            stack = test_skeletons.resolve_stack(
                repo, self.store.path("repos", story.get("target_repository", "") or "-")
            )
            t_files, t_manifest = test_skeletons.render_story_tests(story, stack)
            self._write_files(
                {**t_files, "test-manifest.json": t_manifest},
                "build", "tests", story["story_id"],
            )
```

with `from s7_delivery.factory import test_skeletons` added next to the existing `from s7_delivery.factory import delivery_packs as dp` import at the top of the method.

No change needed for the reset-on-regenerate: `_write_team_pack` builds a fresh `DeliveryPack(...)` row each generation, so `test_plan_status` naturally resets to `"generated"` — Task 6 adds the test proving it.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_factory_delivery_packs.py tests/test_factory_build_review.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/models.py s7_delivery/factory/engine.py tests/test_factory_delivery_packs.py
git commit -m "feat: generate AC test skeletons with packs; packs carry test_plan_status

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: `test_plan_approve` engine action + role + server route

**Files:**
- Modify: `s7_delivery/factory/roles.py:50-53` (PERMISSIONS, build & review section)
- Modify: `s7_delivery/factory/engine.py` (new method after `delivery_packs_generate`, near line 1995)
- Modify: `apps/control/server.py` (new route next to `post_delivery_pack_publish`, line ~663)
- Test: `tests/test_factory_delivery_packs.py` (append), `tests/test_control_api.py` (append)

**Interfaces:**
- Produces (used by Tasks 6, 10):
  - Engine: `test_plan_approve(self, role: Role, pack_id: str, approver: str = "") -> None`.
  - Permission: `"approve_test_plan": {Role.QA_LEAD}`.
  - Route: `POST /api/runs/{run_id}/delivery-packs/{pack_id}/approve-test-plan` with body `{"role": ..., "approver": ...}` (reuses the existing `AcceptBody` model), returns `eng.state()`.
- Consumes: `Approval` model (already imported in engine.py for plan sign-off), `self._save_packs`, `self._activity`, `build_phases.require_at_least`.

- [ ] **Step 1: Write the failing engine tests (append to `tests/test_factory_delivery_packs.py`)**

```python
def test_qa_approves_test_plan(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id, "R. Osei")
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "approved"
    assert pack["test_plan_approved_by"] == "R. Osei"
    assert pack["test_plan_approved_at"]


def test_only_qa_lead_approves_test_plan(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    with pytest.raises(PermissionError_):
        eng.test_plan_approve(Role.ENGINEERING_LEAD, pack_id)


def test_double_approval_rejected(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    with pytest.raises(EngineError, match="already approved"):
        eng.test_plan_approve(Role.QA_LEAD, pack_id)


def test_approve_unknown_pack_rejected(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    with pytest.raises(EngineError, match="Unknown delivery pack"):
        eng.test_plan_approve(Role.QA_LEAD, "PACK-nope")
```

(Ensure the test file imports `PermissionError_` from `s7_delivery.factory.roles` — copy the import from `tests/test_factory_build_review.py` if missing.)

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_factory_delivery_packs.py -v -k approve`
Expected: FAIL (`AttributeError: test_plan_approve` / `PermissionError_: Unknown action`).

- [ ] **Step 3: Implement**

(a) `roles.py` — add in the build & review block, after `"generate_delivery_packs"`:

```python
    # QA approves the AC test plan; the service that generated it never
    # approves its own tests — same separation as architecture acceptance.
    "approve_test_plan": {Role.QA_LEAD},
```

(b) `engine.py` — add after `delivery_packs_generate` (before `_assignments`):

```python
    def test_plan_approve(self, role: Role, pack_id: str, approver: str = "") -> None:
        """Human checkpoint on the AC-derived test skeletons: QA approves a
        pack's test plan before it may publish. The generator (the service)
        never approves its own tests."""
        roles.require("approve_test_plan", role)
        phase = self._build_phase()
        build_phases.require_at_least(
            phase, BuildReviewPhase.DELIVERY_PACKS_READY, "Test plan approval"
        )
        packs = self._packs()
        pack = next((p for p in packs if p["delivery_pack_id"] == pack_id), None)
        if pack is None:
            raise EngineError(f"Unknown delivery pack {pack_id}")
        if pack["test_plan_status"] == "approved":
            raise EngineError(
                f"{pack_id} v{pack['version']} test plan is already approved"
            )
        who = approver.strip() or role.value
        pack["test_plan_status"] = "approved"
        pack["test_plan_approved_by"] = who
        pack["test_plan_approved_at"] = now_iso()
        self._save_packs(packs)
        approvals = self.store.read_ledger("approvals.jsonl")
        self.store.append(
            Approval(
                approval_id=f"APR-{len(approvals) + 1:03d}",
                subject=f"test-plan:{pack_id}",
                role=role,
                approver=who,
                decision="approved",
                note=f"AC test plan for {pack['team']} pack v{pack['version']}",
            ),
            "approvals.jsonl",
        )
        self._activity(
            stage=Stage.BUILD_REVIEW, actor=who, actor_type="human",
            workflow="test-plan-approval", artifact=pack_id, outcome="passed",
            details=f"Test plan for {pack['team']} pack v{pack['version']}"
                    " approved; publication enabled",
        )
```

(c) `apps/control/server.py` — next to `post_delivery_pack_publish`:

```python
@app.post("/api/runs/{run_id}/delivery-packs/{pack_id}/approve-test-plan")
def post_test_plan_approve(run_id: str, pack_id: str, body: AcceptBody) -> dict:
    eng = _engine(run_id)
    eng.test_plan_approve(_role(body.role), pack_id, body.approver)
    return eng.state()
```

(`AcceptBody` is defined above the architecture-accept route; if it sits below this insertion point, reference it anyway — Python resolves at call time — or move the route below it.)

- [ ] **Step 4: Write the failing API test (append to `tests/test_control_api.py`, following its existing client/run fixture pattern — find the delivery-pack publish test there and mirror its setup)**

```python
def test_approve_test_plan_route(client_with_packs):
    client, run_id, pack_id = client_with_packs
    r = client.post(
        f"/api/runs/{run_id}/delivery-packs/{pack_id}/approve-test-plan",
        json={"role": "qa_lead", "approver": "R. Osei"},
    )
    assert r.status_code == 200
    pack = next(p for p in r.json()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "approved"
```

If `tests/test_control_api.py` has no fixture that reaches generated packs, add one locally in the test following the file's existing run-creation helpers (create sim run → intake → plan → sign off → architecture generate+accept → packs generate, all via the API routes used elsewhere in that file). Use the exact role strings the file already uses (grep `"role"` there).

- [ ] **Step 5: Run all new tests**

Run: `python -m pytest tests/test_factory_delivery_packs.py tests/test_control_api.py -q`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add s7_delivery/factory/roles.py s7_delivery/factory/engine.py apps/control/server.py tests/test_factory_delivery_packs.py tests/test_control_api.py
git commit -m "feat: QA Lead test-plan approval action, role and API route

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Publish gates on test-plan approval; regeneration resets it

**Files:**
- Modify: `s7_delivery/factory/engine.py:2316-2323` (`delivery_pack_publish`, after the staleness check)
- Test: `tests/test_factory_delivery_packs.py` (append)

**Interfaces:**
- Consumes: `pack["test_plan_status"]` (Task 4), `test_plan_approve` (Task 5).
- Produces: `delivery_pack_publish` raises `EngineError` (HTTP 409 via the server) for an unapproved pack.

- [ ] **Step 1: Write the failing tests**

```python
def test_publish_requires_test_plan_approval(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    with pytest.raises(EngineError, match="test plan is not approved"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)  # now succeeds
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["publication_status"] == "published"


def test_regeneration_resets_test_plan_approval(eng):
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)
    pack_id = eng.state()["build"]["delivery_packs"][0]["delivery_pack_id"]
    eng.test_plan_approve(Role.QA_LEAD, pack_id)
    eng.delivery_packs_generate(Role.ENGINEERING_LEAD)  # v2
    pack = next(p for p in eng.state()["build"]["delivery_packs"]
                if p["delivery_pack_id"] == pack_id)
    assert pack["test_plan_status"] == "generated", "re-approval required"
    with pytest.raises(EngineError, match="test plan is not approved"):
        eng.delivery_pack_publish(Role.DELIVERY_LEAD, pack_id)
```

- [ ] **Step 2: Run to verify the first fails**

Run: `python -m pytest tests/test_factory_delivery_packs.py -v -k "publish_requires or resets"`
Expected: `test_publish_requires_test_plan_approval` FAILS (publish succeeds without approval); the reset test may already pass — that's fine, it pins the behavior.

- [ ] **Step 3: Implement — in `delivery_pack_publish`, directly after the staleness `raise` block (engine.py ~line 2323), add:**

```python
        if pack.get("test_plan_status") != "approved":
            raise EngineError(
                f"{pack_id} test plan is not approved — the QA Lead must"
                " approve the acceptance-criteria test plan before this pack"
                " can publish"
            )
```

Also check `delivery_packs_publish_all` (engine.py, just below `delivery_pack_publish`) — it loops over packs calling the same publish path, so it inherits the gate; add no separate check, but confirm its error surfacing doesn't swallow `EngineError` (read it; if it catches and records per-pack failures, that behavior is correct and needs no change).

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_factory_delivery_packs.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_delivery_packs.py
git commit -m "feat: publication 409s until the pack's test plan is QA-approved

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: Publication carries skeletons at governed test roots

**Files:**
- Modify: `s7_delivery/factory/publication.py:27` (MANAGED_ROOTS), `:39-73` (`file_plan`), `:93-110` (`check_conflicts`), `:152-161` (`publish_to_clone` add step)
- Test: `tests/test_factory_publication.py` (append)

**Interfaces:**
- Produces:
  - `PYTEST_ROOT = "tests/s7"`, `JUNIT_ROOT = "src/test/java/s7"`, `MANAGED_ROOTS = ("AGENTS.md", ".s7", PYTEST_ROOT, JUNIT_ROOT)`.
  - `file_plan` additionally maps, per story: runnable skeletons to `tests/s7/<file>` or `src/test/java/s7/<file>`; non-runnable ones to `.s7/tests/<story_id>/<file>`; and the manifest to `.s7/stories/<story_id>/test-manifest.json`.
- Consumes: `build/tests/<story_id>/` artifacts (Task 4), `test_skeletons.runnable_root` (Task 2).

- [ ] **Step 1: Write the failing tests (append to `tests/test_factory_publication.py`; reuse its existing fixtures — it already builds a store with pack artifacts; follow the file's existing `file_plan`/`check_conflicts` test setup exactly, extending the fixture to also write `build/tests/US-1/test_us_1.py` and a manifest)**

```python
def _write_skeletons(store, story_id="US-1", runnable=True, stack="pytest",
                     filename="test_us_1.py"):
    store.write_text("import pytest\n", "build", "tests", story_id, filename)
    store.write_json(
        {"story_id": story_id, "stack": stack, "runnable": runnable,
         "provenance": "rule_based", "generated_at": "2026-08-09T00:00:00+00:00",
         "tests": [{"ac_id": f"{story_id}-AC1", "test_name": "test_x",
                    "file": filename}]},
        "build", "tests", story_id, "test-manifest.json",
    )


def test_file_plan_places_runnable_pytest_skeletons(store_with_pack):
    store, pack = store_with_pack  # adapt to the fixture actually present
    _write_skeletons(store, story_id=pack["story_ids"][0])
    plan = publication.file_plan(store, pack)
    sid = pack["story_ids"][0]
    assert f"tests/s7/test_us_1.py" in plan or any(
        k.startswith("tests/s7/") for k in plan
    )
    assert f".s7/stories/{sid}/test-manifest.json" in plan


def test_file_plan_places_reference_only_under_s7(store_with_pack):
    store, pack = store_with_pack
    sid = pack["story_ids"][0]
    _write_skeletons(store, story_id=sid, runnable=False, stack="")
    plan = publication.file_plan(store, pack)
    assert any(k.startswith(f".s7/tests/{sid}/") for k in plan)
    assert not any(k.startswith("tests/s7/") for k in plan)


def test_foreign_test_root_conflicts(tmp_path):
    (tmp_path / "tests" / "s7").mkdir(parents=True)
    (tmp_path / "tests" / "s7" / "existing.py").write_text("x")
    with pytest.raises(publication.PublicationConflict, match="tests/s7"):
        publication.check_conflicts(tmp_path, republish=False)
```

Note to implementer: `store_with_pack` stands for whatever fixture `tests/test_factory_publication.py` actually uses to build a `RunStore` + pack row for `file_plan` tests — open the file first and reuse its real fixture name and pack shape. Do not invent a parallel fixture.

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_factory_publication.py -v -k "skeleton or reference_only or foreign_test"`
Expected: FAIL (plan lacks test paths; no conflict raised).

- [ ] **Step 3: Implement in `publication.py`**

(a) Roots:

```python
PYTEST_ROOT = "tests/s7"
JUNIT_ROOT = "src/test/java/s7"
MANAGED_ROOTS = ("AGENTS.md", ".s7", PYTEST_ROOT, JUNIT_ROOT)
_TEST_ROOTS = (PYTEST_ROOT, JUNIT_ROOT)
```

(b) `file_plan` — after the existing per-story loop, add (and `import json` at top):

```python
    for story_id in pack["story_ids"]:
        tdir = store.path("build", "tests", story_id)
        mpath = tdir / "test-manifest.json"
        if not mpath.is_file():
            continue  # packs generated before the test-plan checkpoint
        manifest = json.loads(mpath.read_text(encoding="utf-8"))
        plan[f".s7/stories/{story_id}/test-manifest.json"] = mpath.read_text(
            encoding="utf-8"
        )
        if manifest.get("runnable"):
            root = runnable_root(manifest["stack"])
        else:
            root = f".s7/tests/{story_id}"
        for p in sorted(tdir.iterdir()):
            if p.is_file() and p.name != "test-manifest.json":
                plan[f"{root}/{p.name}"] = p.read_text(encoding="utf-8")
```

with `from s7_delivery.factory.test_skeletons import runnable_root` added to the imports, and the closing assertion widened:

```python
    for dest in plan:
        assert dest == "AGENTS.md" or dest.startswith(
            (".s7/", PYTEST_ROOT + "/", JUNIT_ROOT + "/")
        ), dest
```

(c) `check_conflicts` — add before the `.s7` check:

```python
    for root in _TEST_ROOTS:
        if (repo_dir / root).exists() and not republish:
            raise PublicationConflict(
                f"{root}/ already exists in the repository and was not"
                " published by this run — resolve deliberately before"
                " publishing"
            )
```

(d) `publish_to_clone` — the `git add` must not fail on roots that don't exist for this stack; replace the add line:

```python
    roots = [r for r in MANAGED_ROOTS if (repo_dir / r).exists()]
    _git(repo_dir, "add", "--", *roots)
```

- [ ] **Step 4: Run the publication tests**

Run: `python -m pytest tests/test_factory_publication.py tests/test_factory_delivery_packs.py -q`
Expected: all PASS (existing managed-root tests still green).

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/publication.py tests/test_factory_publication.py
git commit -m "feat: publish AC test skeletons at governed test roots

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: CI workflows emit per-test results

**Files:**
- Modify: `s7_delivery/factory/ci_bootstrap.py:15-92` (both workflow templates)
- Test: `tests/test_factory_ci_bootstrap.py` (append)

**Interfaces:**
- Produces: `ci-summary.json` gains `"tests": [{"name": str, "outcome": "passed"|"failed"|"skipped"}]` on both stacks; totals now derive from the same parse. Consumed by Task 9's join.

- [ ] **Step 1: Write the failing tests (append)**

```python
def test_pytest_workflow_collects_per_test_results():
    from s7_delivery.factory.ci_bootstrap import PYTEST_WORKFLOW
    assert "--junitxml=junit.xml" in PYTEST_WORKFLOW
    assert '"tests":' in PYTEST_WORKFLOW or "'tests'" in PYTEST_WORKFLOW


def test_maven_workflow_collects_per_test_results():
    from s7_delivery.factory.ci_bootstrap import MAVEN_WORKFLOW
    assert "surefire-reports" in MAVEN_WORKFLOW
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_factory_ci_bootstrap.py -v -k per_test`
Expected: FAIL.

- [ ] **Step 3: Implement — replace both templates' test-run + summarize steps**

`PYTEST_WORKFLOW`: change the run step to
`run: pytest --junitxml=junit.xml | tee test-output.log`
and replace the whole summarize heredoc with:

```yaml
      - name: Summarize results
        if: always()
        run: |
          python3 - <<'PY'
          import json, os, xml.etree.ElementTree as ET
          tests = []
          if os.path.exists("junit.xml"):
              for case in ET.parse("junit.xml").getroot().iter("testcase"):
                  outcome = "passed"
                  if case.find("failure") is not None or case.find("error") is not None:
                      outcome = "failed"
                  elif case.find("skipped") is not None:
                      outcome = "skipped"
                  tests.append({"name": case.get("name", ""), "outcome": outcome})
          counted = [t for t in tests if t["outcome"] != "skipped"]
          failed = sum(1 for t in counted if t["outcome"] == "failed")
          summary = {"tests_total": len(counted), "tests_passed": len(counted) - failed,
                     "tests_failed": failed, "coverage_pct": None, "tests": tests}
          json.dump(summary, open("ci-summary.json", "w"))
          PY
```

`MAVEN_WORKFLOW`: keep `mvn -B test | tee test-output.log`; replace its summarize heredoc with the same parser over surefire reports:

```yaml
      - name: Summarize results
        if: always()
        run: |
          python3 - <<'PY'
          import glob, json, xml.etree.ElementTree as ET
          tests = []
          for path in sorted(glob.glob("target/surefire-reports/TEST-*.xml")):
              for case in ET.parse(path).getroot().iter("testcase"):
                  outcome = "passed"
                  if case.find("failure") is not None or case.find("error") is not None:
                      outcome = "failed"
                  elif case.find("skipped") is not None:
                      outcome = "skipped"
                  tests.append({"name": case.get("name", ""), "outcome": outcome})
          counted = [t for t in tests if t["outcome"] != "skipped"]
          failed = sum(1 for t in counted if t["outcome"] == "failed")
          summary = {"tests_total": len(counted), "tests_passed": len(counted) - failed,
                     "tests_failed": failed, "coverage_pct": None, "tests": tests}
          json.dump(summary, open("ci-summary.json", "w"))
          PY
```

These are plain Python triple-quoted strings — there are no `\\d` regexes left in the new parsers, so no escaping subtleties; verify by importing the module.

- [ ] **Step 4: Run the bootstrap tests**

Run: `python -m pytest tests/test_factory_ci_bootstrap.py tests/test_factory_ci_bootstrap_engine.py -q`
Expected: all PASS (fix any existing assertions that pinned the old regex text — update them to the new parser, keeping their intent: totals present, artifact uploaded).

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/ci_bootstrap.py tests/test_factory_ci_bootstrap.py
git commit -m "feat: S7 CI workflows report per-test results in ci-summary

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Red baseline capture + per-test join in git evidence sync

**Files:**
- Modify: `s7_delivery/factory/engine.py:2148-2252` (`workspaces_sync_git`, `_sync_ci_evidence`)
- Test: `tests/test_factory_ci_sync_engine.py` (append — this file already mocks `gh`/`ci_sync` for engine sync tests; reuse its fixtures and monkeypatch style exactly)

**Interfaces:**
- Produces:
  - Workspace field `red_baseline: dict | None` — `{run_id, status, conclusion, url, checked_at, tests_total?, tests_passed?, tests_failed?, tests?}` from the S7 CI run for the pack's latest **real** publication commit.
  - `ci_evidence` gains a `"tests"` list when the summary provides one.
  - Task test records (`build/tasks.json` → `tests[].current_result`) updated from real per-test outcomes, joined by name.
- Consumes: `publications.jsonl` records (`delivery_pack_id`, `commit`, `simulated`), `ci_sync.latest_run`, `ci_sync.download_summary`, `self._tasks()` / `self._save_tasks()`.

- [ ] **Step 1: Refactor — extract the shared lookup.** Replace `_sync_ci_evidence` with:

```python
    def _ci_run_evidence(self, repo: dict, sha: str) -> dict | None:
        """Best-effort real CI lookup for one commit. Never raises: a gh
        failure, an unresolvable owner/repo, or no run yet all mean "no CI
        evidence yet", not a sync failure."""
        from s7_delivery.factory import ci_sync

        owner_repo = ci_sync.owner_repo_from_url(repo.get("url", ""))
        if owner_repo is None:
            return None
        try:
            run = ci_sync.latest_run(owner_repo, sha)
        except (ci_sync.CiSyncError, ValueError, OSError, KeyError,
                subprocess.TimeoutExpired):
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
            except (ci_sync.CiSyncError, ValueError, OSError, KeyError,
                    subprocess.TimeoutExpired):
                summary = None
            if summary:
                evidence["tests_total"] = summary.get("tests_total")
                evidence["tests_passed"] = summary.get("tests_passed")
                evidence["tests_failed"] = summary.get("tests_failed")
                if summary.get("tests"):
                    evidence["tests"] = summary["tests"]
        return evidence

    def _sync_ci_evidence(self, repo: dict, git_evidence: dict) -> dict | None:
        latest = git_evidence.get("latest")
        if not latest:
            return None
        return self._ci_run_evidence(repo, latest["sha"])

    def _sync_red_baseline(self, repo: dict, ws: dict) -> dict | None:
        """The S7 CI run for this workspace's latest *real* publication
        commit — the genuinely-failing skeletons on the s7/ context branch.
        Simulated publications have no CI run and never invent one."""
        pubs = [
            p for p in self.store.read_ledger("publications.jsonl")
            if p["delivery_pack_id"] == ws.get("delivery_pack_id")
            and not p.get("simulated")
        ]
        if not pubs:
            return None
        return self._ci_run_evidence(repo, pubs[-1]["commit"])
```

- [ ] **Step 2: Wire into `workspaces_sync_git`.** After the line `ws["ci_evidence"] = self._sync_ci_evidence(repo, ws["git_evidence"])` add:

```python
            ws["red_baseline"] = self._sync_red_baseline(repo, ws)
```

And after the loop (before `self._save_workspaces(workspaces)`), add the per-test join:

```python
        tasks = self._tasks()
        tasks_changed = False
        for ws in workspaces:
            results = {
                t["name"]: t["outcome"]
                for t in (ws.get("ci_evidence") or {}).get("tests", [])
            }
            if not results:
                continue
            for task in tasks:
                if task["story_id"] != ws["story_id"]:
                    continue
                for t in task.get("tests", []):
                    if t["name"] in results:
                        new = "passed" if results[t["name"]] == "passed" else "failed"
                        if t.get("current_result") != new:
                            t["current_result"] = new
                            tasks_changed = True
        if tasks_changed:
            self._save_tasks(tasks)
```

(Note `tasks_by_story` in that method maps story→one task; the join loops over all tasks instead so multi-task stories update every record.)

- [ ] **Step 3: Write the tests (append to `tests/test_factory_ci_sync_engine.py`, reusing its live-run + monkeypatched `ci_sync` fixtures — open the file first and copy its setup for the existing `_sync_ci_evidence` tests)**

Cover, using the file's established mocking style:

```python
def test_red_baseline_from_publication_commit(live_eng_with_workspace, monkeypatch):
    eng = live_eng_with_workspace  # adapt to the file's real fixture name
    eng.store.append(
        {"publication_id": "PUB-001", "delivery_pack_id": "PACK-platform-team",
         "repository": "repo-x", "branch": "s7/x", "commit": "a" * 40,
         "published_paths": [], "status": "published", "simulated": False,
         "published_at": "2026-08-09T00:00:00+00:00", "provenance": "human"},
        "publications.jsonl",
    )
    monkeypatch.setattr(
        "s7_delivery.factory.ci_sync.latest_run",
        lambda owner_repo, sha: {"databaseId": 7, "status": "completed",
                                 "conclusion": "failure", "url": "http://run/7"},
    )
    monkeypatch.setattr(
        "s7_delivery.factory.ci_sync.download_summary",
        lambda owner_repo, run_id: {"tests_total": 2, "tests_passed": 0,
                                    "tests_failed": 2,
                                    "tests": [{"name": "test_a", "outcome": "failed"},
                                              {"name": "test_b", "outcome": "failed"}]},
    )
    ws = {"delivery_pack_id": "PACK-platform-team"}
    ev = eng._sync_red_baseline({"url": "https://github.com/o/r"}, ws)
    assert ev["conclusion"] == "failure" and ev["tests_failed"] == 2


def test_simulated_publication_yields_no_red_baseline(live_eng_with_workspace):
    eng = live_eng_with_workspace
    eng.store.append(
        {"publication_id": "PUB-001", "delivery_pack_id": "PACK-platform-team",
         "repository": "repo-x", "branch": "s7/x", "commit": "abc1234",
         "published_paths": [], "status": "published", "simulated": True,
         "published_at": "2026-08-09T00:00:00+00:00", "provenance": "simulated"},
        "publications.jsonl",
    )
    ws = {"delivery_pack_id": "PACK-platform-team"}
    assert eng._sync_red_baseline({"url": "https://github.com/o/r"}, ws) is None


def test_per_test_results_flow_into_task_tests(...):
    # Using the file's full workspaces_sync_git fixture: seed a task whose
    # tests[] contains {"name": "test_a", "current_result": "failed"}, mock
    # ci evidence with tests [{"name": "test_a", "outcome": "passed"}], run
    # workspaces_sync_git, assert the task's current_result flipped to
    # "passed" and initial_result stayed "failed".
```

The third test must be written concretely against the file's real fixture for `workspaces_sync_git` (it exists — that method is already tested there). Keep the assertion exactly: `current_result == "passed"`, `initial_result == "failed"`.

- [ ] **Step 4: Run the sync tests**

Run: `python -m pytest tests/test_factory_ci_sync_engine.py tests/test_factory_git_sync.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_factory_ci_sync_engine.py
git commit -m "feat: capture real red baseline and join per-test CI results

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 10: Delivery Packs UI — Test Plan panel, approve action, publish gating

**Files:**
- Modify: `apps/control/web/src/types.ts:490-505` (`DeliveryPack`)
- Modify: `apps/control/web/src/pages/build/DeliveryPacks.tsx`
- Build: `apps/control/web/` (`npm run build`), commit `dist/`

**Interfaces:**
- Consumes: `test_plan_status` on pack rows (Task 4), `POST .../delivery-packs/{id}/approve-test-plan` (Task 5), manifest at `GET /api/runs/{runId}/artifact-file/build/tests/{storyId}/test-manifest.json` (Task 4; the artifact-file route already serves anything in the store).
- Produces: per-pack Test Plan card; Publish disabled until approved.

- [ ] **Step 1: Extend the type** — in `types.ts`, add to `DeliveryPack`:

```typescript
  test_plan_status?: 'generated' | 'approved'
  test_plan_approved_by?: string
  test_plan_approved_at?: string
```

- [ ] **Step 2: Add the Test Plan card to the pack detail panel in `DeliveryPacks.tsx`.**

State + data (inside the component, following the existing `tabText` fetch pattern):

```typescript
const [manifests, setManifests] = useState<Record<string, TestManifest | null>>({})
const [approving, setApproving] = useState(false)

interface TestManifestRow { ac_id: string; test_name: string; file: string }
interface TestManifest { story_id: string; stack: string; runnable: boolean; provenance: string; tests: TestManifestRow[] }
```

(Place the two interfaces at module scope next to the file's other local types.)

```typescript
useEffect(() => {
  if (!runId || !selectedPack) return
  selectedPack.story_ids.forEach((sid) => {
    if (manifests[sid] !== undefined) return
    fetch(`/api/runs/${runId}/artifact-file/build/tests/${sid}/test-manifest.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((m: TestManifest | null) => setManifests((prev) => ({ ...prev, [sid]: m })))
      .catch(() => setManifests((prev) => ({ ...prev, [sid]: null })))
  })
}, [runId, selectedPack])
```

Approve handler (mirror `doPublish`):

```typescript
const doApproveTestPlan = async (p: DeliveryPack) => {
  setApproving(true)
  await act(`/delivery-packs/${p.delivery_pack_id}/approve-test-plan`, {}, 'Test plan approved')
  setApproving(false)
}
```

Card JSX, rendered in the selected-pack detail column above the publish controls (match the page's existing `card` / `hint` / `dp-*` class conventions; reuse the `Prov` badge component if this page imports one, otherwise a plain `<span className="badge">RULE_BASED</span>` consistent with neighboring badges):

```tsx
<div className="card">
  <h3>Test Plan — Acceptance Criteria</h3>
  <span className="hint">
    Rule-based test skeletons generated from each acceptance criterion.
    QA Lead approves before the pack can publish. Generated (Rule-Based) — not AI output.
  </span>
  {selectedPack.story_ids.map((sid) => {
    const story = storyById.get(sid)
    const m = manifests[sid]
    return (
      <details key={sid}>
        <summary>{sid} — {story?.title ?? ''} {m ? `· ${m.tests.length} tests · ${m.runnable ? m.stack : 'reference only'}` : ''}</summary>
        <table>
          <thead><tr><th>AC</th><th>Criterion</th><th>Test</th></tr></thead>
          <tbody>
            {(m?.tests ?? []).map((t) => (
              <tr key={t.ac_id}>
                <td>{t.ac_id}</td>
                <td>{story?.acceptance_criteria?.find((a) => a.ac_id === t.ac_id)?.text ?? ''}</td>
                <td><code>{t.test_name}</code></td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    )
  })}
  {selectedPack.test_plan_status === 'approved' ? (
    <span className="hint">Approved by {selectedPack.test_plan_approved_by}</span>
  ) : (
    <button className="primary" disabled={approving} onClick={() => doApproveTestPlan(selectedPack)}>
      Approve Test Plan (QA Lead)
    </button>
  )}
</div>
```

- [ ] **Step 3: Gate the Publish button.** Wherever the publish button/confirm renders for a pack `p`, add `p.test_plan_status !== 'approved'` to its `disabled` condition and show a hint when that's the blocker: `Test plan awaiting QA approval`. Update `statusOf`/`packState`-driven labels: an unpublished pack with an unapproved test plan shows label `AWAITING TEST PLAN` instead of `READY TO PUBLISH` (edit the `packState`/status helper near line 60–81).

- [ ] **Step 4: Build and verify**

Run: `cd apps/control/web && npm run build`
Expected: clean build. Then start the server (`demo/run_control.sh` or the existing dev command) against a simulation run and click through: generate packs → Test Plan card lists ACs with test names → Approve → Publish enables. Use Chrome MCP to verify each step renders (per the user's standing preference for live UI verification).

- [ ] **Step 5: Commit (src + dist together)**

```bash
git add apps/control/web/src apps/control/web/dist
git commit -m "feat: Test Plan review panel and publish gating in Delivery Packs UI

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 11: Test Evidence UI — real red baseline

**Files:**
- Modify: `apps/control/web/src/types.ts` (workspace type — find the interface carrying `ci_evidence` and add `red_baseline`)
- Modify: `apps/control/web/src/pages/build/TestEvidence.tsx:129-150` (phase strip), `:266` (CI system label cell)
- Build: `apps/control/web/` (`npm run build`), commit `dist/`

**Interfaces:**
- Consumes: workspace `red_baseline` (Task 9).

- [ ] **Step 1: Extend the workspace type** in `types.ts`:

```typescript
  red_baseline?: {
    run_id?: number
    status?: string
    conclusion?: string
    url?: string
    checked_at?: string
    tests_total?: number
    tests_passed?: number
    tests_failed?: number
  } | null
```

- [ ] **Step 2: Use it in the Red phase chip.** In `TestEvidence.tsx`, where the phases array builds (`['red', 'Red', at('test-first'), `${initialFailures} failures expected`]`), prefer real evidence when present (`w` is the workspace for the selected story — the component already resolves it for `ci_evidence`):

```typescript
const rb = w?.red_baseline
const redTime = rb?.checked_at ? fmtTime(rb.checked_at) : at('test-first')
const redSub = rb
  ? `${rb.tests_failed ?? '?'} failing on branch — real CI baseline`
  : `${initialFailures} failures expected`
```

and use `[redTime, redSub]` in the `red` row (`fmtTime` = whatever HH:MM formatter the file already uses for `Last Run`; reuse it, don't add a new one). If `rb.url` exists, make the Red row's label a link: `<a href={rb.url} target="_blank" rel="noreferrer">Red</a>` styled like the existing "Open CI Pipeline" link.

- [ ] **Step 3: Badge honesty.** The `Simulated CI <Prov provenance="simulated"/>` cell (line ~380) already flips to GitHub Actions when `ci_evidence` exists; extend that condition to `(w?.ci_evidence || w?.red_baseline)` so a synced red baseline alone also stops claiming "Simulated CI".

- [ ] **Step 4: Build and verify**

Run: `cd apps/control/web && npm run build`
Expected: clean build; in a simulation run the page renders exactly as before (no `red_baseline` present anywhere).

- [ ] **Step 5: Commit (src + dist together)**

```bash
git add apps/control/web/src apps/control/web/dist
git commit -m "feat: Test Evidence shows real red baseline when synced

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 12: Docs sync + full-suite verification

**Files:**
- Modify: `CLAUDE.md` (Build & Review paragraph), `AGENTS.md` (same content, same commit)

**Interfaces:** none — documentation and verification only.

- [ ] **Step 1: Add to CLAUDE.md**, as a new paragraph after the “Build & Review redesign” paragraph (mirror the same text into AGENTS.md in the same commit):

```markdown
**AC test-plan checkpoint before publication, added 2026-08-09.** Delivery
packs now carry rule-based test skeletons — one deliberately-failing test
per acceptance criterion, rendered stack-aware (pytest or JUnit) from the
target repo's bootstrap record, badged `RULE_BASED` and never presented as
AI output (`factory/test_skeletons.py`; name derivation shared with
`simulate.py` so simulated and real evidence agree on names). A QA Lead
approval per pack (`test_plan_approve`, role `approve_test_plan`) gates
`delivery_pack_publish` — an unapproved pack 409s; regeneration resets the
approval. Publication carries runnable skeletons at governed test roots
(`tests/s7/`, `src/test/java/s7/`, added to `MANAGED_ROOTS` with the same
foreign-content refusal), so the s7/ context-branch push produces a real
red CI baseline, captured by git evidence sync as `red_baseline`; both
bootstrapped workflows now emit per-test results in `ci-summary.json`,
which sync joins by test name into per-AC evidence. Simulation mode is
unchanged end to end: skeletons generate, QA approves, publish stays a
pseudo-commit, no git and no network.
```

- [ ] **Step 2: Run the entire suite offline**

Run: `cd /Users/alanlands/Documents/ams-s7-demo && python -m pytest -q`
Expected: all tests pass with no API key set. Fix anything red before proceeding — do not skip.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md AGENTS.md
git commit -m "docs: record the AC test-plan checkpoint in CLAUDE.md/AGENTS.md

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
