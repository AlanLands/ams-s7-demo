# Admin API — contract

The separate admin application (`apps/admin/server.py`, port **8730**, UI in
`apps/admin/web/`) is the product's operator surface. Everything it changes
lands in the configuration plane (`s7_delivery/product/`, files under
`config/`, gitignored) and is recorded — prompt edits in the prompt set's own
`history.jsonl`, everything else in `config/audit.jsonl`.

This file is the contract the backend implements and the UI consumes. Keep
both in step with it.

## Conventions

- Base path `/api/admin/`. JSON in, JSON out. Errors are `{"detail": str}`.
- **Auth.** If the environment variable `S7_ADMIN_TOKEN` is set, every
  `/api/admin/*` request must carry `X-Admin-Token: <token>` or gets `401`.
  Unset (the local demo default) means open on 127.0.0.1, same as the
  Control Centre.
- **Actor.** `X-Admin-User: <name>` names who made a change for the audit
  ledger and prompt version lines. Defaults to `admin`.
- Status codes: `400` malformed or refused by validation (`ConfigError`,
  `LayerError`), `404` unknown thing, `409` refused because of state (a set in
  use, a default that cannot be deleted), `401` bad token.
- Nothing here ever returns a credential value — provider status is boolean.

## Overview

`GET /api/admin/health` → `{"ok": true, "config_root": str}`

`GET /api/admin/overview` →
```json
{
  "runs": {"total": 7, "by_mode": {"simulation": 4, "demo": 1, "live": 2, "replay": 0}},
  "prompt_sets": 2,
  "profiles": {"count": 3, "overlays": 1, "legacy_sets": 1},
  "users": 5,
  "llm": {"LLM_PROVIDER": "anthropic", "LLM_MODE": "replay", "effective_mode": "replay"},
  "default_set_unrecorded": [],
  "recent_audit": [ ...last 10 audit rows... ]
}
```

## Delivery profiles (`s7_delivery/product/profiles.py`, `factory/layers.py`)

A **delivery profile** is one named, versioned bundle of everything that
configures S7 for a client or project — eight layers (prompts, standards,
templates, governance, models, identity, integrations, assets), one file
shape, one ledger, one editor, one audit trail (design: `docs/design-history/plans/
2026-09-07-delivery-profiles.md`). A run is created *from* a profile
(`DeliveryRun.prompt_set` names it) and pins the versions it consumed.

- **Overlay, not copy.** A profile (`config/profiles/<name>/`) stores only
  `profile.json` plus the files it **overrides**; every other file falls
  through to the committed default set in `s7_delivery/layers/`, which stays
  recording-pinned. Every file row carries `source`: `default` (showing
  through), `override` (the profile's own copy) or `set` (a legacy full-copy
  prompt set). The first PUT of a default file is copy-on-write: the override
  is created with the default's frontmatter and versioned from v1 in the
  profile's own `history.jsonl`; `revert` deletes it and the default shows
  through again (recorded as a `reverted_to` ledger line, never silently).
- **Pins.** Generated artifacts record the version they consumed as
  `id@vN+<sha8>` (delivery packs: `pins: {file_id: ref}`; the architecture
  pack: the engineering-rules version). A later edit shows as *stale* on the
  artifact, derived on read; regeneration stays a human gate.
- **Impact is stated before a save**, from the files and the run ledgers:
  `recordings_pinned` (committed recordings whose prompt carries the current
  bytes — counted for the default profile's prompt-layer files only, since
  only those enter a model call), the runs on the profile and which of their
  artifacts pinned an older version (`would_go_stale`), and the `consumers`
  that read the file. `enters_model_call` is the flag that separates *edit
  freely* (standards, templates, the structured layers) from *this misses
  recordings* (rules, skills, tasks).
- **Locked tokens.** A file's frontmatter may declare `locked:` literal
  tokens that every edit must keep — the lines a consumer depends on. A PUT
  that drops one is refused (`400`). Variable layers (tasks, standards,
  templates) may only use placeholders declared in `variables`.
