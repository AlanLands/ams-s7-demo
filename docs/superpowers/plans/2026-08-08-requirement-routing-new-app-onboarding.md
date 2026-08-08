# Requirement Routing & New-Application Onboarding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before analysis runs, the Control Centre decides whether a live requirement fits inside the connected repos or needs a brand-new application — and if it needs one, walks a conversational setup, a reviewable scaffold, and an explicit-approval repo creation, after which the new repo grounds epic/story generation exactly like any other connected repo.

**Architecture:** Sub-project A (routing + new-app onboarding) from `docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md` §A, plus sub-project B (§B), which requires no new code — only a regression test proving it. Every new live call lives in `s7_delivery/factory/live_intake.py` and `s7_delivery/factory/scaffold.py` (new), follows the existing `_call`/`PromptLayers`/reject-don't-repair discipline, and every engine action follows the established mutation sequence: role check → precondition → store write → provenance record + activity event.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, `common.llm.complete()` + `PromptLayers`, plain `subprocess` git/`gh`, vanilla JS UI, pytest.

## Global Constraints

- **Hard rules 1–2:** all content synthetic MapleSure fiction; no real client names anywhere.
- **Hard rule 4:** no new dependencies, no CDN, no build step.
- **AI proposes, human decides.** The routing verdict is overridable before use; scaffold generation and the real GitHub repo creation are two separate, explicit human actions — nothing external happens without a distinct approval step.
- **No silent fallback.** A live-mode `LLMError` surfaces as an HTTP error; the run stays at its previous state.
- **Provenance discipline:** `Provenance.LIVE_AI` when `LLM_MODE` ∈ {live, record}, `Provenance.REPLAYED_AI` under replay, `Provenance.HUMAN` for the zero-repos routing short-circuit (deterministic system logic, not model-generated — same use of `HUMAN` already applied to `RepoRecord`, "extraction, not generation").
- **All tests offline.** No network, no API key. LLM calls are monkeypatched; `gh`/`git` network calls are monkeypatched at the single seam that touches them (`scaffold.push_new_repo`); everything else uses local git fixtures via `git init` in tmp dirs, exactly as `tests/test_factory_repos.py` and `tests/test_factory_live_engine.py` already do.
- **Run the full suite (`.venv/bin/pytest -q`) before every commit.**
- Simulation mode is untouched by every task in this plan — every new engine action either requires `DemoMode.LIVE` explicitly or is a pure addition that simulation never calls.
- `CLAUDE.md` and `AGENTS.md` must be updated in the same commit (Task 8) when scope changes.

## File Structure

| File | Responsibility |
|---|---|
| `s7_delivery/factory/models.py` (modify) | Add `RoutingVerdict` |
| `s7_delivery/factory/live_intake.py` (modify) | Add `route_requirement`, `run_new_app_setup` |
| `s7_delivery/factory/scaffold.py` (create) | `generate_scaffold`, `write_scaffold_locally`, `push_new_repo` |
| `s7_delivery/factory/engine.py` (modify) | `intake_route`, `intake_override_route`, `intake_new_app_setup`, `intake_new_app_answer`, `intake_generate_scaffold`, `intake_create_new_app_repo`, `state()` exposure |
| `s7_delivery/factory/roles.py` (modify) | Five new permissions |
| `apps/control/server.py` (modify) | Six new routes |
| `apps/control/static/app.js` (modify) | Routing card, new-app setup chat, scaffold review + create button |
| `tests/test_live_intake.py` (modify) | Task 1, 3 tests |
| `tests/test_scaffold.py` (create) | Task 4, 5 tests |
| `tests/test_factory_live_engine.py` (modify) | Task 2, 5, 6 tests |

---

### Task 1: `route_requirement` in `live_intake.py` + `RoutingVerdict` model

**Files:**
- Modify: `s7_delivery/factory/models.py` (add `RoutingVerdict` after `RepoRecord`, ~line 121)
- Modify: `s7_delivery/factory/live_intake.py` (add after `run_analysis`/`_validate_analysis`, before `run_clarification`)
- Test: `tests/test_live_intake.py` (append)

**Interfaces:**
- Produces: `RoutingVerdict(BaseModel)`: `verdict: str`, `reasoning: str`, `candidate_repos: list[str] = []`, `confidence: int | None = None`, `overridden_by: str = ""`, `overridden_at: str = ""`, `provenance: Provenance = Provenance.SIMULATED`.
- Produces: `live_intake.route_requirement(requirement: dict, packs: dict[str, str]) -> tuple[RoutingVerdict, dict]` — the dict is the usage block (may be `{}` on the zero-repos short-circuit, since no call happens).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
from s7_delivery.factory.models import RoutingVerdict

GOOD_ROUTE_ROUTABLE = {
    "verdict": "routable",
    "reasoning": "The claims-api already exposes member lookup; this extends it.",
    "candidate_repos": ["maplesure-claims-api"],
    "confidence": 85,
}

GOOD_ROUTE_NEW_APP = {
    "verdict": "new_application_needed",
    "reasoning": "Neither connected repository has anything resembling this capability.",
    "candidate_repos": [],
    "confidence": 90,
}


def test_route_requirement_routable(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ROUTE_ROUTABLE))
    monkeypatch.setenv("LLM_MODE", "live")
    verdict, usage = live_intake.route_requirement(REQUIREMENT, PACKS)
    assert isinstance(verdict, RoutingVerdict)
    assert verdict.verdict == "routable"
    assert verdict.candidate_repos == ["maplesure-claims-api"]
    assert verdict.provenance.value == "live_ai"
    assert usage["input_tokens"] == 1200


def test_route_requirement_new_application_needed(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_ROUTE_NEW_APP))
    verdict, _ = live_intake.route_requirement(REQUIREMENT, PACKS)
    assert verdict.verdict == "new_application_needed"
    assert verdict.candidate_repos == []


def test_route_requirement_zero_repos_short_circuits_without_a_call(monkeypatch):
    def forbidden(*a, **kw):
        raise AssertionError("route_requirement called the model with zero repos")
    monkeypatch.setattr(live_intake, "complete", forbidden)
    verdict, usage = live_intake.route_requirement(REQUIREMENT, {})
    assert verdict.verdict == "new_application_needed"
    assert verdict.provenance.value == "human"
    assert usage == {}


def test_route_requirement_rejects_bad_verdict(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, verdict="maybe")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="verdict"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


def test_route_requirement_rejects_unconnected_candidate(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, candidate_repos=["some-invented-repo"])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="candidate_repos"):
        live_intake.route_requirement(REQUIREMENT, PACKS)


