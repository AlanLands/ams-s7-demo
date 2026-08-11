# Human Business Rules + Planner Coverage Retry — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let humans add/edit/remove their own business rules on the intake surface (feeding planning), and give `run_plan` one bounded corrective retry when the model leaves business rules unclaimed.

**Architecture:** Human rules live in a separate per-run file `intake/business_rules.json` (surviving analysis re-runs), merged with AI rules by one engine helper that feeds both the UI state payload and live planning. The planner retry is a single triaged re-call inside `live_intake.run_plan` with distinct cache-key material.

**Tech Stack:** Python (engine + FastAPI server), React + TypeScript + Vite (Control Centre), pytest.

**Spec:** `docs/superpowers/specs/2026-08-11-business-rules-design.md`

## Global Constraints

- Hard rule 4 (amended): any change under `apps/control/web/src/` must be followed by `npm run build` and the regenerated `apps/control/web/dist/` committed **in the same commit**.
- CLAUDE.md § Agent instructions: CLAUDE.md and AGENTS.md must be updated **in the same commit** when scope/features change.
- Human rule IDs are `BR-H<n>`; AI rule IDs stay `BR-<n>`. AI rules are immutable. All rule mutations are refused once `run().plan_locked` is true.
- Permission `manage_business_rules` = `{Role.BUSINESS_OWNER, Role.PRODUCT_ANALYST, Role.DELIVERY_LEAD}` (the `answer_clarification` set).
- The retry in `run_plan` fires **only** when the sole failure is unclaimed rules; every other validation failure raises immediately, unchanged. Exactly one retry, never more.
- Tests must pass offline with no API key: `python3 -m pytest tests/ -q`.

---

### Task 1: Engine — business-rule storage, actions, permission, state payload

**Files:**
- Modify: `s7_delivery/factory/roles.py` (PERMISSIONS dict, after `"answer_clarification"`)
- Modify: `s7_delivery/factory/engine.py` (new methods near `intake_remove_repo`, ~line 966; state payload ~line 319)
- Test: `tests/test_business_rules.py` (new)

**Interfaces:**
- Produces: `Engine._human_business_rules() -> list[dict]`, `Engine.merged_business_rules() -> list[dict]`, `Engine.intake_add_business_rule(role: Role, text: str) -> str` (returns new rule_id), `Engine.intake_edit_business_rule(role: Role, rule_id: str, text: str) -> None`, `Engine.intake_remove_business_rule(role: Role, rule_id: str) -> None`. State payload gains `intake.human_business_rules: list[dict]`.
- Consumes: existing `roles.require`, `self.store.read_json_or/write_json`, `self._record`, `self._activity`, `self.run().plan_locked`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_business_rules.py`:

```python
"""Human business rules: storage, permissions, immutability, merge."""

import pytest

from s7_delivery.factory.engine import Engine, EngineError
from s7_delivery.factory.models import DemoMode, Role
from s7_delivery.factory.roles import PermissionError_


@pytest.fixture()
def eng(tmp_path):
    return Engine.create(DemoMode.SIMULATION, root=tmp_path)


def run_intake(eng):
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    eng.intake_create_epic(Role.PRODUCT_ANALYST)
    eng.intake_pass_gate(Role.BUSINESS_OWNER)


def test_add_business_rule_assigns_human_ids(eng):
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Claims must be sponsor-scoped.")
    assert rid == "BR-H1"
    rid2 = eng.intake_add_business_rule(Role.PRODUCT_ANALYST, "Uploads are AV-scanned.")
    assert rid2 == "BR-H2"
    rules = eng.state()["intake"]["human_business_rules"]
    assert [r["rule_id"] for r in rules] == ["BR-H1", "BR-H2"]
    assert rules[0]["provenance"] == "human"
    assert rules[0]["added_by"] == Role.BUSINESS_OWNER.value


def test_add_business_rule_rejects_blank(eng):
    with pytest.raises(EngineError, match="empty"):
        eng.intake_add_business_rule(Role.BUSINESS_OWNER, "   ")


def test_add_business_rule_permission(eng):
    with pytest.raises(PermissionError_):
        eng.intake_add_business_rule(Role.INDEPENDENT_REVIEWER, "No.")


