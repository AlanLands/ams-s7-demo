# S7 Admin — the operator UI

The admin app (`apps/admin/web/`) is the browser surface over the admin API
in `docs/admin-api.md`. It is served by `apps/admin/server.py` on port
**8730** from the committed build in `apps/admin/web/dist/`, the same way the
Control Centre serves its own `dist/` — no CDN, self-hosted fonts, no runtime
network beyond `/api/admin/*` (hard rule 4, 2026-08-08 amendment).

## Run

```sh
# backend + built UI (fresh clone, no npm needed)
.venv/Scripts/uvicorn.exe apps.admin.server:app --host 127.0.0.1 --port 8730
# → http://127.0.0.1:8730/

# optional token gate: set S7_ADMIN_TOKEN before starting, paste the same
# value into the header's "Admin token" field (sent as X-Admin-Token)
```

Frontend development (Node 24 / npm 11, pinned versions in `package.json`):

```sh
cd apps/admin/web
npm install          # one-time
npm run dev          # http://127.0.0.1:5174, /api proxied to 127.0.0.1:8730
npm run build        # tsc -b && vite build → dist/  (commit dist/ with the change)
```

`dist/` is un-ignored in the root `.gitignore` (`!apps/admin/web/dist/`) for
the same reason as the Control Centre's: the built output is what the
locked-down environment runs. Any change under `src/` must be followed by
`npm run build` and the regenerated `dist/` committed in the same commit.

## Header

The header carries the brand, the API status pill (`/api/admin/health`:
reachable / token rejected 401 / unreachable) with a re-check button, and
one **identity control** — a button reading *Acting as \<name\>* with the
token state (*No token* / *Token set*) underneath. Clicking it opens a
popover with the two fields:

- **Acting as** — a free-text name, persisted in `localStorage`, sent as
  `X-Admin-User` on every request. It is the author on prompt ledger lines
  and the actor on audit rows. Defaults to `admin` server-side when blank.
- **Admin token** — optional, persisted, sent as `X-Admin-Token`, with a
  show/hide toggle. Only needed when the backend was started with
  `S7_ADMIN_TOKEN`.

Both apply to the next request as they are typed; the popover traps focus
and closes on Escape, Done, or a click outside.

## Pages

