# Independent Review Page Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Independent Review into the series' table + inspector governance workspace over the existing isolated-reviewer model.

**Spec:** `docs/superpowers/specs/2026-08-09-independent-review-page-redesign-design.md`

### Task 1: rebuild `IndependentReview.tsx` (+ CSS as needed)
- [ ] Page per spec structure, reusing StatCard/dp-*/dw-* vocabularies; derived checkpoints + score with stated rules; existing execute/return endpoints; findings/history/traceability from state.
- [ ] `npm run build`; commit with dist.

### Task 2: live verification
- [ ] pytest; Chrome walkthrough on S7-00040: submit US-001 to review, execute as independent reviewer, verdict + findings render, rework path when blocked, score/checkpoints derive correctly, empty-state and banner.