def test_edit_and_remove_own_rules(eng):
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Draft text")
    eng.intake_edit_business_rule(Role.BUSINESS_OWNER, rid, "Final text")
    rules = eng.state()["intake"]["human_business_rules"]
    assert rules[0]["text"] == "Final text"
    eng.intake_remove_business_rule(Role.BUSINESS_OWNER, rid)
    assert eng.state()["intake"]["human_business_rules"] == []


def test_ai_rules_are_immutable(eng):
    run_intake(eng)  # seeds analysis with BR-<n> rules
    ai_id = eng.state()["intake"]["analysis"]["business_rules"][0]["rule_id"]
    with pytest.raises(EngineError, match="immutable"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, ai_id, "rewrite")
    with pytest.raises(EngineError, match="immutable"):
        eng.intake_remove_business_rule(Role.BUSINESS_OWNER, ai_id)


def test_unknown_rule_id_refused(eng):
    with pytest.raises(EngineError, match="Unknown"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, "BR-H9", "x")


def test_rules_locked_after_plan_sign_off(eng):
    run_intake(eng)
    eng.planning_generate(Role.DELIVERY_LEAD)
    rid = eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Pre-sign rule")
    eng.planning_sign_off(Role.BUSINESS_OWNER, approver="business owner")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Too late")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_edit_business_rule(Role.BUSINESS_OWNER, rid, "Too late")
    with pytest.raises(EngineError, match="signed"):
        eng.intake_remove_business_rule(Role.BUSINESS_OWNER, rid)


def test_human_rules_survive_reanalysis(eng):
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Survives re-analysis")
    eng.intake_analyse(Role.PRODUCT_ANALYST)
    rules = eng.state()["intake"]["human_business_rules"]
    assert [r["rule_id"] for r in rules] == ["BR-H1"]


def test_merged_rules_are_ai_then_human(eng):
    run_intake(eng)
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Human rule")
    merged = eng.merged_business_rules()
    ai_count = len(eng.state()["intake"]["analysis"]["business_rules"])
    assert len(merged) == ai_count + 1
    assert merged[-1]["rule_id"] == "BR-H1"
```

Note: check `planning_sign_off`'s exact signature at `engine.py:1760` before writing — if `approver` is positional, call it positionally.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_business_rules.py -q`
Expected: FAIL — `AttributeError: 'Engine' object has no attribute 'intake_add_business_rule'` (and similar).

- [ ] **Step 3: Implement**

In `roles.py`, after the `"answer_clarification"` entry:

```python
    # Business rules are business input, like clarification answers: the
    # Business Owner owns them, analysts may capture them. Human rules are
    # BR-H<n>; the AI's BR-<n> extractions stay immutable.
    "manage_business_rules": {Role.BUSINESS_OWNER, Role.PRODUCT_ANALYST,
                              Role.DELIVERY_LEAD},
```

In `engine.py`, after `intake_remove_repo` (keep the intake grouping):

