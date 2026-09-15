---
id: engineering-rules
layer: standard
title: Engineering rules
stage: build_review
summary: The non-negotiable rules every workspace in a delivery follows — scope, test-first, traceability, no self-approval, rollback, data, story-owned files, the developer commits, reporting written for a human, UI is part of done. Rendered into the architecture pack as engineering-rules.md and published to .s7/shared/.
---
# Engineering Rules

Non-negotiable rules for every workspace in this delivery. `.s7/shared/when-to-read-what.md` says which file governs which moment; read that first.

- **Scope**: change only components your story names. Touching an out-of-scope component requires a new ticket, not a bigger diff.
- **Test-first**: every acceptance criterion has a linked, executable test; the red baseline is recorded before implementation.
- **Plan the criterion in hand, on paper first**: before any code, the agent writes that one criterion's plan into the story note — the test that proves it, every function and template it needs and why this criterion needs each, and how a human will see it working. The developer edits that section and the agent builds what it then says. Later criteria are planned when their turn comes, never in advance. Open questions are asked, never guessed.
- **One criterion at a time, seen by a human**: a coding agent builds one acceptance criterion, then hands the developer a way to observe it and records what they saw in their own words; a criterion nobody looked at is not done (`.s7/shared/git-workflow.md`).
- **Traceability**: commits and pull requests reference their story and task ids.
- **No self-approval**: the implementer never approves their own review; independent review precedes quality handoff.
- **Rollback ready**: the story's feature flag and rollback plan are wired before release, not after.
- **Data**: synthetic data only; no client-identifiable information anywhere in code, tests or fixtures.
- **Story-owned files**: a story branch never edits a shared file (`README.md`, `architecture.md`, the shared application config, CI workflows). Story notes go in `docs/delivery/<story-id>.md`; feature-flag defaults live in code. Parallel stories that each append to the same file are how merges conflict.
- **The developer commits**: a coding agent builds in the working tree and stops; it commits only when the developer, having reviewed the diff locally, says so — and pushes only on the push phrase (`.s7/shared/git-workflow.md`).
- **Evidence before a claim**: nothing is called done, passing, fixed or working without the command that proves it having been run just now and its output read (`.s7/shared/verification.md`). A build that did not compile is not a red baseline.
- **A test is never bent to pass**: no assertion weakened, no test renamed, skipped or deleted to reach green — the names S7 generated are how evidence joins to acceptance criteria, and a test that cannot pass is a finding for the developer, not an obstacle to route around.
- **Cause before fix**: a failure is diagnosed before it is patched, one change at a time, and after three failed attempts it goes back to the developer rather than into a fourth (`.s7/shared/debugging.md`).
- **Report for a human**: every handoff leads with the state of the story, shows the files, criteria and test results rather than narrating them, and writes each open question as a decision with lettered options and a recommendation — never as a quotation of the process rules, and never calling an unproven result verified (`.s7/shared/git-workflow.md`).
- **UI is part of done**: every page added or changed follows `.s7/shared/ui-guidelines.md` and ships its screenshots in the pull request.
