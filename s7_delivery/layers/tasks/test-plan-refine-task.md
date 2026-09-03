---
id: test-plan-refine-task
layer: task
title: Test-plan refine — task text
stage: build_review
summary: The per-call task that refines a QA lead's verbatim amendment into additional concrete test cases for one story.
variables: story_id, title, acceptance_criteria, proposal
---
Story {{story_id}} — {{title}}.
Existing acceptance criteria (already covered by generated tests):

{{acceptance_criteria}}

The QA lead proposes this test-plan amendment, verbatim:

{{proposal}}

Refine it into additional concrete test cases. Do not repeat existing AC
coverage. Return JSON exactly matching:
{"cases": [{"description": "<one testable behaviour, one sentence>"}]}