- **Kinds.** `default` (the committed set), `profile` (overlay), `legacy-set`
  (a full copy under `config/prompt-sets/`, created before profiles existed;
  still resolves, still editable, cannot revert or export).

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/profiles` | | `{"profiles": [ProfileSummary]}` — default first, then profiles, then legacy sets |
| POST | `/profiles` | `{name, description?}` | `ProfileSummary` (201); `400` bad name (lowercase kebab-case, 2–40); `409` name taken |
| GET | `/profiles/{name}` | | `ProfileDetail` |
| PATCH | `/profiles/{name}` | `{description}` | `ProfileSummary`; `409` for the default or a legacy set |
| DELETE | `/profiles/{name}` | | 204; `409` for the default or while a run names it; `404` unknown |
| GET | `/profiles/{name}/history` | | `{"history": [LedgerLine]}` oldest first (the profile's own ledger — overrides only) |
| GET | `/profiles/{name}/files/{id}` | | `ProfileFileDetail` |
| PUT | `/profiles/{name}/files/{id}` | `{body, note}` | `{"file": FileRow, "version": LedgerLine \| null}` — `null` when unchanged; copy-on-write in a profile |
| POST | `/profiles/{name}/files` | `{layer, id, title, stage, summary, body, variables?: [str], locked?: [str], note}` | `{"file": FileRow, "version": LedgerLine}` (201); `400` unknown layer, bad id, duplicate id, undeclared placeholder |
| GET | `/profiles/{name}/files/{id}/versions/{n}` | | `{"id", "version": n, "body"}`; `404` when no body recorded |
| GET | `/profiles/{name}/files/{id}/diff?from=1&to=2` | | `{"id", "from", "to", "diff": str}` (unified) |
| POST | `/profiles/{name}/files/{id}/rollback` | `{to_version, note}` | same shape as PUT — a rollback is a *new* version |
| POST | `/profiles/{name}/files/{id}/revert` | `{note}` | same shape as PUT (`version.reverted_to` = `default@vN`); `409` when the file is not overridden, exists only in the profile, or the name is not an overlay profile |
| GET | `/profiles/{name}/files/{id}/impact` | | `Impact` |
| GET | `/profiles/{name}/export.zip` | | `application/zip`, `Content-Disposition: attachment; filename="<name>-profile.zip"` — the profile directory exactly; `409` for the default or a legacy set |
| POST | `/profiles/import?name=&replace=false` | multipart form, field `file` (the zip) | `ProfileSummary` (201); `400` not a zip / no `profile.json` / a member outside the profile shape / a file that does not parse; `409` name exists without `replace`, or names something that is not a profile |

Shapes:

```
ProfileSummary = {name, kind: "default"|"profile"|"legacy-set", description, base,
                  created_at, created_by, root, is_default, overlay: bool,
                  files: int,                        # resolved file count (overlay + default)
                  counts: {prompts, standards, templates, governance, models, identity},
                  overridden: [id],                  # overlay profiles only
                  unrecorded: [id], versions: int,   # the profile's own ledger
                  fingerprint: str}                  # 12 hex over the resolved file set;
                                                     # a run records it at creation
ProfileDetail  = ProfileSummary + {
                  groups: [{id, label, layers: [layer], files: [FileRow], overridden: int}],
                  workflows: [Workflow], history: [LedgerLine], provenance: "rule_based"}
FileRow        = layers.describe(root) row: {id, layer, title, stage, summary, path,
                  sha256, short, body, variables, locked, source, enters_model_call,
                  consumers: [str], version, recorded, recorded_at, workflows}
                  # version/recorded answer from the ledger that owns the file:
                  # the profile's for an override, the default set's otherwise
ProfileFileDetail = {"file": FileRow, "versions": [LedgerLine + {has_body}],
                  "placeholders": [str], "recordings_pinned": int, "impact": Impact}
