---
id: verification
layer: standard
title: Verification before a claim
stage: build_review
summary: What a coding agent must have run before it says something is done, passing, fixed or working — the claim-to-evidence table, and the test-integrity rules that stop a test being bent to reach green. Published to .s7/shared/verification.md; triggered by the situation, not by a developer phrase. The engine supplies the team and the suite command.
variables: team, suite_command
---
# Verification before a claim — {{team}}

**Use when:** you are about to say anything is done, passing, fixed, working, ready, green or complete — including in passing, including when the developer is waiting, including when you are sure.

Every claim you make about this story becomes evidence. The developer acts on it, the pull request repeats it, and the Control Centre records the criterion against it. A claim you did not verify is not optimism; it is a false entry in a delivery record.

## The rule

**Run the command in this reply, read its output, then make the claim — quoting what you read.**

Not a command you ran earlier. Not a command you ran before the last edit. If the check is not in front of you now, you do not have it.

1. Name what would prove the claim.
2. Run it in full — not the single test, the whole thing the claim covers.
3. Read the output and the exit code. Count the failures.
4. If it does not support the claim, say what actually happened instead.
5. Only then say it, and show the line you read.

## What each claim needs

| Saying this | Requires | Does not count |
|---|---|---|
| "The tests pass" | `{{suite_command}}` run now, 0 failures | A run from before the last edit; one test passing; "it should pass" |
| "It builds" | The build command, exit 0 | Tests passing; the linter passing; no red in the editor |
| "The criterion is met" | Its named test green **and** the developer's own observation recorded in the story note | The test alone — a criterion nobody looked at is not done |
| "The red baseline is in" | The tests present, run, and **failing for the stated reason** | The files being on disk; a build that did not compile |
| "I fixed it" | The original failure re-run and now passing | The code being changed; the error message no longer appearing |
| "Nothing else broke" | The full suite, after the change | The tests you thought were related |
| "It's ready to push" | Every step of the push checklist, in order | Your own sense that the work is finished |

## When you cannot run it

Say so plainly, in the same breath as the claim, and say what is missing: *"I could not run the suite — Maven is not installed on this machine, so nothing has executed these tests."* Then ask for what you need.

A result you could not produce is never reported as a result. **A build that did not compile is not a red baseline, and a change nobody ran is not working.** Naming the gap costs a sentence; a false green costs the story's evidence.

## Test integrity — the line that must not move

A test exists to be capable of failing. Everything below follows from that.

1. **Never weaken a test to reach green.** Not by loosening an assertion, not by asserting something trivially true, not by narrowing the input until it passes, not by catching the failure, not by marking it skipped, expected-to-fail or disabled.
2. **Never rename or delete a test to reach green.** The names S7 generated join CI evidence to acceptance criteria; a renamed test silently unhooks a criterion from its proof while still reporting a pass.
3. **Replace `fail(...)` with a real assertion before implementing.** The published skeleton fails because it is unimplemented. Write the assertion that actually checks the criterion, run it, and **watch it fail for the right reason** — a test that has never failed has never been shown to test anything. If it passes before you write the implementation, the test is wrong.
4. **A test that will not pass is a finding, not an obstacle.** Report it: which criterion, what the test expects, what the code does instead, and what you think is wrong. The developer decides. Bending the test to move on is the one thing that makes every other signal in this delivery worthless.
5. Where the only honest verification is the automated test, say exactly that and give the command. Never describe a manual check you did not perform.