```python
    # --- human business rules ------------------------------------------------
    # Stored apart from analysis.json deliberately: re-running analysis
    # overwrites that file wholesale, and human input must survive it.

    def _human_business_rules(self) -> list[dict]:
        return self.store.read_json_or(
            {"rules": []}, "intake", "business_rules.json"
        )["rules"]

    def merged_business_rules(self) -> list[dict]:
        """AI-extracted rules then human-added rules — the canonical set
        planning must cover."""
        analysis = self.store.read_json_or(None, "intake", "analysis.json")
        ai_rules = list((analysis or {}).get("business_rules", []))
        human = [{"rule_id": r["rule_id"], "text": r["text"]}
                 for r in self._human_business_rules()]
        return ai_rules + human

    def _business_rules_open_for_change(self) -> None:
        if self.run().plan_locked:
            raise EngineError(
                "Plan is signed — the rule set it was approved against is "
                "locked; use an amendment instead"
            )

    def intake_add_business_rule(self, role: Role, text: str) -> str:
        roles.require("manage_business_rules", role)
        self._business_rules_open_for_change()
        text = text.strip()
        if not text:
            raise EngineError("A business rule cannot be empty")
        rules = self._human_business_rules()
        next_n = 1 + max(
            (int(r["rule_id"].removeprefix("BR-H")) for r in rules), default=0
        )
        rule = {
            "rule_id": f"BR-H{next_n}", "text": text,
            "added_by": role.value, "added_at": now_iso(),
            "provenance": "human",
        }
        rules.append(rule)
        self.store.write_json({"rules": rules}, "intake", "business_rules.json")
        self._record(
            artifact_id=rule["rule_id"], artifact_type="business_rule",
            payload=rule, author=role.value, stage=Stage.INTAKE,
            action="add", outcome="created",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="business-rules", artifact=rule["rule_id"],
            outcome="created", details=text[:120],
        )
        return rule["rule_id"]

    def _own_business_rule(self, rule_id: str) -> tuple[list[dict], dict]:
        rules = self._human_business_rules()
        target = next((r for r in rules if r["rule_id"] == rule_id), None)
        if target is None:
            if not rule_id.startswith("BR-H"):
                raise EngineError(
                    f"Rule {rule_id!r} is AI-extracted and immutable — add a "
                    "human rule alongside it instead"
                )
            raise EngineError(f"Unknown business rule {rule_id!r}")
        return rules, target

    def intake_edit_business_rule(self, role: Role, rule_id: str, text: str) -> None:
        roles.require("manage_business_rules", role)
        self._business_rules_open_for_change()
        text = text.strip()
        if not text:
            raise EngineError("A business rule cannot be empty")
        rules, target = self._own_business_rule(rule_id)
        target["text"] = text
        self.store.write_json({"rules": rules}, "intake", "business_rules.json")
        self._record(
            artifact_id=rule_id, artifact_type="business_rule", payload=target,
            author=role.value, stage=Stage.INTAKE, action="edit",
            outcome="amended",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="business-rules", artifact=rule_id,
            outcome="amended", details=text[:120],
        )

    def intake_remove_business_rule(self, role: Role, rule_id: str) -> None:
        roles.require("manage_business_rules", role)
        self._business_rules_open_for_change()
        rules, target = self._own_business_rule(rule_id)
        rules.remove(target)
        self.store.write_json({"rules": rules}, "intake", "business_rules.json")
        self._record(
            artifact_id=rule_id, artifact_type="business_rule", payload=target,
            author=role.value, stage=Stage.INTAKE, action="remove",
            outcome="removed",
        )
        self._activity(
            stage=Stage.INTAKE, actor=role.value, actor_type="human",
            workflow="business-rules", artifact=rule_id,
            outcome="removed", details=target["text"][:120],
        )
```

Check `now_iso` is already imported in `engine.py` (it is used at line 566); the immutable-AI-rule test expects the message branch: an ID that does not start with `BR-H` and is present in the analysis raises the "immutable" error — the `_own_business_rule` code above handles this because AI IDs (`BR-3`) don't start with `BR-H`.

Note the test `test_ai_rules_are_immutable` passes an AI id like `BR-1`; `_own_business_rule` raises the "immutable" message for any non-`BR-H` id, whether or not analysis exists — that is intended (the ID namespace, not file lookup, is the authority).

In `state()` (engine.py ~line 326), add to the `"intake"` dict after `"analysis"`:

```python
                "human_business_rules": self._human_business_rules(),
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_business_rules.py -q`
Expected: all PASS.

- [ ] **Step 5: Run the full suite to check nothing broke**

Run: `python3 -m pytest tests/ -q`
Expected: PASS (same count as before + new tests).

- [ ] **Step 6: Commit**

```bash
git add s7_delivery/factory/roles.py s7_delivery/factory/engine.py tests/test_business_rules.py
git commit -m "feat: human business rules — add/edit/remove on intake, BR-H ids, HUMAN provenance"
```

---

### Task 2: Engine — merged rules feed live planning

**Files:**
- Modify: `s7_delivery/factory/engine.py` (`_planning_generate_live`, ~line 1547)
- Test: `tests/test_business_rules.py` (append)

