# Build & Test Evidence Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Build & Test Evidence into the series' evidence-table + inspector layout over existing task/workspace/handoff state, plus a real per-task evidence export endpoint.

**Spec:** `docs/superpowers/specs/2026-08-09-test-evidence-page-redesign-design.md`

## Global Constraints

Hard rule 4 (dist committed with src); SIMULATED badging on all simulated evidence; no fake CI providers/trackers; lucide only; 398 tests stay green.

### Task 1: evidence export endpoint (TDD)
- [ ] Failing test in `tests/test_factory_build_review.py` (or control api tests): drive a run to task evidence, GET `/api/runs/{run}/tasks/{task_id}/evidence.zip` → 200 zip containing task-evidence.json; unknown task → 404.
- [ ] Implement using the existing `_zip_response` helper; commit.

### Task 2: rebuild `TestEvidence.tsx` + CSS
- [ ] Page per spec structure, reusing StatCard/dp-*/dw-* vocabularies, existing failure-analysis + timeline logic, quality_handoff rows for gates/readiness, submit-review action.
- [ ] `npm run build`; commit with dist.

### Task 3: live verification
- [ ] pytest; Chrome walkthrough on S7-00040 (evidence present for US-001): metrics, filters, row select, gates, AC rows, failure analysis when present, export download 200, submit-readiness states, empty state on a fresh run.
