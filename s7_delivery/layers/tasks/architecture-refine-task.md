---
id: architecture-refine-task
layer: task
title: Architecture refine — task text
stage: build_review
summary: The per-call task that folds an engineering lead's verbatim proposal into a revision section of the architecture document.
variables: architecture_md, proposal
---
The current architecture document, verbatim:

{{architecture_md}}

An engineering lead proposes this revision, verbatim:

{{proposal}}

Rewrite the proposal as a revision section for the document. Use ###
subsections (change summary, affected components, risks). Keep the lead's
intent; do not add scope. Return JSON exactly matching:
{"refined_markdown": "<the section, markdown>"}
