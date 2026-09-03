---
id: developer-task
layer: task
title: Developer — build task
stage: build_review
summary: The Developer agent's task: the story, its acceptance criteria and the single-page MapleSure SponsorConnect screen to build.
variables: skill, task_id, stream, task_summary, story_id, story_title, narrative, acceptance_criteria
---
{{skill}} Your task:

Task {{task_id}} ({{stream}}): {{task_summary}}
Story {{story_id}}: {{story_title}}
Narrative: {{narrative}}
Acceptance criteria this task must satisfy:
{{acceptance_criteria}}

Build a single-page MapleSure SponsorConnect screen: the plan sponsor
disability claim submission journey. One self-contained index.html
(inline CSS and JS, professional insurer-portal look, works when opened as a
local file). Required behaviour, happy path only:

- Fields: policy number (id="policy-number") and member id (id="member-id"),
  with a "Look up member" button that fills a member-details panel from a
  small mock data object defined in the page's own JS (no fetch, no backend).
- A claim details section: last day worked (date), first day absent (date),
  nature of absence (select), and a free-text details field.
- A document upload input (id="documents") with the `multiple` attribute and
  a visible list of chosen file names.
- The whole thing wrapped in a form (id="claim-form"). Submitting hides the
  form and shows a confirmation panel (id="confirmation") containing a
  reference number like MS-2026-08-XXXX generated in JS and the status text
  "Received".
- A small footer note: "MapleSure Insurance — fictional demo application".

JSON schema: {"files": [{"path": "index.html", "content": str}]}
