# Demo Mode + Release Document Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A fourth "demo" environment in the Control Centre with a scripted click-through Sync storyline (green, green, push-failure, rerun-fix, parallel, complete) and DEMO badge presentation, plus a mode-independent release/design document generator (markdown + MapleSure-themed HTML).

**Architecture:** `DemoMode.DEMO` behaves as simulation in every engine branch; demo-specific behaviour is confined to (a) `intake_create_epic` ignoring extraction, (b) a scripted sync state machine in `s7_delivery/factory/demo_sync.py` persisted at `demo/script.json`, (c) frontend badge presentation. The document generator (`s7_delivery/factory/release_doc.py`) renders from `Engine.state()` only.

**Tech Stack:** Python 3.12 / pydantic / FastAPI (backend), React + TypeScript + Vite (frontend, committed `dist/`), pytest.

**Spec:** `docs/superpowers/specs/2026-08-10-demo-mode-and-release-document-design.md`

## Global Constraints

- Hard rule 2: MapleSure branding only; the real client's name appears nowhere.
- Hard rule 4: no CDN, no new runtime deps; any `apps/control/web/src` change requires `npm run build` and the regenerated `apps/control/web/dist/` committed in the same commit.
- Labelling: stored provenance values are never changed; only on-screen presentation maps to the DEMO chip, and only when `run.mode === 'demo'`. Nothing ever renders as live AI in demo mode.
- All tests run offline with no API key.
- CLAUDE.md and AGENTS.md must be updated in the same commit when scope/rules change (final task).

---

### Task 1: `DemoMode.DEMO` + demo intake behaviour + header selector

**Files:**
- Modify: `s7_delivery/factory/models.py:40-43` (DemoMode)
- Modify: `s7_delivery/factory/engine.py` (`intake_create_epic`, ~line 786)
- Modify: `apps/control/web/src/components/Header.tsx:60-64`
- Modify: `apps/control/web/src/types.ts` (run mode type, if narrowed)
- Test: `tests/test_demo_mode.py` (new)

**Interfaces:**
- Produces: `DemoMode.DEMO == "demo"`; `Engine.create(DemoMode.DEMO)` yields a run whose `mode` is `"demo"` and which behaves as simulation everywhere except epic creation.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_demo_mode.py
from s7_delivery.factory.engine import Engine
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory import seed