def test_route_requirement_rejects_routable_with_no_candidates(monkeypatch):
    bad = dict(GOOD_ROUTE_ROUTABLE, candidate_repos=[])
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="routable"):
        live_intake.route_requirement(REQUIREMENT, PACKS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/test_live_intake.py -k route_requirement -v`
Expected: FAIL with `AttributeError: module 's7_delivery.factory.live_intake' has no attribute 'route_requirement'`

- [ ] **Step 3: Add `RoutingVerdict` to models.py**

In `s7_delivery/factory/models.py`, immediately after the `RepoRecord` class:

```python
class RoutingVerdict(BaseModel):
    """Whether a requirement fits the connected repos, or needs a new one."""

    verdict: str  # "routable" | "new_application_needed"
    reasoning: str
    candidate_repos: list[str] = []
    confidence: int | None = None
    overridden_by: str = ""
    overridden_at: str = ""
    provenance: Provenance = Provenance.SIMULATED
```

- [ ] **Step 4: Add `route_requirement` to `live_intake.py`**

Insert after `_validate_analysis` (before `def run_clarification`):

```python
ROUTE_ROLE = (
    "Your role is requirement routing: decide whether a business change "
    "request's capabilities plausibly land inside the connected application "
    "repositories, or whether it needs an application that does not exist "
    "yet. Ground the verdict in what the repositories' architecture.md files "
    "say they do and do not do."
)

_ROUTE_SHAPE = """{
  "verdict": "routable" | "new_application_needed",
  "reasoning": "<one paragraph>",
  "candidate_repos": ["<connected repository name, only if routable>"],
  "confidence": <0-100 self-assessment>
}"""


def route_requirement(
    requirement: dict, packs: dict[str, str]
) -> tuple["RoutingVerdict", dict]:
    from s7_delivery.factory.models import RoutingVerdict

    if not packs:
        # Deterministic: zero connected repos always means a new application
        # is needed. No model call — cheaper and more honest than asking a
        # model to notice an empty list. HUMAN provenance because this is
        # engine logic, not a model assertion (same use as RepoRecord's
        # "extraction, not generation").
        return RoutingVerdict(
            verdict="new_application_needed",
            reasoning="No repositories are connected yet.",
            candidate_repos=[],
            confidence=100,
            provenance=Provenance.HUMAN,
        ), {}
    task = f"""Decide whether this change request fits inside the connected
repositories, or needs an application that does not exist yet. Return JSON
exactly matching:
{_ROUTE_SHAPE}"""
    data, usage = _call(
        role=ROUTE_ROLE,
        ref=_ref(requirement, packs),
        task=task,
        beat="route",
        key_material=json.dumps(requirement, sort_keys=True)
        + "".join(packs[k] for k in sorted(packs)),
    )
    return _validate_route(data, set(packs)), usage


def _validate_route(data: dict, repo_names: set[str]) -> "RoutingVerdict":
    from s7_delivery.factory.models import RoutingVerdict

    verdict = data.get("verdict")
    if verdict not in {"routable", "new_application_needed"}:
        raise LLMError(
            f"route verdict must be 'routable' or 'new_application_needed', "
            f"got {verdict!r}"
        )
    candidates = data.get("candidate_repos") or []
    if not isinstance(candidates, list):
        raise LLMError("candidate_repos must be a list")
    unknown = [c for c in candidates if c not in repo_names]
    if unknown:
        raise LLMError(f"candidate_repos names non-connected repositories: {unknown}")
    if verdict == "routable" and not candidates:
        raise LLMError("verdict is routable but candidate_repos is empty")
    return RoutingVerdict(
        verdict=verdict,
        reasoning=str(data.get("reasoning", "")),
        candidate_repos=candidates,
        confidence=data.get("confidence"),
        provenance=provenance_now(),
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_live_intake.py -k route_requirement -v`
Expected: 6 PASS

- [ ] **Step 6: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/models.py s7_delivery/factory/live_intake.py tests/test_live_intake.py
git commit -m "feat: requirement routing verdict — routable vs new-application-needed"
```

---

### Task 2: `intake_route` / `intake_override_route` engine actions

**Files:**
- Modify: `s7_delivery/factory/engine.py` (new methods after `_context_packs`, ~line 568; `state()` intake dict)
- Modify: `s7_delivery/factory/roles.py` (add `route_requirement` permission)
- Modify: `apps/control/server.py` (two routes)
- Test: `tests/test_factory_live_engine.py` (append)

**Interfaces:**
- Consumes: `live_intake.route_requirement` (Task 1).
- Produces: `Engine.intake_route(role)`, `Engine.intake_override_route(role, verdict: str)`; artifact `intake/routing.json`; `state()["intake"]["routing"]`; routes `POST /api/runs/{run_id}/intake/route` `{role}` and `POST /api/runs/{run_id}/intake/override-route` `{role, verdict}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_live_engine.py`:

```python
def test_intake_route_calls_model_and_stores_verdict(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "route_requirement",
        lambda req, packs: (
            RoutingVerdict(
                verdict="routable", reasoning="fits",
                candidate_repos=["maplesure-sponsor-portal"],
                confidence=80, provenance=Provenance.LIVE_AI,
            ),
            {"input_tokens": 5, "output_tokens": 2},
        ),
    )
    eng.intake_route(Role.PRODUCT_ANALYST)
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "routable"
    assert routing["candidate_repos"] == ["maplesure-sponsor-portal"]


def test_intake_route_zero_repos_needs_no_monkeypatch(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    eng.intake_route(Role.PRODUCT_ANALYST)
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "new_application_needed"
    assert routing["provenance"] == "human"


def test_intake_override_route_records_who_and_when(tmp_path, monkeypatch):
    eng = _live_engine_with_repo(tmp_path, monkeypatch)
    monkeypatch.setattr(
        live_intake, "route_requirement",
        lambda req, packs: (
            RoutingVerdict(verdict="new_application_needed", reasoning="r",
                           provenance=Provenance.LIVE_AI), {},
        ),
    )
    eng.intake_route(Role.PRODUCT_ANALYST)
    eng.intake_override_route(Role.DELIVERY_LEAD, "routable")
    routing = eng.state()["intake"]["routing"]
    assert routing["verdict"] == "routable"
    assert routing["overridden_by"] == "delivery_lead"
    assert routing["overridden_at"]


def test_intake_override_route_before_route_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="[Rr]out"):
        eng.intake_override_route(Role.DELIVERY_LEAD, "routable")


def test_intake_route_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_route(Role.PRODUCT_ANALYST)
```

At the top of `tests/test_factory_live_engine.py`, the existing import block reads:

```python
from s7_delivery.factory.models import (
    AcceptanceCriterion,
    DemoMode,
    FeatureFlag,
    IntakeAnalysis,
    Provenance,
    Role,
    RollbackPlan,
    Story,
)
```

Add `RoutingVerdict` alphabetically so it reads:

```python
from s7_delivery.factory.models import (
    AcceptanceCriterion,
    DemoMode,
    FeatureFlag,
    IntakeAnalysis,
    Provenance,
    Role,
    RollbackPlan,
    RoutingVerdict,
    Story,
)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_live_engine.py -k "route" -v`
Expected: FAIL — `intake_route` does not exist.

- [ ] **Step 3: Implement**

`s7_delivery/factory/roles.py` — under `# intake`:

```python
    "route_requirement": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
```

`s7_delivery/factory/engine.py` — after `_context_packs` (~line 568):

```python
    def _routing(self) -> dict | None:
        return self.store.read_json_or(None, "intake", "routing.json")

    def intake_route(self, role: Role) -> None:
        """Live mode only: classify routable vs new_application_needed
        before analysis runs."""
        roles.require("route_requirement", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("Requirement routing runs in live mode only")
        import time

        from s7_delivery.factory import live_intake

        requirement = self.store.read_json("intake", "requirement.json")
        packs = self._context_packs()
        t0 = time.monotonic()
        verdict, usage = live_intake.route_requirement(requirement, packs)
        self.store.write_json(verdict, "intake", "routing.json")
        self._record(
            artifact_id="ROUTE-001", artifact_type="routing_verdict",
            payload=verdict, author="requirement-routing",
            stage=Stage.INTAKE, action="route", outcome="created",
            inputs=[requirement["request_id"]],
        )
        self._activity(
            stage=Stage.INTAKE, actor="requirement-routing",
            actor_type="live_ai" if packs else "system",
            workflow="requirement-routing",
            duration_s=round(time.monotonic() - t0, 2), outcome="created",
            details=f"verdict={verdict.verdict}; "
            f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_override_route(self, role: Role, verdict: str) -> None:
        roles.require("route_requirement", role)
        current = self._routing()
        if current is None:
            raise EngineError("Run requirement routing before overriding it")
        if verdict not in {"routable", "new_application_needed"}:
            raise EngineError(f"Unknown verdict {verdict!r}")
        current["verdict"] = verdict
        current["overridden_by"] = role.value
        current["overridden_at"] = now_iso()
        self.store.write_json(current, "intake", "routing.json")
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="requirement-routing", outcome="overridden",
            details=f"verdict set to {verdict}",
        )
```

In `Engine.state()`, the `"intake"` dict currently reads:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
            },
```

Add one line so it reads:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
                "routing": self.store.read_json_or(None, "intake", "routing.json"),
            },
```

`apps/control/server.py` — after the clarify-answer route:

```python
@app.post("/api/runs/{run_id}/intake/route")
def post_intake_route(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_route(_role(body.role))
    return eng.state()


class OverrideRouteBody(BaseModel):
    role: str
    verdict: str


@app.post("/api/runs/{run_id}/intake/override-route")
def post_intake_override_route(run_id: str, body: OverrideRouteBody) -> dict:
    eng = _engine(run_id)
    eng.intake_override_route(_role(body.role), body.verdict)
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_live_engine.py -k "route" -v`
Expected: 5 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_factory_live_engine.py
git commit -m "feat: intake_route/intake_override_route engine actions and routes"
```

---

### Task 3: New-application conversational setup

**Files:**
- Modify: `s7_delivery/factory/live_intake.py` (add `run_new_app_setup`)
- Modify: `s7_delivery/factory/engine.py` (add `_new_app`, `intake_new_app_setup`, `intake_new_app_answer`; `state()` intake dict)
- Modify: `s7_delivery/factory/roles.py` (add `setup_new_application`)
- Modify: `apps/control/server.py` (two routes)
- Test: `tests/test_live_intake.py`, `tests/test_factory_live_engine.py` (append)

**Interfaces:**
- Produces: `live_intake.run_new_app_setup(requirement: dict, transcript: list[dict]) -> tuple[dict, dict]` — result dict is either `{"done": False, "questions": [...]}` or `{"done": True, "name": str, "description": str, "stack": str}`; raises `LLMError` past the 2-round cap.
- Produces: `Engine.intake_new_app_setup(role)`, `Engine.intake_new_app_answer(role, answers)`; artifact `intake/new_app.json`: `{transcript, pending, rounds_used, max_rounds, name, description, stack}` (`name`/`description`/`stack` are `None` until settled); `state()["intake"]["new_app"]`; routes `POST .../intake/new-app-setup` `{role}`, `POST .../intake/new-app-answer` `{role, answers}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
GOOD_NEW_APP_QUESTIONS = {
    "needs_more_info": True,
    "questions": ["What should the repository be named?", "What stack should it use?"],
}
GOOD_NEW_APP_SETTLED = {
    "needs_more_info": False,
    "name": "maplesure-eligibility-check",
    "description": "Retirement eligibility check service.",
    "stack": "FastAPI + SQLite",
}


def test_run_new_app_setup_asks_questions(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_QUESTIONS))
    result, usage = live_intake.run_new_app_setup(REQUIREMENT, [])
    assert result == {"done": False, "questions": GOOD_NEW_APP_QUESTIONS["questions"]}
    assert usage["input_tokens"] == 1200


