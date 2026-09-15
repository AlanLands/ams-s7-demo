---
id: git-workflow
layer: standard
title: Git workflow
stage: build_review
summary: The developer-facing git rules a team pack publishes to .s7/shared/git-workflow.md — the five developer phrases, the per-criterion plan-then-build loop the developer owns and edits, how a phase reports back to a developer and how it writes an open question as a lettered decision, the story-owned-files rule and the push checklist. The engine supplies the branch names, story rows and phrases; the locked placeholders are the ones the Control Centre reads progress by.
variables: team, repository, context_branch, default_branch, branch_rows, note_rows, phrase_start, phrase_plan, phrase_build, phrase_commit, phrase_push
locked: {{context_branch}}, {{default_branch}}, {{phrase_push}}, {{branch_rows}}
---
# Git workflow — {{team}}

**Use when:** the developer says one of the five phrases below, or you are about to branch, commit, push, open a pull request, or touch a file the story may not own.

Rules for working against `{{repository}}`. The Control Centre reads progress from this repository, so the conventions below are load-bearing, not style.

This file governs the **phrases**. The situations nobody announces — a test failing, a claim about to be made, review comments arriving — are governed by their own files; `.s7/shared/when-to-read-what.md` routes every moment to the one file that covers it, and is the first thing to read.

## The five phrases — what the developer says, what the agent does

A story is delivered **one acceptance criterion at a time**, and each criterion is planned on paper, edited by the developer, built, and then seen working before the next one is planned. A coding agent acts on exactly these phrases and on nothing else:

| Developer says | Agent does | Never |
|---|---|---|
| `{{phrase_start}}` | Prepares the branch, lists the criteria in the order they will be built, lays the red baseline, raises the questions that block the story, stops | plan a criterion, write implementation code, commit, push |
| `{{phrase_plan}}` | Writes the code plan for **one** criterion into the story note and stops, so the developer can change it | write code, plan a second criterion |
| `{{phrase_build}}` | Re-reads that section **as the developer left it**, builds exactly that in the **working tree only**, gets the suite green, hands over a way to see it working, stops | build anything the section does not name, commit, push |
| `{{phrase_commit}}` | Commits what the developer has just reviewed locally — red baseline first, implementation second | push, amend, squash, force |
| `{{phrase_push}}` | Runs the push checklist below in order and pushes the story branch | push on a red suite, push anything else |

Any other instruction is ordinary work in the working tree. The agent never writes implementation code without the build phrase, never commits on its own initiative, never stashes or resets the developer's uncommitted work, and never pushes without the push phrase.

## How to report back — write for the developer, not for the process

Every phrase ends in a report a developer reads in under a minute and can act on without opening this file.

- **Lead with state.** First line: which story, which phase it is in, and what the developer's next word is. Then what is on disk. Then the questions. Never open by justifying what you did or did not do.
- **Show it, do not narrate it.** Branch, files written, criteria with the test that proves each, test results — a short list or a small table, one line each. Prose is for the questions.
- **Never quote these rules back.** The developer has not read this file and should not need to. Say *"there is no build file, so nothing compiles yet"*, not *"rule 5 forbids scaffolding"*. A refusal is explained by its consequence, never by its rule number.
- **Plain language.** Name the file, the command and the error. Keep this file's process vocabulary — baseline, contract, provenance, gate, phase — out of the report; it is S7's language, not the developer's.
- **Say what is not proven.** If the suite could not run, give the command and the reason it failed, and do not call the result a red baseline — a build that never compiled proves nothing either way. Never describe an untried change as working.

### Questions — a decision, not an essay

A question a developer cannot answer in a word stalls the story. Write each one as:

- **one line of context** — what is missing or ambiguous, and what it breaks;
- **lettered options**, each concrete enough to act on — *A: I add a minimal `pom.xml` in its own commit · B: you add it before I continue*. Two or three of them; never an open-ended question where a real choice exists;
- **your recommendation**, marked, with one clause of why — a question with no recommendation hands your own thinking back to the developer;
- **who owns it** — where the answer belongs to the story author rather than the developer (an acceptance criterion that cannot be tested as written, scope that sits in another story), say so, so it escalates instead of being guessed.

Put the questions that block work first and the quick confirmations after, and say which are which. Ask only what the repository, `.s7/**` and the story note cannot answer — read them first. Three sharp questions beat ten thorough ones.

## `{{phrase_start}}` — set up, do not plan and do not code

