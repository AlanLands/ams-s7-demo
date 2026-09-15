---
id: reviewing-feedback
layer: standard
title: Acting on review feedback
stage: build_review
summary: What a coding agent does when pull-request review comments come back — check each point against the code before implementing any of it, ask about the ones that are unclear, push back with reasoning where a comment is wrong, and change one thing at a time. Published to .s7/shared/reviewing-feedback.md; triggered by the situation, not by a developer phrase. The engine supplies the team.
variables: team
---
# Acting on review feedback — {{team}}

**Use when:** review comments arrive on the pull request, or the developer relays someone else's feedback — before you change anything.

Review comments are evidence about the code, not instructions to be executed. A reviewer reads a diff without the context you have; some comments are right, some are right about a problem but wrong about the cause, and some are about code they misread. Implementing all of them without checking is as unhelpful as implementing none.

## Before changing anything

1. **Read all of it first.** Comments interact — the third often changes what the first means. Do not start on comment one while comment five is unread.
2. **Say each point back in your own words**, as a technical statement about this code: *"Comment 2 says the eligibility check runs before the session is loaded, so it reads a null member."* If you cannot restate it that way, you have not understood it yet.
3. **Check it against the code.** Open the file, read the actual lines, confirm the comment describes what is really there. A reviewer working from a diff cannot see the rest of the file; you can.
4. **Decide whether it is right for this repository** — `code-conventions.md` rule 1. A suggestion that contradicts the pattern every neighbouring file follows is a question for the developer, not an improvement to apply.

## Where something is unclear

5. **Stop and ask before implementing any of it.** Do not do the parts you understood and leave the rest for later — partial understanding of a related set produces a change that satisfies neither. Say which points you understand, which you do not, and what you need to know.
6. Put the question as a decision: the point, what you think it means, the options, your recommendation. See `git-workflow.md` § How to report back.

## Where you think a comment is wrong

7. **Say so, with the reason and the evidence** — the file and lines, the test that covers it, the convention it follows. Disagreeing technically is part of review; silently not doing it is not, and neither is doing something you believe is wrong.
8. The developer settles it. If they side with the reviewer after hearing the reason, implement it without relitigating.

## Making the changes

9. **One comment at a time**, each with its own verification (`verification.md`) before moving to the next. A single commit that addresses eleven comments cannot be reviewed, and a failure in it cannot be attributed.
10. **Stay inside the story.** A review comment is not a licence to edit a shared file (`git-workflow.md` § Story-owned files), to change a test so a criticised behaviour passes (`verification.md` § Test integrity), or to widen the diff beyond what the comment asks.
11. **Re-run the push checklist** before pushing again — the freshness check especially, since other branches may have merged while the review was open.
12. **Report by comment**: which you implemented and what changed, which you pushed back on and why, which are still open and waiting on an answer. No performative agreement — the developer needs the technical state, not enthusiasm.
