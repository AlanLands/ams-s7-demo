---
id: new-application-scaffold-task
layer: task
title: New-application scaffold — task text
stage: intake
summary: The per-call task for the reviewable architecture.md + README.md scaffold of an application that does not exist yet.
variables: name, description, stack
---
New application:
name: {{name}}
description: {{description}}
stack: {{stack}}

Write architecture.md (components: none yet; data: none yet; explicitly
state this is a new application with no code) and a short README.md. Return
JSON exactly matching:
{
  "architecture_md": "<full markdown content for architecture.md>",
  "readme_md": "<full markdown content for README.md>"
}
