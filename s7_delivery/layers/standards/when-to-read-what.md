---
id: when-to-read-what
layer: standard
title: When to read what
stage: build_review
summary: The routing table for everything S7 publishes to a developer workspace — each moment in a story and the one file that governs it, so a coding agent opens the rules that apply now instead of skimming all of them once. Published to .s7/shared/when-to-read-what.md and pointed at from the top of AGENTS.md. The engine supplies the team and the five developer phrases.
variables: team, phrase_start, phrase_plan, phrase_build, phrase_commit, phrase_push
locked: {{phrase_push}}
---
# When to read what — {{team}}

**Use when:** starting anything. Read this file first and keep it open.

Every other file here governs **one moment**. Find the moment you are in, open that file, and follow it. Do not work from memory of a file you read earlier in the session — open it again when its moment comes round.

Two kinds of moment. **Phrases** are said by the developer; you act only when you hear one. **Situations** you must notice yourself — nobody announces them, and they are the ones most often missed.

## Phrases — the developer says these

| The developer says | Read | And then |
|---|---|---|
| `{{phrase_start}}` | `git-workflow.md` § `{{phrase_start}}` | Branch, list the criteria in build order, copy in the red baseline, ask what blocks the story. Plan nothing, write nothing. |
| `{{phrase_plan}}` | `git-workflow.md` § `{{phrase_plan}}` | Write **one** criterion's plan into the story note and stop, so they can edit it. |
| `{{phrase_build}}` | `git-workflow.md` § `{{phrase_build}}` | Re-read that section as they left it, build exactly that, hand them a way to see it working. |
| `{{phrase_commit}}` | `git-workflow.md` § `{{phrase_commit}}` | Red baseline first, implementation second, story id in every message. |
| `{{phrase_push}}` | `git-workflow.md` § `{{phrase_push}}` | Run the checklist in order and refuse to push if a step fails. |

## Situations — you notice these

| When this happens | Read | Why it matters |
|---|---|---|
| A test fails, a build breaks, or something behaves other than you expected | `debugging.md` | Guessing at fixes is how a symptom gets patched and the cause ships. |
| You are about to say something is done, passing, fixed, working or ready | `verification.md` | This is the moment a false claim enters the record. Every claim needs evidence you ran just now. |
| You are about to write or change a test | `verification.md` § Test integrity | A test bent to pass turns the whole evidence chain into theatre. |
| You are about to write any application code | `code-conventions.md` | Its first rule outranks everything: the repository's own conventions win. |
| A criterion adds or changes a page | `ui-guidelines.md` | A page that works but looks like a framework default is not done. |
| A criterion touches persistence | `db-conventions.md` | One forward-only migration per story; never edit the shared config. |
| Review comments come back on the pull request | `reviewing-feedback.md` | Verify each point against the code before implementing any of it. |
| You are about to touch a file the story does not own | `git-workflow.md` § Story-owned files | This is the single biggest cause of merge conflicts between parallel stories. |
| You are about to report anything to the developer | `git-workflow.md` § How to report back | Written for them, not for the process. Decisions, not essays. |

## The two that are never optional

Everything above is situational except these:

1. **`verification.md` before any claim.** No exceptions, including when you are confident, when the change is small, and when the developer is waiting.
2. **`debugging.md` before any fix.** Including the fix that looks obvious.

## Reference, not rules

`architecture.md` (boundaries and data flow), `engineering-rules.md` (what must be true of the delivery), `assigned-stories.json` (who owns what), `.s7/stories/<story>/` and `.s7/tasks/<task>/` (the work itself). Read these when you need the fact they hold.
