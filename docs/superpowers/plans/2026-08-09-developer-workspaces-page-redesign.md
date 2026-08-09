# Developer Workspaces Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Build & Review → Developer Workspaces to the reference screenshot as a pure control/evidence view over existing workspace state, plus fix the toast-over-footer overlap.

**Architecture:** Frontend-only. Reuses StatCard/Badge/TeamChip/Modal/lucide and the Delivery Packs CSS vocabulary; all data from existing `build.workspaces`, `build.tasks`, `build.delivery_packs`, plan stories and the activity log.

**Spec:** `docs/superpowers/specs/2026-08-09-developer-workspaces-page-redesign-design.md` (+ the user's 45-section message as source spec)

## Global Constraints

- Hard rule 4 (amended): `npm run build` + commit `dist/` with any src change.
- No IDE/terminal/coding-chat surfaces; simulated developer steps stay, labelled "(simulated)".
- Lucide icons only; aria-labels on icon-only buttons; existing 398 tests stay green.

---

### Task 1: Rebuild `DeveloperWorkspaces.tsx` + CSS + toast fix

- [ ] Rewrite page per spec structure (header badges, 6 StatCards, filter row, 11-column table, detail panel with expandable sections, assign modal, empty state, info banner).
- [ ] `theme.css`: dev-workspace additions (dw-* classes reusing dp-* patterns), toast `bottom` raised above sticky footer.
- [ ] `npm run build` green; commit with dist.

### Task 2: Live verification

- [ ] pytest green (no backend change); Chrome walkthrough: metrics/filters, row select, sections expand with real counts, Assign Developer PATCH works, simulated dev steps advance commit/CI/dev status live, View Build Evidence lands on test_evidence with the story selected, stale/correction states visible where present, toast no longer overlaps footer.
- [ ] Fix-ups committed with dist.