1. The context branch `{{context_branch}}` is **read-only** — read `AGENTS.md` and `.s7/**` from it, never commit to it.
2. Fetch, then create the working branch from `origin/{{default_branch}}`, **not** from `{{context_branch}}` — branching off the context branch would drag `.s7/**` files into your pull request. One branch per story:
{{branch_rows}}
3. Read `.s7/stories/<story>/story.md` and `acceptance-criteria.md`. List the acceptance criteria back to the developer **in the order they will be built**, each with the skeleton test that will prove it, and say which is first. Do **not** plan them yet: a criterion is planned when its turn comes, against the code that exists by then. If a dependency story is not merged on `origin/{{default_branch}}`, say so and stop.
4. Create the story note with one empty section per criterion, in that order. It is the story's own file and the developer's working copy of the plan:
{{note_rows}}
5. Copy the story's S7 test skeleton in **unchanged** (test names are how CI evidence joins to acceptance criteria). Every criterion's test now fails, which is the red baseline, and it is the only code written before a plan is accepted — no implementation, no stubs, no scaffolding, no "obvious" helpers.
6. **Raise the questions that block the story** — anything unsettled that changes the order of the criteria, the boundary the story sits behind, or whether a criterion is deliverable at all. Ask them now and **do not guess**; a question the developer cannot answer is escalated to the story author, never resolved by inventing an answer. Then **stop**.

## `{{phrase_plan}}` — one criterion, on paper first

7. Plan **exactly one acceptance criterion** — the next unticked section. Never plan two, never plan ahead of the criterion in hand: planning later criteria against code that does not exist yet is guesswork, and the point of planning late is that the plan can name what is really there.
8. Write into that criterion's section of the story note:
   - the criterion verbatim, with its id;
   - the skeleton test that proves it, by name;
   - the **code plan** — every function, module, template and configuration key to be created or changed, each named concretely and each with one sentence on **why this criterion needs it**;
   - **how the developer will see it working** — the page, command or query a human can run to observe this criterion for themselves;
   - any question specific to this criterion, unanswered.
9. Ground the plan in the code that exists **now**: read the files it will touch and name real modules, real functions and real call sites, not placeholders. Where the criterion needs a pattern the repository already uses, follow that pattern and say which existing file it came from.
10. **The section is the contract, and the developer owns it.** Report the plan, say plainly that it is theirs to change, and **stop**. They may rewrite any part of it in the story note — add a function, remove one, change an approach, correct a name. No implementation code is written until they give the build phrase.

## `{{phrase_build}}` — build exactly what the note says, then show it working

11. **Re-read that criterion's section from the story note first and build what it now says**, not what was proposed. The developer's edits are authoritative. If something they wrote cannot be implemented as written, say why and stop — never silently deviate from the accepted plan.
12. Build in the **working tree only**: un-skip that criterion's skeleton test, implement what the section names, and keep going until that test **and the full suite** are green. Work inside one criterion is continuous — the developer is not asked to approve each function, because they approved the plan as a whole.
13. **Give the test real assertions before implementing, and watch it fail.** The skeleton fails only because it is unimplemented; replace that with an assertion that actually checks the criterion, run it, and confirm it fails *for the reason you expect*. A test that has never failed has never been shown to test anything. Everything that then holds the test still — never weaken it, rename it, skip it or delete it to reach green — is in `.s7/shared/verification.md` § Test integrity, and it is the rule this whole delivery's evidence rests on.
14. **When something fails, find the cause before fixing it** — `.s7/shared/debugging.md`. One hypothesis, one change, one run. After three failed attempts, stop and bring it to the developer instead of trying a fourth.
15. If the criterion turns out to need something the section does not name, add it to the section and say so in the report. If the criterion cannot be met as planned at all, stop and re-plan with the developer rather than improvising around it.
16. **Hand the criterion over to be checked.** Report the files changed and the test summary, then give the most direct way a human can observe this criterion themselves: the page and the input to type, the command and the output to expect, the query and the rows it should return. Where the only honest observation is the automated test, say exactly that and give the command to run it — never describe a manual check that does not exist.
17. **Wait for what they saw.** The developer runs it and reports the observation in their own words; the agent compares that with the criterion. If what they describe does not match the criterion, the criterion is **not met** — fix it and hand it back. Record in that section what was run, what the developer observed, and when.
18. Tick the section and **stop**. The next criterion is planned only when the developer asks for it. When the last section is ticked, report the full list of changed files, the test summary and any open question, and stop there — the developer reviews the diff locally, and nothing is committed until they say so.

## `{{phrase_commit}}` — commit what was reviewed

