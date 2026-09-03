# Real CI evidence — GitHub Actions results for real developer pushes

Date: 2026-08-09. Status: approved by user (conversation), implementing.

## Problem

`git_sync.py` (§ see `2026-08-09-git-evidence-sync-design.md`) already proves a
developer pushed real work — real commit, real branch, real merge state. But
the Build & Test Evidence page's Tests/Coverage/Quality Gates numbers still
come entirely from the deterministic simulation engine's `BuildTask` fields
(`tests`, `coverage_pct`), even for a task with a real, verified push. A live
test on TASK-001 (US-1, `advisor-portal-signin`) surfaced this directly: the
real commit showed up, but "2/2 tests, 94% coverage" was the simulation's
canned number, not anything the pushed code actually produced.

Separately, investigating this surfaced one real defect: the "Sync Now"
button on Build & Test Evidence calls `refresh()` — it re-reads cached state
and has never actually triggered a sync. Only Developer Workspaces' "Sync
from Git" button calls the real `/workspaces/sync-git` endpoint. Fixed as
part of this change (§ Components, item 3).

## Design

**GitHub Actions runs the developer's code for real, on GitHub's own
runners.** S7 never executes a developer's pushed code itself — consistent
with "S7 is the governed control plane, not an IDE." S7's job is: (a) make
sure a workflow exists so a push produces a real run, and (b) read that run's
result back via `gh`, the same CLI already used for repo creation and
publishing.

### Bootstrap: getting a real CI workflow onto the repo

One workflow file per repo, `.github/workflows/s7-ci.yml`, committed straight
to the repo's default branch, written once, right after the repo is cloned —
in both `intake_connect_repo` (engine.py:845) and `intake_create_new_app_repo`
(engine.py:1056), both of which already converge on `clone_repo(...)`.

Stack determination differs by path, because the two paths differ in timing:

- **Connect-by-URL** (existing app, code already present): detect from files.
  `pom.xml` → Maven. `requirements.txt` / `pyproject.toml` / loose `*.py` →
  pytest. Anything else → unsupported, recorded as
  `ci_bootstrap_status: "unsupported_stack"`, not silently skipped.