def test_run_new_app_setup_settles(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_SETTLED))
    result, _ = live_intake.run_new_app_setup(REQUIREMENT, [{"role": "assistant", "text": "q"}])
    assert result == {
        "done": True, "name": "maplesure-eligibility-check",
        "description": "Retirement eligibility check service.", "stack": "FastAPI + SQLite",
    }


def test_run_new_app_setup_rejects_invalid_name(monkeypatch):
    bad = dict(GOOD_NEW_APP_SETTLED, name="Not A Valid Name!")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="not a valid repository name"):
        live_intake.run_new_app_setup(REQUIREMENT, [])


def test_run_new_app_setup_rejects_missing_description(monkeypatch):
    bad = dict(GOOD_NEW_APP_SETTLED, description="")
    monkeypatch.setattr(live_intake, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="missing description or stack"):
        live_intake.run_new_app_setup(REQUIREMENT, [])


def test_run_new_app_setup_enforces_round_cap(monkeypatch):
    monkeypatch.setattr(live_intake, "complete", fake_complete(GOOD_NEW_APP_QUESTIONS))
    transcript = [
        {"role": "assistant", "text": "q1"}, {"role": "user", "text": "a1"},
        {"role": "assistant", "text": "q2"}, {"role": "user", "text": "a2"},
    ]
    with pytest.raises(LLMError, match="cap"):
        live_intake.run_new_app_setup(REQUIREMENT, transcript)
