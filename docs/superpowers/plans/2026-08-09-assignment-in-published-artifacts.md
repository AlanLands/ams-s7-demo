# Assignment in published artifacts — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans.
> Spec: `docs/superpowers/specs/2026-08-09-assignment-in-published-artifacts-design.md`

**Goal:** Developer assignment travels with the published `.s7/**` artifacts so
a coding agent in the clone can answer "what is assigned to me?".

**Architecture:** Renderers gain an `assignments` mapping; assignment bumps the
team pack version and resets publication status (existing refresh model); the
human republishes to push. No new enums, no publish-time overlays.

**Tech stack:** Python (pytest, TDD) + one toast string in React.

## Global constraints

- Hard rule 4: no Claude-Code-specific tooling in artifacts; `AGENTS.md` is the
  open convention.
- Frontend `src/` change ⇒ `npm run build` and commit `dist/` in same commit.
- All 399 existing tests must stay green; `pytest` run without `| tail`.

---

### Task 1: Renderers carry assignments

**Files:** Modify `s7_delivery/factory/delivery_packs.py`;
test `tests/test_factory_delivery_packs.py`.

- [ ] Failing tests: `render_team_pack(..., assignments={"S7-001": "Alan"})`
      → `assigned-stories.json` entries carry `assigned_to` ("" when absent);
      `render_team_agents_md` output contains `## Story Assignments`,
      the developer's name, and a `What is assigned to me?` section pointing
      at `.s7/shared/assigned-stories.json` and `.s7/stories/`.
- [ ] Implement: optional `assignments: dict[str, str] | None = None` param on
      both renderers, threaded from `render_team_pack` into
      `render_team_agents_md`.
- [ ] Suite green; commit.

### Task 2: Engine — generate passes assignments; assigning refreshes the pack

**Files:** Modify `s7_delivery/factory/engine.py`;
test `tests/test_factory_delivery_packs.py`.

- [ ] Failing test: generate → publish → `workspace_assign_developer` →
      pack version bumped, `publication_status == "not_published"`, stored
      `build/packs/<slug>/assigned-stories.json` names the developer, AGENTS.md
      mentions them; second publish succeeds and `pub.file_plan` output carries
      the name; workspace `developer` survives.
- [ ] Extract per-team pack writing in `delivery_packs_generate` into
      `_write_team_pack(...)` helper (renders task packs + team pack, writes
      files, returns pack dict, records provenance); generate builds
      `assignments` from `self._workspaces()`.
- [ ] `workspace_assign_developer` calls the helper for the affected team after
      saving the workspace, with activity noting republish needed.
- [ ] Suite green; commit.

### Task 3: Frontend toast + verify live

**Files:** Modify `apps/control/web/src/pages/build/DeveloperWorkspaces.tsx`;
rebuild `apps/control/web/dist/`.

- [ ] Assign-success toast: "Assigned <name>. Team pack refreshed — republish
      Delivery Packs to sync the assignment to Git."
- [ ] `npm run build` green; walk the flow live in Chrome on a demo run:
      publish → assign → pack shows ready to publish v2 → publish → workspace
      current.
- [ ] Commit (src + dist together).
