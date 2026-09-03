---
id: prompt-improve-task
layer: task
title: Prompt improvement task
stage: admin
summary: The per-proposal task for the prompt-improve skill — names the target file, its declared variables, its current body and the human corrections to learn from.
variables: target_layer, target_id, variables, current_body, corrections
---
Target file: {{target_id}} (layer: {{target_layer}}; declared variables: {{variables}})

Current body, verbatim:
<<<
{{current_body}}
>>>

Human corrections of output produced under this file, newest first. Each has the field that was corrected, the model's original ("before") and the person's version ("after"):
{{corrections}}

Propose the revised body. Return JSON exactly matching:
{"revised_body": "<complete revised body>", "rationale": "<one paragraph>", "learned": ["<lesson>"]}