- **Create-new-app**: at creation time the scaffold is deliberately just
  `architecture.md` + `README.md` (`scaffold.py`'s own docstring: "No
  per-stack boilerplate source files") — there is nothing to detect yet. Use
  the stack the human already typed into the setup conversation
  (`setup["stack"]`, free text) instead: keyword-match
  "java"/"spring"/"maven" → Maven, "python"/"flask"/"fastapi"/"django" →
  pytest. This is `advisor-portal-signin`'s actual path — created empty, a
  developer later pushed a real Spring Boot scaffold to a feature branch. The
  workflow has to already be sitting on `main` waiting for that push, or
  "automatically, once per repo" doesn't hold for this path.

Each stack's workflow: checkout → toolchain setup action → run the test
command (`mvn -B test` / `pytest`) → an `if: always()` step running a short
inline Python snippet (no third-party lib) that regexes the tool's own
summary line out of the captured log (Maven's
`Tests run: N, Failures: F, Errors: E, Skipped: S`; pytest's `N passed` /
`N failed` summary line) into a flat `ci-summary.json`
(`tests_total`, `tests_passed`, `tests_failed`) → `actions/upload-artifact`
named `ci-summary`.

**Coverage stays `null` in v1.** No coverage tooling (JaCoCo, pytest-cov)
gets injected into the developer's own build config — that's the target
repo's decision, not S7's to make for them. Blank, not fabricated, same
discipline as everywhere else in this codebase.

### Reading results back

New module `s7_delivery/factory/ci_sync.py`, same shape as `git_sync.py` but
talking to the GitHub API via `gh` instead of a local clone:

- `latest_run(owner_repo, sha) -> dict | None` —
  `gh run list --repo <owner_repo> --commit <sha> --json databaseId,status,conclusion,url,workflowName -L1`.
  `None` when nothing has run yet for that commit.
- `download_summary(owner_repo, run_id) -> dict | None` —
  `gh run download <id> --repo <owner_repo> -n ci-summary -D <tmpdir>`, parses
  `ci-summary.json`. `None` when the run hasn't finished or produced nothing
  (not an error).

`Engine.workspaces_sync_git` gains one more step per workspace: once it has
`git_evidence.latest.sha`, ask `ci_sync` for that commit's run and store the
combined result as `ws["ci_evidence"]`
(`{status, conclusion, run_id, url, tests_total, tests_passed, tests_failed, checked_at}`).
A `gh`/network failure here is caught and logged, never aborts the git sync —
CI evidence is additive, not load-bearing.

`_workspaces_view` gains a second override block, running after the existing
`git_evidence` block: when `ci_evidence` has a mappable conclusion
(`success→passed`, `failure→failed`, `queued`/`in_progress→running`), it now
fills `ci_status` for real instead of leaving it blank — closing the actual
gap the live test hit, where a real push blanked CI status instead of
reporting it. Unmapped conclusions (`cancelled`, `skipped`, `neutral`,
`action_required`) leave `ci_status` as-is; nothing is invented.

### Frontend — Build & Test Evidence

Once a workspace carries `ci_evidence`:

- CI System / Pipeline / "Open CI Pipeline" switch from the fixed "Simulated
  CI" placeholder to the real GitHub Actions run, linked, badged `HUMAN`.
- A new **"Real CI Run"** block shows real `tests_total/passed/failed`,
  positioned above the existing simulated Test Summary/AC panel. The
  simulated panel stays, relabeled "Simulated Test Plan (baseline)" with its
  `SIMULATED` badge kept — nothing is silently overwritten, both are visible
  and clearly attributed (the "show both, label clearly" principle already
  recorded in this project's design notes, § Design review item 4).
- The table's Tests/Build columns switch to the real numbers and "GitHub
  Actions" label once evidence exists; unchanged fallback to simulated
  otherwise.
- No AC-level mapping in v1 (per the scoping conversation) — the Acceptance
  Criteria Coverage panel keeps showing the simulated baseline's per-AC rows,
  under the relabeled "Simulated Test Plan" heading, not blended with real
  counts.

### Components

1. `s7_delivery/factory/ci_bootstrap.py` — `detect_stack_from_files(repo_dir)`,
   `detect_stack_from_text(stack_hint)`, `workflow_yaml_for(stack)`,
   `bootstrap(repo_dir, owner_repo, stack)` (writes, commits, pushes to
   default branch; no-op + status recorded if stack is `None`).
2. `s7_delivery/factory/ci_sync.py` — `latest_run`, `download_summary`, as above.
3. `Engine.workspaces_sync_git` extended per § Reading results back. The
   Build & Test Evidence page's "Sync Now" button (`TestEvidence.tsx`,
   currently just `await refresh()`) is fixed to call the same
   `POST /api/runs/{run_id}/workspaces/sync-git` endpoint Developer
   Workspaces already uses, then refresh — it has never actually synced
   anything until now.
4. `_workspaces_view` — ci_evidence override block, as above.
5. Frontend: `types.ts` (`DeveloperWorkspace.ci_evidence` and derived fields),
   `TestEvidence.tsx` (Real CI Run block, relabeled simulated panel, CI
   System/Pipeline/Open-CI-Pipeline wiring, Sync Now fix), `DeveloperWorkspaces.tsx`
   (CI column reflects real evidence the same way commit/status already do).

### Artifact consistency — answers "is this in the artifacts already created"

Two existing artifact surfaces would otherwise go stale relative to the live
UI, and both are in scope here:

- **`build/tasks/{task_id}/task-evidence.json`** (part of the delivery pack,
  rendered once at pack-generation time by `delivery_packs.py` from the raw
  `task.get(...)` simulated fields) is a point-in-time snapshot, never
  refreshed. It is also exactly what `GET .../tasks/{id}/evidence.zip`
  downloads (`server.py:610`, zips `build/tasks/{task_id}/*` verbatim) — so
  today's export ZIP shows the stale simulated placeholder even after a real
  sync. Fix: `workspaces_sync_git` rewrites the affected task's
  `task-evidence.json` (adding `ci_evidence` alongside the existing simulated
  fields) whenever sync produces new evidence for that task, so the exported
  ZIP matches what the page shows. New file `ci-evidence.json` is not
  needed — one updated file is simpler and keeps `TASK_FILES` unchanged.
- **Run state / API** (`build/workspaces.json`, served through
  `_workspaces_view()`) already is the live source of truth the UI reads —
  no gap there once § Reading results back lands.

## Out of scope

- AC-level test-to-criterion mapping for real tests (would need a developer
  naming/tagging convention — deferred, per the scoping conversation).
- PR discovery via `gh` (still out of scope per the git-evidence-sync spec;
  not revisited here even though `gh` is now in use for CI).
- Coverage tooling injection into target repos (§ Bootstrap).
- Any write to the remote beyond the one-time workflow-file bootstrap commit.