```

Append to `tests/test_factory_live_engine.py`:

```python
def test_new_app_setup_roundtrip(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: ({"done": False, "questions": ["Name it?"]}, {}),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    setup = eng.state()["intake"]["new_app"]
    assert setup["pending"] == ["Name it?"]

    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_answer(Role.PRODUCT_ANALYST, ["maplesure-eligibility-check"])
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    setup = eng.state()["intake"]["new_app"]
    assert setup["name"] == "maplesure-eligibility-check"
    assert setup["pending"] == []


def test_new_app_setup_in_simulation_mode_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.SIMULATION, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="live"):
        eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_live_intake.py tests/test_factory_live_engine.py -k "new_app" -v`
Expected: FAIL — `run_new_app_setup`/`intake_new_app_setup` missing.

- [ ] **Step 3: Implement**

`live_intake.py` — add near the top-level constants, `import re` alongside `hashlib, json, os`:

```python
import re
```

Append after `run_clarification`:

```python
NEW_APP_ROLE = (
    "Your role is capturing the essentials of a brand-new application "
    "before it exists: a short, valid repository name, a one-line "
    "description, and the intended technology stack. Ask only what is "
    "still missing; once all three are known, stop asking and report them."
)

_REPO_NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,38}$")

_NEW_APP_SHAPE_QUESTIONS = """{"needs_more_info": true, "questions": ["<question>"]}"""
_NEW_APP_SHAPE_SETTLED = (
    """{"needs_more_info": false, "name": "<repo-name-like-this>", """
    """"description": "<one line>", "stack": "<e.g. Flask + SQLite>"}"""
)


def run_new_app_setup(
    requirement: dict, transcript: list[dict]
) -> tuple[dict, dict]:
    rounds_used = sum(1 for t in transcript if t["role"] == "assistant")
    if rounds_used >= MAX_CLARIFICATION_ROUNDS:
        raise LLMError(
            f"New-application setup cap reached ({MAX_CLARIFICATION_ROUNDS} "
            "rounds) — name, description and stack must be settled by now."
        )
    task = f"""Conversation so far:
{_transcript_text(transcript)}

The requirement this new application would satisfy:
{json.dumps(requirement, indent=2)}

If name, description and stack are not all known yet, ask 1 to 3 short
questions. Otherwise, report the final values. Return JSON exactly matching
exactly one of:
{_NEW_APP_SHAPE_QUESTIONS}
{_NEW_APP_SHAPE_SETTLED}"""
    data, usage = _call(
        role=NEW_APP_ROLE,
        ref=json.dumps(requirement, indent=2),
        task=task,
        beat="new-app-setup",
        key_material=json.dumps(requirement, sort_keys=True)
        + json.dumps(transcript, sort_keys=True),
    )
    if data.get("needs_more_info"):
        questions = [str(q).strip() for q in data.get("questions", []) if str(q).strip()]
        if not 1 <= len(questions) <= 3:
            raise LLMError(f"expected 1-3 setup questions, got {len(questions)}")
        return {"done": False, "questions": questions}, usage
    name = str(data.get("name", "")).strip()
    if not _REPO_NAME_RE.match(name):
        raise LLMError(f"new application name {name!r} is not a valid repository name")
    description = str(data.get("description", "")).strip()
    stack = str(data.get("stack", "")).strip()
    if not description or not stack:
        raise LLMError("new application setup is missing description or stack")
    return {"done": True, "name": name, "description": description, "stack": stack}, usage
```

`roles.py` — under `# intake`:

```python
    "setup_new_application": {Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD},
```

`engine.py` — after `intake_override_route`:

```python
    def _new_app(self) -> dict:
        return self.store.read_json_or(
            {"transcript": [], "pending": [], "rounds_used": 0, "max_rounds": 2,
             "name": None, "description": None, "stack": None},
            "intake", "new_app.json",
        )

    def intake_new_app_setup(self, role: Role) -> None:
        roles.require("setup_new_application", role)
        if self.run().mode is not DemoMode.LIVE:
            raise EngineError("New-application setup runs in live mode only")
        import time

        from s7_delivery.factory import live_intake

        setup = self._new_app()
        if setup["pending"]:
            raise EngineError("Answer the open questions before asking again")
        if setup["name"]:
            raise EngineError("New-application setup is already complete")
        requirement = self.store.read_json("intake", "requirement.json")
        t0 = time.monotonic()
        result, usage = live_intake.run_new_app_setup(requirement, setup["transcript"])
        if result["done"]:
            setup["name"] = result["name"]
            setup["description"] = result["description"]
            setup["stack"] = result["stack"]
            outcome = "settled"
        else:
            questions = result["questions"]
            setup["transcript"].append({"role": "assistant", "text": "\n".join(questions)})
            setup["pending"] = questions
            setup["rounds_used"] = sum(
                1 for t in setup["transcript"] if t["role"] == "assistant"
            )
            outcome = "asked"
        self.store.write_json(setup, "intake", "new_app.json")
        self._activity(
            stage=Stage.INTAKE, actor="requirement-routing", actor_type="live_ai",
            workflow="new-app-setup", duration_s=round(time.monotonic() - t0, 2),
            outcome=outcome,
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )

    def intake_new_app_answer(self, role: Role, answers: list[str]) -> None:
        roles.require("setup_new_application", role)
        setup = self._new_app()
        if not setup["pending"]:
            raise EngineError("There are no open questions to answer")
        if len(answers) != len(setup["pending"]):
            raise EngineError(
                f"Expected {len(setup['pending'])} answers, got {len(answers)}"
            )
        joined = "\n".join(
            f"Q: {q}\nA: {a.strip() or '(no answer — make a stated assumption)'}"
            for q, a in zip(setup["pending"], answers, strict=True)
        )
        setup["transcript"].append({"role": "user", "text": joined})
        setup["pending"] = []
        self.store.write_json(setup, "intake", "new_app.json")
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="new-app-setup", outcome="answered",
            details=f"{len(answers)} answers recorded",
        )
```