| Page | What it shows / does |
|---|---|
| Overview | Runs by mode, delivery-profile (or, on an older backend, prompt-set) and user counts, effective LLM mode/provider, a warning when the default profile has unrecorded files, the last 10 audit rows |
| Delivery Profiles | One row per profile — the committed default first, then overlay profiles, then any legacy full-copy prompt set — with a kind badge (*Default* / *Profile* / *Legacy copy*), the description (inline edit, profiles only), the **layer strip** (seven cells in a fixed order: prompts, standards, templates, governance, models, identity, integrations, each with its file count), overridden count, ledger lines, recorded state, the resolved-set fingerprint and created by/at. Actions: Open editor; a menu with Export as zip (overlay profiles only — fetched with the auth headers and handed to the browser as a download) and Delete (disabled for the default; behind an in-page confirm; a `409` — in use by a run — is shown inline). *New profile* takes a kebab-case name and a description and says what it makes: an overlay, nothing copied, the default showing through until a file is edited. *Import profile* takes the zip, an optional name and a *replace* checkbox; a `400`/`409` from the server is shown inside the dialog. The lead paragraph states the model once: one bundle, seven layers, overlay, versions |
| Profile Editor | Per profile (the nav's *Editor \<name\>* sub-item). Left: a filter box and seven collapsible groups in the fixed order — Prompts (sub-headed rules / skills / tasks / playbooks), Standards, Templates, Governance, Models, Identity, Integrations — each head showing its file count and, in red, how many are overridden here; every file carries its `vN` / `unrecorded` chip and a **source badge** (*default* shows through from the committed set, *overridden* is stored in this profile, *set* belongs to a legacy copy). Right, per file: layer, stage, source, an *enters model call* / *no model call* chip and the version; path, hash, recorded time, the consumers that read it and the workflows that use it; declared `{{variables}}` against the placeholders actually used (tasks); **locked tokens** as chips (green when present in the body, red when missing) with the sentence that they must stay — a save that drops one is refused client-side; the `CodeEditor`; for JSON layers (playbook, governance, model, identity, integration) the body is pretty-printed on load and validated client-side before Save enables; the required note beside *Save as vN+1*; and, when the file is an override, a **Revert to default** action behind an in-page confirm with its own note. The **Impact** card (from the file GET, refreshable) states the current pin, the consumers, whether the file enters a prompt and how many committed recordings hash the current text (a re-record warning when > 0), and the runs on this profile whose generated artifacts pinned this file — each artifact with its pinned `id@vN` and a stale/current chip. The shared Versions card (timeline, diff, view, rollback) runs on the profile routes. A banner lists unrecorded files. New file supports every layer, with a *Locked tokens* field. Workflow preview drawer as before |
| Playbooks | The self-healing layer edited as steps, per prompt set (default first, with the same committed-files warning as the editor). Left: playbooks with change type, stage, version chip and "used by n runs, n changes". Right: header (title, summary, trigger, stage), then the step rail — ordered cards with up/down reorder, step id (kebab-case, unique), a mechanical/gate toggle, an action select filtered by kind from `/playbook-actions` with the action's description underneath, label, detail, the recording role for gates (only roles that hold the action; `default_role` pre-selected) or an optional acting-as role for mechanical steps, remove with inline undo, and add-a-step by kind. Each card ends with the engine's own sentence (a gate "stops the playbook until \<role\> records \<action\>", a mechanical step "runs immediately when reached"). Validate calls the dry-run route and lists problems/warnings inline; note + Save (PUT, Ctrl/Cmd+S, unsaved indicator); a collapsible read-only raw JSON mirror; the shared Versions card (timeline, diff, rollback through the file route with the playbook id). A 404 from the routes shows a designed empty state, not an error |
| Correction Learning | Admin-only, invisible to the Control Centre: the loop where the product learns from people who corrected its output. Filters (prompt set, window 7/30/90/all, an *include non-learnable corrections* checkbox), five tiles (corrections, learnable, proposals pending / accepted / rejected), then **Learning targets** (the skill or task that produced each corrected original, with learnable/total counts, last correction, version chip, pending proposals and a per-row *Propose revision* — disabled with a tooltip when nothing is learnable), **Corrections** (newest first, stage/target filters, row checkboxes, an expandable before/after pair, *Propose from selected*) and **Proposals** (status, provenance, versions, stale / re-record chips, a review drawer with rationale, lessons, warnings, corrections used, the unified diff and Accept / Reject behind in-page confirms). See § Correction learning below |
| LLM Settings | Default provider/model, per-stage overrides grouped intake / planning / build_review / legacy with the effective value, mode override (blank = environment), provider status (boolean chips, never a value), environment summary. A `400` is shown inline |
| Recordings & Cache | Committed replay recordings table (read-only here — never deleted from this app), ephemeral cache stats with Clear behind an in-page confirm |
| Roles & Permissions | Action × role checkbox matrix grouped by phase (two-line role headers with the summary on hover, sticky header row and first column, full-width group bands), rows that differ from the built-in table highlighted with an *Overridden* or *Unsaved* chip; role profile cards (label / summary / signs); Save sends every action's holder list; Reset to defaults behind a confirm; "every action needs at least one holder" is enforced client-side and the server's `400` shown inline if it disagrees |
| Users | Table, add form, inline edit (name / email / role / active), activate / deactivate / delete behind a per-row menu, delete confirmed in-page. These are the people the Control Centre's role picker offers as "Act as …" |
| Runs | Active runs (mode, entry mode, the **profile** it resolves against with its kind badge, status, size, stage chips) with Reset / Archive / Delete in a per-row menu, each behind an in-page confirm; archived runs list. Each row also carries a **Self-healing** column: an icon button (also in the menu) opens a read-only `DetailDrawer` over `GET /runs/{id}/self-healing`, fetched only when the drawer opens so the list never pays for it, and the row shows the fetched open / waiting / failed counts afterwards. The drawer: a `RULE_BASED` chip and a Refresh, four tiles (open, waiting on a human, completed, failed), stale-now chips, then one card per change newest first â€” type and status badge (*waiting on \<role\>* for a blocked gate), the reason as a quote, initiator, trigger artifact @ version, the pinned playbook@version as a link that opens that playbook on the Playbooks page (in the run's prompt set), impact chips, progress, a step rail (ink circle-dot for mechanical, amber octagon for gates; green tick / red cross once done or failed; the blocked gate reads *Waiting on \<Role\> to record \<action\> in the Control Centre*; detail, outcome, time and provenance under each) and the change's activity events as a compact list. A run with no changes shows the designed empty state plus the playbooks it would follow. Nothing here signs, advances or retries: the helper text says gates are signed in the Control Centre by the named role and this view observes them |
| Repositories | The cross-run **known-repositories registry** (`artifacts/known_repos.json`, what the Control Centre's reconnect chips read) joined with the runs that use each repository, plus the **GitHub integration** as a profile resolves it and the gh CLI's own login status. A profile picker, the effective settings as read-only rows, a source badge, *Check gh*, *Edit in profile editor* (opens `integrations/github` in the editor), then the table with *Test connection* (`git ls-remote`, result inline) and *Forget* (in-page confirm; disabled for run-only rows). See § Repositories below |
| Observability | Cross-run figures from `/observability`, window 7/30/90 days and a prompt-set filter in one row above everything. Sections: LLM calls (stat tiles — calls, live/cached, failed, cache-hit ratio, cache-read ratio; stacked columns by day live/cached/failed with hover and keyboard focus per column and a table twin; by-stage and by-model tables; recent failures), Runs (by mode / prompt set / status as single-hue bar rows), Gates (one passed/pending/blocked bar per gate with the counts as text), Self-healing (open/completed/failed, by change type, by playbook version, gates waiting by role), Independent review (first-time-right ratio and counts), Prompts (sets, versions recorded, edits in window, unrecorded default files) and Cost (the honest "not measured — pricing table deliberately empty" card). The page header says once that everything is counted from files · `RULE_BASED`; a null renders as *unreported* / *not measured*, never 0. A 404 shows a designed empty state |
| Audit | `config/audit.jsonl` newest first, filter by action, limit |

The app never calls `window.confirm/alert/prompt`; every destructive action
confirms in-page, next to the row it acts on. Every `{detail}` error lands in
a blocking popup titled by status (validation / state / not found / auth).

Honesty rule carried over from the Control Centre: nothing here is an AI
output and nothing is badged as one. Version chips, `RULE_BASED`-style
derivations and counts are all file-derived.

## UI conventions

The 2026-09-03 quality pass applied one set of rules across every page.
They live in `src/theme.css` (tokens and component classes) and
`src/components/ui.tsx` (the components that enforce them); a new page
should compose those rather than add its own.

1. **Contrast.** Body text is warm near-black (`--ink #2a2924`); secondary
   text is never lighter than `--muted #6b6560` (≥ 5:1 on cream and white).
   Every badge tone pairs a dark text colour with a pale fill and a border,
   so chips stay readable; disabled controls keep their text and drop to
   50 % opacity with `cursor: not-allowed`.
2. **Type scale.** One scale — 12 / 13 / 14 / 16 / 20 / 26 px, body 14 px,
   line-height 1.5. Page title 26 px > section title 20 px > card title 16 px
   > table header 12 px. Uppercase tracking is used only for table headers
   and the sidebar's section eyebrows. Monospace is reserved for ids, paths,
   hashes, prompt bodies and diffs.
3. **Spacing and layout.** An 8 px scale (4 / 8 / 12 / 16 / 24 / 32); cards
   pad 24 px (compact 16 px); sections are 32 px apart. Content is centred at
   a 1320 px maximum with fluid gutters; the sidebar is 240 px, set in ink
   with a crimson rail on the active item and eyebrows per group.
4. **Header.** Brand, status pill, re-check button and the identity control;
   the actor and token fields live in the identity popover, not in the bar.
5. **Tables.** `TableWrap` gives every table a sticky header row inside a
   scroll box (so wide tables scroll within their card and the page never
   scrolls sideways), row hover, right-aligned numeric columns (`.num`),
   truncation with title tooltips for paths, hashes and prompt heads, and
   one compact actions cell per record — a primary button plus a kebab
   `ActionMenu`, never a stack of buttons. Empty states are a sentence and,
   where one applies, a primary action.
6. **Forms.** `Field` puts the label above the control, helper text below,
   errors in red with an icon, a `*` for required and *(optional)* where
   useful. Controls are 36 px tall (32 px small), 2 px corners; every
   interactive element has a visible focus ring; hit targets are ≥ 32 px.
   One primary button per view; secondary for the rest; danger (outline)
   for destructive triggers; solid danger only on the confirm itself.
7. **Profile editor.** Filterable file list in seven collapsible groups with
   per-group counts; a `CodeEditor` (`components/CodeEditor.tsx`) with soft
   wrap by default, a line-number gutter when wrap is off, a resize handle,
   an unsaved indicator, line/char counts and Ctrl/Cmd+S; the note sits
   beside Save. Every file shows a **source badge** — *default* (neutral),
   *overridden* (accent), *set* (info) — and the same badge sits in the
   rail so the overlay is legible without opening a file. **Locked
   tokens** are chips that turn red when the body no longer contains them,
   and Save stays disabled until they are back; JSON layers are
   pretty-printed on load and Save stays disabled while the body does not
   parse. The recordings-pinned warning is a `Notice` above the body and
   is only shown for files that enter a model call. **Impact** is a card
   under the editor, never a modal: it is read from the file GET and
   refreshed after every save, rollback or revert. **Revert to default**
   appears only on an override, as a danger-outline trigger inside the
   *Overridden in this profile* notice, and confirms in-page with a
   required note. Versions are a timeline; the diff carries +/− glyphs and
   a left border as well as colour; rollback, compare and view each open in
   their own sub-panel.
8. **Roles matrix.** Two-line role headers (full label and summary on
   hover), sticky header and first column, full-width group bands, and an
   *Overridden* / *Unsaved* chip on rows that differ from the built-in
   table. Checkboxes are native, keyboard-operable and focus-visible.
9. **Feedback.** Toast on success; `Notice` panels for inline 400 / 409
   detail and unsaved-changes reminders; a spinner in the button and the
   busy overlay during requests; the page header renders before data so
   loading does not shift the layout.
10. **Accessibility.** `header` / `nav` / `main` landmarks, a skip link,
    `aria-current` on the active nav item, labelled icon buttons, focus
    trapped in modals, drawers, popovers and confirm panels with Escape to
    close and focus restored afterwards, `prefers-reduced-motion` honoured,
    and colour never the only signal (icons on notices, glyphs on diffs,
    text on badges).
11. **Responsive.** Usable down to 1024 px: the sidebar collapses to an icon
    rail below 1200 px, grids stack below 1024 px, the editor stacks below
    900 px, and tables scroll inside their card.
12. **Consistency.** One `Badge` (neutral / info / success / warning /
    danger / accent), one `Card`, one `TableWrap`, one `PageHeader`
    (title, description, right-aligned actions), one `Button`, one `Field`,
    one `Notice`, one `ConfirmPanel`, one `ActionMenu` — used by every page.
    The version ledger (timeline, diff, view, rollback) is one
    `VersionsCard` in `components/Versions.tsx`, shared by the profile
    editor and the playbook editor — it takes a `LedgerClient` so the same
    card runs on the profile routes and the prompt-set routes.
13. **Charts.** Inline SVG and CSS bars only — no chart library. Marks are
    thin (columns ≤ 24 px, 4 px rounded data-end, a 2 px surface gap between
    stacked segments), gridlines are solid hairlines, and text never wears
    the series colour. The chart hues are the MapleSure families stepped up
    to pass the colour checks (`--viz-*` tokens in `theme.css`: live blue,
    cached green, failed / blocked crimson, pending amber, single-hue blue
    for one-measure bars) — the UI tokens are too muted to carry identity in
    a mark. Every chart has a legend when it carries more than one series,
    the values as text beside the marks, a keyboard-focusable hover target
    with the same tooltip as the mouse, and a table twin. A null renders as
    a word (*unreported*, *not measured*), never as 0.

## Correction learning

`src/pages/Learning.tsx` is the UI over docs/admin-api.md § Correction
learning. Three honesty rules shape it, and every piece of copy on the page
repeats one of them: corrections are **recorded by the engine** when someone
edits model output in the Control Centre (a story, the extracted
requirement, an architecture proposal, a business rule the analysis missed)
— nothing is typed here; a proposal is **one real model call** through the
`prompt-improve` stage and is badged `LIVE_AI` or `REPLAYED_AI`, never
anything else (any other value renders as a red badge, because it would be
a contract breach, not a third kind); and **nothing is applied until an
operator accepts it**, which records a version through the ordinary ledger.

- **Filters.** Prompt set (default first), window (7 / 30 / 90 / all) and
  the *Include non-learnable corrections* checkbox with its helper text.
  Corrections of `simulated`, `rule_based` or `human` originals are shown
  with a neutral badge reading *not learnable*; model originals read as an
  info badge. The toggle is sent as `learnable_only=false` on both the
  corrections list and the proposal request.
- **Learning targets.** One row per skill/task the corrections point at.
  The card opens with the effective mode / provider / model for the
  `prompt-improve` stage (from `/llm`, resolved stage → default →
  environment) and a sentence per mode: a live call, a recorded call, or a
  replay that fails loudly. *Propose revision* opens an in-page
  `ConfirmPanel` (optional note); a `502` (model call failed, replay
  recording missing) or `400` (nothing to learn from) lands inline in that
  panel, not in the popup. Success toasts, reloads and opens the drawer.
- **Corrections.** Newest first, with stage and target filters. Each row
  expands (a keyboard-operable button with `aria-expanded`) into the
  before/after pair — *What the model wrote* with a crimson rule, *What
  \<author\> changed it to* with a green one; non-strings are pretty JSON,
  values over 480 characters fold behind *Show all*. Row checkboxes feed a
  selection bar whose target select lists only the skills/tasks every
  selected correction shares, since a proposal rewrites one file.
- **Proposals.** Id, target, status (proposed = warning, accepted =
  success, rejected = neutral), provenance, proposed by / at, `v<base> →
  v<result>`, a *stale* chip when the file changed underneath the proposal
  and the re-record chip after acceptance (*re-recorded* / *awaiting
  re-record (LLM_MODE=record)*). The drawer shows rationale, lessons,
  warnings, the corrections used (each a link that filters and highlights
  the corrections table), the server's unified diff through the shared
  `DiffView`, model / provider / token usage (*unreported* where the
  provider said nothing), and Accept (primary, disabled when stale) /
  Reject behind `ConfirmPanel`s with a required note. A `409` (stale or
  already decided) is shown inline with a *Propose again* action.
- **Overview and audit.** The Overview page carries a *Correction learning*
  card (corrections total / learnable, proposals pending, decided) linking
  here; the audit filter lists `prompt.propose`, `prompt.accept_proposal`
  and `prompt.reject_proposal`.
- **Empty states.** No corrections: explains where they come from. Some
  corrections but none learnable: says so and points at the toggle. A 404
  from `/learning/overview` shows the designed not-available state.

## Where things live

```
apps/admin/web/
  index.html, vite.config.ts (port 5174, proxy → 8730), tsconfig*.json
  public/favicon.svg, public/fonts/*.woff2      # copied from the Control Centre
  src/theme.css        # same design tokens as apps/control/web/src/theme.css
  src/api.ts           # typed client, one function per docs/admin-api.md route;
                       # X-Admin-User / X-Admin-Token headers; ApiError{status}
  src/types.ts         # the contract's shapes
  src/hooks.tsx        # useLoad (loading / error / reload) + LoadError
  src/state/AdminContext.tsx   # section, actor, token, health, toast, error popup, busy
  src/components/{Header,SideNav,ui}.tsx   # ui.tsx = PageHeader, Card, TableWrap, Badge,
                                           # Button, Field, Notice, ActionMenu, Modal,
                                           # DetailDrawer, ConfirmPanel, Toast, ErrorPopup…
  src/components/Versions.tsx              # VersionChip, DiffView, VersionsCard (shared ledger UI)
  src/components/CodeEditor.tsx            # CodeEditor, usedPlaceholders, missingLocked
  src/pages/{Overview,Profiles,ProfileEditor,Playbooks,Learning,LlmSettings,Recordings,Roles,Users,Runs,
             Repositories,Observability,Audit}.tsx   # Profiles.tsx also exports KindBadge, LayerStrip, GROUP_ORDER
  src/pages/RunSelfHealing.tsx             # SelfHealingDrawer + HealSummaryChips (Runs page)
  dist/                # committed build, served by apps/admin/server.py
```

## Control Centre side

Self-healing moved here on 2026-09-03: it is operator territory, so the
Control Centre's Governance â†’ Self-Healing page is gone (page, nav row and
its types removed; `state.self_healing` still arrives in the run payload and
is simply not rendered there). The Runs drawer above and the Playbooks page
are now the only surfaces for it.

Two additions in `apps/control/web/` consume the same configuration plane:

- The header role picker lists **Act as \<name\> · \<role\>** entries from
  `GET /api/users` above the plain roles. Choosing a person sets the acting
  role to theirs and stores the id so `api.ts` sends `X-S7-User: <id>` on
  every request; choosing a plain role clears it. With no users defined the
  picker is exactly as before.
- Settings → new-run form has a **prompt set** selector fed by
  `GET /api/prompt-sets`, sent as `prompt_set` on `POST /api/runs`; the run
  summary shows the run's `prompt_set` when the state payload carries it.
  Since 2026-09-07 that name is a delivery profile — the same string names
  both, and the admin Runs page shows it under *Profile* with its kind.

## Repositories

Added 2026-09-07, under Operations before Observability. Repositories are
connected **per run** in the Control Centre (Intake page), where a run
clones them and grounds analysis on them; the admin page is the cross-run
view, `api.repositories.*` and `api.integrations.github` in `src/api.ts`
over `/api/admin/repositories*` and `/api/admin/integrations/github`, shapes
`RepoRow`, `RepoTestResult` and `GithubIntegration` in `src/types.ts`.

- **GitHub integration card.** A profile picker (from the profiles list,
  `default` preselected) drives `GET /integrations/github?profile=`. The
  effective settings render as read-only rows — host, allowed owners (or
  *any owner on \<host\>*), local paths allowed / refused, repo creation
  allowed / refused, refused branch names, expected login — with the same
  **source badge** the editor uses (*default* / *overridden* / *set*) and
  the consumers that read the file. The **gh status** line says whether the
  CLI is on PATH, whether it is authenticated and as whom, and, when the
  profile names an `expected_gh_login`, whether the login matches (a warning
  chip when it does not). *Check gh* re-reads; *Edit in profile editor*
  opens that profile with `integrations/github` preselected
  (`openEditor(name, fileId)` in `AdminContext`, honoured once by the
  editor and cleared). No token is ever requested, sent or shown — the
  card's copy says so, and the server's validator refuses a body that
  carries one.
- **Known repositories table.** One row per repository, newest first as
  the registry keeps them: name with the URL in monospace beneath (and the
  registry's `head` / `cloned` when present), kind chip (https / ssh /
  local path) with host/owner, default branch, stack with a **bootstrap
  badge** (`bootstrapped:<stack>` green, `push_failed` red,
  `unsupported_stack` amber, empty = *not bootstrapped*), a runs count that
  expands into the run ids with mode, profile, status, branch and the run's
  own bootstrap record, and an *in registry* / *run only* chip — a run-only
  row is one a run still names but the registry forgot, so it is not
  offered as a reconnect chip — and a **Status** column: the newest
  audited probe (`last_check`) as *reachable*, *not found* (the host
  reports the repository gone: deleted, renamed or made private) or *not
  reachable*, with when it was checked; *not checked* when never probed.
  Actions: **Test connection** posts to `/repositories/test`, shows the
  result inline (reachable with default branch and head count, or the
  error the server reported — a disallowed owner is reported as such, not
  as unreachable) and reloads the table so the Status column reflects it;
  **Forget** (in the row menu, disabled for run-only rows — the tooltip
  names the runs holding the repository; archiving or deleting those runs
  drops the row) confirms in-page and posts `/repositories/forget`; a
  `404` lands in the popup. The registry path is
  shown as a hint under the table; the section carries the payload's
  `RULE_BASED` provenance chip. Empty state when nothing was ever connected;
  a `404` from the integration route shows a designed not-available state
  inside the card.
- **Overview.** When the overview payload carries `repositories`
  (`{count, run_only}`) a *Known repositories* stat card is added; an
  older backend without it shows nothing new.

## Delivery profiles

Added 2026-09-07 (design: `docs/design-history/plans/2026-09-07-delivery-
profiles.md`). The *Prompt Sets* and *Prompt Editor* pages became
*Delivery Profiles* and *Profile Editor*; a stored section choice of the
old names maps onto the new ones. A seventh layer group, **Integrations** (layer kind `integration`,
JSON-bodied like governance / model / identity, one default file `github`),
joined the fixed order on 2026-09-07: it appears as the last cell of the
layer strip, the last group of the editor's rail, the last entry of the
New-file layer picker, and the `integrations` key of a profile's `counts`.
The Repositories page reads it; the editor edits it. The client is `api.profiles.*` in
`src/api.ts`, one function per `/api/admin/profiles/*` route; the shapes
are `ProfileSummary`, `ProfileDetail`, `ProfileFileRow`, `ProfileFileDetail`,
`Impact` and `ProfileSaveResult` in `src/types.ts`. Three copy rules hold on
both pages: an overlay is described as *nothing copied, the default shows
through*; nothing is ever badged as AI output — source, version, impact and
fingerprint are all file-derived; and a refusal (`400`/`409`) lands next to
the control that caused it, never only in the popup. The Playbooks,
Correction Learning, LLM Settings and Recordings pages are unchanged and
keep working on the same files.