Impact         = {provenance: "rule_based", profile, file_id, layer, source,
                  current: "id@vN+sha8", enters_model_call: bool,
                  recordings_pinned: int, re_record_needed: bool, consumers: [str],
                  runs: [{run_id, artifacts: [{artifact, kind, artifact_version,
                          pinned, stale}], would_go_stale: [artifact]}]}
```

Structured layers (`governance`, `model`, `identity`) validate on PUT the
way their consumers read them: `roles` through `roles_config.validate`
(never an action with no holder), `llm-settings` through
`llm_settings.validate`, `identity` needs organisation/short_mark/
product_line/synthetic_domain and a `#hex` palette, `pricing` non-negative
rates. A refused body is `400`, nothing written.

Audit actions: `profile.create`, `profile.describe`, `profile.delete`,
`profile.write` (target `<name>:<id>`), `profile.create_file`,
`profile.rollback`, `profile.revert`, `profile.import`. Exports are reads and
are not audited.

### Assets — project artifacts (`s7_delivery/product/assets.py`)

The eighth layer (2026-09-11). An **asset** is a file the *project* supplies
that is neither a prompt, a developer standard, nor something S7 generates
mechanically — a baseline schema, an OpenAPI contract, a document template,
a reference payload. Assets are published verbatim into every repository the
profile delivers to, under `.s7/assets/<dest>`, and listed in the team pack's
`AGENTS.md` so a coding agent knows they exist.

Four things separate assets from the other layers:

- **The body is the artifact, not a template.** Assets are not a variable
  layer: `{{...}}` inside one is the content's own templating syntax
  (Handlebars, Jinja, Liquid, a Flyway placeholder) and survives untouched.
  Rendering them would refuse a perfectly good Handlebars template at load
  for declaring no `variables:`.
- **`dest` is frontmatter.** Every asset declares where it publishes to,
  relative to `.s7/assets/`. It is validated on create *and* on load, so a
  hand-edited file cannot escape the managed root: no leading slash, no
  `..`, no backslash, at most four directories deep, and an extension. Two
  assets may not claim the same `dest`.
- **Text only, and credentials are refused.** A layer body is hashed,
  CRLF-normalised text; binaries are refused at the door (512 KB cap) rather
  than base64-smuggled through a mechanism that cannot diff them. A private
  key, cloud key or hard-coded secret is refused outright (hard rule 3);
  content that merely *looks* like personal data comes back as `warnings`,
  never a refusal — an operator's own schema legitimately mentions `email`.
- **The default set ships none.** `s7_delivery/layers/assets/` is empty, so a
  profile that supplies no assets publishes exactly what it published before
  the layer existed, and hard rule 5 is untouched.

| Method | Path | Notes |
|---|---|---|
| POST | `/api/admin/profiles/{name}/assets` | Author one. Body `{id, dest, title, summary, body, note, stage?}` → `201 {file, version, warnings}`. `400` on a bad `dest`, a credential, or the `default` profile. |
| POST | `/api/admin/profiles/{name}/assets/browse` | `{repository, ref?, subdir?}` → the repository's importable text files with `suggested_id`, `suggested_dest`, a preview, and `importable:false` + `reason` for binaries. Read-only: the clone is temporary. |
| POST | `/api/admin/profiles/{name}/assets/import` | `{repository, ref?, note?, files:[{path, id?, dest?, title?, summary?}]}` → `201 {created, warnings, files}`. Each file is re-read from a fresh clone. |

