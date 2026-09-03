---
id: reviewer-task
layer: task
title: Reviewer — independent review task
stage: build_review
summary: The Reviewer agent's task: verify the Developer's output against the acceptance criteria using the files and pytest output as evidence.
variables: skill, task_id, acceptance_criteria, file_listing, html, test_output
---
{{skill}} Verify the Developer's
output for task {{task_id}} against the acceptance criteria, using the evidence
below. Be strict: an unmet criterion is a fail even if the code looks nice.

Acceptance criteria:
{{acceptance_criteria}}

Files produced:
{{file_listing}}

index.html content:
{{html}}

pytest output:
{{test_output}}

JSON schema: {"verdict": "pass" | "fail",
"criteria": [{"id": str, "met": bool, "note": str}],
"notes": [str]}
