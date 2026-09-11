# Delivery Profiles — one configuration tool, six layers, one mechanism

**Date:** 2026-09-07 · **Status:** in build · **Owner:** product layer

## Why

The admin panel grew as five separate features that happen to share an app:
prompt sets, LLM settings, roles, users, runs. The first real multi-story
delivery (S7-00011) showed a sixth was needed — *standards*, what the packs
tell a developer about git, UI and the database — and it would not have been
the last. Every one of these is the same thing: **configuration that shapes
how S7 behaves for a client or project**, and every one deserves the
treatment prompt sets already have (files, versions, diff, rollback, audit).

## The model

A **Delivery Profile** is a named, versioned bundle of everything that
configures S7 for one tenant or project. A run is created *from* a profile
and pins the versions it consumed.

| Layer | Files | What it is | Consumer |
|---|---|---|---|
| Prompts | `rules/`, `skills/`, `tasks/`, `playbooks/` | What the models are told | every model call (`_llm_env`) |
| Standards | `standards/` | What developers are told: git workflow, engineering rules, UI guidelines, DB conventions, starter UI files | delivery packs, architecture pack, publication |
| Templates | `templates/` | What S7 generates mechanically: CI bootstraps, release-document theme | `ci_bootstrap`, `release_doc` |
| Governance | `governance/` | Roles × permissions overrides | `roles.require` on every engine call |
| Models | `models/` | Provider and model per stage, pricing table | `llm_settings.for_stage` |
| Identity | `identity/` | Organisation, product line, palette tokens, synthetic domain | UI standards, release theme |
| Integrations | `integrations/` | GitHub host, owner allowlist, local paths, repo creation, refused branch names, expected `gh` login | `intake_connect_repo`, `intake_create_new_app_repo`, `publication.check_branch`, the admin Repositories page |

**One mechanism for all six** — every layer is a frontmatter + body file
loaded by `factory/layers.py`:

- **Every setting is a file.** Markdown bodies for text, JSON bodies for
  structured layers (the playbook precedent). No database; a profile is a
  folder under `config/profiles/<name>/` and ports as one.
- **Every file declares its contract** in frontmatter: `variables:` the
  engine supplies (an edit can restructure text but never reference data
  the workflow does not pass), `locked:` literal tokens that must survive
  every edit (the lines the Control Centre depends on), and — in the
  describe payload — which consumer reads it and whether it enters a model
  call (the flag that separates *edit freely* from *this misses recordings*).
- **Every change is a version.** One `history.jsonl` per profile, snapshots
  under `versions/`, diff and rollback as new versions, an audit line per
  admin action. The prompt editor is the editor for every layer.
- **Every consumer pins a version.** Packs record `standards: {id: id@vN}`,
  the architecture pack records the engineering-rules version, events carry
  `skill@vN` as before. A later edit shows as *stale* on the artifact,
  derived on read; regeneration and republication stay human gates.
- **Overlay, not copy.** A profile stores only the files it overrides;
  everything else falls through to the committed default set, which stays
  recording-pinned. The resolved view marks each file *default* or
  *overridden*; an override can be reverted to default.
- **Impact preview before save.** For a file: recordings pinned to its
  current bytes (default set only), runs using the profile whose artifacts
  pinned an older version, and the consumers that read it.
- **Export and import** a profile as a zip.

## What stays out

- The target application's own code and schema — developer work in the
  developer's IDE. S7 is the governed control plane, not an IDE.
- Run evidence, approvals and provenance — audit records, not configuration.
- Named **users** stay global (`config/users.json`): they are identities that
  act across profiles, not tenant configuration.
- Gate *conditions* stay in `gates.py` for now; a profile overrides who may
  sign a gate (governance), not what a gate checks. Follow-up.

## Compatibility

- `DeliveryRun.prompt_set` keeps its name and now names a profile.
  `profiles.root_of()` resolves `config/profiles/<name>` first and falls
  back to a legacy full-copy prompt set under `config/prompt-sets/<name>`,
  so existing runs keep working. The admin *Prompt Sets* routes stay as
  aliases over the same files.
- Hard rule 5 untouched: simulation and demo runs make no model call, and
  the default profile renders exactly the bytes the code rendered before —
  the standards and templates were extracted verbatim.
- The recordings guard (`tests/test_layers.py`) is unchanged in meaning: it
  hashes rules and skills; standards, templates and the JSON layers never
  enter a prompt.

## Phases

1. **Core** — `layers.py` overlay resolution, new kinds, `locked`,
   copy-on-write `write_body`, `revert_override`, `render()`;
   `product/profiles.py` (create, list, describe, delete, export, import);
   engine `_require` so governance resolves per run; version pinning on
   packs and architecture; tests.
2. **Standards + templates + identity** — default files under
   `s7_delivery/layers/`, renderers read them, starter UI files published
   under `.s7/shared/ui/`, DB conventions, CI templates, release theme from
   identity; tests keep the default output byte-identical.
3. **Admin API + UI** — `/api/admin/profiles/*`, impact endpoint, export
   and import, the six-layer editor with source badges and revert, runs show
   `profile@version`; `docs/admin-api.md`, `docs/admin-ui.md`.
4. **Follow-ups** — pricing wired into cost-per-release once token usage is
   measured; gate conditions as governance; test-skeleton shapes as
   templates (their names are the CI join key, so they stay locked).
