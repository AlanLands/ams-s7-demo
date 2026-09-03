---
id: new-application-setup-task
layer: task
title: New-application setup — task text
stage: intake
summary: The per-call task for the capped new-application conversation: transcript, final-round note, and the two JSON shapes it may return.
variables: transcript, force_note, requirement
---
Conversation so far:
{{transcript}}
{{force_note}}
The requirement this new application would satisfy:
{{requirement}}

If name, description and stack are not all known yet, ask 1 to 3 short
questions. Otherwise, report the final values. Return JSON exactly matching
exactly one of:
{"needs_more_info": true, "questions": ["<question>"]}
{"needs_more_info": false, "name": "<repo-name-like-this>", "description": "<one line>", "stack": "<e.g. Flask + SQLite>"}