Both git routes honour the profile's Integrations layer (`integrations/
github.md`) exactly as `intake_connect_repo` does — host, allowed owners,
whether local paths are permitted. Audit actions: `profile.create_asset`,
`profile.browse_assets`, `profile.import_assets`.

**Import is a loader, not a link.** Imported files become ordinary asset
files versioned in the profile's ledger; nothing re-syncs afterwards. A
pinned artifact that silently followed someone else's `main` would defeat the
pinning every other layer depends on, so re-importing is an explicit,
versioned act.

**Publication.** `delivery_packs.render_asset_files()` lays them out under
`build/packs/<slug>/assets/` with an `assets-manifest.json`;
`publication.file_plan` carries them to `.s7/assets/**` and the manifest to
`.s7/shared/assets-manifest.json`. `.s7` is already a managed root, so the
foreign-content refusal and the never-a-default-branch check cover assets
unchanged. Asset ids are pinned on the pack like every other profile file, so
editing one marks the pack stale rather than silently changing the next
publish.

## Prompt sets — legacy alias, resolves profiles too (`s7_delivery/product/prompt_sets.py`, `factory/layers.py`)

These routes predate delivery profiles and stay as aliases over the same
files: `{set}` is resolved through `profiles.root_of`, so a delivery profile
opens here as well (its file routes edit the same overlay, copy-on-write
included, and `GET /prompt-sets/{profile}` returns the profile's summary with
the prompt-layer rows). `POST /prompt-sets` still creates a legacy full copy;
new configuration should be a profile. The playbook routes below resolve a
legacy set or the default only.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/prompt-sets` | | `[SetSummary]` |
| POST | `/prompt-sets` | `{name, cloned_from?="default", description?, note?}` | `SetSummary` (201) |
| GET | `/prompt-sets/{set}` | | `SetDetail` |
| PATCH | `/prompt-sets/{set}` | `{description}` | `SetSummary` |
| DELETE | `/prompt-sets/{set}` | | 204; `409` when a run names it or it is `default` |
| GET | `/prompt-sets/{set}/history` | | ledger lines, oldest first |
| GET | `/prompt-sets/{set}/files/{id}` | | `FileDetail` |
| PUT | `/prompt-sets/{set}/files/{id}` | `{body, note}` | `{"record": LedgerLine \| null, "unchanged": bool, "file": FileDetail}` |
| POST | `/prompt-sets/{set}/files` | `{layer, id, title, stage, summary, body, variables?: [str], note}` | `FileDetail` (201) |
| GET | `/prompt-sets/{set}/files/{id}/versions/{n}` | | `{"version": n, "body": str}`; `404` when no body recorded |
| GET | `/prompt-sets/{set}/files/{id}/diff?from=1&to=2` | | `{"from": 1, "to": 2, "diff": str}` (unified) |
| POST | `/prompt-sets/{set}/files/{id}/rollback` | `{to_version, note}` | same shape as PUT |
| GET | `/prompt-sets/{set}/workflows` | | `[WorkflowPreview]` |
| GET | `/prompt-sets/{set}/workflows/{workflow}` | | `WorkflowPreview` |

Shapes:

```
SetSummary   = prompt_sets.describe(name):
               {name, description, cloned_from, created_at, created_by, root,
                is_default, files, counts: {rules, skill, task, playbook},
                unrecorded: [id], versions: int}
SetDetail    = SetSummary + {"rules": [FileRow], "skills": [FileRow],
                "tasks": [FileRow], "playbooks": [FileRow],
                "workflows": [Workflow]}          # from layers.describe(root)
FileRow      = layers.describe(root) row: {id, layer, title, stage, summary, path,
                sha256, short, body, variables, version, recorded, recorded_at,
                workflows}
FileDetail   = FileRow + {"versions": [LedgerLine + {has_body}],
                "placeholders": [str],            # placeholders actually used
                "recordings_pinned": int}         # default set only: committed
                                                  # recordings whose system or
                                                  # prompt carries this body;
                                                  # 0 for custom sets
LedgerLine   = {recorded_at, id, layer, path, version, sha256, previous_sha256,
                author, note}
WorkflowPreview = Workflow + {"system_prompt": str,   # rules + skill(s) assembled
                  "tasks": [{id, title, variables, body}],
                  "llm": {<stage key>: {provider?, model?}}}
                  # effective settings keyed by stage key — one key for most
                  # workflows, three for development-lane (developer/tester/reviewer)
```

Rules for the editor: a task body may only use placeholders declared in the
file's `variables`; a playbook body must be JSON; every save needs a `note`.
Editing a file in the `default` set is allowed but the response's
`recordings_pinned` tells the UI to warn that those recordings will miss until
re-recorded (the repo's own test suite reports the same).

## LLM settings, recordings, cache (`s7_delivery/product/llm_settings.py`)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/llm` | | `llm_settings.describe()` — `{settings, stages: [{key,label,group,effective}], providers: [{provider, configured, needs, env_model}], environment, providers_available, modes}` |
| PUT | `/llm` | `{default: {provider?, model?}, stages: {key: {provider?, model?}}, llm_mode?: "live"\|"record"\|"replay"\|null}` | saved settings |
| GET | `/recordings` | | `{replay_dir, count, total_bytes, items: [{name, provider, model, lane, skill, prompt_head, size, modified_at}]}` |
| GET | `/cache` | | `{cache_dir, count, total_bytes}` — the ephemeral live cache |
| DELETE | `/cache` | | `{"removed": n}` — never touches committed recordings |

`lane` is the rules-file id whose body prefixes the recording's system prompt
(or `null`); `skill` the skill id whose body follows it, or opens the prompt
for the downstream lane.

## Roles and permissions (`s7_delivery/product/roles_config.py`, `factory/roles.py`)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/roles` | | `{roles: [{id, label, summary, signs, actions: [str], overridden: bool}], actions: [{action, group, roles: [id], default_roles: [id], overridden: bool}], overrides: RolesOverrides}` |
| PUT | `/roles` | `RolesOverrides = {permissions?: {action: [role id]}, profiles?: {role id: {label?, summary?, signs?}}}` | the same payload as GET |
| POST | `/roles/reset` | | GET payload with overrides cleared |

Validation: unknown action or role → 400; an action left with zero roles →
400 ("every action needs at least one holder"). Overrides are *complete
replacements* per action (the list given is the holder set). The engine's
`roles.require/allowed/permitted_roles/actions_for` consult the effective
table on every call, so a change applies to the next request with no restart.

`group` is the section comment in `PERMISSIONS`: intake, planning,
build_review, quality, release, governance, run.

## Users (`s7_delivery/product/users.py`)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/users` | | `[User]` |
| POST | `/users` | `{name, role, email?}` | `User` (201) |
| PATCH | `/users/{id}` | `{name?, email?, role?, active?}` | `User` |
| DELETE | `/users/{id}` | | 204 |

`User = {id, name, email, role, active, created_at}`; `id` is generated
(`u-<6 hex>`). The Control Centre exposes `GET /api/users` (active only) and
accepts `X-S7-User: <id>` on every request: the user's role becomes the acting
role and the user's name is recorded as the actor on approvals and activity
where a name is recorded. Role bodies keep working unchanged when the header
is absent.

## Runs (`s7_delivery/product/runs_admin.py`)

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/runs` | | `[{run_id, mode, entry_mode, prompt_set, profile: {name, kind}, status, created_at, stages: [{stage, status}], size_bytes, archived: false}]` — `profile.kind` is `default`, `profile`, `legacy-set`, or `missing` when the folder the run names is gone |
| GET | `/runs/archived` | | same rows with `archived: true, archive: "<dir name>"` |
| POST | `/runs/{id}/reset` | | run row |
| POST | `/runs/{id}/archive` | | `{archived_to: str}` — moves `artifacts/runs/<id>` under `artifacts/runs-archive-<YYYYMMDD>/` |
| GET | `/runs/{id}/self-healing` | | the run's self-healing view (`self_heal.view`): `{provenance, summary: {open, waiting_on_human, completed, failed}, stale_now: [id], changes: [change record + waiting_on, blocked_step, done_steps, events], playbooks}` — read-only; moved here from the Control Centre on 2026-09-03 |
| DELETE | `/runs/{id}` | | 204 |

Every action is audited with the actor.

## Repositories and the GitHub integration (`s7_delivery/product/repos_admin.py`, `integrations.py`)

Connecting a repository stays a per-run action in the Control Centre (Intake
→ connect by URL). The admin panel shows the **cross-run registry** those
reconnect chips read (`artifacts/known_repos.json`), joined with the runs
that name each repository, and the **GitHub integration layer** of a
profile — `integrations/github.md`, the seventh profile layer (added
2026-09-07): host, owner allowlist, whether local paths may be connected,
whether S7 may create repositories, the branch names publication refuses,
and the `gh` login expected. Credentials never live in configuration (hard
rule 3): publication, CI sync and repo creation use the `gh` CLI's own
login, and the panel reports only whether that login exists and who it is.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/repositories` | | `{provenance: "rule_based", registry_path, repositories: [{url, name, kind: https\|ssh\|local, host, owner, default_branch, ci_bootstrap_status, stack, in_registry, runs: [{run_id, mode, status, profile, ci_bootstrap_status, default_branch}], run_count, last_check: {at, reachable, detail} \| null, …registry fields}]}` — a repository a run names but the registry forgot appears with `in_registry: false`; `last_check` is the newest `repository.test` audit line for the url (derived on read, never stored twice), so a repository deleted on its host stays visibly *not found* after one probe |
| POST | `/repositories/forget` | `{url}` | 204; 404 when not in the registry. Runs keep their own record |
| POST | `/repositories/test` | `{url}` | `{url, reachable, default_branch, heads, error, checked_at, kind, host, owner, repo}` — an explicit operator probe: the profile's URL checks first (a disallowed owner is reported as policy, git never runs), then `git ls-remote --symref --heads`, no clone; audited `repository.test` |
| GET | `/integrations/github?profile=` | | `{provenance, profile, source: default\|override\|set, settings: {host, allowed_owners, allow_local_paths, allow_repo_creation, refuse_branch_names, expected_gh_login}, gh: {available, authenticated, login, host, error, expected_login, login_matches, checked_at}, consumers}` — 404 for an unknown profile |

The settings are edited like any other profile file
(`PUT /profiles/{name}/files/github`, validated by `integrations.validate`:
a body carrying a token, password or secret is refused). They are inputs to
checks the engine already makes and can only tighten them:
`Engine.intake_connect_repo` refuses a host, owner or local path the profile
does not allow before anything is cloned; `intake_create_new_app_repo`
refuses when `allow_repo_creation` is false; `publication.check_branch` adds
`refuse_branch_names` to the main/master refusal it always had.

## Audit

`GET /api/admin/audit?limit=200&action=` → newest first,
`[{at, actor, action, target, detail, before_sha256, after_sha256}]`.

Action names in use: `prompt_set.create`, `prompt_set.delete`,
`prompt_set.describe`, `prompt.write`, `prompt.create`, `prompt.rollback`,
`llm_settings.save`, `cache.clear`, `roles.save`, `roles.reset`,
`user.create`, `user.update`, `user.delete`, `run.reset`, `run.archive`,
`run.delete`.

## Playbooks (structured editing of the self-healing layer)

Playbooks are layer files (`playbooks/<change-type>.md`, JSON body) already
editable as raw text through the file routes; these routes edit them as
*steps*, validated against the engine's own catalogue
(`factory/self_heal.py`: `MECHANICAL_ACTIONS`, `GATE_ACTIONS`). A playbook's
id is the change type the engine looks up (`layers.playbook(change_type)`),
so ids are not renamed here.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/playbook-actions` | | `{"mechanical": [ActionInfo], "gate": [ActionInfo], "roles": [{id, label}], "change_types": [str]}` |
| GET | `/prompt-sets/{set}/playbooks` | | `[PlaybookDetail]` |
| GET | `/prompt-sets/{set}/playbooks/{id}` | | `PlaybookDetail` |
| PUT | `/prompt-sets/{set}/playbooks/{id}` | `{trigger?, stage?, steps: [Step], note}` | `{"record": LedgerLine \| null, "unchanged": bool, "playbook": PlaybookDetail}` |
| POST | `/prompt-sets/{set}/playbooks/{id}/validate` | `{steps: [Step]}` | `{"ok": bool, "problems": [str]}` — dry run, writes nothing |

```
ActionInfo     = {action, kind: "mechanical"|"gate", label, description,
                  default_role: role id | null,       # gate: who normally signs
                  permitted_roles: [role id]}         # gate: roles.permitted_roles(action)
Step           = {step_id, kind: "mechanical"|"gate", action, label,
                  detail?: str, role?: role id (gate only, required),
                  as_role?: role id (mechanical only, optional)}
PlaybookDetail = FileRow (layer "playbook", body = raw JSON text) +
                 {change_type, trigger, stage, steps: [Step],
                  versions: [LedgerLine + {has_body}],
                  usage: {"runs": n, "changes": n}}   # how many runs' self-healing
                                                      # records pin this playbook id
```

Validation (400 with every problem listed): `step_id` unique and kebab-case;
`kind` ∈ mechanical|gate; `action` must be in the catalogue for that kind; a
gate step needs a `role` that holds the action in the effective permission
table; `label` required; at least one step; the first step is normally
`assess_impact` (returned under `warnings`, not refused). Two mechanical
actions, `regenerate_delivery_packs` and `revalidate_stale_artifacts`,
**require** `as_role` (the engine runs them as that role and the permission
check is not caught), and that role must hold the underlying engine action
(`ActionInfo.engine_action`). `PlaybookDetail` also carries
`frontmatter_stage` (the file's own `stage:` line, distinct from the body's
`stage` the engine reads), and observability's `by_stage` rows carry the raw
telemetry `beat` beside the normalised `stage`. The PUT writes the body as
`json.dumps(indent=2)` through `layers.write_body` (so the ledger, snapshots,
diff and rollback all apply) and audits `playbook.write`.

## Observability (cross-run, derived on read, `RULE_BASED`)

`GET /api/admin/observability?days=30&prompt_set=` →

```json
{
  "provenance": "rule_based",
  "window": {"days": 30, "from": iso, "to": iso},
  "llm": {
    "source": ".cache/llm/telemetry.jsonl",          // LLM_TELEMETRY_PATH
    "calls": n, "live_calls": n, "cached_calls": n, "failed_calls": n,
    "cache_hit_ratio": 0.0-1.0 | null,                // cached_calls / calls
    "tokens": {"input": n|null, "output": n|null, "cache_read": n|null, "cache_write": n|null},
    "cache_read_ratio": float | null,                 // cache_read / (input + cache_read); null when unreported
    "by_stage":    [{"stage": beat, "calls", "cached", "failed", "avg_latency_s", "input_tokens", "output_tokens"}],
    "by_model":    [{"provider", "model", "calls", "cached", "input_tokens", "output_tokens"}],
    "by_day":      [{"day": "YYYY-MM-DD", "calls", "cached", "failed"}],
    "recent_failures": [{"ts", "stage", "provider", "model", "error"}]   // last 10
  },
  "runs": {"total": n, "by_mode": {...}, "by_prompt_set": {...}, "by_status": {...}},
  "gates": [{"gate": "G0".."G4", "passed": n, "blocked": n, "pending": n}],
  "self_healing": {
    "changes": n, "completed": n, "open": n, "failed": n,
    "by_change_type": [{"change_type", "count", "completed", "avg_steps_done"}],
    "by_playbook_version": [{"playbook_id", "version", "count"}],
    "gates_waiting": [{"role", "count"}]
  },
  "review": {"tasks_reviewed": n, "first_time_right": n, "first_time_right_ratio": float|null,
             "returned_to_development": n},
  "prompts": {"sets": n, "versions_recorded": n, "unrecorded_default": [id],
              "edits_last_window": n},                // ledger lines within the window, all sets
  "cost": {"value": null, "reason": "pricing table deliberately empty (CLAUDE.md § Metrics)"}
}
```

Every number is counted from files: the telemetry ledger, each run's
`run.json`, `activity.jsonl`, `approvals.jsonl`, gate records and
`governance/self_healing.json`, and the prompt sets' ledgers. `None`/`null`
means unmeasured, never zero. Nothing here is an AI claim.

## Correction learning (admin only; invisible to the Control Centre)

The engine appends a line to a run's `corrections.jsonl` whenever a person
edits model output (story fields, the extracted requirement, an
architecture proposal against the current document, a business rule the
analysis missed). Only the admin panel reads it (`product/corrections.py`);
the Control Centre's state payload never carries it. `product/improve.py`
turns corrections into a *proposed* new version of the skill or task that
produced the original, through one real model call, and an operator accepts
or rejects the proposal. No proposal is ever applied on its own.

| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/learning/overview?prompt_set=&days=` | | `{corrections: corrections.summary(), proposals: {proposed, accepted, rejected}, targets: [TargetRow]}` |
| GET | `/learning/corrections?prompt_set=&stage=&target_id=&days=&learnable_only=true` | | `[Correction]` newest first |
| GET | `/learning/corrections/{id}` | | `Correction` |
| GET | `/learning/proposals?prompt_set=&status=` | | `[Proposal + state]` newest first |
| POST | `/learning/proposals` | `{prompt_set, target_id, correction_ids?: [str], days?: int, learnable_only?: true, note?}` | `Proposal + state` (201); `502` when the model call fails or a replay recording is missing; `400` for nothing to learn from / a non-learnable target |
| GET | `/learning/proposals/{set}/{id}` | | `Proposal + state + {"diff": str}` |
| POST | `/learning/proposals/{set}/{id}/accept` | `{note}` | `Proposal + state`; `409` when the file changed since the proposal (stale) or the proposal is already decided |
| POST | `/learning/proposals/{set}/{id}/reject` | `{note}` | `Proposal + state` |

```
Correction = {correction_id, run_id, prompt_set, timestamp, stage, skill_id, skill,
              task_id, artifact_id, artifact_type, field, before, after,
              original_provenance, learnable: bool, author, source}
Proposal   = {proposal_id, prompt_set, target_id, target_layer, base_version,
              base_sha256, corrections: [id], revised_body, rationale, learned: [str],
              warnings: [str], provenance: "live_ai"|"replayed_ai", skill,
              llm: {provider, model, usage}, status: proposed|accepted|rejected,
              created_at, created_by, note, decided_at, decided_by, decision_note,
              resulting_version}
state      = improve.current_state(): {file_exists, stale, current_version,
              current_sha256, re_record: null | "re-recorded" | "awaiting re-record (LLM_MODE=record)"}
TargetRow  = {target_id, layer, stage, corrections_learnable, corrections_total,
              proposals_pending, last_correction, version}
```

When `correction_ids` is omitted the proposal uses every learnable
correction for the target in the window (newest first, capped at 40; values
over 4000 characters are truncated in the prompt and marked as such).
Corrections whose original was not model output (`simulated`, `rule_based`,
`human`) are `learnable: false` and excluded unless `learnable_only=false`
is passed explicitly — teaching a prompt to reproduce a seed is not learning.
The improver's own prompt is the `prompt-improve` skill and
`prompt-improve-task` template of the same set, editable like any other; its
provider/model is the `prompt-improve` stage key in LLM settings. Audit
actions: `prompt.propose`, `prompt.accept_proposal`, `prompt.reject_proposal`.

## Control Centre additions (same contract, other server)

- `POST /api/runs` accepts `prompt_set` (default `"default"`); `404`-style
  `400` for an unknown set. The run's state payload carries `prompt_set`.
  `profile` is accepted as an alias for the same field (a delivery profile
  name; wins when both are given) with the same `400` for an unknown name.
- `GET /api/profiles` → `{"profiles": [{name, kind, description}]}` — every
  delivery profile a new run may be created from, for the run-creation
  picker. Read-only; the editor is the admin app.
- `GET /api/users` and the `X-S7-User` header, as above.
- `GET /api/delivery-system` unchanged, plus a `tasks` list and `root`.
