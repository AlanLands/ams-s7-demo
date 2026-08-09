# Delivery Packs Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Build & Review → Delivery Packs to the reference screenshot with working metrics, filters, inspector, preview tabs, publish flow and bulk actions over real pack state.

**Architecture:** Two small backend additions (pack stats in state, bulk-download endpoint), then a full frontend rebuild reusing StatCard/Badge/TeamChip/Modal and lucide-react. Display-maps publication states honestly; no stored enum changes.

**Tech Stack:** Python + FastAPI (existing), React 19 + TS + lucide-react (existing).

**Spec:** `docs/superpowers/specs/2026-08-09-delivery-packs-page-redesign-design.md` (+ the user's 51-section message as source spec)

## Global Constraints

- Hard rule 4 (amended): `npm run build` + commit `dist/` with any src change.
- SIMULATED honesty on every simulated publication; real counts only.
- Lucide icons exclusively on this page; aria-labels on icon-only buttons.
- Backend TDD; existing 394 tests stay green.

---

### Task 1: Pack stats in state (TDD)

**Files:** Modify `s7_delivery/factory/engine.py` (state assembly), extend `tests/test_factory_delivery_packs.py`.

**Interfaces:** each pack dict in `build.delivery_packs` gains `artifact_count: int`, `size_bytes: int` — walk `build/packs/<slug>` + `architecture/v<N>/{architecture,engineering-rules}.md` + `build/stories/<id>` + `build/tasks/<id>` (mirror of the ZIP file set).

- [ ] Failing test: generate packs → every pack in `state()` has `artifact_count > 0` and `size_bytes > 0`.
- [ ] Implement `_pack_stats(pack) -> tuple[int, int]`; enrich in state assembly only (meta.json unchanged).
- [ ] Green; commit.

### Task 2: Bulk download endpoint (TDD)

**Files:** Modify `apps/control/server.py`; extend `tests/test_control_api.py`.

**Interfaces:** `GET /api/runs/{run_id}/delivery-packs/download-all.zip` → zip with `delivery-packs/<team-slug>/…` per pack (reuse per-pack collection); 404 when no packs.

- [ ] Failing test: drive a run to packs, GET endpoint → 200, zip lists entries for every team slug; no packs → 404.
- [ ] Implement (factor shared collection out of the per-pack endpoint).
- [ ] Green; commit.

### Task 3: Frontend types + rebuild `DeliveryPacks.tsx`

**Files:** Modify `apps/control/web/src/types.ts` (DeliveryPack: `artifact_count?`, `size_bytes?`), rewrite `apps/control/web/src/pages/build/DeliveryPacks.tsx`, extend `theme.css` (filter bar, inspector, team avatar palette, sc-teal accent, spinner, breadcrumb, tooltips).

Structure per spec: header actions, 6 StatCards, filter bar, table, inspector, preview modal (tabs fetch real files), publish confirm/success modals, publish-all confirm, bottom info banner, empty/generating/stale states. Client-side transient PUBLISHING/GENERATING with LoaderCircle.

- [ ] Implement page + CSS; `npm run build` green; commit with dist.

### Task 4: Live verification

- [ ] pytest green; fresh server; Chrome walkthrough: empty state → generate → metrics/filters/search → row select → inspector counts → preview tabs → publish single (confirm → spinner → success modal with SIMULATED badge) → publish-all → per-pack + bulk downloads respond 200 → staleness display after a plan-side revision if reproducible.
- [ ] Fix-ups committed with dist.
