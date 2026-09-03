# Git evidence sync — developer progress from real pushes

Date: 2026-08-09. Status: approved by user (conversation), implementing.

## Problem

After S7 publishes the delivery packs, the developer implements in their own
IDE and pushes to the real repository. The Control Centre currently derives
workspace commit/PR/CI state only from the *simulated* task lifecycle — a
live run has no way to see the developer's actual pushed work.

## Design

**A "Sync from Git" action reads real evidence from the repository remote.**
Read-only with respect to the remote; live runs only (a simulation run has no
real clone, and mixing real git evidence into simulated provenance would
muddy the badging).

### Attribution rule (stated in the UI)

A commit belongs to a story when its message mentions the story id or one of
its task ids (case-insensitive). This is the traceability convention the
published `AGENTS.md` already demands ("PR linked to story/task ids");
`AGENTS.md` gains one explicit line telling coding agents to reference the
story id in every commit message.

### Derivation rule (stated in the UI)

- no matching commits → workspace stays as provisioned (`ready`)
- matching commits exist → `in_development`, latest commit shown
- latest matching commit reachable from `origin/<default_branch>` →
  `complete` (a human merged it — S7 never merges)

No percentages, no fake CI: fields git cannot prove (CI status, PR state)
stay blank rather than invented. Everything synced is real human work —
provenance `HUMAN`, plus a visible "last synced" timestamp.

### Components

1. `s7_delivery/factory/git_sync.py` — pure functions over a local clone:
   `fetch(repo_dir)` (git fetch --all --prune) and
   `story_evidence(repo_dir, story_id, task_ids, default_branch)` →
   `{commit_count, latest {sha, author, when, subject}, branches, merged}`.
   Excludes `s7/**` context branches from branch attribution. Offline-
   testable against a local bare "remote".
2. `Engine.workspaces_sync_git(role)` — live mode only; fetches each
   workspace repository's clone once, stores evidence on the workspace
   record (`git_evidence`, `last_sync_at`), records activity.
3. `_workspaces_view` — when a workspace carries synced git evidence, the
   view's commit/branch/status derive from it instead of the simulated task
   lifecycle; `ci_status`/`pull_request` stay untouched by sync.
4. `POST /api/runs/{run_id}/workspaces/sync-git` endpoint.
5. Developer Workspaces page: a **Sync from Git** button (live runs;
   disabled with stated reason in simulation), commit cell shows the real
   sha + subject, status chip from the derivation rule, drawer's Git Handoff
   section shows branch / commit count / merged / last synced.

## Out of scope

- PR discovery via `gh` (phase 2 if wanted) — git alone cannot see PRs.
- Test-result evidence from the developer machine (stays simulated-badged).
- Any write to the remote. Sync is `git fetch` + local ref inspection only.
