# Playbook Self-Learning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every human correction anywhere in a run is captured, distilled into a grounded rule, admitted into a persistent versioned playbook under governance, and injected into later runs' prompts — with a Playbook admin page in the Control Centre.

**Architecture:** A new `s7_delivery/factory/playbook.py` owns the global append-only store (`artifacts/playbook.json`, mirroring `repos.py`'s `_default_root()` pattern), the deterministic grounding check, distillation (template in sim, model call in live), and the admission matrix. `engine.py` grows one capture helper wired into seven existing human touchpoints and a per-run snapshot for replay pinning; `live_intake._call` gains a `memory` parameter feeding the existing `PromptLayers.memory` slot. FastAPI endpoints under `/api/playbook` plus a React `Playbook.tsx` page complete the admin panel.

**Tech Stack:** Plain Python (no new deps), existing `common/llm.py` + `common/prompt.py`, FastAPI (existing), React + TypeScript + Vite (existing, committed `dist/`).

**Spec:** `docs/superpowers/specs/2026-08-20-playbook-self-learning-design.md` — read it first.

## Global Constraints

- Hard rule 4: after any change under `apps/control/web/src/`, run `npm run build` in `apps/control/web/` and commit the regenerated `dist/` **in the same commit**.
- Hard rule 5 / § Staged output: sim/demo distillation is badged `RULE_BASED` and never labelled AI; live is `LIVE_AI`, replayed is `REPLAYED_AI`.
- Capture must never break the governance action that triggered it: every capture path is wrapped so a distiller failure records an error on the event and the human's action still succeeds.
- Empty playbook ⇒ byte-identical prompts to today (memory layer absent, not blank) — committed replay recordings stay valid.
- All playbook mutations are append-only in effect: no history entry is ever deleted or rewritten; status changes append events.
- Tests run offline with no API key: `.venv/bin/python -m pytest tests/ -x -q`. Lint: `.venv/bin/ruff check .`.
- Commit messages end with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.

## File Structure

- **Create** `s7_delivery/factory/playbook.py` — store, grounding, distillation, admission, memory layer. One responsibility: the playbook lifecycle.
- **Create** `tests/test_playbook.py` — store/grounding/admission unit tests.
- **Create** `tests/test_playbook_engine.py` — capture, snapshot pinning, offline E2E.
- **Modify** `tests/conftest.py` — autouse isolation fixture (like `_isolated_known_repos_registry`).
- **Modify** `s7_delivery/factory/roles.py` — `manage_playbook` permission.
- **Modify** `s7_delivery/factory/engine.py` — `_playbook_capture` + seven wire-ins + `_playbook_memory` snapshot + `state()` block.
- **Modify** `s7_delivery/factory/live_intake.py` — `_call(memory=...)`; `run_analysis`/`run_plan` accept and pass `memory`.
- **Modify** `apps/control/server.py` + `tests/test_control_api.py` — `/api/playbook` endpoints.
- **Create** `apps/control/web/src/pages/Playbook.tsx`; **modify** `App.tsx`, `components/SideNav.tsx`, `web/dist/` (rebuilt).
- **Modify** `CLAUDE.md` + `AGENTS.md` (same commit — sync rule).

---

### Task 1: Playbook store (append-only, versioned, survives run resets)

**Files:**
- Create: `s7_delivery/factory/playbook.py`
- Create: `tests/test_playbook.py`
- Modify: `tests/conftest.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `PlaybookError(Exception)`; `_default_root() -> Path`; `load(root=None) -> dict` (shape `{"version": int, "next_id": int, "rules": [rule]}`); `add_rule(*, text, stage_scope, repo_scope, origin, provenance, traces_to, status, actor, reason="", root=None) -> dict`; `get_rule(rule_id, root=None) -> dict`; `decide_rule(rule_id, *, decision, actor, reason="", text=None, root=None) -> dict`; `retire_rule(rule_id, *, actor, reason, root=None) -> dict`; `restore_rule(rule_id, *, actor, root=None) -> dict`; `active_rules(stage, repo=None, root=None) -> list[dict]`; `memory_layer(stage, repo=None, root=None) -> str | None`.
- Rule dict keys: `id` ("PB-1"…), `text`, `stage_scope` ("planning"|"architecture"|"test"|"all"), `repo_scope` ("global" or repo name), `status` ("pending"|"active"|"retired"), `origin` ("human_explicit"|"ai_inferred"), `provenance` (string), `traces_to` (dict), `created` (iso str), `pending_reason` (str, "" when none), `history` (list of `{"action","actor","reason","at"}`).

- [ ] **Step 1: Add conftest isolation fixture**

In `tests/conftest.py`, next to `_isolated_known_repos_registry`, add:

```python
@pytest.fixture(autouse=True)
def _isolated_playbook(tmp_path_factory, monkeypatch):
    """Point the global playbook store at a per-session tmp dir so tests can
    never write this repo's real artifacts/playbook.json. Tests that need
    their own registry re-monkeypatch this to their own tmp_path."""
    from s7_delivery.factory import playbook as playbook_mod

    root = tmp_path_factory.mktemp("playbook_store")
    monkeypatch.setattr(playbook_mod, "_default_root", lambda: root)
```

(This forces `playbook.py` to exist with `_default_root` before any test runs — that is Step 3.)

- [ ] **Step 2: Write the failing tests**

`tests/test_playbook.py`:

```python
"""Playbook store: append-only, versioned, monotonic ids."""

import pytest

from s7_delivery.factory import playbook


def _mk(text="Check what already exists before proposing anything new",
        status="active", origin="human_explicit", **kw):
    defaults = dict(
        text=text, stage_scope="planning", repo_scope="global",
        origin=origin, provenance="RULE_BASED",
        traces_to={"run_id": "S7-00001", "event_kind": "plan_revision",
                   "event_ref": "CE-001", "excerpt": text},
        status=status, actor="Delivery Lead",
    )
    defaults.update(kw)
    return playbook.add_rule(**defaults)


def test_load_missing_file_is_empty_book():
    book = playbook.load()
    assert book == {"version": 0, "next_id": 1, "rules": []}


def test_add_rule_assigns_monotonic_ids_and_bumps_version():
    r1 = _mk()
    r2 = _mk(text="Every story gets testable criteria")
    assert (r1["id"], r2["id"]) == ("PB-1", "PB-2")
    book = playbook.load()
    assert book["version"] == 2
    assert book["next_id"] == 3
    assert r1["history"][0]["action"] == "created"


def test_decide_approves_pending_with_optional_edit():
    r = _mk(status="pending", origin="ai_inferred")
    out = playbook.decide_rule(r["id"], decision="approve",
                               actor="Engineering Lead",
                               text="Split work by team and repository")
    assert out["status"] == "active"
    assert out["text"] == "Split work by team and repository"
    actions = [h["action"] for h in out["history"]]
    assert "edited" in actions and "approved" in actions
    # the pre-edit text survives in history — append-only in effect
    edited = next(h for h in out["history"] if h["action"] == "edited")
    assert edited["reason"].startswith("was: ")


def test_decide_reject_and_only_pending_rules_are_decidable():
    r = _mk(status="pending", origin="ai_inferred")
    out = playbook.decide_rule(r["id"], decision="reject",
                               actor="Delivery Lead", reason="too broad")
    assert out["status"] == "retired"
    active = _mk()
    with pytest.raises(playbook.PlaybookError):
        playbook.decide_rule(active["id"], decision="approve", actor="x")


def test_retire_requires_reason_and_restore_reactivates():
    r = _mk()
    with pytest.raises(playbook.PlaybookError):
        playbook.retire_rule(r["id"], actor="Delivery Lead", reason=" ")
    playbook.retire_rule(r["id"], actor="Delivery Lead", reason="superseded")
    assert playbook.get_rule(r["id"])["status"] == "retired"
    playbook.restore_rule(r["id"], actor="Delivery Lead")
    assert playbook.get_rule(r["id"])["status"] == "active"


def test_unknown_rule_id_raises():
    with pytest.raises(playbook.PlaybookError):
        playbook.get_rule("PB-999")


def test_active_rules_filter_by_stage_and_repo():
    _mk()                                             # planning / global
    _mk(text="Use the application's own vocabulary",
        repo_scope="maplesure-sponsor-portal")
    _mk(text="Name every artifact", stage_scope="all")
    _mk(text="Retired rule", status="active")
    playbook.retire_rule("PB-4", actor="x", reason="gone")
    _mk(text="Pending rule", status="pending", origin="ai_inferred")

    ids = [r["id"] for r in playbook.active_rules("planning")]
    assert ids == ["PB-1", "PB-3"]          # global only, no repo given
    ids = [r["id"] for r in
           playbook.active_rules("planning", repo="maplesure-sponsor-portal")]
    assert ids == ["PB-1", "PB-2", "PB-3"]
    ids = [r["id"] for r in playbook.active_rules("test")]
    assert ids == ["PB-3"]


def test_memory_layer_renders_sorted_or_none():
    assert playbook.memory_layer("planning") is None
    _mk()
    _mk(text="Every story gets testable criteria")
    text = playbook.memory_layer("planning")
    assert text.index("PB-1") < text.index("PB-2")
    assert "human corrections" in text
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook.py -x -q`
Expected: FAIL — `ModuleNotFoundError: No module named 's7_delivery.factory.playbook'` (or the conftest import error naming it).

- [ ] **Step 4: Implement the store**

`s7_delivery/factory/playbook.py`:

```python
"""The playbook — cross-run self-learning from human corrections.

Spec: docs/superpowers/specs/2026-08-20-playbook-self-learning-design.md.
A global, append-only, versioned rule store at artifacts/playbook.json —
a sibling of known_repos.json, deliberately outside artifacts/runs/ so
discarding every run never touches what the humans taught the system.

`_default_root` is a module-level function (not a constant baked into each
call's default argument) specifically so tests can monkeypatch it and never
risk writing to this repo's real `artifacts/` directory — the same pattern
as repos.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

STAGE_SCOPES = ("planning", "architecture", "test", "all")


class PlaybookError(Exception):
    pass


def _default_root() -> Path:
    return REPO_ROOT / "artifacts"


def _book_path(root: Path | None) -> Path:
    return (root or _default_root()) / "playbook.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load(root: Path | None = None) -> dict:
    path = _book_path(root)
    if not path.is_file():
        return {"version": 0, "next_id": 1, "rules": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        # Refuse writes loudly later; reads surface the problem too. A
        # corrupt store must never silently become an empty one.
        raise PlaybookError(f"Unreadable playbook store at {path}: {exc}") from exc
    return data


def _save(book: dict, root: Path | None) -> None:
    path = _book_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(book, indent=2) + "\n", encoding="utf-8")


def get_rule(rule_id: str, root: Path | None = None) -> dict:
    for rule in load(root)["rules"]:
        if rule["id"] == rule_id:
            return rule
    raise PlaybookError(f"No playbook rule {rule_id}")


def add_rule(
    *,
    text: str,
    stage_scope: str,
    repo_scope: str,
    origin: str,
    provenance: str,
    traces_to: dict,
    status: str,
    actor: str,
    reason: str = "",
    root: Path | None = None,
) -> dict:
    if stage_scope not in STAGE_SCOPES:
        raise PlaybookError(f"Unknown stage_scope {stage_scope!r}")
    if status not in ("pending", "active"):
        raise PlaybookError("A new rule is admitted 'active' or queued 'pending'")
    book = load(root)
    rule = {
        "id": f"PB-{book['next_id']}",
        "text": text.strip(),
        "stage_scope": stage_scope,
        "repo_scope": repo_scope,
        "status": status,
        "origin": origin,
        "provenance": provenance,
        "traces_to": traces_to,
        "created": _now(),
        "pending_reason": reason if status == "pending" else "",
        "history": [
            {"action": "created", "actor": actor, "reason": reason, "at": _now()}
        ],
    }
    book["next_id"] += 1
    book["version"] += 1
    book["rules"].append(rule)
    _save(book, root)
    return rule


def _mutate(rule_id: str, action, root: Path | None) -> dict:
    """Load, apply `action(rule)`, bump version, save. History only grows."""
    book = load(root)
    for rule in book["rules"]:
        if rule["id"] == rule_id:
            action(rule)
            book["version"] += 1
            _save(book, root)
            return rule
    raise PlaybookError(f"No playbook rule {rule_id}")


def decide_rule(
    rule_id: str,
    *,
    decision: str,
    actor: str,
    reason: str = "",
    text: str | None = None,
    root: Path | None = None,
) -> dict:
    if decision not in ("approve", "reject"):
        raise PlaybookError("Decision must be 'approve' or 'reject'")
    current = get_rule(rule_id, root)
    if current["status"] != "pending":
        raise PlaybookError(f"{rule_id} is {current['status']}; only pending rules are decidable")

    def action(rule: dict) -> None:
        if decision == "approve":
            if text is not None and text.strip() and text.strip() != rule["text"]:
                rule["history"].append({
                    "action": "edited", "actor": actor,
                    "reason": f"was: {rule['text']}", "at": _now(),
                })
                rule["text"] = text.strip()
            rule["status"] = "active"
            rule["pending_reason"] = ""
            rule["history"].append(
                {"action": "approved", "actor": actor, "reason": reason, "at": _now()})
        else:
            rule["status"] = "retired"
            rule["history"].append(
                {"action": "rejected", "actor": actor, "reason": reason, "at": _now()})

    return _mutate(rule_id, action, root)


def retire_rule(rule_id: str, *, actor: str, reason: str,
                root: Path | None = None) -> dict:
    if not reason.strip():
        raise PlaybookError("Retiring a rule requires a reason")

    def action(rule: dict) -> None:
        rule["status"] = "retired"
        rule["history"].append(
            {"action": "retired", "actor": actor, "reason": reason, "at": _now()})

    return _mutate(rule_id, action, root)


def restore_rule(rule_id: str, *, actor: str, root: Path | None = None) -> dict:
    def action(rule: dict) -> None:
        rule["status"] = "active"
        rule["history"].append(
            {"action": "restored", "actor": actor, "reason": "", "at": _now()})

    return _mutate(rule_id, action, root)


def active_rules(stage: str, repo: str | None = None,
                 root: Path | None = None) -> list[dict]:
    out = []
    for rule in load(root)["rules"]:
        if rule["status"] != "active":
            continue
        if rule["stage_scope"] not in (stage, "all"):
            continue
        if rule["repo_scope"] != "global" and rule["repo_scope"] != repo:
            continue
        out.append(rule)
    return sorted(out, key=lambda r: int(r["id"].split("-")[1]))


def memory_layer(stage: str, repo: str | None = None,
                 root: Path | None = None) -> str | None:
    """Render active rules as the prompt's memory layer, stable order.

    None (not "") when no rules apply, so an empty playbook contributes no
    layer at all and assembled prompts stay byte-identical to a build with
    no playbook — committed recordings must not miss (spec §4).
    """
    rules = active_rules(stage, repo, root)
    if not rules:
        return None
    lines = [f"{r['id']} · {r['text']}" for r in rules]
    return (
        "The delivery playbook — rules learned from human corrections on "
        "previous runs. Obey every rule:\n" + "\n".join(lines)
    )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_playbook.py -x -q`
Expected: PASS (8 tests).

- [ ] **Step 6: Lint and commit**

```bash
.venv/bin/ruff check . && git add s7_delivery/factory/playbook.py tests/test_playbook.py tests/conftest.py
git commit -m "feat(playbook): append-only versioned global rule store

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Grounding check — the no-hallucination gate

**Files:**
- Modify: `s7_delivery/factory/playbook.py`
- Test: `tests/test_playbook.py` (append)

**Interfaces:**
- Produces: `grounding_check(rule_text: str, source_text: str) -> tuple[bool, list[str]]` — `(ok, missing_terms)`; deterministic, no I/O.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_playbook.py`)

```python
class TestGrounding:
    def test_restatement_passes(self):
        ok, missing = playbook.grounding_check(
            "Re-use the lookup the application already has",
            "Don't build a new member lookup service — re-use the lookup "
            "the application already has.",
        )
        assert ok and missing == []

    def test_invented_entities_fail_and_are_named(self):
        ok, missing = playbook.grounding_check(
            "Always deploy the billing microservice to kubernetes first",
            "Re-use the lookup the application already has.",
        )
        assert not ok
        assert "billing" in missing and "kubernetes" in missing

    def test_stage_vocabulary_allowlist(self):
        # "story"/"acceptance criteria" are craft vocabulary, not entities —
        # a rule may use them even when the correction did not.
        ok, missing = playbook.grounding_check(
            "Every story must claim its business rules",
            "You left four business rules unclaimed.",
        )
        assert ok, missing

    def test_short_and_stop_words_never_count(self):
        ok, _ = playbook.grounding_check(
            "Do not propose it before checking",
            "checked the proposal before it went out",
        )
        assert ok
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook.py::TestGrounding -x -q`
Expected: FAIL — `AttributeError: ... no attribute 'grounding_check'`.

- [ ] **Step 3: Implement** (append to `playbook.py`)

```python
# --- grounding ---------------------------------------------------------------
#
# The no-hallucination contract (spec §3): every substantive term in a
# candidate rule must be traceable to the human's own words, up to light
# stemming. Craft vocabulary the distiller legitimately adds ("story",
# "acceptance criteria") is allowlisted; entities are not. Deterministic on
# purpose — the same check runs identically in every mode.

_STOPWORDS = frozenset(
    "a an and are as at be before being but by do does for from has have if in "
    "is it its may must never no not of on or should so that the their then "
    "this to was when where which while with without you your every each all "
    "any one once only own same after first new".split()
)

_ALLOWED_TERMS = frozenset(
    "story stories task tasks acceptance criteria criterion rule rules plan "
    "planning epic sprint team teams repository repositories application "
    "architecture test tests testing review sign-off gate check checking "
    "propose proposing draft drafting apply honour address".split()
)


def _terms(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9][a-z0-9'-]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in _STOPWORDS}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def grounding_check(rule_text: str, source_text: str) -> tuple[bool, list[str]]:
    source = {_stem(w) for w in _terms(source_text)}
    allowed = {_stem(w) for w in _ALLOWED_TERMS}
    missing = sorted(
        w for w in _terms(rule_text)
        if _stem(w) not in source and _stem(w) not in allowed
    )
    return (not missing, missing)
```

Add `import re` to the module imports.

- [ ] **Step 4: Run the full playbook file, then lint**

Run: `.venv/bin/python -m pytest tests/test_playbook.py -x -q && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/playbook.py tests/test_playbook.py
git commit -m "feat(playbook): deterministic grounding check names untraceable terms

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Distillation and the admission matrix

**Files:**
- Modify: `s7_delivery/factory/playbook.py`
- Test: `tests/test_playbook.py` (append)

**Interfaces:**
- Consumes: `common.llm.complete`, `common.llm.parse_json_response`, `common.prompt.PromptLayers` (exact pattern of `live_intake._call`).
- Produces: `process_event(event: dict, *, live: bool, root=None) -> dict` returning `{"status": "active"|"pending"|"error", "rule_id": str|None, "reason": str}`. Event dict keys (produced by Task 4's engine capture): `event_id`, `kind`, `stage`, `text`, `context`, `actor`, `run_id`, `at`.
- Event kinds → template + origin (sim): `business_rule` (text verbatim, `human_explicit`); `plan_revision` → `"When drafting the plan, apply: {text}"` (`human_explicit`); `architecture_proposal` → `"When drafting architecture, apply: {text}"` (`human_explicit`); `test_plan_amendment` → `"When drafting test plans, apply: {text}"` (`human_explicit`); `gate_rejection` → `"Before requesting {stage} sign-off, address: {text}"` (`human_explicit`); `dependency_override` and `clarification_answer` → `"Learned from a {kind} on {run_id}: {text}"` (`ai_inferred` — an answer or an override is context, generalising it is inference).
- Stage scope = event `stage`; repo scope = `"global"` in v1 distillation (repo-scoped rules arrive via admin authoring).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_playbook.py`)

```python
def _event(kind="plan_revision", stage="planning",
           text="Check what already exists before proposing anything new"):
    return {"event_id": "CE-001", "kind": kind, "stage": stage, "text": text,
            "context": "", "actor": "Delivery Lead", "run_id": "S7-00001",
            "at": "2026-08-20T00:00:00+00:00"}


class TestAdmission:
    def test_sim_human_explicit_grounded_auto_admits_rule_based(self):
        out = playbook.process_event(_event(), live=False)
        assert out["status"] == "active"
        rule = playbook.get_rule(out["rule_id"])
        assert rule["provenance"] == "RULE_BASED"
        assert rule["origin"] == "human_explicit"
        assert rule["traces_to"]["excerpt"] == _event()["text"]

    def test_sim_ai_inferred_queues_pending(self):
        out = playbook.process_event(
            _event(kind="clarification_answer",
                   text="Sponsors authenticate with their portal account"),
            live=False)
        assert out["status"] == "pending"
        assert playbook.get_rule(out["rule_id"])["status"] == "pending"

    def test_live_without_review_model_queues_pending(self, monkeypatch):
        # Live distillation is stubbed; with no REVIEW_LLM_* configured,
        # nothing auto-admits — fail toward governance (spec §6).
        monkeypatch.delenv("REVIEW_LLM_PROVIDER", raising=False)
        monkeypatch.setattr(playbook, "_distill_live", lambda event: {
            "text": event["text"], "origin": "human_explicit"})
        out = playbook.process_event(_event(), live=True)
        assert out["status"] == "pending"
        assert "independent check" in out["reason"]
        assert playbook.get_rule(out["rule_id"])["provenance"] in (
            "LIVE_AI", "REPLAYED_AI")

    def test_grounding_failure_demotes_with_named_terms(self, monkeypatch):
        monkeypatch.setattr(playbook, "_distill_live", lambda event: {
            "text": "Always deploy the billing microservice first",
            "origin": "human_explicit"})
        monkeypatch.setattr(playbook, "_verify_live", lambda rule, src: True)
        out = playbook.process_event(_event(), live=True)
        assert out["status"] == "pending"
        assert "billing" in out["reason"]

    def test_distiller_exception_reports_error_and_saves_nothing(self, monkeypatch):
        def boom(event):
            raise RuntimeError("provider down")
        monkeypatch.setattr(playbook, "_distill_live", boom)
        out = playbook.process_event(_event(), live=True)
        assert out["status"] == "error"
        assert "provider down" in out["reason"]
        assert playbook.load()["rules"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook.py::TestAdmission -x -q`
Expected: FAIL — no attribute `process_event`.

- [ ] **Step 3: Implement** (append to `playbook.py`)

```python
# --- distillation ------------------------------------------------------------

import os

from common.llm import complete, parse_json_response
from common.prompt import PromptLayers

_HUMAN_EXPLICIT_KINDS = frozenset({
    "business_rule", "plan_revision", "architecture_proposal",
    "test_plan_amendment", "gate_rejection",
})

_TEMPLATES = {
    "business_rule": "{text}",
    "plan_revision": "When drafting the plan, apply: {text}",
    "architecture_proposal": "When drafting architecture, apply: {text}",
    "test_plan_amendment": "When drafting test plans, apply: {text}",
    "gate_rejection": "Before requesting {stage} sign-off, address: {text}",
    "dependency_override": "Learned from a dependency_override on {run_id}: {text}",
    "clarification_answer": "Learned from a clarification_answer on {run_id}: {text}",
}

_DISTILL_RULES = (
    "You distill one human correction into at most one imperative playbook "
    "rule. Quote the human's vocabulary; generalise no further than the "
    "correction itself. Output JSON only."
)

_DISTILL_SHAPE = """{
  "text": "<one imperative rule, in the human's own vocabulary>",
  "origin": "human_explicit" | "ai_inferred"
}"""


def _distill_template(event: dict) -> dict:
    kind = event["kind"]
    text = _TEMPLATES.get(kind, "{text}").format(**event)
    origin = "human_explicit" if kind in _HUMAN_EXPLICIT_KINDS else "ai_inferred"
    return {"text": text, "origin": origin}


def _distill_live(event: dict) -> dict:
    task = (
        f"A human made this correction during the {event['stage']} stage "
        f"(kind: {event['kind']}):\n\n{event['text']}\n\n"
        f"Context: {event['context'] or '(none)'}\n\n"
        f"Distill it. Respond with JSON exactly shaped:\n{_DISTILL_SHAPE}"
    )
    digest = hashlib.sha256(
        f"{event['run_id']}|{event['event_id']}|{event['text']}".encode()
    ).hexdigest()[:16]
    response = complete(
        PromptLayers(rules=_DISTILL_RULES, role="playbook-distiller", task=task),
        json_mode=True,
        cache_key=f"s7_playbook_distill:{digest}",
    )
    data = parse_json_response(response)
    origin = data.get("origin", "ai_inferred")
    if origin not in ("human_explicit", "ai_inferred"):
        origin = "ai_inferred"
    return {"text": str(data.get("text", "")).strip(), "origin": origin}


def _verify_live(rule_text: str, source_text: str) -> bool:
    """Independent rule-against-source check by the review model. False when
    no REVIEW_LLM_* is configured — nothing auto-admits unreviewed (spec §6)."""
    provider = os.environ.get("REVIEW_LLM_PROVIDER", "").strip()
    if not provider:
        return False
    saved = {k: os.environ.get(k) for k in ("LLM_PROVIDER", "LLM_MODEL")}
    try:
        os.environ["LLM_PROVIDER"] = provider
        model = os.environ.get("REVIEW_LLM_MODEL", "").strip()
        if model:
            os.environ["LLM_MODEL"] = model
        task = (
            "Does this rule restate the human correction without adding "
            "anything the human did not say or clearly imply? Respond with "
            'JSON exactly shaped {"faithful": true|false}.\n\n'
            f"Rule: {rule_text}\n\nCorrection: {source_text}"
        )
        digest = hashlib.sha256(f"{rule_text}|{source_text}".encode()).hexdigest()[:16]
        response = complete(
            PromptLayers(rules=_DISTILL_RULES, role="playbook-verifier", task=task),
            json_mode=True,
            cache_key=f"s7_playbook_verify:{digest}",
        )
        return bool(parse_json_response(response).get("faithful") is True)
    finally:
        for key, value in saved.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _live_provenance() -> str:
    mode = os.environ.get("LLM_MODE", "replay").lower()
    return "LIVE_AI" if mode in ("live", "record") else "REPLAYED_AI"


def process_event(event: dict, *, live: bool, root: Path | None = None) -> dict:
    """Distill → ground → (verify) → admit. Never raises: the capture site is
    inside a human's governance action, which must succeed regardless."""
    try:
        candidate = _distill_live(event) if live else _distill_template(event)
        if not candidate["text"]:
            return {"status": "error", "rule_id": None,
                    "reason": "distiller returned no rule text"}
        ok, missing = grounding_check(candidate["text"], event["text"])
        reason = ""
        if not ok:
            reason = ("grounding failed — terms not traceable to the "
                      f"correction: {', '.join(missing)}")
        elif candidate["origin"] != "human_explicit":
            reason = "AI-inferred generalisation — needs human approval"
        elif live and not _verify_live(candidate["text"], event["text"]):
            reason = ("independent check unavailable or not passed — "
                      "queued for human approval")
        status = "active" if not reason else "pending"
        rule = add_rule(
            text=candidate["text"],
            stage_scope=event["stage"] if event["stage"] in STAGE_SCOPES else "all",
            repo_scope="global",
            origin=candidate["origin"],
            provenance=_live_provenance() if live else "RULE_BASED",
            traces_to={"run_id": event["run_id"], "event_kind": event["kind"],
                       "event_ref": event["event_id"], "excerpt": event["text"]},
            status=status,
            actor=event["actor"],
            reason=reason,
            root=root,
        )
        return {"status": status, "rule_id": rule["id"], "reason": reason}
    except Exception as exc:  # noqa: BLE001 — spec §6: never lose the event
        return {"status": "error", "rule_id": None, "reason": str(exc)}
```

Add `import hashlib` to the module imports.

- [ ] **Step 4: Run all playbook tests, lint**

Run: `.venv/bin/python -m pytest tests/test_playbook.py -x -q && .venv/bin/ruff check .`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add s7_delivery/factory/playbook.py tests/test_playbook.py
git commit -m "feat(playbook): distillation with grounding-gated admission matrix

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Engine capture at the seven human touchpoints

**Files:**
- Modify: `s7_delivery/factory/engine.py`
- Test: `tests/test_playbook_engine.py` (create)

**Interfaces:**
- Consumes: `playbook.process_event`.
- Produces: `Engine._playbook_capture(self, *, kind: str, stage: str, text: str, context: str = "", actor: str = "") -> None`; per-run event log at store path `("playbook", "events.json")` (a JSON list); approvals-ledger record for rules admitted `active` during a run (workflow `"playbook-admission"`).

- [ ] **Step 1: Write the failing tests**

`tests/test_playbook_engine.py`. Follow `tests/test_factory_engine.py`'s existing fixture pattern for building a simulation-mode `Engine` (copy its engine/run fixture verbatim — it already isolates `artifacts/runs/` to a tmp path). Then:

```python
"""Ambient capture: human corrections become playbook rules as a side effect
of existing governance actions — and never break those actions."""

from s7_delivery.factory import playbook
from s7_delivery.factory.roles import Role


def test_business_rule_add_captures_and_admits(engine):
    engine.intake_add_business_rule(
        Role.BUSINESS_OWNER,
        "A sponsor may only submit claims for their own members")
    events = engine.store.read_json_or([], "playbook", "events.json")
    assert len(events) == 1
    assert events[0]["kind"] == "business_rule"
    assert events[0]["status"] == "active"
    rule = playbook.get_rule(events[0]["rule_id"])
    assert rule["provenance"] == "RULE_BASED"
    assert rule["traces_to"]["run_id"] == engine.run_id


def test_planning_revise_captures_plan_revision(engine_with_plan):
    engine_with_plan.planning_revise(
        Role.DELIVERY_LEAD, "Split the intake story by team")
    events = engine_with_plan.store.read_json_or([], "playbook", "events.json")
    kinds = [e["kind"] for e in events]
    assert "plan_revision" in kinds


def test_admitted_rule_lands_in_approvals_ledger(engine):
    engine.intake_add_business_rule(Role.BUSINESS_OWNER, "Members are employees")
    approvals = engine.store.read_ledger("approvals.jsonl")
    assert any(a.get("workflow") == "playbook-admission" for a in approvals)


def test_capture_failure_never_breaks_the_action(engine, monkeypatch):
    def boom(event, *, live, root=None):
        raise RuntimeError("store offline")
    monkeypatch.setattr(playbook, "process_event", boom)
    # The governance action still succeeds…
    engine.intake_add_business_rule(Role.BUSINESS_OWNER, "Still works")
    # …and the event is kept with the error recorded, never lost.
    events = engine.store.read_json_or([], "playbook", "events.json")
    assert events and events[-1]["status"].startswith("error")
```

(`engine_with_plan` = the existing fixture/helper in `test_factory_engine.py` that advances a simulation run through `planning_generate`; reuse whatever that file already provides rather than inventing a new path.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook_engine.py -x -q`
Expected: FAIL — no `playbook/events.json` written (assertion on empty list).

- [ ] **Step 3: Implement capture in `engine.py`**

Add near the other private helpers (import `playbook` alongside the existing factory imports):

```python
def _playbook_capture(self, *, kind: str, stage: str, text: str,
                      context: str = "", actor: str = "") -> None:
    """Ambient playbook capture (spec §2). Wraps everything: a distiller
    failure records an error on the event — it must never break the
    human's governance action that triggered it."""
    text = (text or "").strip()
    if not text:
        return
    try:
        events = self.store.read_json_or([], "playbook", "events.json")
        event = {
            "event_id": f"CE-{len(events) + 1:03d}",
            "kind": kind, "stage": stage, "text": text, "context": context,
            "actor": actor, "run_id": self.run_id,
            "at": datetime.now(timezone.utc).isoformat(),
        }
        live = self.run().mode in (DemoMode.LIVE, DemoMode.REPLAY)
        try:
            result = playbook.process_event(event, live=live)
        except Exception as exc:  # noqa: BLE001
            result = {"status": f"error: {exc}", "rule_id": None, "reason": str(exc)}
        event["status"] = result["status"] if result["status"] != "error" \
            else f"error: {result['reason']}"
        event["rule_id"] = result.get("rule_id")
        events.append(event)
        self.store.write_json(events, "playbook", "events.json")
        if result["status"] == "active":
            approvals = self.store.read_ledger("approvals.jsonl")
            self.store.append({
                "approval_id": f"APR-{len(approvals) + 1:03d}",
                "workflow": "playbook-admission",
                "outcome": "auto-admitted",
                "details": f"{result['rule_id']}: {event['text'][:120]}",
                "actor": actor, "at": event["at"],
            }, "approvals.jsonl")
    except Exception:  # noqa: BLE001 — capture is best-effort by contract
        pass
```

(Match the surrounding file's existing imports for `datetime`/`timezone` and the approvals record's exact field names — copy the field set used by the `workspace_override_dependency` approvals append at engine.py:3584 so ledger records stay uniform.)

Wire-ins — one line at the end of each method, after its existing ledger/state writes succeed:

| Method (location) | Call |
|---|---|
| `intake_add_business_rule` (≈1111) | `self._playbook_capture(kind="business_rule", stage="planning", text=text, actor=role.value)` |
| `intake_edit_business_rule` (≈1152) | same, `context=f"edit of {rule_id}"` |
| `intake_clarify_answer` (≈769) | one capture per answer: `kind="clarification_answer", stage="planning", text=answer` |
| `planning_revise` (≈2015) | `kind="plan_revision", stage="planning", text=feedback` |
| `architecture_revise` (≈2211) | `kind="architecture_proposal", stage="architecture", text=feedback` |
| `test_plan_amend` (≈2527) | `kind="test_plan_amendment", stage="test", text=proposal, context=f"{pack_id}/{story_id}"` |
| `workspace_override_dependency` (≈3536) | `kind="dependency_override", stage="all", text=reason, context=story_id` |
| `release_approve` (≈4474), only when `decision == "rejected"` and `note` non-empty | `kind="gate_rejection", stage="all", text=note` |

- [ ] **Step 4: Run new tests, then the full suite**

Run: `.venv/bin/python -m pytest tests/test_playbook_engine.py -x -q && .venv/bin/python -m pytest tests/ -q`
Expected: PASS everywhere — existing engine tests must not regress (capture is additive and swallowed on failure).

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . && git add s7_delivery/factory/engine.py tests/test_playbook_engine.py
git commit -m "feat(playbook): ambient capture at seven human touchpoints

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Prompt injection with per-run snapshot and replay pinning

**Files:**
- Modify: `s7_delivery/factory/live_intake.py`
- Modify: `s7_delivery/factory/engine.py`
- Test: `tests/test_playbook_engine.py` (append), `tests/test_playbook.py` (append)

**Interfaces:**
- Consumes: `playbook.memory_layer`, `PromptLayers.memory`.
- Produces: `live_intake._call(*, role, ref, task, beat, key_material, memory: str | None = None)`; `live_intake.run_analysis(..., memory: str | None = None)` and `run_plan(..., memory: str | None = None)` passing it through to every `_call` they make; `Engine._playbook_memory(self, stage: str) -> str | None` writing/reading run snapshot at store path `("playbook", "snapshot.json")` shaped `{"version": int, "rule_ids": {stage: [ids]}, "memory": {stage: str|None}}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_playbook.py`:

```python
def test_prompt_layers_with_no_memory_is_byte_identical():
    from common.prompt import PromptLayers
    bare = PromptLayers(rules="r", role="ro", ref="ref", task="t")
    with_none = PromptLayers(rules="r", role="ro", memory=None, ref="ref", task="t")
    assert bare.assemble() == with_none.assemble()
```

Append to `tests/test_playbook_engine.py`:

```python
def test_playbook_memory_snapshots_and_replay_pins(engine, monkeypatch, tmp_path):
    playbook.add_rule(
        text="Check what already exists", stage_scope="planning",
        repo_scope="global", origin="human_explicit", provenance="RULE_BASED",
        traces_to={}, status="active", actor="x")
    mem = engine._playbook_memory("planning")
    assert "PB-1" in mem
    snap = engine.store.read_json("playbook", "snapshot.json")
    assert snap["rule_ids"]["planning"] == ["PB-1"]

    # The store moves on…
    playbook.add_rule(
        text="A later rule", stage_scope="planning", repo_scope="global",
        origin="human_explicit", provenance="RULE_BASED",
        traces_to={}, status="active", actor="x")
    # …but a REPLAY run keeps injecting its recorded snapshot (spec §4).
    monkeypatch.setattr(type(engine), "_playbook_is_replay",
                        lambda self: True, raising=False)
    pinned = engine._playbook_memory("planning")
    assert "PB-2" not in pinned and "PB-1" in pinned


def test_empty_playbook_memory_is_none(engine):
    assert engine._playbook_memory("planning") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook_engine.py -x -q`
Expected: FAIL — `AttributeError: 'Engine' object has no attribute '_playbook_memory'`.

- [ ] **Step 3: Implement**

`live_intake.py` — extend `_call` (line ≈83) minimally:

```python
def _call(*, role: str, ref: str, task: str, beat: str, key_material: str,
          memory: str | None = None) -> tuple[dict, dict]:
    usage: dict = {}
    response = complete(
        PromptLayers(rules=RULES, role=role, memory=memory, ref=ref, task=task),
        json_mode=True,
        cache_key=f"s7_factory_{beat}:{_cache_digest(key_material)}",
        usage_out=usage,
    )
    return parse_json_response(response), usage
```

Give `run_analysis` and `run_plan` a `memory: str | None = None` keyword parameter and pass `memory=memory` in each `_call` they make (including `run_plan`'s corrective-retry call — the correction must obey the same playbook). `memory=None` assembles byte-identical prompts (the `_join` in `common/prompt.py` drops absent layers), so **existing committed recordings keep replaying**; a populated memory layer changes the assembled prompt and therefore the hashed cache key — a miss, which is correct, and in replay mode a loud `LLMError` rather than a silent live call.

`engine.py`:

```python
def _playbook_is_replay(self) -> bool:
    return self.run().mode is DemoMode.REPLAY

def _playbook_memory(self, stage: str, repo: str | None = None) -> str | None:
    """Memory layer for a live call at `stage`, with replay pinning: a
    replay run injects the snapshot recorded with the run, never the
    current store — committed recordings cannot desync (spec §4). A
    corrupt global store degrades to no-memory rather than breaking the
    run (spec §6): the capture/admin paths surface the loud error."""
    try:
        snap = self.store.read_json_or(
            {"version": 0, "rule_ids": {}, "memory": {}},
            "playbook", "snapshot.json")
        if self._playbook_is_replay() and stage in snap["memory"]:
            return snap["memory"][stage]
        rules = playbook.active_rules(stage, repo)
        mem = playbook.memory_layer(stage, repo)
        snap["version"] = playbook.load()["version"]
        snap["rule_ids"][stage] = [r["id"] for r in rules]
        snap["memory"][stage] = mem
        self.store.write_json(snap, "playbook", "snapshot.json")
        return mem
    except playbook.PlaybookError:
        return None
```

Then, at the engine call sites that invoke `live_intake.run_analysis(...)` and `live_intake.run_plan(...)` (find them with `grep -n "run_analysis\|run_plan" s7_delivery/factory/engine.py`), pass `memory=self._playbook_memory("planning", repo=<name of the run's first connected repo, from the same repos record those call sites already read>)` — repo-scoped rules (spec §4 "matching the call's stage and target repo") ride the same filter `active_rules` already tests.

- [ ] **Step 4: Run everything**

Run: `.venv/bin/python -m pytest tests/test_playbook.py tests/test_playbook_engine.py -x -q && .venv/bin/python -m pytest tests/ -q`
Expected: PASS — in particular the existing live-intake replay tests, which prove the byte-identical no-op.

- [ ] **Step 5: Lint and commit**

```bash
.venv/bin/ruff check . && git add s7_delivery/factory/live_intake.py s7_delivery/factory/engine.py tests/test_playbook.py tests/test_playbook_engine.py
git commit -m "feat(playbook): memory-layer injection with per-run snapshot and replay pinning

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: Permission, state exposure, offline E2E

**Files:**
- Modify: `s7_delivery/factory/roles.py`
- Modify: `s7_delivery/factory/engine.py` (`state()`)
- Test: `tests/test_playbook_engine.py` (append)

**Interfaces:**
- Produces: `PERMISSIONS["manage_playbook"] = {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD}`; `state()["playbook"]` = `{"version": int, "active": int, "pending": int, "run_rule_ids": {stage: [ids]}}`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_playbook_engine.py`)

```python
def test_manage_playbook_permission():
    from s7_delivery.factory import roles
    assert roles.allowed("manage_playbook", Role.DELIVERY_LEAD)
    assert roles.allowed("manage_playbook", Role.ENGINEERING_LEAD)
    assert not roles.allowed("manage_playbook", Role.BUSINESS_OWNER)


def test_state_exposes_playbook_summary(engine):
    engine.intake_add_business_rule(Role.BUSINESS_OWNER, "Members are employees")
    block = engine.state()["playbook"]
    assert block["active"] == 1 and block["pending"] == 0
    assert block["version"] >= 1


def test_offline_e2e_correction_teaches_the_next_run(engine, engine_factory):
    """Spec §7: correction → rule → next run's planning prompt contains it;
    retirement removes it. Fully offline, simulation mode."""
    engine.intake_add_business_rule(
        Role.BUSINESS_OWNER, "Check what already exists before proposing")
    nxt = engine_factory()          # a second, fresh run — same global store
    mem = nxt._playbook_memory("planning")
    assert "Check what already exists" in mem
    rule_id = playbook.load()["rules"][0]["id"]
    playbook.retire_rule(rule_id, actor="Delivery Lead", reason="rescinded")
    third = engine_factory()
    assert third._playbook_memory("planning") is None
```

(`engine_factory` = a small fixture returning a function that builds a fresh simulation `Engine` with a new run id against the same tmp roots — derive it from the same setup the `engine` fixture uses.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_playbook_engine.py -x -q`
Expected: FAIL — `manage_playbook` unknown / `state()` missing `playbook` key.

- [ ] **Step 3: Implement**

`roles.py` — add to `PERMISSIONS` (alphabetical position with the others):

```python
"manage_playbook": {Role.DELIVERY_LEAD, Role.ENGINEERING_LEAD},
```

`engine.py` — in `state()` (≈358), alongside the other top-level blocks:

```python
book = playbook.load()
rules = book["rules"]
snap = self.store.read_json_or({"rule_ids": {}}, "playbook", "snapshot.json")
payload["playbook"] = {
    "version": book["version"],
    "active": sum(1 for r in rules if r["status"] == "active"),
    "pending": sum(1 for r in rules if r["status"] == "pending"),
    "run_rule_ids": snap["rule_ids"],
}
```

(Use the actual local name of the returned dict in `state()` in place of `payload`.)

- [ ] **Step 4: Run, lint, commit**

```bash
.venv/bin/python -m pytest tests/ -q && .venv/bin/ruff check .
git add s7_delivery/factory/roles.py s7_delivery/factory/engine.py tests/test_playbook_engine.py
git commit -m "feat(playbook): manage_playbook permission, state exposure, offline E2E

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 7: API endpoints

**Files:**
- Modify: `apps/control/server.py`
- Test: `tests/test_control_api.py` (append)

**Interfaces:**
- Consumes: `playbook.load/add_rule/decide_rule/retire_rule/restore_rule`, `roles.require("manage_playbook", role)`, the server's existing `_role()` helper and `PlaybookError` → add an exception handler mapping it to 409 like `EngineError`.
- Produces: `GET /api/playbook` → the full book; `POST /api/playbook/rules` (author, provenance `HUMAN`, status `active`); `POST /api/playbook/rules/{rule_id}/decision` (`{role, decision, reason?, text?}`); `POST /api/playbook/rules/{rule_id}/retire` (`{role, reason}`); `POST /api/playbook/rules/{rule_id}/restore` (`{role}`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_control_api.py`, reusing its existing `client` fixture)

```python
class TestPlaybookApi:
    def test_get_playbook_empty(self, client):
        r = client.get("/api/playbook")
        assert r.status_code == 200
        assert r.json()["rules"] == []

    def test_author_requires_manage_playbook(self, client):
        r = client.post("/api/playbook/rules", json={
            "role": "business_owner", "text": "No"})
        assert r.status_code == 403
        r = client.post("/api/playbook/rules", json={
            "role": "delivery_lead",
            "text": "Split work by team and repository",
            "stage_scope": "planning", "repo_scope": "global"})
        assert r.status_code == 200
        rule = r.json()
        assert rule["provenance"] == "HUMAN" and rule["status"] == "active"

    def test_decision_retire_restore_roundtrip(self, client):
        from s7_delivery.factory import playbook
        pending = playbook.add_rule(
            text="Sponsors authenticate with their portal account",
            stage_scope="planning", repo_scope="global", origin="ai_inferred",
            provenance="RULE_BASED", traces_to={}, status="pending",
            actor="x", reason="needs approval")
        rid = pending["id"]
        r = client.post(f"/api/playbook/rules/{rid}/decision", json={
            "role": "engineering_lead", "decision": "approve"})
        assert r.status_code == 200 and r.json()["status"] == "active"
        r = client.post(f"/api/playbook/rules/{rid}/retire", json={
            "role": "delivery_lead", "reason": "superseded"})
        assert r.status_code == 200 and r.json()["status"] == "retired"
        r = client.post(f"/api/playbook/rules/{rid}/restore", json={
            "role": "delivery_lead"})
        assert r.status_code == 200 and r.json()["status"] == "active"

    def test_unknown_rule_is_409(self, client):
        r = client.post("/api/playbook/rules/PB-999/retire", json={
            "role": "delivery_lead", "reason": "x"})
        assert r.status_code == 409
```

(Role strings: use the exact `Role` enum values — check `roles.py`'s `Role` definitions and match the casing the other API tests use.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_control_api.py -k Playbook -x -q`
Expected: FAIL — 404 on `/api/playbook`.

- [ ] **Step 3: Implement in `server.py`**

Pydantic bodies (beside the existing ones), exception handler, and routes:

```python
from s7_delivery.factory import playbook
from s7_delivery.factory.playbook import PlaybookError


@app.exception_handler(PlaybookError)
async def _playbook_error(_req: Any, exc: PlaybookError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


class PlaybookAuthorBody(BaseModel):
    role: str
    text: str
    stage_scope: str = "all"
    repo_scope: str = "global"


class PlaybookDecisionBody(BaseModel):
    role: str
    decision: str
    reason: str = ""
    text: str | None = None


class PlaybookRetireBody(BaseModel):
    role: str
    reason: str = ""


@app.get("/api/playbook")
def get_playbook() -> dict:
    return playbook.load()


@app.post("/api/playbook/rules")
def post_playbook_rule(body: PlaybookAuthorBody) -> dict:
    role = _role(body.role)
    roles.require("manage_playbook", role)
    return playbook.add_rule(
        text=body.text, stage_scope=body.stage_scope,
        repo_scope=body.repo_scope, origin="human_explicit",
        provenance="HUMAN",
        traces_to={"run_id": "", "event_kind": "manual", "event_ref": "",
                   "excerpt": body.text},
        status="active", actor=role.value)


@app.post("/api/playbook/rules/{rule_id}/decision")
def post_playbook_decision(rule_id: str, body: PlaybookDecisionBody) -> dict:
    role = _role(body.role)
    roles.require("manage_playbook", role)
    return playbook.decide_rule(rule_id, decision=body.decision,
                                actor=role.value, reason=body.reason,
                                text=body.text)


@app.post("/api/playbook/rules/{rule_id}/retire")
def post_playbook_retire(rule_id: str, body: PlaybookRetireBody) -> dict:
    role = _role(body.role)
    roles.require("manage_playbook", role)
    return playbook.retire_rule(rule_id, actor=role.value, reason=body.reason)


@app.post("/api/playbook/rules/{rule_id}/restore")
def post_playbook_restore(rule_id: str, body: PlaybookRetireBody) -> dict:
    role = _role(body.role)
    roles.require("manage_playbook", role)
    return playbook.restore_rule(rule_id, actor=role.value)
```

(`roles` is already imported by `server.py` for the permission-error handler; if not, import it. Match the module's existing import style.)

- [ ] **Step 4: Run, lint, commit**

```bash
.venv/bin/python -m pytest tests/test_control_api.py -q && .venv/bin/ruff check .
git add apps/control/server.py tests/test_control_api.py
git commit -m "feat(playbook): /api/playbook admin endpoints behind manage_playbook

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 8: Playbook admin page (frontend)

**Files:**
- Create: `apps/control/web/src/pages/Playbook.tsx`
- Modify: `apps/control/web/src/App.tsx`, `apps/control/web/src/components/SideNav.tsx`
- Modify (regenerated): `apps/control/web/dist/`

**Interfaces:**
- Consumes: `apiGet`/`apiPost` from `src/api.ts`; the endpoints from Task 7; the current role from wherever `Scorecard.tsx`/`Approvals.tsx` reads it (reuse that exact mechanism).
- Produces: page id `playbook`, nav label `Playbook`, registered in `App.tsx`'s page map like `scorecard: Scorecard`.

- [ ] **Step 1: Read the two neighbouring pages**

Read `apps/control/web/src/pages/Scorecard.tsx` and `Approvals.tsx` fully before writing anything — match their data-loading, styling and badge components exactly. This page must look native, not bolted on.

- [ ] **Step 2: Implement `Playbook.tsx`**

Sections, in order:
1. **Pending queue** — each pending rule as a card: rule text, provenance badge, origin, `pending_reason`, and the **verbatim source excerpt side-by-side** (`traces_to.excerpt`, with `run_id`/`event_kind`); actions Approve / Edit & approve (textarea pre-filled with the rule text, posts `decision: "approve", text`) / Reject (reason input). Actions disabled (with tooltip) unless the current role has `manage_playbook` — mirror how other pages gate buttons by role.
2. **Active rules table** — id, text, stage/repo scope, provenance badge, origin, source excerpt (collapsible), Retire (reason required).
3. **Retired fold** — collapsed list with Restore.
4. **Header line** — playbook version, active/pending counts (from `GET /api/playbook`, computed client-side).
5. **Used by runs** (spec §5) — on expanding a rule, lazily fetch `GET /api/runs` and each run's state, and list run ids whose `playbook.run_rule_ids` contain this rule id. Lazy on expand only — never on page load.

Empty state copy: "No rules yet — the playbook learns from human corrections during runs."

- [ ] **Step 3: Register the page**

- `App.tsx`: `import { Playbook } from './pages/Playbook'` and add `playbook: Playbook,` to the page map (line ≈45).
- `SideNav.tsx`: add `['playbook', 'Playbook', '▤'],` next to `['scorecard', 'KPI Scorecard', '◫'],` in the same (governance) group.

- [ ] **Step 4: Build and verify**

```bash
cd apps/control/web && npm run build && cd -
```

Expected: clean build, `dist/` regenerated. Then start the server (`demo/run_control.sh` or however the repo's run script does it), open the Playbook page, and click through: author a rule, approve a pending one (seed one via `POST /api/playbook/rules` then a manual `playbook.add_rule(status="pending", ...)` if needed), retire, restore. Verify the 403 path by switching to a non-lead role.

- [ ] **Step 5: Commit (dist in the same commit — hard rule 4)**

```bash
git add apps/control/web/src apps/control/web/dist
git commit -m "feat(playbook): Playbook admin page — pending queue, active rules, retire/restore

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Docs sync and final verification

**Files:**
- Modify: `CLAUDE.md`, `AGENTS.md` (same commit — the sync rule at the bottom of CLAUDE.md)

- [ ] **Step 1: Add the feature note to `CLAUDE.md`**

A short dated paragraph in the feature-notes sequence (match the existing style), covering: the playbook (`factory/playbook.py`, `artifacts/playbook.json`, gitignored, survives resets); ambient capture at the seven touchpoints; the grounding gate and admission matrix (auto-admit human-explicit grounded, pending otherwise; live auto-admission additionally requires the second-model check; no review model configured ⇒ everything pending); memory-layer injection with per-run snapshot + replay pinning; `manage_playbook`; the Playbook admin page; and the honesty line — no payoff numbers claimed until measured. Mirror the identical paragraph into `AGENTS.md`.

- [ ] **Step 2: Update `docs/s7-feature-priorities.md` item 8**

Change its status line to record that cross-run learning at the artifact level is now built (dated), with system-level workflow self-amendment still open.

- [ ] **Step 3: Full verification**

```bash
.venv/bin/python -m pytest tests/ -q && .venv/bin/ruff check .
git status --short   # nothing unexpected; artifacts/playbook.json must NOT appear (gitignored via artifacts/ rules — verify: git check-ignore artifacts/playbook.json)
```

Expected: full suite green offline; `git check-ignore` confirms the store is ignored. If it is not ignored, add `artifacts/playbook.json` to `.gitignore` beside `artifacts/known_repos.json` in this commit.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md AGENTS.md docs/s7-feature-priorities.md .gitignore
git commit -m "docs: playbook self-learning shipped — CLAUDE/AGENTS sync, feature-priorities item 8

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
