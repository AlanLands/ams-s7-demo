---
id: epic-decomposition-task
layer: task
title: Epic decomposition — task text
stage: planning
summary: The per-call task for breaking the approved epic into stories: epic, business rules, transcript, team roster and the plan JSON shape.
variables: epic, business_rules, transcript, roster
---
The approved epic:
{{epic}}

The intake analysis' business rules (every rule id must be claimed by at
least one story's "traces_to"):
{{business_rules}}

Clarification conversation so far:
{{transcript}}

The team roster. Assign each story's accountable_team from this list ONLY:
{{roster}}

Break the epic into 4 to 8 stories across sprints 1 to 3. Every story needs
2 to 4 acceptance criteria, each independently testable. Every story's
target_repository must be one of the connected repositories. Return JSON
exactly matching:
{
  "stories": [
    {
      "story_id": "US-<n>, numbered from 1 in delivery order",
      "title": "<short imperative title>",
      "purpose": "<why this story exists, one or two sentences>",
      "accountable_team": "<one team from the roster>",
      "target_application": "<the connected repository this changes>",
      "target_repository": "<same connected repository name>",
      "target_component": "<the part of that repository this lands in>",
      "acceptance_criteria": [
        {"ac_id": "US-<n>-AC<m>",
         "text": "Given <context>, when <action>, then <observable result>"}
      ],
      "dependencies": ["<story ids this cannot start before>"],
      "impacts": ["<existing file or behaviour this touches>"],
      "feature_flag": {"name": "<flag to ship dark behind>"},
      "rollback_plan": {"method": "<one line: how this is backed out>"},
      "task_type": "feature | config | migration | integration | test",
      "estimate": <integer: 1/2/3/5/8/13>,
      "sprint": <1, 2 or 3>,
      "traces_to": ["<business rule ids from the analysis this story delivers>"]
    }
  ],
  "confidence": <0-100 self-assessment of the draft>,
  "rationale": "<one paragraph: the decomposition logic>"
}