**Interfaces:**
- Consumes: `Engine.merged_business_rules()` from Task 1; `live_intake.run_plan(epic, analysis, packs, transcript, teams)`.
- Produces: `_planning_generate_live` passes `analysis` whose `business_rules` is the merged list.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_business_rules.py`:

```python
def test_live_planning_receives_merged_rules(eng, monkeypatch, tmp_path):
    """The analysis dict handed to run_plan must carry human rules too."""
    from s7_delivery.factory import engine as engine_mod
    from s7_delivery.factory.models import DemoMode as DM

    run_intake(eng)
    eng.intake_add_business_rule(Role.BUSINESS_OWNER, "Human rule for planning")

    seen = {}

    def fake_run_plan(epic, analysis, packs, transcript, teams):
        seen["rule_ids"] = [r["rule_id"] for r in analysis["business_rules"]]
        raise RuntimeError("stop here")

    monkeypatch.setattr(
        "s7_delivery.factory.live_intake.run_plan", fake_run_plan
    )
    # Force the live branch without a real repo/context pack.
    monkeypatch.setattr(
        type(eng), "_context_packs", lambda self: {"fake-repo": "# pack"},
        raising=True,
    )
    run = eng.run()
    run.mode = DM.LIVE
    monkeypatch.setattr(type(eng), "run", lambda self: run, raising=True)

    with pytest.raises(RuntimeError, match="stop here"):
        eng.planning_generate(Role.DELIVERY_LEAD)
    assert "BR-H1" in seen["rule_ids"]
```

Note: if `run.mode` is frozen (pydantic model), use `run = eng.run().model_copy(update={"mode": DM.LIVE})` instead of assignment. Check `Run` model in `s7_delivery/factory/models.py` first and use whichever works; the intent is only that `planning_generate` takes the live branch.

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_business_rules.py::test_live_planning_receives_merged_rules -q`
Expected: FAIL — `assert 'BR-H1' in ['BR-1', ...]` (human rule missing).

- [ ] **Step 3: Implement**

In `_planning_generate_live` (engine.py ~line 1556), replace:

```python
        analysis = self.store.read_json("intake", "analysis.json")
```

with:

```python
        analysis = self.store.read_json("intake", "analysis.json")
        # Human-added rules join the AI extraction: planning must cover the
        # whole merged set, and the cache key hashes rule ids, so adding a
        # rule forces a fresh plan call rather than replaying a stale one.
        analysis = {**analysis, "business_rules": self.merged_business_rules()}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_business_rules.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/engine.py tests/test_business_rules.py
git commit -m "feat: live planning covers merged AI + human business rules"
```

---

### Task 3: `run_plan` coverage retry (the S7-00022 fix)

**Files:**
- Modify: `s7_delivery/factory/live_intake.py` (`run_plan`, lines 435–543)
- Test: `tests/test_live_intake.py` (append)

**Interfaces:**
- Consumes: existing `_call(role=, ref=, task=, beat=, key_material=)`, `_PLAN_SHAPE`, `PLAN_ROLE`, `_ref`.
- Produces: `run_plan` signature unchanged (`(epic, analysis, packs, transcript, teams) -> tuple[list, dict, dict, dict]`); internal helper `_parse_plan_stories(data, *, epic, packs, teams) -> list[Story]` (raises `LLMError` on any structural failure; does **not** check rule coverage).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_live_intake.py`:

```python
# --- coverage retry --------------------------------------------------------


def fake_complete_seq(responses: list[dict]):
    """Return each canned response in turn; records every call."""
    calls: list[dict] = []

    def _fake(prompt, *, json_mode=False, cache_key=None, usage_out=None, **kw):
        calls.append({"prompt": prompt, "cache_key": cache_key})
        if usage_out is not None:
            usage_out.update({"input_tokens": 1000, "output_tokens": 300})
        return json.dumps(responses[min(len(calls) - 1, len(responses) - 1)])

    _fake.calls = calls
    return _fake


UNCOVERED_PLAN = {
    "stories": [dict(GOOD_STORY, traces_to=[])],
    "confidence": 70,
    "rationale": "Missed the rule.",
}


def test_run_plan_retries_once_on_unclaimed_rules(monkeypatch):
    fake = fake_complete_seq([UNCOVERED_PLAN, GOOD_PLAN])
    monkeypatch.setattr(live_intake, "complete", fake)
    monkeypatch.setenv("LLM_MODE", "live")
    stories, confidence, rationale, usage = live_intake.run_plan(
        EPIC, ANALYSIS, PACKS, [], TEAMS
    )
    assert len(fake.calls) == 2
    assert stories[0].traces_to == ["BR-01"]
    # The corrective prompt names the unclaimed rule and carries the draft.
    retry_task = fake.calls[1]["prompt"].task
    assert "BR-01" in retry_task and "unclaimed" in retry_task
    # Distinct cache key: the recorded first response can never be replayed
    # as the retry.
    assert fake.calls[0]["cache_key"] != fake.calls[1]["cache_key"]
    # Usage totals cover both calls.
    assert usage["input_tokens"] == 2000


