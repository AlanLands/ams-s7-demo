# Architecture Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deterministic architecture validations that gate acceptance, derived landscape diagram data, enriched architecture meta (hash/sizes/plan version), and a mockup-matching Architecture page.

**Architecture:** Backend first (pure-function checks module + engine wiring, TDD via pytest), then frontend rebuild consuming the enriched `build.architecture` state. Five-file pack unchanged; all new data rides `meta.json`.

**Tech Stack:** Python 3 + pydantic (existing), React 19 + TS + lucide-react (existing).

**Spec:** `docs/superpowers/specs/2026-08-09-architecture-page-redesign-design.md`

## Global Constraints

- Hard rule 4 (amended): any `apps/control/web/src` change ⇒ `npm run build` + commit `dist/` in the same commit.
- Honesty: validations labelled "Automated checks"; generation badge = provenance (SIMULATED/RULE_BASED), never "AI Generated" for a rule-based render; diagram derives only from run data.
- `architecture_accept` blocks on mandatory check failure server-side.
- All Python work is TDD: failing test → minimal code → green → commit.

---

### Task 1: `factory/architecture_checks.py` (TDD)

**Files:** Create `s7_delivery/factory/architecture_checks.py`, `tests/test_factory_architecture_checks.py`.

**Interfaces:** Produces `run_checks(stories: list[dict], repos: list[dict], files: dict[str, object]) -> list[dict]` where each row is `{"check_id", "label", "result": "passed"|"warning"|"failed", "detail", "mandatory": bool}`; also `mandatory_failures(checks) -> list[str]`. Nine checks per spec table (app_ownership, repo_mapping, dependency_validity, circular_dependencies, integration_boundaries, security_constraints, deployment_constraints, data_flow, team_ownership).

- [ ] Write failing tests: happy path (all pass on a well-formed plan/pack), missing repo → repo_mapping failed, unknown dependency id → dependency_validity failed, cycle A→B→A → circular_dependencies failed, architecture.md without `## Data Flow` → data_flow warning, unconnected repo → team_ownership warning, `mandatory_failures` lists only mandatory fails.
- [ ] Run: `python -m pytest tests/test_factory_architecture_checks.py -q` → fails (module missing).
- [ ] Implement module (pure functions; cycle check via iterative DFS; section checks via `"## <Heading>" in files["architecture.md"]`).
- [ ] Green, then commit.

### Task 2: `landscape()` in `factory/architecture.py` (TDD)

**Files:** Modify `s7_delivery/factory/architecture.py`; extend `tests/test_factory_architecture_checks.py` (same commit family).

**Interfaces:** Produces `landscape(stories, analysis, repos) -> dict` = `{"nodes": [{"application", "layer": client|core|data|external, "repository", "teams": [...]}], "edges": [{"from_app", "to_app", "kind": "sync"|"data"}]}` per spec classification rule.

- [ ] Failing tests: portal app → client; app with connected repo → core; `store/db` name → data; analysis-only app with no repo → external; cross-team dependency yields a sync edge between the two apps; core→data edge added when both present.
- [ ] Implement; green; commit.

### Task 3: Engine meta enrichment + blocked acceptance (TDD)

**Files:** Modify `s7_delivery/factory/models.py` (ArchitectureMeta: `plan_version: int = 0`, `content_hash: str = ""`, `file_sizes: dict[str, int] = {}`, `validations: list[dict] = []`, `landscape: dict = {}`), `s7_delivery/factory/engine.py` (`_write_architecture_pack` computes sizes/hash/checks/landscape/plan_version; `architecture_accept` raises `EngineError("mandatory validation failed: …")` when `mandatory_failures` non-empty), extend `tests/test_factory_architecture.py`.

- [ ] Failing tests: generated meta carries plan_version + 5 file_sizes + 9 validations + non-empty content_hash + landscape nodes; acceptance blocked when a mandatory check fails (monkeypatch a story to drop its repository, regenerate → accept raises); normal accept still passes and keeps hash.
- [ ] Implement (sha256 over sorted filename+bytes; sizes from rendered payloads; JSON payloads hashed via their serialized form the store writes).
- [ ] Green + full `python -m pytest -q`; commit.

### Task 4: Frontend rebuild

**Files:** Modify `apps/control/web/src/types.ts` (ArchitectureMeta additions), `apps/control/web/src/pages/build/Architecture.tsx` (full rebuild per spec layout), `apps/control/web/src/theme.css` (tabs, landscape SVG, validation rows, pack list), reuse `bo-compact` conventions via an `arch-compact` scope.

**Interfaces:** Consumes `build.architecture.{validations,landscape,file_sizes,content_hash,plan_version}`, `data.staleness`, existing act endpoints. Tab ids: overview, repos, dependencies, integration, dataflow, tech, security, deployment.

- [ ] Query ui-ux-pro-max for tab + diagram guidance (already loaded this session; one targeted search).
- [ ] Extend types.ts; build the page: header actions, info banner, summary strip, landscape SVG card (layered rows + legend), tab bar with per-tab renderers (md section parser: split on `\n## `), rail (pack files with sizes + preview/download each + Download All, validations panel, next-step card), staleness banner.
- [ ] `npm run build` green; commit with dist.

### Task 5: Live verification

- [ ] Fresh server on 8720; Chrome walkthrough: pre-G1 empty state → generate on a signed run → validations all render → tabs all populate → landscape shows run's own apps → revise (v2, note preserved, prior version resolvable) → accept (canonical, hash shown) → next-step card → Delivery Packs.
- [ ] Full pytest; fix-ups committed with dist if needed.