In `Engine.state()`, the `"intake"` dict now ends with the `"routing"` line added in Task 2. Add one more line so it reads:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
                "routing": self.store.read_json_or(None, "intake", "routing.json"),
                "new_app": self.store.read_json_or(None, "intake", "new_app.json"),
            },
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/intake/new-app-setup")
def post_new_app_setup(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_new_app_setup(_role(body.role))
    return eng.state()


class NewAppAnswerBody(BaseModel):
    role: str
    answers: list[str]


@app.post("/api/runs/{run_id}/intake/new-app-answer")
def post_new_app_answer(run_id: str, body: NewAppAnswerBody) -> dict:
    eng = _engine(run_id)
    eng.intake_new_app_answer(_role(body.role), body.answers)
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_live_intake.py tests/test_factory_live_engine.py -k "new_app" -v`
Expected: PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/live_intake.py s7_delivery/factory/engine.py s7_delivery/factory/roles.py apps/control/server.py tests/test_live_intake.py tests/test_factory_live_engine.py
git commit -m "feat: new-application conversational setup, capped and transcripted"
```

---

### Task 4: Scaffold generation

**Files:**
- Create: `s7_delivery/factory/scaffold.py`
- Modify: `s7_delivery/factory/engine.py` (add `intake_generate_scaffold`, `_scaffold_dir_files`, `_scaffold_files`; `state()` intake dict)
- Modify: `s7_delivery/factory/roles.py` (reuse `setup_new_application`)
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_scaffold.py` (create), `tests/test_factory_live_engine.py` (append)

**Interfaces:**
- Produces: `scaffold.generate_scaffold(name: str, description: str, stack: str) -> tuple[dict[str, str], dict]` — file map is `{"architecture.md": str, "README.md": str}`.
- Produces: `Engine.intake_generate_scaffold(role)`; files written to `intake/scaffold/<name>/architecture.md` and `.../README.md`; `state()["intake"]["scaffold"]` — a `dict[str, str]` or `None`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_scaffold.py`:

```python
"""Scaffold generation — canned model JSON, offline."""
import pytest

from common.llm import LLMError
from s7_delivery.factory import scaffold


def fake_complete(response: dict):
    import json

    def _fake(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        if usage_out is not None:
            usage_out.update({"input_tokens": 400, "output_tokens": 300})
        return json.dumps(response)
    return _fake


GOOD_SCAFFOLD = {
    "architecture_md": (
        "# MapleSure Eligibility Check — architecture\n\n"
        "New application. No components exist yet.\n\n"
        "## What this application does NOT do\n- Nothing is built yet.\n"
    ),
    "readme_md": "# MapleSure Eligibility Check\n\nNew synthetic demo application.\n",
}


def test_generate_scaffold_returns_two_files(monkeypatch):
    monkeypatch.setattr(scaffold, "complete", fake_complete(GOOD_SCAFFOLD))
    files, usage = scaffold.generate_scaffold(
        "maplesure-eligibility-check", "Retirement eligibility check.", "FastAPI"
    )
    assert set(files) == {"architecture.md", "README.md"}
    assert "does NOT do" in files["architecture.md"]
    assert usage["input_tokens"] == 400


def test_generate_scaffold_rejects_empty_architecture(monkeypatch):
    bad = dict(GOOD_SCAFFOLD, architecture_md="")
    monkeypatch.setattr(scaffold, "complete", fake_complete(bad))
    with pytest.raises(LLMError, match="empty"):
        scaffold.generate_scaffold("name", "desc", "stack")
```

Append to `tests/test_factory_live_engine.py`:

```python
from s7_delivery.factory import scaffold as scaffold_mod


def test_generate_scaffold_writes_files(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": "maplesure-eligibility-check",
             "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda name, description, stack: (
            {"architecture.md": "# arch\n", "README.md": "# readme\n"}, {},
        ),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)
    scaffold_state = eng.state()["intake"]["scaffold"]
    assert scaffold_state["architecture.md"] == "# arch\n"


def test_generate_scaffold_before_setup_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="setup"):
        eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_scaffold.py tests/test_factory_live_engine.py -k scaffold -v`
Expected: FAIL — `s7_delivery.factory.scaffold` does not exist.

- [ ] **Step 3: Write `scaffold.py` (generation half) and wire the engine**

```python
# s7_delivery/factory/scaffold.py
"""New-application scaffold generation and creation (spec: requirement-
routing-and-delivery-handoff-design.md §A4).

Deliberately minimal: architecture.md + README.md only, describing an
application that does not exist yet. No per-stack boilerplate source files —
generating real, runnable code for an arbitrary stack is a separately-scoped
problem (see the design's Out of scope).

`push_new_repo` is the only function here that touches the network (`gh`);
everything else is local file and git operations, exercised for real in
tests.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from common.llm import LLMError, complete, parse_json_response
from common.prompt import PromptLayers
from s7_delivery.factory.repos import RepoConnectError

RULES = (
    "You are an AI delivery assistant for MapleSure Insurance, a fictional "
    "insurer in a tabletop exercise. All data is synthetic. Answer with "
    "structured JSON only, and never invent facts the input does not support."
)

SCAFFOLD_ROLE = (
    "Your role is writing the founding architecture.md for a brand-new "
    "application: name, description and stack are known; the application "
    "has no code yet. State plainly, in the architecture.md's own 'what "
    "this application does NOT do' convention, that nothing is built yet."
)

_SCAFFOLD_SHAPE = """{
  "architecture_md": "<full markdown content for architecture.md>",
  "readme_md": "<full markdown content for README.md>"
}"""


def generate_scaffold(
    name: str, description: str, stack: str
) -> tuple[dict[str, str], dict]:
    task = f"""New application:
name: {name}
description: {description}
stack: {stack}

Write architecture.md (components: none yet; data: none yet; explicitly
state this is a new application with no code) and a short README.md. Return
JSON exactly matching:
{_SCAFFOLD_SHAPE}"""
    usage: dict = {}
    response = complete(
        PromptLayers(rules=RULES, role=SCAFFOLD_ROLE, task=task),
        json_mode=True,
        cache_key=f"s7_factory_scaffold:{name}",
        usage_out=usage,
    )
    data = parse_json_response(response, required_keys={"architecture_md", "readme_md"})
    arch = str(data["architecture_md"]).strip()
    readme = str(data["readme_md"]).strip()
    if not arch or not readme:
        raise LLMError("scaffold response has an empty architecture.md or README.md")
    return {"architecture.md": arch, "README.md": readme}, usage


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True,
    )


def write_scaffold_locally(name: str, files: dict[str, str], dest_root: Path) -> Path:
    """Write the reviewed scaffold to disk and commit it locally. No network."""
    repo = dest_root / name
    if repo.exists():
        raise RepoConnectError(f"{name} scaffold already exists locally")
    for filename, content in files.items():
        target = repo / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    ident = ["-c", "user.email=demo@example.invalid", "-c", "user.name=s7-delivery-factory"]
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, *ident, "commit", "-qm", "Initial application scaffold")
    return repo


def push_new_repo(repo: Path, name: str) -> str:
    """The only network-touching call: gh repo create --push. Tests
    monkeypatch this function; write_scaffold_locally is exercised for real."""
    try:
        subprocess.run(
            ["gh", "repo", "create", name, "--private", "--source", str(repo), "--push"],
            check=True, capture_output=True, text=True,
        )
        owner = subprocess.run(
            ["gh", "api", "user", "-q", ".login"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise RepoConnectError((exc.stderr or str(exc)).strip()) from exc
    return f"https://github.com/{owner}/{name}"
```

`engine.py` — after `intake_new_app_answer`:

```python
    def _scaffold_dir_files(self, name: str) -> dict[str, str]:
        root = self.store.path("intake", "scaffold", name)
        if not root.is_dir():
            return {}
        return {p.name: p.read_text(encoding="utf-8") for p in sorted(root.iterdir()) if p.is_file()}

    def _scaffold_files(self, name: str) -> dict[str, str]:
        files = self._scaffold_dir_files(name)
        if not files:
            raise EngineError(f"No scaffold generated for {name!r} yet")
        return files

    def intake_generate_scaffold(self, role: Role) -> None:
        roles.require("setup_new_application", role)
        import time

        from s7_delivery.factory import scaffold as scaffold_mod

        setup = self._new_app()
        if not setup["name"]:
            raise EngineError("Complete the new-application setup conversation first")
        t0 = time.monotonic()
        files, usage = scaffold_mod.generate_scaffold(
            setup["name"], setup["description"], setup["stack"]
        )
        for filename, content in files.items():
            self.store.write_text(content, "intake", "scaffold", setup["name"], filename)
        self._activity(
            stage=Stage.INTAKE, actor="requirement-routing", actor_type="live_ai",
            workflow="new-app-scaffold", duration_s=round(time.monotonic() - t0, 2),
            outcome="created",
            details=f"in={usage.get('input_tokens')} out={usage.get('output_tokens')} tokens",
        )
```

In `Engine.state()`, insert new local computations directly after the existing `stale_ids = {s["artifact_id"] for s in stale}` line and before `for row in current:`:

```python
        stale_ids = {s["artifact_id"] for s in stale}
        new_app = self.store.read_json_or(None, "intake", "new_app.json")
        scaffold = None
        if new_app and new_app.get("name"):
            files = self._scaffold_dir_files(new_app["name"])
            scaffold = files or None
        for row in current:
```

Then change the `"intake"` dict's `"new_app"` line (added in Task 3) to reuse this local instead of re-reading the file, and add `"scaffold"` immediately after it, so the block reads:

```python
            "intake": {
                "requirement": self.store.read_json_or(None, "intake", "requirement.json"),
                "analysis": self.store.read_json_or(None, "intake", "analysis.json"),
                "epic": self.store.read_json_or(None, "intake", "epic.json"),
                "repos": self.store.read_json_or([], "intake", "repos.json"),
                "clarifications": self.store.read_json_or(None, "intake", "clarifications.json"),
                "routing": self.store.read_json_or(None, "intake", "routing.json"),
                "new_app": new_app,
                "scaffold": scaffold,
            },
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/intake/generate-scaffold")
def post_generate_scaffold(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_generate_scaffold(_role(body.role))
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_scaffold.py tests/test_factory_live_engine.py -k scaffold -v`
Expected: PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/scaffold.py s7_delivery/factory/engine.py apps/control/server.py tests/test_scaffold.py tests/test_factory_live_engine.py
git commit -m "feat: new-application scaffold generation, reviewed before creation"
```

---

### Task 5: Repo creation from scaffold — the approval action

**Files:**
- Modify: `s7_delivery/factory/roles.py` (add `create_new_application_repo`)
- Modify: `s7_delivery/factory/engine.py` (add `intake_create_new_app_repo`)
- Modify: `apps/control/server.py` (one route)
- Test: `tests/test_factory_live_engine.py` (append)

**Interfaces:**
- Consumes: `scaffold.write_scaffold_locally`, `scaffold.push_new_repo` (Task 4); `repos.clone_repo`, `repos.build_context_pack`, `repos.RepoConnectError` (existing).
- Produces: `Engine.intake_create_new_app_repo(role)` — on success, the new repo is a `RepoRecord` in `intake/repos.json` exactly like any connected repo, and its context pack exists at `intake/context/<name>.md`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_factory_live_engine.py`:

```python
def _settled_new_app(eng, monkeypatch, name="maplesure-eligibility-check"):
    monkeypatch.setattr(
        live_intake, "run_new_app_setup",
        lambda req, transcript: (
            {"done": True, "name": name, "description": "d", "stack": "FastAPI"}, {},
        ),
    )
    eng.intake_new_app_setup(Role.PRODUCT_ANALYST)
    monkeypatch.setattr(
        scaffold_mod, "generate_scaffold",
        lambda n, d, s: ({"architecture.md": "# arch\n\nWhat this application does NOT do\n- nothing yet\n", "README.md": "# readme\n"}, {}),
    )
    eng.intake_generate_scaffold(Role.PRODUCT_ANALYST)


def test_create_new_app_repo_normalizes_into_connected_repos(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)

    def fake_push(repo_path, name):
        return str(repo_path)  # a local path is a valid clone_repo() URL too

    monkeypatch.setattr(scaffold_mod, "push_new_repo", fake_push)
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    repos = eng.state()["intake"]["repos"]
    assert repos[-1]["name"] == "maplesure-eligibility-check"
    assert eng.store.exists("intake", "context", "maplesure-eligibility-check.md")


def test_create_new_app_repo_before_setup_is_an_error(tmp_path):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    with pytest.raises(EngineError, match="setup"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)


def test_create_new_app_repo_push_failure_leaves_no_connected_repo(tmp_path, monkeypatch):
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch)

    def boom(repo_path, name):
        from s7_delivery.factory.repos import RepoConnectError
        raise RepoConnectError("gh: name already taken")

    monkeypatch.setattr(scaffold_mod, "push_new_repo", boom)
    with pytest.raises(EngineError, match="failed"):
        eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)
    assert eng.state()["intake"]["repos"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_factory_live_engine.py -k create_new_app_repo -v`
Expected: FAIL — `intake_create_new_app_repo` missing.

- [ ] **Step 3: Implement**

`roles.py` — under `# intake`:

```python
    "create_new_application_repo": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
```

`engine.py` — after `intake_generate_scaffold`:

```python
    def intake_create_new_app_repo(self, role: Role) -> None:
        """The approval action: creates the real GitHub repo from the
        reviewed scaffold, then normalizes it into an ordinary connected
        repo — §B needs no special case because of this."""
        roles.require("create_new_application_repo", role)
        from s7_delivery.factory.repos import RepoConnectError, build_context_pack, clone_repo
        from s7_delivery.factory.scaffold import push_new_repo, write_scaffold_locally

        setup = self._new_app()
        name = setup.get("name")
        if not name:
            raise EngineError("Complete the new-application setup conversation first")
        files = self._scaffold_files(name)
        if any(r["name"] == name for r in self._connected_repos()):
            raise EngineError(f"{name} is already connected")

        try:
            repo_path = write_scaffold_locally(name, files, self.store.path("scaffold-src"))
        except RepoConnectError as exc:
            raise EngineError(f"Writing the scaffold locally failed: {exc}") from exc
        try:
            url = push_new_repo(repo_path, name)
        except RepoConnectError as exc:
            raise EngineError(f"New application repo creation failed: {exc}") from exc
        try:
            rec = clone_repo(url, self.store.path("repos"))
        except RepoConnectError as exc:
            raise EngineError(f"Cloning the newly created repo failed: {exc}") from exc

        repos = self.store.read_json_or([], "intake", "repos.json")
        repos.append(rec.model_dump(mode="json"))
        self.store.write_json(repos, "intake", "repos.json")
        pack = build_context_pack(self.store.path("repos", rec.name), rec.name)
        self.store.write_text(pack, "intake", "context", f"{rec.name}.md")

        self._record(
            artifact_id=f"REPO-{rec.name}", artifact_type="repository", payload=rec,
            author=role.value, stage=Stage.INTAKE, action="create-new-app-repo",
            outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="create-new-application-repo", artifact=rec.name,
            outcome="created", details=f"{rec.url} @ {rec.head_sha[:10]}",
        )
```

`server.py`:

```python
@app.post("/api/runs/{run_id}/intake/create-new-app-repo")
def post_create_new_app_repo(run_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_create_new_app_repo(_role(body.role))
    return eng.state()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_factory_live_engine.py -k create_new_app_repo -v`
Expected: 3 PASS

- [ ] **Step 5: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add s7_delivery/factory/roles.py s7_delivery/factory/engine.py apps/control/server.py tests/test_factory_live_engine.py
git commit -m "feat: create-new-application-repo — the approval action, normalized into connected repos"
```

---

### Task 6: Sub-project B verification — new-app repos ground analysis and planning unchanged

**Files:**
- Test: `tests/test_factory_live_engine.py` (append)

**Interfaces:**
- No new production code. This task exists to prove, with a real test, the design's B claim: "no special case needed."

- [ ] **Step 1: Write the test**

Append to `tests/test_factory_live_engine.py`:

```python
def test_new_app_repo_grounds_live_analysis_with_no_special_case(tmp_path, monkeypatch):
    """B: a repo created via the new-app path is indistinguishable, to
    run_analysis, from one connected by URL — same context-pack shape,
    same validator, no branch in live_intake for repo origin."""
    eng = Engine.create(DemoMode.LIVE, root=tmp_path / "runs")
    _settled_new_app(eng, monkeypatch, name="maplesure-new-claims-portal")
    monkeypatch.setattr(scaffold_mod, "push_new_repo", lambda repo_path, name: str(repo_path))
    eng.intake_create_new_app_repo(Role.DELIVERY_LEAD)

    monkeypatch.setattr(
        live_intake, "run_analysis",
        lambda req, packs, transcript: (
            _fake_analysis_for(list(packs)[0]), {"input_tokens": 1, "output_tokens": 1},
        ),
    )
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    analysis = eng.state()["intake"]["analysis"]
    assert analysis["affected_applications"] == ["maplesure-new-claims-portal"]
    assert analysis["provenance"] == "live_ai"


def _fake_analysis_for(repo_name: str) -> IntakeAnalysis:
    return IntakeAnalysis(
        problem_understood=True, business_impact="impact",
        affected_applications=[repo_name],
        stakeholders=["ops"], dependencies=["dep"], risks=["risk"],
        clarification_questions=["q1"], assumptions=["a1"],
        business_rules=[{"rule_id": "BR-01", "text": "rule"}],
        risk_register=[{"text": "r", "severity": "high"}],
        confidence=80, provenance=Provenance.LIVE_AI,
    )
```

- [ ] **Step 2: Run the test**

Run: `.venv/bin/pytest tests/test_factory_live_engine.py -k grounds_live_analysis -v`
Expected: PASS on first run — this task adds no production code, only proof.

- [ ] **Step 3: Full suite, then commit**

```bash
.venv/bin/pytest -q
git add tests/test_factory_live_engine.py
git commit -m "test: new-application repos ground live analysis with no special case (B)"
```

---

### Task 7: UI — routing card, new-app setup chat, scaffold review

No JS test harness exists in this repo; verified by driving the app in Chrome/curl (Step 4). Follow the existing style: `el()` builders, `act(path, body, okMessage)` (auto-injects role), the `clarCard`/`repoCard` pattern already in `renderIntake`.

**Files:**
- Modify: `apps/control/static/app.js` (`renderIntake`, ~lines 404–564)

**Interfaces:**
- Consumes: `intake.routing`, `intake.new_app`, `intake.scaffold`, `run.mode` from the state payload; routes from Tasks 2, 3, 4, 5.

- [ ] **Step 1: Routing card**

In `renderIntake`, after the `repoCard` definition and before the `rail` const, add:

```js
    const routing = d.intake?.routing;
    const routingCard = isLive ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "Requirement Routing" }),
        routing ? prov(routing.provenance) : null),
      routing
        ? el("div", {},
            el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
              el("b", { text: "Verdict" }),
              el("span", {}, el("span", {
                class: `chip ${routing.verdict === "routable" ? "priority-low" : "priority-high"}`,
                text: routing.verdict === "routable" ? "Fits connected repos" : "New application needed",
              })),
              el("b", { text: "Reasoning" }), el("span", { text: routing.reasoning }),
              routing.candidate_repos?.length ? el("b", { text: "Candidate repos" }) : null,
              routing.candidate_repos?.length ? el("span", { text: routing.candidate_repos.join(", ") }) : null,
              routing.overridden_by ? el("b", { text: "Overridden by" }) : null,
              routing.overridden_by ? el("span", { text: `${routing.overridden_by} at ${routing.overridden_at}` }) : null),
            (() => {
              const sel = el("select", {},
                el("option", { value: "routable", text: "Routable" }),
                el("option", { value: "new_application_needed", text: "New application needed" }));
              sel.value = routing.verdict;
              return el("div", { style: "margin-top:10px; display:flex; gap:8px; align-items:center" },
                el("span", { class: "hint", text: "Override:" }), sel,
                el("button", {
                  class: "outline", text: "Apply override",
                  onclick: () => act("/intake/override-route", { verdict: sel.value }, "Routing verdict overridden"),
                }));
            })())
        : el("p", { class: "hint", text: "Run requirement routing to decide whether this fits the connected repos, or needs a new application." })) : null;
