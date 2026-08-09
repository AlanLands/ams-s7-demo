# Build & Review — Overview page redesign

**Date:** 2026-08-09 · **Status:** approved by user (mockup-driven)

## Goal

Rebuild `apps/control/web/src/pages/build/BuildOverview.tsx` as the control
tower for post-planning execution, matching the approved mockup: icon stat
cards, a richer team progress table, Recent Activity and Top Blockers panels,
and four compact readiness cards with drill-in links. No backend changes.

## Constraints

- Hard rule 4 (amended): pinned deps only, no CDN/runtime fetch. Icons come
  from `lucide-react`, pinned in `package-lock.json`, tree-shaken into the
  committed `dist/`. `npm run build` + regenerated `dist/` land in the same
  commit as any `src/` change.
- Staged-output honesty: every displayed value is either real run state or a
  **stated derivation rule** written next to the code. Nothing pretends to be
  live git/CI when it is simulated.

## Components

### 1. Stat card row (6 cards)

New shared `StatCard` component (icon tile + big value + label + sub-line),
colored per mockup. Data from `build.summary.totals`, `build.workspaces`:

| Card | Value | Sub-line | Accent |
|---|---|---|---|
| Workspaces | count | "Ready" when all `artifact_status === 'current'` | green |
| Stories | `totals.total` | "Total" | blue |
| In Development | `totals.in_progress` | % of total | orange |
| Testing | stories with `tests_total > 0` | % of total | purple |
| In Review | stories with `review === 'passed'` | % of total | violet |
| Blocked | `totals.blocked` | % of total | red |

The mockup's duplicated "In Review" card is read as a mockup glitch — one card.
Percentages are real arithmetic over the summary; zero states render 0%, not
blanks.

### 2. Delivery Progress by Team

Same grouping as today (`groupByTeam` over `summary.stories`), restyled:

- Team chip (existing `TeamChip`), story count.
- **Workspace / Repo**: GitHub mark icon + repository name from the team's
  delivery pack.
- **Development / Testing / Review**: icon + word (Complete / In Progress /
  Running / Waiting / Passed / Pending / Failing / Blocked) using the existing
  worst-state helpers.
- **Status**: chip *On Track* / *At Risk*. Rule: a team is At Risk iff any of
  its stories is `blocked` or `stale`; otherwise On Track.
- **Dependencies**: count of dependency edges from the plan's stories for that
  team (story `dependencies` arrays), replacing the blocked-ID list.
- Footer link "View all teams →" → `build_summary`.

### 3. Right rail

- **Recent Activity**: `data.activity` filtered to `build_review`, latest 6;
  each row = time (hh:mm), small event icon, one-line text, team chip when the
  entry names a team. "View all activity" → `activity` page.
- **Top Blockers**: from `summary.blockers` (top 3); story-id chip, team +
  reason, severity chip derived by stated rule — review-blocked ⇒ Critical,
  dependency-wait ⇒ High, stale ⇒ Medium. Row click → Independent Review with
  the story selected. "View all blockers" → `independent_review`.
- Next-action button and `GuidanceCard` remain in the rail.

### 4. Bottom readiness cards (4)

- **Architecture**: status badge + `v<N>`; link → `architecture`.
- **Git Integration**: from `build.publications` — `CONNECTED` only when a
  non-simulated publication exists; `SIMULATED` badge when publications are
  simulated; `NOT PUBLISHED` otherwise. Link → `delivery_packs`.
- **Delivery Packs**: `published/total` + "Ready" when all published; link →
  `delivery_packs`.
- **Quality Ready**: count of `ready` rows in `build.quality_handoff`; link →
  `quality`.

### 5. Kept from the current page

Phase rail card, honest next-action derivation, `OwnershipChips`, control-plane
guidance card, empty states ("opens when the plan is signed at Gate 1").

## Where code lives

- Derivation rules (At Risk, severity, testing/review counts, git integration
  state) in `buildHelpers.tsx`, each with the rule stated in a comment.
- `StatCard` and icon usage shared so the other Build pages can adopt the same
  visual language later.
- New CSS in `theme.css` using existing tokens; both themes supported.

## Testing

- Frontend has no test harness; verification is `npm run build` (type check +
  bundle) plus live Chrome MCP walkthrough of the page against a demo run —
  per the user's standing preference for verifying each UI step live.
- Python tests untouched (no backend change); run pytest to confirm.
