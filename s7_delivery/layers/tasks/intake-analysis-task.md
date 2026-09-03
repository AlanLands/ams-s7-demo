---
id: intake-analysis-task
layer: task
title: Intake analysis — task text
stage: intake
summary: The per-call task for the grounded intake analysis: the clarification transcript and the JSON shape the analysis must return.
variables: transcript
---
Clarification conversation so far:
{{transcript}}

Analyse the change request against the connected repositories. Return JSON
exactly matching:
{
  "problem_understood": true,
  "business_impact": "<one paragraph>",
  "affected_applications":
    ["<connected repository name, or an external system suffixed ' (externally owned)'>"],
  "stakeholders": ["<who>"],
  "dependencies": ["<what this depends on, grounded in the repositories>"],
  "risks": ["<risk>"],
  "clarification_questions": ["<open question for the SME>"],
  "assumptions": ["<assumption carried>"],
  "business_rules": [{"rule_id": "BR-<n>", "text": "<rule in the requirement's words>"}],
  "risk_register": [{"text": "<risk>", "severity": "high|medium|low"}],
  "confidence": <0-100 self-assessment>
}
