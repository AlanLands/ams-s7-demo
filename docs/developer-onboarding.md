# Developer Onboarding — working after the handoff

**S7 is the governed control plane; your IDE, CLI and Git are the execution
plane.** Everything S7 publishes for you lands on a context branch named
`s7/<run>-<team>` in your repository. Your job is to bring that context
under your own feature branch and drive the failing tests green. S7 never
creates your branch, never opens your PR, and never merges anything — those
are yours (Human Controlled · AI Assisted).

## The loop

### 1. Fetch and inspect the context branch

```bash
git clone <repo> && cd <repo>        # or just: git fetch origin
git branch -r | grep s7/             # e.g. origin/s7/s7-00005-services-team
```

The branch contains only governed content — `AGENTS.md`, the `.s7/` tree
(team pack, story packs with acceptance criteria, thin task packs that
reference plan and architecture by version, the QA-approved test plan) and
runnable red-baseline test skeletons under `tests/s7/` (pytest) or
`src/test/java/s7/` (JUnit). It never touches source files.

### 2. Branch from main, merge the context in

This is the deliberately manual step S7 never automates:

```bash
git checkout -b feature/US-002-member-lookup origin/main
git merge origin/s7/s7-00005-services-team
```

### 3. Read the brief — or let your assistant read it

`AGENTS.md` is picked up automatically by Claude Code and similar coding
agents, so your assistant starts already knowing the story, acceptance
criteria, architecture version, engineering rules and scope. Your
assignment is in the artifacts too (`.s7/packs/**/assigned-stories.json`).
Scope control applies: your story's target component plus its tests;
anything else is a new ticket, not a bigger diff.

### 4. Run the tests — red is the starting gun

The `tests/s7/` skeletons fail by design: one deliberately-failing test per
acceptance criterion. That is your work list. Implement in your own IDE,
replace each `pytest.fail(...)` / `fail(...)` with real assertions, and
**keep the test names** — CI evidence joins back to acceptance criteria by
name.

### 5. Commit with the story id in the message

```
US-002: add member lookup with sponsor-organization isolation
```

That is how S7's Sync-from-Git attributes real commits to your story — no
plugin, no agent on your machine, just commit-message convention.

### 6. Push, open a PR to main, get it reviewed and merged by a human

The bootstrapped CI workflow runs the s7 tests and emits per-test results
in `ci-summary.json`.

### 7. S7 observes — your merge unlocks the next team

On the next Sync-from-Git, the Control Centre picks up your commits, joins
CI results into per-AC evidence, and a merge to the default branch with a
green CI run is exactly the signal that flips your story to complete and
**unlocks the dependency-blocked stories waiting on it**. Your merge is not
just your finish line; it is the next team's starting permission.

## Don'ts

- **Never develop on the `s7/` branch.** It is disposable context, replaced
  wholesale on the next publish.
- **Never edit `.s7/` or `AGENTS.md` by hand.** They are S7-managed roots;
  the publication machinery refuses foreign content on them.
- **Never start a dependency-blocked story silently.** If you must begin
  before the upstream story is merged and green (e.g. an agreed interface
  contract), a Delivery/Engineering Lead records the override in S7 — it is
  a visible, audited risk decision, not a workaround.
