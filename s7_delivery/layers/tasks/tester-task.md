---
id: tester-task
layer: task
title: Tester — write tests task
stage: build_review
summary: The Tester agent's task: the Developer's files, the acceptance criteria, and the structural pytest tests to write.
variables: skill, task_id, task_summary, generated_files, acceptance_criteria
---
{{skill}} The Developer produced these files for
task {{task_id}} ({{task_summary}}):

{{generated_files}}

Acceptance criteria:
{{acceptance_criteria}}

Write pytest tests (a single test_app.py) that verify the happy path
STRUCTURALLY against the actual file above — read index.html from
Path(__file__).parent and assert what the criteria need: the form and its
required field ids exist, the upload input allows multiple files, the
confirmation panel and status markup exist, the member lookup mock data is
present. 4 to 6 focused tests, stdlib + pytest only, no browser, no server,
no network. Every assertion must hold for the file exactly as shown above,
and must be independent of the current date, time, or environment — never
hard-code a year, month, or timestamp; where the page generates a value at
runtime, assert the generating code exists, not the value it would produce
today.

JSON schema: {"files": [{"path": "test_app.py", "content": str}]}