```

- [ ] **Step 2: New-app setup chat and scaffold review**

Immediately after the `routingCard` block:

```js
    const newApp = d.intake?.new_app;
    const scaffoldFiles = d.intake?.scaffold;
    const newAppCard = (isLive && routing?.verdict === "new_application_needed") ? el("div", { class: "card" },
      el("div", { class: "section-title" }, el("h3", { text: "New Application Setup" })),
      newApp?.name
        ? el("div", {},
            el("div", { class: "kv", style: "grid-template-columns: 130px 1fr" },
              el("b", { text: "Name" }), el("span", { class: "mono", text: newApp.name }),
              el("b", { text: "Description" }), el("span", { text: newApp.description }),
              el("b", { text: "Stack" }), el("span", { text: newApp.stack })),
            scaffoldFiles
              ? el("div", { style: "margin-top:10px" },
                  el("p", { class: "hint", text: "Scaffold generated — review before creating the repository." }),
                  ...Object.entries(scaffoldFiles).map(([name, content]) =>
                    el("details", { style: "margin-top:6px" },
                      el("summary", { text: name }),
                      el("pre", { class: "mono", style: "white-space:pre-wrap; font-size:12px", text: content }))),
                  el("button", {
                    class: "primary sq block", style: "margin-top:10px", text: "Create Repository",
                    onclick: () => act("/intake/create-new-app-repo", {}, "New application repository created"),
                  }))
              : el("button", {
                  class: "outline block", style: "margin-top:10px", text: "Generate Scaffold",
                  onclick: () => act("/intake/generate-scaffold", {}, "Scaffold generated"),
                }))
        : el("div", {},
            newApp?.pending?.length
              ? (() => {
                  const inputs = newApp.pending.map((q) =>
                    ({ q, input: el("input", { type: "text", placeholder: "Answer" }) }));
                  return el("div", {},
                    ...inputs.map(({ q, input }) => el("div", { style: "margin-bottom:8px" },
                      el("p", { text: q }), input)),
                    el("button", {
                      class: "primary sq", text: "Submit answers",
                      onclick: () => act("/intake/new-app-answer",
                        { answers: inputs.map(({ input }) => input.value) }, "Answers recorded"),
                    }));
                })()
              : el("button", {
                  class: "outline block", text: "Start New Application Setup",
                  onclick: () => act("/intake/new-app-setup", {}, "Setup started"),
                }))) : null;