def test_run_plan_retry_still_unclaimed_raises(monkeypatch):
    fake = fake_complete_seq([UNCOVERED_PLAN, UNCOVERED_PLAN])
    monkeypatch.setattr(live_intake, "complete", fake)
    with pytest.raises(LLMError, match="BR-01"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)
    assert len(fake.calls) == 2  # bounded: exactly one retry


def test_run_plan_no_retry_for_structural_failures(monkeypatch):
    bad_team = {**GOOD_PLAN,
                "stories": [dict(GOOD_STORY, accountable_team="Invented Team")]}
    fake = fake_complete_seq([bad_team, GOOD_PLAN])
    monkeypatch.setattr(live_intake, "complete", fake)
    with pytest.raises(LLMError, match="team"):
        live_intake.run_plan(EPIC, ANALYSIS, PACKS, [], TEAMS)
    assert len(fake.calls) == 1  # structural failures never retry
```

`json`, `pytest`, `LLMError`, `live_intake`, `GOOD_STORY`, `GOOD_PLAN`, `EPIC`, `ANALYSIS`, `PACKS`, `TEAMS` all already exist in this file. `fake.calls[1]["prompt"]` is the `PromptLayers` object — its `.task` attribute is the task string (confirm the attribute name in `common/prompt.py`; it is the `task` layer).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_live_intake.py -k retry -q`
Expected: FAIL — first test raises `LLMError: business rules claimed by no story` instead of retrying.

- [ ] **Step 3: Implement**

Restructure `run_plan` in `live_intake.py`. Extract the per-story validation (current lines 480–526, from `raw_stories = data.get("stories")` through the dangling-dependencies check) into a module-level helper placed just above `run_plan`:

```python
def _parse_plan_stories(data: dict, *, epic: dict, packs: dict, teams: list[str]) -> list:
    """Validate the model's plan structurally and return Story objects.
    Raises LLMError on any failure. Rule coverage is checked by the caller —
    it is the one failure with a bounded corrective retry."""
    from s7_delivery.factory.models import Status, Story

    raw_stories = data.get("stories")
    if not isinstance(raw_stories, list) or not 1 <= len(raw_stories) <= 10:
        raise LLMError("plan must contain 1-10 stories")

    provenance = provenance_now()
    stories: list[Story] = []
    seen: set[str] = set()
    for raw in raw_stories:
        sid = str(raw.get("story_id", ""))
        if not sid or sid in seen:
            raise LLMError(f"missing or duplicate story_id {sid!r}")
        seen.add(sid)
        if raw.get("accountable_team") not in teams:
            raise LLMError(
                f"story {sid}: accountable_team {raw.get('accountable_team')!r} "
                "is not on the team roster"
            )
        if raw.get("target_repository") not in packs:
            raise LLMError(
                f"story {sid}: target_repository {raw.get('target_repository')!r} "
                "is not a connected repository"
            )
        if raw.get("estimate") not in _POINT_SCALE:
            raise LLMError(f"story {sid}: estimate must be one of {_POINT_SCALE}")
        if len(raw.get("acceptance_criteria") or []) < 2:
            raise LLMError(
                f"story {sid}: needs at least 2 acceptance criteria"
            )
        _excluded = {"provenance", "status", "version", "epic_id"}  # ours to set
        try:
            story = Story(
                **{k: v for k, v in raw.items()
                   if k in Story.model_fields and k not in _excluded},
                epic_id=str(epic.get("epic_id", "")),
                provenance=provenance,
            )
        except Exception as exc:
            raise LLMError(f"story {sid} failed validation: {exc}") from exc
        if story.sprint != 1:
            story = story.model_copy(update={"status": Status.PLANNED})
        stories.append(story)

    ids = {s.story_id for s in stories}
    for s in stories:
        dangling = [d for d in s.dependencies if d not in ids]
        if dangling:
            raise LLMError(f"story {s.story_id} depends on unknown stories {dangling}")
    return stories
```

