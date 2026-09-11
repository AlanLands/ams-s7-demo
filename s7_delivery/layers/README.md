# The delivery system's own instructions — Rules and Skills as files

This directory is the data half of the four-layer delivery system
(feature priority #2; loader in `s7_delivery/factory/layers.py`):

| Layer | Where | What |
|---|---|---|
| **Rules** | `rules/<id>.md` | The stable prefix every model call of one lane starts with |
| **Skills** | `skills/<id>.md` | One per stage: the role text that specialises a call |
| **Playbooks** | `playbooks/<change-type>.md` | The ordered steps a self-healing change runs (JSON body): mechanical steps run automatically, gate steps wait for the named role |
| **Tasks** | `tasks/<id>.md` | The per-call task text with the `{{variables}}` the workflow supplies |
| Workflows | `s7_delivery/factory/engine.py`, `gates.py`, `build_phases.py` | Role check → gate check → write → provenance append → activity append |
| Orchestrator | `apps/control/` and `s7_delivery/cli.py` | Thin surfaces over the same engine |

Since 2026-09-07 this directory is also the **default delivery profile**
(`docs/design-history/plans/2026-09-07-delivery-profiles.md`): the same
loader carries every configuration layer, and a profile under
`config/profiles/<name>/` overrides only the files it changes.

| Profile layer | Where | Body | Consumer |
|---|---|---|---|
| **Standards** | `standards/<id>.md` | markdown with `{{variables}}` | delivery packs → `.s7/shared/` (git workflow, engineering rules, UI guidelines, DB conventions, starter UI files) |
| **Templates** | `templates/<id>.md` | the generated file verbatim | CI bootstrap workflows, new-application build scaffolds, release-document theme |
| **Governance** | `governance/roles.md` | JSON | `roles.require` on every engine call |
| **Models** | `models/llm-settings.md`, `models/pricing.md` | JSON | `llm_settings.for_stage`, cost per release |
| **Identity** | `identity/identity.md` | JSON | organisation, palette and synthetic domain for the standards and the release theme |
| **Integrations** | `integrations/github.md` | JSON | how S7 may talk to the tenant's git hosting — host, owner allowlist, refused branch names |
| **Assets** | `assets/<id>.md` | the artifact verbatim | delivery packs → `.s7/assets/<dest>` — project artifacts (baseline schema, API contract, document template). **Not** a variable layer: `{{…}}` is the content's own templating syntax and survives untouched. The default set ships none. |

Only rules, skills and tasks enter a model call: editing them misses
recordings (below). Editing any other layer only makes generated artifacts
stale — packs and the architecture pack pin the versions they were rendered
from (`pins`), and the Control Centre reports `stale_pins` on read.

The mapping onto the prompt-prefix convention (`common/prompt.py`) is
exact: a Rules file fills the `rules` slot, a Skills file fills the `role`
slot, and the workflow supplies `memory`, `ref` and `task` per call.

## File format

```
---
id: intake-analysis          # must equal the file name
layer: skill                 # rules | skill | task | playbook | standard | template | governance | model | identity
title: Intake analysis
stage: intake
summary: one line for the app and the CLI
variables: a, b              # task/standard/template: the only {{placeholders}} the body may use
locked: {{a}}, s7-managed    # optional: literal tokens every edit must keep
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
