---
id: requirement-routing-task
layer: task
title: Requirement routing — task text
stage: intake
summary: The per-call task for the routable vs new-application verdict and the JSON shape it must return.
---
Decide whether this change request fits inside the connected
repositories, or needs an application that does not exist yet. Return JSON
exactly matching:
{
  "verdict": "routable" | "new_application_needed",
  "reasoning": "<one paragraph>",
  "candidate_repos": ["<connected repository name, only if routable>"],
  "confidence": <0-100 self-assessment>
}
