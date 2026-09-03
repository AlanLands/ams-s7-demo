---
id: tester-revision-task
layer: task
title: Tester — test revision task
stage: build_review
summary: The Tester agent's bounded fix of a defective test per the Reviewer's diagnosis, without weakening a valid assertion.
variables: skill, findings, html, tests, test_output
---
{{skill}} Your tests are red against the current
build and the independent Reviewer's diagnosis is that at least one test is
itself defective. Fix the tests — and only what is defective in them. A fixed
test must still genuinely verify its acceptance criterion against the file as
it exists; do not weaken or delete a valid assertion to force green.

Reviewer findings:
{{findings}}

Current index.html:
{{html}}

Current test_app.py:
{{tests}}

pytest output:
{{test_output}}

Assertions must be independent of the current date, time, or environment —
assert that generating code exists rather than the value it would produce
today. Return the complete revised test_app.py.

JSON schema: {"files": [{"path": "test_app.py", "content": str}]}
