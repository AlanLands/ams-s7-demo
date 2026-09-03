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
| Overview | Runs by mode, prompt-set and user counts, effective LLM mode/provider, a warning when the default set has unrecorded files, the last 10 audit rows |
| Prompt Sets | List (files, versions, unrecorded, default badge); create by cloning (name validated kebab-case client-side); edit description inline; delete behind an in-page confirm — a `409` (set in use / default) is shown inline |
| Prompt Editor | Per set. Left: a filter box and files grouped rules / skills / tasks / playbooks with per-layer counts and `vN` or `unrecorded` chips. Right: metadata, declared `{{variables}}` vs placeholders actually used (tasks), a monospace editor with soft wrap (default) or a line-number gutter, a resize handle, an unsaved-changes indicator, line/char counts and Ctrl/Cmd+S; the required note sits next to Save (which reports "unchanged" when the server says so). Default set shows `recordings_pinned` ("N committed recordings hash this text"). Versions panel: a timeline newest first (author, note, time, hash), pick two → unified diff with +/− glyphs and a coloured left border, view a version's body, roll back in its own panel with a note. New file form. Workflow preview drawer: assembled system prompt, task templates, effective provider/model |
| Playbooks | The self-healing layer edited as steps, per prompt set (default first, with the same committed-files warning as the editor). Left: playbooks with change type, stage, version chip and "used by n runs, n changes". Right: header (title, summary, trigger, stage), then the step rail — ordered cards with up/down reorder, step id (kebab-case, unique), a mechanical/gate toggle, an action select filtered by kind from `/playbook-actions` with the action's description underneath, label, detail, the recording role for gates (only roles that hold the action; `default_role` pre-selected) or an optional acting-as role for mechanical steps, remove with inline undo, and add-a-step by kind. Each card ends with the engine's own sentence (a gate "stops the playbook until \<role\> records \<action\>", a mechanical step "runs immediately when reached"). Validate calls the dry-run route and lists problems/warnings inline; note + Save (PUT, Ctrl/Cmd+S, unsaved indicator); a collapsible read-only raw JSON mirror; the shared Versions card (timeline, diff, rollback through the file route with the playbook id). A 404 from the routes shows a designed empty state, not an error |
| Correction Learning | Admin-only, invisible to the Control Centre: the loop where the product learns from people who corrected its output. Filters (prompt set, window 7/30/90/all, an *include non-learnable corrections* checkbox), five tiles (corrections, learnable, proposals pending / accepted / rejected), then **Learning targets** (the skill or task that produced each corrected original, with learnable/total counts, last correction, version chip, pending proposals and a per-row *Propose revision* — disabled with a tooltip when nothing is learnable), **Corrections** (newest first, stage/target filters, row checkboxes, an expandable before/after pair, *Propose from selected*) and **Proposals** (status, provenance, versions, stale / re-record chips, a review drawer with rationale, lessons, warnings, corrections used, the unified diff and Accept / Reject behind in-page confirms). See § Correction learning below |
| LLM Settings | Default provider/model, per-stage overrides grouped intake / planning / build_review / legacy with the effective value, mode override (blank = environment), provider status (boolean chips, never a value), environment summary. A `400` is shown inline |
| Recordings & Cache | Committed replay recordings table (read-only here — never deleted from this app), ephemeral cache stats with Clear behind an in-page confirm |
| Roles & Permissions | Action × role checkbox matrix grouped by phase (two-line role headers with the summary on hover, sticky header row and first column, full-width group bands), rows that differ from the built-in table highlighted with an *Overridden* or *Unsaved* chip; role profile cards (label / summary / signs); Save sends every action's holder list; Reset to defaults behind a confirm; "every action needs at least one holder" is enforced client-side and the server's `400` shown inline if it disagrees |
| Users | Table, add form, inline edit (name / email / role / active), activate / deactivate / delete behind a per-row menu, delete confirmed in-page. These are the people the Control Centre's role picker offers as "Act as …" |
| Runs | Active runs (mode, entry mode, prompt set, status, size, stage chips) with Reset / Archive / Delete in a per-row menu, each behind an in-page confirm; archived runs list. Each row also carries a **Self-healing** column: an icon button (also in the menu) opens a read-only `DetailDrawer` over `GET /runs/{id}/self-healing`, fetched only when the drawer opens so the list never pays for it, and the row shows the fetched open / waiting / failed counts afterwards. The drawer: a `RULE_BASED` chip and a Refresh, four tiles (open, waiting on a human, completed, failed), stale-now chips, then one card per change newest first â€” type and status badge (*waiting on \<role\>* for a blocked gate), the reason as a quote, initiator, trigger artifact @ version, the pinned playbook@version as a link that opens that playbook on the Playbooks page (in the run's prompt set), impact chips, progress, a step rail (ink circle-dot for mechanical, amber octagon for gates; green tick / red cross once done or failed; the blocked gate reads *Waiting on \<Role\> to record \<action\> in the Control Centre*; detail, outcome, time and provenance under each) and the change's activity events as a compact list. A run with no changes shows the designed empty state plus the playbooks it would follow. Nothing here signs, advances or retries: the helper text says gates are signed in the Control Centre by the named role and this view observes them |
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
7. **Prompt editor.** Filterable file list with per-layer counts; a
   `CodeEditor` with soft wrap by default, a line-number gutter when wrap
   is off, a resize handle, an unsaved indicator, line/char counts and
   Ctrl/Cmd+S; the note sits beside Save. The recordings-pinned warning is
   a `Notice` above the body. Versions are a timeline; the diff carries +/−
   glyphs and a left border as well as colour; rollback, compare and view
   each open in their own sub-panel.
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
    `VersionsCard` in `components/Versions.tsx`, shared by the prompt editor
    and the playbook editor.
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
  src/pages/{Overview,PromptSets,PromptEditor,Playbooks,Learning,LlmSettings,Recordings,Roles,Users,Runs,
             Observability,Audit}.tsx
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