```

- [ ] **Step 3: Insert into the returned layout and add the "Route Requirement" rail button**

In the rail's Actions card (before "Ask AI Clarification"), add:

```js
        isLive ? el("button", {
          class: "outline block", style: "margin-top:10px", text: "Route Requirement",
          onclick: () => act("/intake/route", {}, "Requirement routed"),
        }) : null,
```

In the returned layout, insert `routingCard` and `newAppCard` between `repoCard` and `reqCard`:

```js
        repoCard ? el("div", { style: "margin-bottom:14px" }, repoCard) : null,
        routingCard ? el("div", { style: "margin-bottom:14px" }, routingCard) : null,
        newAppCard ? el("div", { style: "margin-bottom:14px" }, newAppCard) : null,
        reqCard,
```

- [ ] **Step 4: Verify by driving the app**

```bash
lsof -ti:8720 | xargs -r kill 2>/dev/null
set -a; source .env 2>/dev/null; set +a
LLM_MODE=replay .venv/bin/uvicorn apps.control.server:app --port 8720 &
```

Then in a browser or via curl:
1. Create a live run with **zero** connected repos, click "Route Requirement" → verdict renders as "New application needed" immediately (no LLM wait — the zero-repos short-circuit).
2. Click "Start New Application Setup" → answer its questions → "Generate Scaffold" renders `architecture.md`/`README.md` previews → "Create Repository" (only run this against a throwaway name if actually exercising the real path; verify the button and its request wiring without necessarily completing a real `gh repo create` in this manual check — Task 8's rehearsal covers the full real path).
3. On a run with a connected repo, click "Route Requirement" again → override control renders and flips the verdict via `/intake/override-route`.
4. Kill the server.

- [ ] **Step 5: Commit**

```bash
git add apps/control/static/app.js
git commit -m "feat(ui): requirement routing, new-app setup chat, scaffold review"
```

---

### Task 8: Docs and rehearsal

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md` (mirrored, same commit), `README.md`, `docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md` (status line for §A/§B only — leave §C/§D status alone, that's the sibling plan's job)

