---
id: clarification-task
layer: task
title: Clarification round — task text
stage: intake
summary: The per-call task for one clarification round: the transcript so far and the 1-4 question cap.
variables: transcript
---
Clarification conversation so far:
{{transcript}}

Ask the 1 to 4 clarifying questions (one topic each) whose answers would most
change the delivery plan. Return JSON exactly matching:
{"questions": ["<question>"]}