def test_demo_mode_exists_and_creates_run(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    assert eng.run().mode is DemoMode.DEMO


def test_demo_epic_ignores_extraction(tmp_path):
    """Demo runs always present the seeded MapleSure epic, even when an
    upload has produced an extraction record (spec: story source decision)."""
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.store.write_json(
        {"epic_title": "Uploaded title", "business_objective": "x",
         "requirement_summary": "y", "extracted_requirements": ["a", "b"],
         "method": "rule_based", "provenance": "rule_based"},
        "intake", "extraction.json",
    )
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    epic = eng.store.read_json("intake", "epic.json")
    assert epic["title"] == seed.EPIC.title


def test_simulation_epic_still_uses_extraction(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.store.write_json(
        {"epic_title": "Uploaded title", "business_objective": "x",
         "requirement_summary": "y", "extracted_requirements": ["a", "b"],
         "method": "rule_based", "provenance": "rule_based"},
        "intake", "extraction.json",
    )
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    assert eng.store.read_json("intake", "epic.json")["title"] == "Uploaded title"
```

Check `Engine.create`'s actual signature for the root/store parameter (existing tests in `tests/` show the established fixture pattern — follow it).

- [ ] **Step 2: Run tests, verify failure** — `pytest tests/test_demo_mode.py -v` fails (`DEMO` not defined).

- [ ] **Step 3: Implement**

`models.py`:
```python
class DemoMode(StrEnum):
    SIMULATION = "simulation"
    REPLAY = "replay"
    LIVE = "live"
    DEMO = "demo"
```

`engine.py`, in `intake_create_epic`, immediately after reading extraction:
```python
        extraction = self.store.read_json_or(None, "intake", "extraction.json")
        # Demo runs always present the seeded MapleSure epic: the upload is
        # shown on the intake page, but epic creation ignores it (spec
        # 2026-08-10-demo-mode, story-source decision).
        if extraction is not None and self.run().mode is DemoMode.DEMO:
            extraction = None
```

`Header.tsx` — the dropdown gains the demo mode and stops labelling simulation "Demo":
```tsx
            <option value="demo">Demo</option>
            <option value="simulation">Simulation</option>
            <option value="replay">Replay</option>
            <option value="live">Live</option>
```

`types.ts`: if `run.mode` is a string union, add `'demo'`.

- [ ] **Step 4: Run tests** — new tests pass; `pytest` whole suite stays green.
- [ ] **Step 5: Commit** (frontend build happens in Task 3 with the rest of the UI work; Header change may sit uncommitted until then OR build dist here — build dist in whichever task commits a `src/` change: run `cd apps/control/web && npm run build`, commit `dist/` together).

```bash
git add s7_delivery/factory/models.py s7_delivery/factory/engine.py tests/test_demo_mode.py apps/control/web/src apps/control/web/dist
git commit -m "feat: demo mode — fourth environment; seeded epic regardless of upload"
```

---

### Task 2: Scripted sync state machine

**Files:**
- Create: `s7_delivery/factory/demo_sync.py`
- Modify: `s7_delivery/factory/engine.py` (two wrapper methods + `state()` key)
- Test: `tests/test_demo_sync.py` (new)

**Interfaces:**
- Consumes: engine task-lifecycle methods used by `demo.py`: `task_run_to_review`, `review_execute`, `review_return_to_development`, `task_generate_tests`, `task_develop`, `task_verify`, `task_submit_review`; `demo.py`'s `_intake_and_plan` pattern for test setup.
- Produces:
  - `demo_sync.advance(eng) -> dict` and `demo_sync.rerun(eng, story_id) -> dict`
  - `Engine.demo_sync_advance(role) -> dict`, `Engine.demo_rerun_story(role, story_id) -> dict`
  - `state()["demo"]` = script state dict or `None` (only present once a demo sync ran)
  - Script state shape: `{"step": int, "failed_story": "US-003", "fix_pending": bool, "complete": bool, "history": [str, ...]}`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_demo_sync.py
import pytest
from s7_delivery.factory import demo
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def demo_run(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    demo._intake_and_plan(eng)  # real engine actions up to workspaces
    return eng


def _story_status(eng, sid):
    return next(
        r for r in eng.state()["build"]["summary"]["rows"] if r["story_id"] == sid
    )


def test_sync_requires_demo_mode(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError):
        eng.demo_sync_advance(Role.DELIVERY_LEAD)


def test_sync_requires_workspaces(tmp_path):
    eng = Engine.create(DemoMode.DEMO, root=tmp_path)
    with pytest.raises(EngineError):
        eng.demo_sync_advance(Role.DELIVERY_LEAD)


def test_scripted_storyline(demo_run):
    eng = demo_run
    r1 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r1["status"] == "advanced" and r1["stories"] == ["US-001"]

    eng.demo_sync_advance(Role.DELIVERY_LEAD)          # US-002
    r3 = eng.demo_sync_advance(Role.DELIVERY_LEAD)     # US-003 fails
    assert r3["status"] == "failure" and r3["stories"] == ["US-003"]
    assert eng.state()["demo"]["fix_pending"] is True

    # Sync while the failure stands re-reports, never advances
    r_again = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r_again["status"] == "failure_pending"

    # Rerun on the wrong story refuses, naming the right one
    with pytest.raises(EngineError, match="US-003"):
        eng.demo_rerun_story(Role.DELIVERY_LEAD, "US-004")

    fix = eng.demo_rerun_story(Role.DELIVERY_LEAD, "US-003")
    assert fix["status"] == "fixed"
    assert eng.state()["demo"]["fix_pending"] is False

    r4 = eng.demo_sync_advance(Role.DELIVERY_LEAD)     # parallel beat
    assert r4["stories"] == ["US-004", "US-005"]

    r5 = eng.demo_sync_advance(Role.DELIVERY_LEAD)
    assert r5["stories"] == ["US-006", "US-007"]
    assert eng.state()["demo"]["complete"] is True

    # Past the end: no-op, never an error
    assert eng.demo_sync_advance(Role.DELIVERY_LEAD)["status"] == "complete"


def test_script_survives_engine_reload(demo_run, tmp_path):
    eng = demo_run
    eng.demo_sync_advance(Role.DELIVERY_LEAD)
    reloaded = Engine(eng.store.root)  # match the codebase's reload pattern
    assert reloaded.state()["demo"]["step"] == 1
```

Adjust fixture/reload construction to the codebase's established test patterns (`tests/` has factory-engine tests to copy). Assert the exact summary-row story states the walk produces (e.g. after r1, `_story_status(eng, "US-001")["overall"]` is complete/ready_for_quality; after r3, US-003 is `blocked` and is the only blocked row).

- [ ] **Step 2: Run tests, verify failure.**

- [ ] **Step 3: Implement `s7_delivery/factory/demo_sync.py`**

```python
"""Scripted Sync storyline for demo mode (spec 2026-08-10).

Macros, not fixtures — each step drives the same engine actions a presenter
could click, so every gate, role check and ledger append genuinely runs.
The only direct writes are the git-push evidence fields on the failure beat,
in the same style demo.py's missing_test_coverage uses. Stored provenance
stays `simulated`; the DEMO chip is presentation only (spec, labelling
resolution).
"""

from __future__ import annotations

from typing import Any

from s7_delivery.factory.models import Role, Stage

FAILED_STORY = "US-003"

STEPS: list[list[str]] = [
    ["US-001"],
    ["US-002"],
    [FAILED_STORY],        # arrives red: push rejected, review blocked
    ["US-004", "US-005"],  # parallel iteration
    ["US-006", "US-007"],  # storyline completes
]

_INITIAL: dict[str, Any] = {
    "step": 0,
    "failed_story": FAILED_STORY,
    "fix_pending": False,
    "complete": False,
    "history": [],
}


def read_state(store) -> dict[str, Any]:
    return store.read_json_or(dict(_INITIAL), "demo", "script.json")


def _task_id(eng, story_id: str) -> str:
    return next(
        t for t in eng.state()["build"]["tasks"] if t["story_id"] == story_id
    )["task_id"]


def _set_task_ci(eng, story_id: str, status: str) -> None:
    tasks = eng.store.read_json_or([], "build", "tasks.json")
    for t in tasks:
        if t["story_id"] == story_id:
            t["ci_status"] = status
    eng.store.write_json(tasks, "build", "tasks.json")


def advance(eng) -> dict[str, Any]:
    state = read_state(eng.store)
    if state["complete"]:
        return {"status": "complete", "stories": []}
    if state["fix_pending"]:
        return {"status": "failure_pending", "stories": [FAILED_STORY]}

    stories = STEPS[state["step"]]
    failed = False
    for sid in stories:
        tid = _task_id(eng, sid)
        eng.task_run_to_review(Role.ENGINEERING_LEAD, tid)
        report = eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
        if report["result"] == "blocked":
            # The scripted failure beat: the push is rejected and CI is red
            # on the story's s7 branch — evidence, in existing shapes.
            _set_task_ci(eng, sid, "failed")
            eng._activity(
                stage=Stage.BUILD, actor="git-sync (demo)",
                actor_type="simulation", workflow="demo-sync", artifact=sid,
                duration_s=2.0, outcome="failed",
                details="git push rejected (non-fast-forward); CI failed on "
                        "the story branch",
            )
            failed = True
    state["step"] += 1
    state["fix_pending"] = failed
    state["history"].append(
        ("failure:" if failed else "advanced:") + ",".join(stories)
    )
    state["complete"] = state["step"] >= len(STEPS) and not failed
    eng.store.write_json(state, "demo", "script.json")
    return {"status": "failure" if failed else "advanced", "stories": stories}


def rerun(eng, story_id: str) -> dict[str, Any]:
    from s7_delivery.factory.engine import EngineError

    state = read_state(eng.store)
    if not state["fix_pending"]:
        raise EngineError("No failed story to rerun — sync first")
    if story_id != FAILED_STORY:
        raise EngineError(
            f"Only {FAILED_STORY} has a failed sync to rerun"
        )
    tid = _task_id(eng, story_id)
    eng.review_return_to_development(Role.INDEPENDENT_REVIEWER, tid)
    eng.task_generate_tests(Role.ENGINEERING_LEAD, tid)
    eng.task_develop(Role.ENGINEERING_LEAD, tid)
    eng.task_verify(Role.ENGINEERING_LEAD, tid)
    eng.task_submit_review(Role.ENGINEERING_LEAD, tid)
    eng.review_execute(Role.INDEPENDENT_REVIEWER, tid)
    state["fix_pending"] = False
    state["history"].append(f"fixed:{story_id}")
    state["complete"] = state["step"] >= len(STEPS)
    eng.store.write_json(state, "demo", "script.json")
    return {"status": "fixed", "stories": [story_id]}
```

(`review_execute` on US-003's first pass blocks via `simulate.review_findings` — the existing deliberate defect; `task_verify` on the corrected pass sets `ci_status = "passed"`. Verify these behaviours against `engine.py` while implementing; adjust the failure beat if `review_execute` already sets a different ci value.)

Engine wrappers (place near `workspaces_sync_git`):
```python
    def demo_sync_advance(self, role: Role) -> dict:
        """One click of the scripted demo Sync storyline (demo mode only)."""
        roles.require("sync_git_evidence", role)
        if self.run().mode is not DemoMode.DEMO:
            raise EngineError("Scripted sync runs in demo mode only")
        if not self._workspaces():
            raise EngineError(
                "Publish delivery packs and provision workspaces before the "
                "demo sync storyline"
            )
        from s7_delivery.factory import demo_sync
        return demo_sync.advance(self)

    def demo_rerun_story(self, role: Role, story_id: str) -> dict:
        roles.require("sync_git_evidence", role)
        if self.run().mode is not DemoMode.DEMO:
            raise EngineError("Scripted sync runs in demo mode only")
        from s7_delivery.factory import demo_sync
        return demo_sync.rerun(self, story_id)
```

`state()` gains (in the top-level dict):
```python
            "demo": self.store.read_json_or(None, "demo", "script.json"),
```

- [ ] **Step 4: Run tests** — `pytest tests/test_demo_sync.py -v` passes; whole suite green.
- [ ] **Step 5: Commit** — `feat: scripted demo Sync storyline — green, green, push-failure, rerun-fix, parallel, complete`.

---

### Task 3: Server endpoints, Sync-button routing, DEMO badge presentation

**Files:**
- Modify: `apps/control/server.py` (two endpoints)
- Modify: `apps/control/web/src/components/Badge.tsx` (`Prov`)
- Modify: `apps/control/web/src/pages/build/DeveloperWorkspaces.tsx` (Sync gating + rerun action)
- Modify: `apps/control/web/src/pages/build/buildHelpers.tsx` (`gitIntegrationState` demo label)
- Modify: `apps/control/web/src/types.ts` (`demo` state key)
- Modify: the theme CSS (locate `prov-` classes; add `.prov-demo`)
- Test: `tests/test_demo_sync.py` (endpoint smoke via FastAPI TestClient if the repo has server tests; otherwise engine-level coverage from Task 2 stands)

**Interfaces:**
- Consumes: `Engine.demo_sync_advance`, `Engine.demo_rerun_story`, `state()["demo"]` from Task 2.
- Produces: `POST /api/runs/{run_id}/demo/sync` (RoleBody) and `POST /api/runs/{run_id}/demo/rerun` (`{role, story_id}`), both returning `{"result": {...}, **state}`.

- [ ] **Step 1: Server endpoints**

```python
class DemoRerunBody(BaseModel):
    role: str
    story_id: str


@app.post("/api/runs/{run_id}/demo/sync")
def post_demo_sync(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    result = eng.demo_sync_advance(_role(body.role))
    return {"result": result, **eng.state()}


@app.post("/api/runs/{run_id}/demo/rerun")
def post_demo_rerun(run_id: str, body: DemoRerunBody) -> dict:
    eng = _engine(run_id)
    result = eng.demo_rerun_story(_role(body.role), body.story_id)
    return {"result": result, **eng.state()}
```

- [ ] **Step 2: `Prov` demo presentation** (Badge.tsx)

```tsx
import { useRun } from '../state/RunContext'

export function Prov({ provenance }: { provenance?: string }) {
  const { data } = useRun()
  if (!provenance) return null
  // Demo-mode presentation rule (spec 2026-08-10): non-AI provenance renders
  // as one neutral DEMO chip; stored provenance is untouched. Live/replayed
  // AI badges are never rewritten (they cannot occur in a demo run).
  if (data?.run?.mode === 'demo'
      && (provenance === 'simulated' || provenance === 'rule_based')) {
    return <span className="prov prov-demo">DEMO</span>
  }
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
```

Confirm every `Prov` render site sits under the Run context provider (App-level provider — check `App.tsx`). Then sweep for other literal simulated wording shown in demo mode: `grep -rin "simulat" apps/control/web/src/pages apps/control/web/src/components` and map user-visible labels (e.g. `gitIntegrationState`'s `SIMULATED` label, any "Simulated" copy on build pages) to `DEMO` when `run.mode === 'demo'` — pass the mode in as a parameter rather than importing state into helpers.

- [ ] **Step 3: Sync button + rerun action** (DeveloperWorkspaces.tsx)

- Enable condition becomes `!(data.run.mode === 'live' || data.run.mode === 'demo') || syncing`.
- `doSyncGit` routes by mode: demo → `POST /demo/sync`, notify per `result.status`:
  - `advanced`: `Synced — ${stories.join(', ')} completed`
  - `failure`: `Sync failed for US-003 — git push rejected. Rerun the story to retry.`
  - `failure_pending`: same failure notice
  - `complete`: `Storyline complete — all stories synced and acceptance criteria met`
- On the failed workspace card (when `data.demo?.fix_pending && ws.story_id === data.demo.failed_story`): a **Rerun sync** button posting `/demo/rerun`.
- `types.ts`: `demo?: { step: number; failed_story: string; fix_pending: boolean; complete: boolean; history: string[] } | null`.

- [ ] **Step 4: CSS** — add alongside the other `prov-` rules (find them: `grep -rn "prov-simulated" apps/control/web/src`):

```css
.prov-demo { background: var(--surface2, #f4f4f2); color: var(--muted, #66655b); border: 1px solid var(--border, #d8d8d3); }
```

Match the existing `.prov` rule structure exactly — copy the `.prov-simulated` declaration block and neutralise the colors.

- [ ] **Step 5: Build + verify + commit**

```bash
cd apps/control/web && npm run build
cd ../../.. && pytest -q
git add apps/control/server.py apps/control/web/src apps/control/web/dist
git commit -m "feat: demo Sync surface and DEMO badge presentation"
```

---

### Task 4: Release/design document generator (backend)

**Files:**
- Create: `s7_delivery/factory/release_doc.py`
- Modify: `s7_delivery/factory/engine.py` (`release_document_generate` + `state()` key)
- Modify: `s7_delivery/factory/roles.py` (permission `generate_release_document`: `{Role.RELEASE_MANAGER, Role.DELIVERY_LEAD}`)
- Test: `tests/test_release_doc.py` (new)

**Interfaces:**
- Consumes: `Engine.state()` keys: `intake.epic`, `planning.stories` (each story has `story_id`, `title`, `acceptance_criteria[{ac_id, text}]`, `accountable_team`), `build.tasks` (per-story `tests[{name, ac_id, current_result}]`, `change_summary` if present — else `simulate.change_summary`), `build.workspaces` (`story_id`, `developer`, `team`), `build.reviews`, `build.quality_handoff`, `approvals` ledger (`subject`, `role`, `approver`, `decision`, `decided_at`, `note`), `build.architecture` (accepted-by/version), `release` record (`release_id`, `version`, `deployment`, `handover`), `quality` report.
- Produces:
  - `release_doc.document_data(state: dict) -> dict` — pure assembly, no I/O
  - `release_doc.render_markdown(data: dict) -> str`
  - `release_doc.render_html(data: dict) -> str` — self-contained, MapleSure red theme
  - `Engine.release_document_generate(role) -> dict` writes `release/release-document.md`, `release/release-document.html`, and meta `release/release-document.json` (`{generated_at, generated_by, provenance, sections: [...]}`); `state()["release_document"]` returns the meta or None.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_release_doc.py
import pytest
from s7_delivery.factory import demo, release_doc
from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role


@pytest.fixture()
def finished_run(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    demo.happy_path(eng)
    return eng


def test_document_requires_release_stage(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path)
    with pytest.raises(EngineError, match="release"):
        eng.release_document_generate(Role.RELEASE_MANAGER)


def test_document_contents(finished_run):
    eng = finished_run
    meta = eng.release_document_generate(Role.RELEASE_MANAGER)
    md = eng.store.read_text("release", "release-document.md")
    html = eng.store.read_text("release", "release-document.html")

    # TOC + required sections
    for heading in ("Table of Contents", "Plan Approval", "Development",
                    "Testing & Quality", "Acceptance Criteria",
                    "Release Approvals"):
        assert heading in md and heading in html

    # Who approved the plan, who developed, who tested
    assert "P. Moreau" in md            # plan sign-off (demo.py)
    assert "Priya Raman" in md          # a workspace developer
    assert "R. Osei" in md              # QA test-plan approver
    # Every story and every AC with a pass state
    for sid in ("US-001", "US-007"):
        assert sid in md
    assert "US-003-AC3" in md
    # The correction story is on record
    assert "Correction after independent review" in md
    # Branding: MapleSure only (hard rule 2 — the client name is asserted
    # absent by tests/test_no_client_names.py if present; at minimum:)
    assert "MapleSure" in html
    assert meta["sections"]


def test_state_exposes_document_meta(finished_run):
    eng = finished_run
    assert eng.state()["release_document"] is None
    eng.release_document_generate(Role.RELEASE_MANAGER)
    assert eng.state()["release_document"]["generated_by"]
```

(Adjust `read_text` to the store's actual reader; add one if the store only reads JSON — check `store.py:104` `write_text` for the symmetric reader.)

- [ ] **Step 2: Run tests, verify failure.**

- [ ] **Step 3: Implement `release_doc.py`**

`document_data(state)` assembles:
- `epic`: id, title, business outcome (from `intake.epic`).
- `plan_approvals`: approvals ledger rows with `subject == "plan"` (verify the actual subject value `planning_sign_off` writes — grep it) plus architecture acceptance (`build.architecture`: accepted_by, version).
- `stories`: per planning story — title, team, developer (workspace join on `story_id`), tester (QA approver from the pack's `test_plan` approval rows — join pack↔story via `build.delivery_packs`/`quality_handoff`; fall back to the QA Lead approver name), review verdict (`build.reviews` latest per task), change summary (task field or `simulate.change_summary(story_id)`), and `acceptance_criteria`: each AC with its test's `current_result` (join `build.tasks[].tests` on `ac_id`).
- `quality`: gate outcome from `quality` report.
- `release_approvals`: ledger rows with `subject == "release"`; `deployment` and `handover` from the release record.
- `toc`: derived list of section titles.

`render_markdown(data)`: plain portable markdown, numbered TOC linking to headings, one `##` per section, a table per story section (`| AC | Result |`).

`render_html(data)`: one self-contained string — inline CSS only, no CDN, palette and fonts matching `docs/s7-epic-to-release-deck.html`: `--red:#a20a29`, `--ink:#292923`, `--bg:#f2f2ef`, `Segoe UI` stack, the `MS` brand mark + "MapleSure Insurance" header, 4px red brandline top border. Sticky TOC not required — a simple anchor list is fine. Every section renders the same data as the markdown (single `document_data` source guarantees agreement).

Engine method:
```python
    def release_document_generate(self, role: Role) -> dict:
        """Render the release/design document from run state (any mode)."""
        roles.require("generate_release_document", role)
        if not self.store.exists("release", "release-record.json"):
            raise EngineError(
                "The release stage has not been reached — request release "
                "approval first"
            )
        from s7_delivery.factory import release_doc
        data = release_doc.document_data(self.state())
        self.store.write_text(release_doc.render_markdown(data), "release", "release-document.md")
        self.store.write_text(release_doc.render_html(data), "release", "release-document.html")
        meta = {
            "generated_at": now_iso(), "generated_by": role.value,
            "provenance": Provenance.SIMULATED.value
                if self.run().mode is not DemoMode.LIVE else Provenance.LIVE_AI.value,
            "sections": data["toc"],
        }
```
**Correction to the above provenance line:** the document is a deterministic rendering of run state — it is never AI output. Always record `provenance: "rule_based"`, in every mode. Then `self.store.write_json(meta, "release", "release-document.json")`, `self._record(...)` + `self._activity(...)` in the established style (artifact_type `release_document`, stage `Stage.RELEASE`), and return the meta.

`state()` gains:
```python
            "release_document": self.store.read_json_or(None, "release", "release-document.json"),
```

- [ ] **Step 4: Run tests; whole suite green.**
- [ ] **Step 5: Commit** — `feat: release/design document generator — markdown + MapleSure-themed HTML from run state`.

---

### Task 5: Release page UI + document endpoints

**Files:**
- Modify: `apps/control/server.py` (generate + two GET endpoints)
- Modify: `apps/control/web/src/pages/Release.tsx`
- Modify: `apps/control/web/src/types.ts` (`release_document` key)

**Interfaces:**
- Consumes: `Engine.release_document_generate`, files at `release/release-document.{md,html}`, `state()["release_document"]`.
- Produces: `POST /api/runs/{run_id}/release/document` (RoleBody); `GET /api/runs/{run_id}/release/document.html` (FileResponse, `text/html`); `GET /api/runs/{run_id}/release/document.md` (`text/markdown`, `Content-Disposition: attachment`).

- [ ] **Step 1: Endpoints**

```python
@app.post("/api/runs/{run_id}/release/document")
def post_release_document(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.release_document_generate(_role(body.role))
    return eng.state()


@app.get("/api/runs/{run_id}/release/document.html")
def get_release_document_html(run_id: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path("release", "release-document.html")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not generated yet")
    return FileResponse(path, media_type="text/html")


@app.get("/api/runs/{run_id}/release/document.md")
def get_release_document_md(run_id: str) -> FileResponse:
    eng = _engine(run_id)
    path = eng.store.path("release", "release-document.md")
    if not path.exists():
        raise HTTPException(status_code=404, detail="Document not generated yet")
    return FileResponse(
        path, media_type="text/markdown",
        filename=f"release-document-{run_id}.md",
    )
```

- [ ] **Step 2: Release.tsx** — after the approvals grid, a "Release document" card:
  - Not generated: explanation line + **Generate release document** button (`act('/release/document', {}, 'Release document generated')`).
  - Generated (`data.release_document`): meta line (`generated_by`, `generated_at`, `Prov` chip with the meta's provenance), **Open document** (new tab → `/api/runs/${runId}/release/document.html`), **Download markdown** (link to `.md` endpoint), and **Regenerate**.
  - Get `runId` the same way DeveloperWorkspaces does.

- [ ] **Step 3: Build, verify, commit**

```bash
cd apps/control/web && npm run build && cd ../../..
pytest -q
git add apps/control/server.py apps/control/web/src apps/control/web/dist
git commit -m "feat: release document surface — generate, view, download"
```

---

### Task 6: Docs sync + full verification

**Files:**
- Modify: `CLAUDE.md` (mode table / labelling note)
- Modify: `AGENTS.md` (mirror)

- [ ] **Step 1: CLAUDE.md** — add a short subsection under the Control Centre notes: demo mode is a fourth environment; scripted sync storyline; **the DEMO-chip presentation rule** (stored provenance untouched; on-screen `SIMULATED`/`RULE_BASED` render as a neutral DEMO chip in demo runs only; nothing ever renders as live AI); release document generator exists in all modes and is always badged rule-based. Mirror the same text in AGENTS.md.
- [ ] **Step 2: Full suite** — `pytest -q` all green; `npm run build` output already committed; `git status` clean of stray files (LLM cache files from earlier sessions stay untouched).
- [ ] **Step 3: Commit** — `docs: demo mode and release document recorded in CLAUDE.md/AGENTS.md`.

---

## Self-review notes

- Spec coverage: mode+selector (T1), labelling (T3), intake behaviour (T1), sync storyline incl. failure/rerun/parallel/no-op-past-end (T2/T3), document generator md+HTML+theme (T4), Release surface + download (T5), CLAUDE/AGENTS + dist rule (T3/T5/T6). Error handling: non-demo 409 (T2 wrapper), premature sync (T2), wrong-story rerun (T2), pre-release document 409 (T4); demo-sync HTTP surface returns 409 via the existing EngineError handler.
- The provenance line in Task 4's first draft is corrected inline: the document is always `rule_based`, never AI-badged.
- Names used across tasks: `demo_sync_advance` / `demo_rerun_story` / `state()["demo"]` / `state()["release_document"]` are consistent between Tasks 2, 3, 4, 5.