Then in `run_plan`, after the existing first `_call` (keep its `key_material` exactly as today), replace everything from `raw_stories = data.get("stories")` down to the `unclaimed` raise with:

```python
    base_key = (
        json.dumps(epic, sort_keys=True)
        + json.dumps(rule_ids)
        + json.dumps(transcript, sort_keys=True)
    )
    stories = _parse_plan_stories(data, epic=epic, packs=packs, teams=teams)
    unclaimed = [
        rid for rid in rule_ids
        if rid not in {r for s in stories for r in s.traces_to}
    ]
    if unclaimed:
        # One bounded corrective pass: name the miss, hand back the draft,
        # demand full coverage. Distinct key material so the recorded first
        # response can never be replayed as the answer to this correction.
        retry_task = f"""{task}

Your previous draft left these business rules unclaimed: {unclaimed}.
That draft's stories were:
{json.dumps(data.get("stories", []), indent=2)}

Revise the plan so EVERY business rule id is claimed by at least one
story's "traces_to" — extend existing stories' traces_to where a story
already delivers the rule, or add stories (still 8 at most). Return the
complete corrected JSON in the same shape."""
        data, retry_usage = _call(
            role=PLAN_ROLE,
            ref=_ref(epic, packs),
            task=retry_task,
            beat="plan",
            key_material=base_key + f"coverage-retry:{json.dumps(unclaimed)}",
        )
        for k, v in retry_usage.items():
            usage[k] = usage.get(k, 0) + v if isinstance(v, (int, float)) else v
        stories = _parse_plan_stories(data, epic=epic, packs=packs, teams=teams)
        unclaimed = [
            rid for rid in rule_ids
            if rid not in {r for s in stories for r in s.traces_to}
        ]
        if unclaimed:
            raise LLMError(f"business rules claimed by no story: {unclaimed}")
```

