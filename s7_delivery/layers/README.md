# The delivery system's own instructions — Rules and Skills as files

This directory is the data half of the four-layer delivery system
(feature priority #2; loader in `s7_delivery/factory/layers.py`):

| Layer | Where | What |
|---|---|---|
| **Rules** | `rules/<id>.md` | The stable prefix every model call of one lane starts with |
| **Skills** | `skills/<id>.md` | One per stage: the role text that specialises a call |
| **Playbooks** | `playbooks/<change-type>.md` | The ordered steps a self-healing change runs (JSON body): mechanical steps run automatically, gate steps wait for the named role |
| Workflows | `s7_delivery/factory/engine.py`, `gates.py`, `build_phases.py` | Role check → gate check → write → provenance append → activity append |
| Orchestrator | `apps/control/` and `s7_delivery/cli.py` | Thin surfaces over the same engine |

The mapping onto the prompt-prefix convention (`common/prompt.py`) is
exact: a Rules file fills the `rules` slot, a Skills file fills the `role`
slot, and the workflow supplies `memory`, `ref` and `task` per call.

## File format

```
---
id: intake-analysis          # must equal the file name
layer: skill                 # rules | skill
title: Intake analysis
stage: intake
summary: one line for the app and the CLI
---
<the prompt text, verbatim>
```

**The body is the prompt, byte for byte.** No markdown formatting, no
wrapping for readability, no trailing commentary — whatever is below the
frontmatter is what the model receives. Files are read as bytes and
CRLF-normalised, and `.gitattributes` pins them to LF, so a Windows
checkout produces the same hash as any other.

## Editing one — the cost is deliberate

Committed replay recordings (`s7_delivery/cache/llm/`) hash the assembled
prompt. Editing a rules or skill file therefore misses every recording that
carried the old text, and `tests/test_layers.py` says so instead of letting
a fresh clone silently serve stale prompts. The loop is:

1. Edit the file.
2. `python -m s7_delivery layers record --note "what changed and why" --author "you"`
   — appends one line per changed file to `history.jsonl` (append-only; the
   version number is the ledger's, never implied by the file).
3. Re-record the affected beats with `LLM_MODE=record`, then commit the
   file, the ledger line and the refreshed recordings together.

`python -m s7_delivery layers` lists every file with its recorded version
and flags anything **UNRECORDED**; `layers show <id>` prints one file. The
Control Centre renders the same thing under Governance → Delivery System,
including which skill versions ran in the current run (the activity ledger
carries `id@vN` on every live call).
