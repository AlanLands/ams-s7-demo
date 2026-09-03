---
id: requirement-extraction-task
layer: task
title: Requirement extraction — task text
stage: intake
summary: The per-call task for extracting a requirement from uploaded or pasted source text.
variables: text
---
The source text, verbatim:

{{text}}

Extract the requirement from this text. Return JSON exactly matching:
{
  "epic_title": "<short title>",
  "business_objective": "<one paragraph>",
  "requirement_summary": "<short paragraph>",
  "extracted_requirements": [
    {"rule_id": "REQ-<n>", "text": "<requirement, in the source's own words>"}
  ]
}