19. Two commits, in this order, so the history itself is the test-first evidence: first the tests alone (`US-1: red baseline for US-1-AC1..AC3 (TASK-001)`), then the implementation (`US-1: add sign-in form (TASK-001)`).
20. Every commit message starts with the story id and names the task id. The Control Centre matches progress by exactly this convention.
21. The implementation commit is made only with the full suite green; a red suite is reported, not committed. Never amend, never squash the baseline away, never commit secrets, `.env` or generated artifacts.
22. Never modify `AGENTS.md` or anything under `.s7/` — S7-managed; they change only via a Control Centre republish.

## Story-owned files — the rule that prevents merge conflicts

Parallel stories conflict when each one appends its own section to the same shared file. So a story branch **never edits** the shared, integration-owned files:
- `README.md`
- `architecture.md`
- the shared application config (`application.yml`, `settings.py`, `.env.example`)
- CI workflows
- `AGENTS.md` and `.s7/**`

A story branch writes only to files it owns:

23. Its own packages, modules, templates and tests.
24. Its **story note** — one file per story, created at rule 4, carrying each criterion's plan as the developer edited it and the verification they recorded, then every config key with its default, the feature flag, endpoints, and follow-ups. After the merge, the team lead folds the note into `README.md` and `architecture.md` in a docs-only commit on its own branch.
25. Its feature flag's default (**off**) declared in code — the properties class or settings constant — so the shared config needs no edit. Where the stack composes config from a directory, the story's keys go in its own fragment (`config/<story-id>.yml`); otherwise they are documented in the story note only.
26. The dependency manifest (`pom.xml`, `package.json`, `requirements.txt`) is the one shared file a story may touch: one minimal hunk, in its own commit, named for the story. An identical addition on two branches merges clean; a differing one is resolved on the story branch at the freshness check — never on `{{default_branch}}`.

## `{{phrase_push}}` — the push checklist

When the developer says this, run the checklist **in order** and refuse to push if any step fails:

27. **Scope check** — only files inside Allowed Components and the story-owned files above changed; nothing staged under `.s7/` or `AGENTS.md`; no shared file edited.
28. **Plan check** — every criterion's section in the story note carries its plan, is ticked, and records the developer's own observation, and nothing was built that no section named. A criterion nobody looked at is not done.
29. **Acceptance check** — every criterion in `.s7/stories/<story>/acceptance-criteria.md` has a passing test, each still carrying the assertions that prove its criterion and the name S7 generated for it (`.s7/shared/verification.md` § Test integrity); run the full suite **now** rather than quoting an earlier run. **Red suite = no push** — report the failures instead.
30. **Traceability check** — every commit on the branch references the story id; working tree clean.
31. **Freshness check** — fetch and rebase on latest `origin/{{default_branch}}`, re-run the full suite after the rebase. Conflicts are resolved here, on the story branch, by the story author.
32. **UI evidence** — for any story that adds or changes a page, the screenshots `.s7/shared/ui-guidelines.md` asks for are ready for the pull request body. For a UI criterion, the screenshot the developer took at rule 16 *is* that evidence.
33. **Push the story branch only** — `git push -u origin feature/<story-id>-…`. Never push to `{{default_branch}}`, never push to `s7/**`, never `--force` a shared branch. After a rebase, `--force-with-lease` on your **own** story branch is the only force ever permitted.
34. **Report back** — branch, commit list, test summary, each claim carrying the output you read for it (`.s7/shared/verification.md`); the developer opens the pull request, and the Control Centre's *Sync from Git* shows the progress.

## Pull request & merge rules

35. PR title starts with the story id; the body maps each acceptance criterion to its test evidence **and to the developer's recorded observation of it**, carries the UI screenshots, and links the story note so the reviewer can read the plan that was agreed; target is `{{default_branch}}`.
36. The author never merges their own PR — no self-approval.
37. **One merge at a time.** After any PR merges, every other open story branch re-runs the freshness check (fetch, rebase, full suite, `--force-with-lease` on its own branch) **before** the next merge. Nobody resolves a conflict on `{{default_branch}}` by hand.
38. Merging is always a human action. After the merge, *Sync from Git* marks the workspace complete — that is the only way a story completes.

## Prohibited, always

39. Writing implementation code without the build phrase; planning or building more than the one criterion in hand; building something the accepted plan does not name; generating a whole story in one pass; ticking a criterion the developer never observed; guessing an answer to an open question instead of asking it; pushing to `{{default_branch}}` directly; pushing to any `s7/**` branch; force-pushing shared branches; deleting branches you do not own; committing without the commit phrase; committing credentials; editing a shared file on a story branch; declaring done with failing tests; weakening, skipping, renaming or deleting a test to reach green; applying a fix without finding the cause; reporting an unproven result as verified — a build that did not compile is not a red baseline, and a change nobody ran is not working.