- [ ] **Step 1: Update the docs**

- `CLAUDE.md`/`AGENTS.md`: one paragraph noting live mode now includes a requirement-routing verdict (routable vs. new-application-needed, human-overridable) and a conversational new-application onboarding flow (setup → scaffold review → approved GitHub repo creation), after which the new repo grounds analysis/planning exactly like any connected repo.
- `README.md`: extend the "Live mode" section with the routing/new-app beats in the rehearsal beat order.
- Spec file: mark §A and §B as `implemented` in a status note (leave the overall doc status alone since §C/§D are a separate plan).

- [ ] **Step 2: Rehearsal (manual, real API key and one real throwaway GitHub repo)**

⚠️ This step creates one additional real, private GitHub repo under the authenticated `gh` account, named clearly as disposable (e.g. `maplesure-scaffold-rehearsal`) — report its URL so it can be deleted afterward if not wanted.

With `LLM_MODE=record`: create a live run, do **not** connect any repos, run requirement routing (confirm the zero-repos short-circuit, no LLM call), start new-application setup, answer its questions, generate the scaffold, review it, then create the real repo (`maplesure-scaffold-rehearsal`). Confirm it appears as a connected repo and that a subsequent live analysis grounds against it. Then set `LLM_MODE=replay`, reset, repeat the same conversational answers: routing, setup, and scaffold-generation beats must replay offline (repo creation is a one-time real action, not repeated under replay — the created repo is simply reconnected by URL like any other repo for the replay pass).

- [ ] **Step 3: Full suite + ruff, commit**

```bash
.venv/bin/pytest -q
ruff check s7_delivery/factory/scaffold.py s7_delivery/factory/live_intake.py s7_delivery/factory/engine.py apps/control/server.py tests/test_scaffold.py tests/test_live_intake.py tests/test_factory_live_engine.py
git add CLAUDE.md AGENTS.md README.md docs/superpowers/specs/2026-08-08-requirement-routing-and-delivery-handoff-design.md
git commit -m "docs: requirement routing and new-application onboarding — status, runbook"
```