The first `_call`'s `key_material` argument today is built inline; refactor it to use the same `base_key` variable (defined **before** the first `_call`) so the two stay literally identical apart from the retry suffix. The trailing `confidence`/`rationale`/`return` block stays unchanged — it reads from `data`, which now holds the corrected plan when a retry ran.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_live_intake.py -q`
Expected: all PASS, including the pre-existing `test_run_plan_rejects_unclaimed_business_rule` (its single canned response is served for both calls by `fake_complete`, so the retry also comes back unclaimed and the error still raises — same match).

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add s7_delivery/factory/live_intake.py tests/test_live_intake.py
git commit -m "fix: bounded coverage retry in run_plan — unclaimed rules get one corrective pass"
```

---

### Task 4: Server endpoints + Control Centre panel (+ dist rebuild)

**Files:**
- Modify: `apps/control/server.py` (after the `/intake/repos/{name}/remove` endpoint, ~line 196)
- Modify: `apps/control/web/src/types.ts` (intake state type, near line 44)
- Modify: `apps/control/web/src/pages/intake/AdvancedAnalysisSection.tsx` (business-rules block, ~line 178)
- Modify (generated): `apps/control/web/dist/` (committed same commit)
- Test: `tests/test_business_rules.py` (endpoint smoke test only if `tests/` already has server tests — check `grep -l TestClient tests/*.py`; if none exist, skip server tests, engine tests already cover the logic)

**Interfaces:**
- Consumes: `Engine.intake_add_business_rule` / `intake_edit_business_rule` / `intake_remove_business_rule` from Task 1; UI consumes `data.intake.human_business_rules` and `act(path, body, message)` from `useRun()`.
- Produces: `POST /api/runs/{run_id}/intake/business-rules` (body `{role, text}`), `POST /api/runs/{run_id}/intake/business-rules/{rule_id}/edit` (body `{role, text}`), `POST /api/runs/{run_id}/intake/business-rules/{rule_id}/remove` (body `{role}`).

- [ ] **Step 1: Add server endpoints**

In `apps/control/server.py`, next to the other intake endpoints (follow the local pattern for body models — `RoleBody` exists; add one subclass):

```python
class BusinessRuleBody(RoleBody):
    text: str


@app.post("/api/runs/{run_id}/intake/business-rules")
def post_intake_add_business_rule(run_id: str, body: BusinessRuleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_add_business_rule(_role(body.role), body.text)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/business-rules/{rule_id}/edit")
def post_intake_edit_business_rule(run_id: str, rule_id: str, body: BusinessRuleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_edit_business_rule(_role(body.role), rule_id, body.text)
    return eng.state()


@app.post("/api/runs/{run_id}/intake/business-rules/{rule_id}/remove")
def post_intake_remove_business_rule(run_id: str, rule_id: str, body: RoleBody) -> dict:
    eng = _engine(run_id)
    eng.intake_remove_business_rule(_role(body.role), rule_id)
    return eng.state()
```

Before writing, read the neighbouring endpoints (e.g. `post_intake_remove_repo` at ~line 196) and copy their exact helper names — if the file uses a different engine-lookup helper than `_engine(run_id)` or returns something other than `eng.state()`, match the file, not this snippet.

- [ ] **Step 2: Extend the UI types**

In `apps/control/web/src/types.ts`, inside the intake state type (same object that has `analysis`), add:

```ts
  human_business_rules?: {
    rule_id: string
    text: string
    added_by: string
    added_at: string
    provenance: string
  }[]
```

- [ ] **Step 3: Build the panel**

In `AdvancedAnalysisSection.tsx`:

Add component state next to the existing `useState` hooks (~line 17):

```tsx
  const [newRuleText, setNewRuleText] = useState('')
  const [editingRule, setEditingRule] = useState<string | null>(null)
  const [editRuleText, setEditRuleText] = useState('')
```

Add below the `analysis` const (~line 51): `const humanRules = data.intake?.human_business_rules ?? []`

Replace the existing AI-rules block (lines 178–191) with a combined block that keeps the AI list untouched and appends the human panel:

```tsx
        {(analysis?.business_rules?.length || humanRules.length) ? (
          <details className="card sub-fold" style={{ marginBottom: 12 }} open={humanRules.length > 0}>
            <summary>
              <h3>Business Rules</h3>
              <span className="chip tag">{(analysis?.business_rules?.length ?? 0) + humanRules.length}</span>
              {analysis ? <Prov provenance={analysis.provenance} /> : null}
            </summary>
            <div className="fold-body">
              <ul className="plain">
                {(analysis?.business_rules ?? []).map((r) => (
                  <li key={r.rule_id}>
                    <span className="chip priority-high" style={{ marginRight: 8 }}>{r.rule_id}</span>
                    {r.text}
                  </li>
                ))}
                {humanRules.map((r) => (
                  <li key={r.rule_id} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span className="chip priority-high">{r.rule_id}</span>
                    <span className="chip tag">HUMAN</span>
                    {editingRule === r.rule_id ? (
                      <>
                        <input
                          type="text"
                          value={editRuleText}
                          onChange={(e) => setEditRuleText(e.target.value)}
                          style={{ flex: 1 }}
                        />
                        <button
                          type="button"
                          className="primary sq"
                          onClick={async () => {
                            if (await act(`/intake/business-rules/${r.rule_id}/edit`, { text: editRuleText }, 'Rule updated')) setEditingRule(null)
                          }}
                        >
                          Save
                        </button>
                        <button type="button" className="ghost" onClick={() => setEditingRule(null)}>Cancel</button>
                      </>
                    ) : (
                      <>
                        <span style={{ flex: 1 }}>{r.text}</span>
                        {!planLocked && (
                          <>
                            <button
                              type="button"
                              className="ghost"
                              style={{ padding: '3px 10px', fontSize: 11.5 }}
                              onClick={() => { setEditingRule(r.rule_id); setEditRuleText(r.text) }}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="ghost"
                              style={{ padding: '3px 10px', fontSize: 11.5 }}
                              onClick={() => act(`/intake/business-rules/${r.rule_id}/remove`, {}, 'Rule removed')}
                            >
                              Remove
                            </button>
                          </>
                        )}
                      </>
                    )}
                  </li>
                ))}
              </ul>
              {!planLocked && (
                <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                  <input
                    type="text"
                    placeholder="Add a business rule the analysis missed…"
                    value={newRuleText}
                    onChange={(e) => setNewRuleText(e.target.value)}
                    style={{ flex: 1 }}
                  />
                  <button
                    type="button"
                    className="primary sq"
                    disabled={!newRuleText.trim()}
                    onClick={async () => {
                      if (await act('/intake/business-rules', { text: newRuleText.trim() }, 'Rule added')) setNewRuleText('')
                    }}
                  >
                    Add rule
                  </button>
                </div>
              )}
              {planLocked && (
                <p className="hint" style={{ marginTop: 8 }}>
                  Plan is signed — the rule set it was approved against is locked.
                </p>
              )}
            </div>
          </details>
        ) : null}
```

Check how `act` injects the role: the existing calls (`act('/intake/clarify-answer', { answers }, …)`) don't pass `role`, so `act` adds it — confirm in `state/RunContext.tsx` and rely on the same behaviour. Keep the heading "Business Rules" (it now holds both provenances; each human rule carries its own HUMAN chip, AI rules stay under the analysis's provenance badge).

- [ ] **Step 4: Rebuild the frontend**

```bash
cd apps/control/web && npm run build
```

Expected: build succeeds, `dist/` regenerated. If TypeScript errors point at the types file or component, fix them now.

- [ ] **Step 5: Verify in the running app**

Run: `python3 -m pytest tests/ -q` (server import still healthy), then start the app per `demo/run_control.sh`, open a simulation run, run analysis, and confirm: the Business Rules fold shows AI rules + an add form; adding a rule shows it with a HUMAN chip; edit/remove work; the activity feed records the actions. Kill the server after (watch for the port-8720 stale-server gotcha — kill any existing process on the port first).

- [ ] **Step 6: Commit (src + dist together)**

```bash
git add apps/control/server.py apps/control/web/src apps/control/web/dist
git commit -m "feat: business-rules panel — add/edit/remove human rules on the intake surface"
```

---

### Task 5: Documentation sync

**Files:**
- Modify: `CLAUDE.md` (feature log, after the "Known-repository memory" entry)
- Modify: `AGENTS.md` (same paragraph, same commit — the two files must stay in sync)

**Interfaces:** none — prose only.

- [ ] **Step 1: Add the feature paragraph to both files**

Insert into `CLAUDE.md` (and mirror verbatim in `AGENTS.md`), after the "**Known-repository memory and repo removal, added 2026-08-10.**" paragraph:

```markdown
**Human business rules and planner coverage retry, added 2026-08-11.** The
intake surface's business-rules fold now accepts human input: rules a person
adds carry `BR-H<n>` ids and HUMAN provenance in a separate
`intake/business_rules.json` (surviving analysis re-runs), editable and
removable — human rules only, AI extractions stay immutable — until plan
sign-off locks the set (`manage_business_rules`: Business Owner + analysts).
Planning covers the merged AI + human set, and because the plan cache key
hashes rule ids, adding a rule forces a fresh model call. Separately,
`live_intake.run_plan` gained a bounded corrective retry: when the only
validation failure is business rules claimed by no story (the S7-00022
failure — 12 rules, 8 claimed), one follow-up call names the unclaimed ids
and hands back the draft for revision, under distinct cache-key material so
a recorded miss can never replay as the correction; a second miss raises the
original error. Structural failures (teams, repos, estimates, ACs) still
fail hard with no retry.
```

- [ ] **Step 2: Verify sync and commit**

```bash
git diff --stat CLAUDE.md AGENTS.md   # both files touched
git add CLAUDE.md AGENTS.md
git commit -m "docs: record human business rules + planner coverage retry in project brief"
```

---

## Self-review notes

- Spec coverage: storage/IDs (Task 1), permission (Task 1), merge feeding planning (Task 2), retry with distinct key material (Task 3), UI panel with HUMAN chips + sign-off lock (Task 4), mode honesty (no simulation changes needed — seeded sim planning ignores rules by design, human rules simply render), docs (Task 5).
- The pre-existing test `test_run_plan_rejects_unclaimed_business_rule` keeps passing because its single-response fake serves the same uncovered plan to the retry call too.
- Type consistency: `merged_business_rules` (Tasks 1→2), `_parse_plan_stories` (Task 3 only), endpoint paths (Task 4 server ↔ TSX).
