# Build & Review Overview Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the Build & Review Overview page (`BuildOverview.tsx`) as the mockup-matching control tower: icon stat cards, richer team table with On Track/At Risk chips, Recent Activity + Top Blockers rail, and four readiness cards.

**Architecture:** Frontend-only. All new values are either real run state or rule-based derivations that live in `buildHelpers.tsx` with the rule stated in a comment. Icons come from `lucide-react`, pinned exact, tree-shaken into the committed `dist/`. No backend or Python changes.

**Tech Stack:** React 19 + TypeScript + Vite (existing), lucide-react (new, pinned).

**Spec:** `docs/superpowers/specs/2026-08-09-build-overview-redesign-design.md`

## Global Constraints

- Hard rule 4 (amended): every commit that touches `apps/control/web/src/` must run `npm run build` and include the regenerated `apps/control/web/dist/` **in the same commit**.
- No CDN, no runtime fetch, no new fonts. `lucide-react` is installed with `--save-exact` so `package.json` + `package-lock.json` pin it.
- Staged-output honesty: the Git Integration card must never say `CONNECTED` when publications are simulated — it says `SIMULATED`.
- The frontend has **no test harness**; verification per task is `npm run build` (runs `tsc -b`, which is the type check) and, at the end, a live Chrome walkthrough (user's standing preference: verify UI steps live). Python tests must stay green: `python -m pytest -q` from repo root.
- Working directory for npm commands: `apps/control/web/`.

---

### Task 1: Pinned lucide-react + `StatCard` component + CSS

**Files:**
- Modify: `apps/control/web/package.json`, `apps/control/web/package-lock.json` (via npm)
- Create: `apps/control/web/src/components/StatCard.tsx`
- Modify: `apps/control/web/src/theme.css` (append at end)

**Interfaces:**
- Consumes: nothing new.
- Produces: `StatCard({ icon, value, label, sub, accent }: { icon: ReactNode; value: string; label: string; sub?: string; accent: 'green' | 'blue' | 'orange' | 'purple' | 'violet' | 'red' })` — a named export. CSS classes `.stat-row`, `.stat-card`, `.sc-<accent>`, `.risk-chip.on_track|.at_risk`, `.sev-chip.critical|.high|.medium`, `.cell-status`, `.readiness-row`, `.readiness-card`, `.rail-link`.

- [ ] **Step 1: Install lucide-react (pinned)**

```bash
cd apps/control/web && npm install --save-exact lucide-react@0.545.0
```

Expected: `package.json` gains `"lucide-react": "0.545.0"` (no caret).

- [ ] **Step 2: Create `StatCard.tsx`**

```tsx
import type { ReactNode } from 'react'

/** Mockup-style metric card: colored icon tile, big value, label, sub-line. */
export function StatCard({ icon, value, label, sub, accent }: {
  icon: ReactNode
  value: string
  label: string
  sub?: string
  accent: 'green' | 'blue' | 'orange' | 'purple' | 'violet' | 'red'
}) {
  return (
    <div className={`stat-card sc-${accent}`}>
      <div className="ic">{icon}</div>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
      {sub ? <div className="s">{sub}</div> : null}
    </div>
  )
}
```

- [ ] **Step 3: Append CSS to `theme.css`**

```css
/* --- Build & Review overview (control tower) ------------------------------ */
.stat-row { display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); gap: 12px; margin: 16px 0; }
.stat-card {
  background: var(--surface); border: 1px solid var(--border);
  border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--shadow-sm);
}
.stat-card .ic { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; margin-bottom: 8px; border: 1px solid transparent; }
.stat-card .ic svg { width: 18px; height: 18px; }
.stat-card .v { font-size: 24px; font-weight: 650; line-height: 1.15; }
.stat-card .l { font-size: 12px; font-weight: 600; margin-top: 1px; }
.stat-card .s { font-size: 11px; color: var(--muted); margin-top: 2px; font-weight: 600; }
.sc-green .ic { background: var(--green-pale); color: var(--green); }
.sc-green .s { color: var(--green); }
.sc-blue .ic { background: #e3edf6; color: #2c5f8f; }
.sc-orange .ic { background: #fdeadd; color: #c2570e; }
.sc-purple .ic { background: #ede9fb; color: #6d3fc4; }
.sc-violet .ic { background: #f1e8f9; color: #8b3fc4; }
.sc-red .ic { background: var(--red-pale); color: var(--red); }
.sc-red .v { color: var(--red); }

.risk-chip { display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: 11px; font-weight: 650; border: 1px solid transparent; white-space: nowrap; }
.risk-chip.on_track { background: var(--green-pale); color: var(--green); border-color: var(--green); }
.risk-chip.at_risk { background: var(--amber-pale); color: var(--amber-text); border-color: var(--amber); }

.sev-chip { display: inline-block; padding: 1px 8px; border-radius: 6px; font-size: 10.5px; font-weight: 650; }
.sev-chip.critical { background: var(--red-pale); color: var(--red-dark); }
.sev-chip.high { background: #fdeadd; color: #c2570e; }
.sev-chip.medium { background: var(--amber-pale); color: var(--amber-text); }

.cell-status { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font-weight: 600; font-size: 12.5px; }
.cell-status svg { width: 14px; height: 14px; }
.cell-status.cs-ok { color: var(--green); }
.cell-status.cs-run { color: #2c5f8f; }
.cell-status.cs-warn { color: #c2570e; }
.cell-status.cs-bad { color: var(--red-dark); }
.cell-status.cs-idle { color: var(--muted); }

.repo-cell { display: inline-flex; align-items: center; gap: 6px; }
.repo-cell svg { width: 14px; height: 14px; color: var(--muted); }

.readiness-row { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 14px; }
.readiness-card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px 16px; box-shadow: var(--shadow-sm); cursor: pointer; text-align: left; font: inherit; color: inherit; }
.readiness-card:hover { border-color: var(--red); }
.readiness-card .ic { width: 34px; height: 34px; border-radius: 9px; display: grid; place-items: center; margin-bottom: 8px; }
.readiness-card .ic svg { width: 18px; height: 18px; }
.readiness-card h4 { font-size: 13px; margin: 0 0 6px; }
.readiness-card .m { font-size: 16px; font-weight: 650; }
.readiness-card .s { font-size: 11px; color: var(--muted); font-weight: 600; margin-top: 2px; }

.rail-link, .table-foot-link { background: none; border: 0; padding: 0; color: var(--red); font: inherit; font-size: 12.5px; font-weight: 650; cursor: pointer; }
.rail-link:hover, .table-foot-link:hover { text-decoration: underline; }
.table-foot { text-align: center; padding-top: 10px; }

.act-row { display: flex; align-items: flex-start; gap: 8px; }
.act-row .t { font-size: 11px; color: var(--muted); font-variant-numeric: tabular-nums; padding-top: 1px; }
.act-row svg { width: 13px; height: 13px; color: var(--muted); flex: none; margin-top: 2px; }
.act-row .x { flex: 1; min-width: 0; }

@media (max-width: 1100px) {
  .stat-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .readiness-row { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
```

- [ ] **Step 4: Build to verify types and bundle**

Run: `cd apps/control/web && npm run build`
Expected: exits 0.

- [ ] **Step 5: Commit (include dist per hard rule 4)**

```bash
git add apps/control/web/package.json apps/control/web/package-lock.json apps/control/web/src/components/StatCard.tsx apps/control/web/src/theme.css apps/control/web/dist
git commit -m "build-overview 1/3: pinned lucide-react, StatCard component, control-tower CSS"
```

---

### Task 2: Derivation helpers in `buildHelpers.tsx`

**Files:**
- Modify: `apps/control/web/src/pages/build/buildHelpers.tsx` (append; also extend the import line from `'../../types'`)

**Interfaces:**
- Consumes: types `BuildSummaryRow`, `GitPublication`, `PlanStory`, `ActivityEvent` from `types.ts`.
- Produces (all named exports):
  - `teamRisk(rows: BuildSummaryRow[]): 'on_track' | 'at_risk'`
  - `blockerSeverity(reason: string, row?: BuildSummaryRow): 'critical' | 'high' | 'medium'`
  - `gitIntegrationState(pubs: GitPublication[]): { state: 'connected' | 'simulated' | 'not_published'; label: string; sub: string }`
  - `teamDependencyCount(team: string, stories: PlanStory[]): number`
  - `activityTeam(ev: ActivityEvent, teams: string[]): string | null`

- [ ] **Step 1: Extend the type import**

Change the import at the top of `buildHelpers.tsx` to:

```tsx
import type {
  ActivityEvent,
  BuildReviewPhase,
  BuildState,
  BuildSummaryRow,
  GitPublication,
  PlanStory,
  RunState,
} from '../../types'
```

- [ ] **Step 2: Append the derivation helpers**

```tsx
/* --- Overview derivations. Each is a stated rule over real run state — the
 * UI never invents data (see spec 2026-08-09-build-overview-redesign). ----- */

/** Rule: a team is At Risk iff any of its stories is blocked or stale. */
export function teamRisk(rows: BuildSummaryRow[]): 'on_track' | 'at_risk' {
  return rows.some((r) => r.overall === 'blocked' || r.stale) ? 'at_risk' : 'on_track'
}

/**
 * Rule: review-blocked ⇒ critical; dependency/waiting ⇒ high; otherwise
 * (stale artifacts and the rest) ⇒ medium. Derived from the blocker reason —
 * severity is not a stored field.
 */
export function blockerSeverity(
  reason: string,
  row?: BuildSummaryRow,
): 'critical' | 'high' | 'medium' {
  if (row?.review === 'blocked' || /review/i.test(reason)) return 'critical'
  if (/depend|waiting/i.test(reason)) return 'high'
  return 'medium'
}

/**
 * Rule: CONNECTED only when a real (non-simulated) publication succeeded;
 * SIMULATED when publications exist but are simulation pseudo-commits;
 * NOT PUBLISHED otherwise. Never pretends a simulated push is a live remote.
 */
export function gitIntegrationState(pubs: GitPublication[]): {
  state: 'connected' | 'simulated' | 'not_published'
  label: string
  sub: string
} {
  const done = pubs.filter((p) => p.status === 'published')
  if (done.some((p) => !p.simulated)) {
    return { state: 'connected', label: 'CONNECTED', sub: `${done.length} branch(es) published` }
  }
  if (done.length > 0) {
    return { state: 'simulated', label: 'SIMULATED', sub: 'No real git touched in simulation' }
  }
  return { state: 'not_published', label: 'NOT PUBLISHED', sub: 'Publish delivery packs first' }
}

/** Rule: sum of dependency edges across the plan stories the team owns. */
export function teamDependencyCount(team: string, stories: PlanStory[]): number {
  return stories
    .filter((s) => s.accountable_team === team)
    .reduce((n, s) => n + s.dependencies.length, 0)
}

/** Best-effort team attribution for an activity row: first team name found in
 * the event's text fields; null when the event names no team. */
export function activityTeam(ev: ActivityEvent, teams: string[]): string | null {
  const hay = [ev.actor, ev.artifact, ev.details, ev.outcome].filter(Boolean).join(' ')
  return teams.find((t) => hay.includes(t)) ?? null
}
```

- [ ] **Step 3: Build to verify types**

Run: `cd apps/control/web && npm run build`
Expected: exits 0 (helpers are not yet consumed; `tsc` must still be clean — unused exports are fine).

- [ ] **Step 4: Commit**

```bash
git add apps/control/web/src/pages/build/buildHelpers.tsx apps/control/web/dist
git commit -m "build-overview 2/3: rule-based derivations (team risk, blocker severity, git integration state)"
```

---

### Task 3: Rebuild `BuildOverview.tsx` to the mockup layout

**Files:**
- Modify: `apps/control/web/src/pages/build/BuildOverview.tsx` (full rewrite of the component body; keep the existing worst-state helpers `devWorst`, `testWorst`, `reviewWorst`, `overallWorst`, and `groupByTeam` exactly as they are)

**Interfaces:**
- Consumes: `StatCard` from `../../components/StatCard`; `teamRisk`, `blockerSeverity`, `gitIntegrationState`, `teamDependencyCount`, `activityTeam` from `./buildHelpers` (Task 2 signatures); lucide icons; existing `useRun`, `Badge`, `TeamChip`, `buildOf`, `PHASE_ORDER`, `PHASE_LABELS`, `GuidanceCard`, `CONTROL_PLANE_GUIDANCE`, `OwnershipChips`, `hhmm`, `selectStory`.
- Produces: the `BuildOverview` page component (same export name; `App.tsx` needs no change).

- [ ] **Step 1: Rewrite the render**

Replace the imports and the `BuildOverview` function with the following (the four worst-state helpers and `groupByTeam` stay untouched above it):

```tsx
import {
  Blocks, Boxes, Building2, CircleAlert, CircleCheck, CircleDashed, CircleDot,
  FileText, FlaskConical, GitCommitHorizontal, Github, Hammer, LoaderCircle,
  MessageSquareText, Package, ShieldCheck,
} from 'lucide-react'
import { useRun } from '../../state/RunContext'
import { Badge } from '../../components/Badge'
import { StatCard } from '../../components/StatCard'
import { TeamChip } from '../planning/TeamChip'
import {
  activityTeam, blockerSeverity, buildOf, CONTROL_PLANE_GUIDANCE, GuidanceCard,
  gitIntegrationState, hhmm, OwnershipChips, PHASE_LABELS, PHASE_ORDER,
  selectStory, teamDependencyCount, teamRisk,
} from './buildHelpers'
import type { BuildSummaryRow } from '../../types'
```

Status-cell renderer (module-level, above the component):

```tsx
/** Icon + word for a table status cell, mockup-style. */
function StatusCell({ status }: { status: string }) {
  const MAP: Record<string, { cls: string; icon: JSX.Element; word: string }> = {
    completed: { cls: 'cs-ok', icon: <CircleCheck />, word: 'Complete' },
    passed: { cls: 'cs-ok', icon: <CircleCheck />, word: 'Passed' },
    ready: { cls: 'cs-ok', icon: <CircleCheck />, word: 'Ready' },
    in_progress: { cls: 'cs-warn', icon: <LoaderCircle />, word: 'In Progress' },
    running: { cls: 'cs-run', icon: <LoaderCircle />, word: 'Running' },
    waiting_for_approval: { cls: 'cs-idle', icon: <CircleDashed />, word: 'Pending' },
    not_started: { cls: 'cs-idle', icon: <CircleDashed />, word: 'Waiting' },
    failed: { cls: 'cs-bad', icon: <CircleAlert />, word: 'Failing' },
    blocked: { cls: 'cs-bad', icon: <CircleAlert />, word: 'Blocked' },
  }
  const m = MAP[status] ?? { cls: 'cs-idle', icon: <CircleDot />, word: status }
  return <span className={`cell-status ${m.cls}`}>{m.icon}{m.word}</span>
}
```

Inside `BuildOverview` (replacing the current body from `const build = ...` down, keeping `useRun`/null-guard):

```tsx
  const build = buildOf(data)
  const summary = build.summary
  const workspaces = build.workspaces ?? []
  const packs = build.delivery_packs ?? []
  const pubs = build.publications ?? []
  const phase = build.phase ?? null
  const totals = summary?.totals
  const blockers = summary?.blockers ?? []
  const rows = summary?.stories ?? []
  const teams = groupByTeam(rows)
  const planStories = data.planning?.stories ?? []
  const arch = build.architecture
  const published = packs.filter((p) => p.publication_status === 'published').length
  const phaseIdx = phase ? PHASE_ORDER.indexOf(phase) : -1
  const activity = (data.activity ?? []).filter((a) => a.stage === 'build_review').slice(-6).reverse()
  const teamNames = teams.map((t) => t.team)
  const git = gitIntegrationState(pubs)
  const qualityReady = (build.quality_handoff ?? []).filter((q) => q.ready).length

  const total = totals?.total ?? 0
  const pct = (n: number) => (total > 0 ? `${Math.round((n / total) * 100)}%` : '0%')
  const testingCount = rows.filter((r) => r.tests_total > 0).length
  const reviewedCount = rows.filter((r) => r.review === 'passed').length
  const wsReady = workspaces.length > 0 && workspaces.every((w) => w.artifact_status === 'current')
```

Keep the existing `nextAction` derivation and `repoOf` exactly as they are today. Then the JSX:

```tsx
  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '14px' }}>
          <h2>Build &amp; Review — Overview</h2>
          <span className="hint">
            Real-time view of delivery execution across teams and quality gates. S7 governs; developers execute in their own workspaces.
          </span>
          <OwnershipChips />
        </div>

        {/* phase rail card — unchanged from the current page */}

        <div className="stat-row">
          <StatCard accent="green" icon={<Boxes />} value={String(workspaces.length)} label="Workspaces" sub={wsReady ? 'Ready' : workspaces.length ? 'Provisioning' : '—'} />
          <StatCard accent="blue" icon={<FileText />} value={String(total)} label="Stories" sub="Total" />
          <StatCard accent="orange" icon={<Hammer />} value={String(totals?.in_progress ?? 0)} label="In Development" sub={pct(totals?.in_progress ?? 0)} />
          <StatCard accent="purple" icon={<FlaskConical />} value={String(testingCount)} label="Testing" sub={pct(testingCount)} />
          <StatCard accent="violet" icon={<MessageSquareText />} value={String(reviewedCount)} label="In Review" sub={pct(reviewedCount)} />
          <StatCard accent="red" icon={<CircleAlert />} value={String(totals?.blocked ?? 0)} label="Blocked" sub={pct(totals?.blocked ?? 0)} />
        </div>

        <div className="card">
          <div className="card-head"><h3>Delivery Progress by Team</h3></div>
          {teams.length === 0 ? (
            <p className="hint">No stories in the build yet — teams appear once delivery packs are generated.</p>
          ) : (
            <>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Team</th><th>Stories</th><th>Workspace / Repo</th><th>Development</th>
                      <th>Testing</th><th>Review</th><th>Status</th><th>Dependencies</th>
                    </tr>
                  </thead>
                  <tbody>
                    {teams.map((g) => (
                      <tr key={g.team}>
                        <td><TeamChip name={g.team} /></td>
                        <td>{String(g.rows.length)}</td>
                        <td><span className="repo-cell"><Github /><span className="mono">{repoOf(g.team)}</span></span></td>
                        <td><StatusCell status={devWorst(g.rows)} /></td>
                        <td><StatusCell status={testWorst(g.rows)} /></td>
                        <td><StatusCell status={reviewWorst(g.rows)} /></td>
                        <td><span className={`risk-chip ${teamRisk(g.rows)}`}>{teamRisk(g.rows) === 'at_risk' ? 'At Risk' : 'On Track'}</span></td>
                        <td>{String(teamDependencyCount(g.team, planStories))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div className="table-foot">
                <button type="button" className="table-foot-link" onClick={() => goTo('build_summary')}>View all teams →</button>
              </div>
            </>
          )}
        </div>

        <div className="readiness-row">
          <button type="button" className="readiness-card" onClick={() => goTo('architecture')}>
            <div className="ic sc-blue-ic"><Building2 /></div>
            <h4>Architecture Status</h4>
            <div className="m">{arch ? <Badge status={arch.status} /> : <span className="hint">Not generated</span>}</div>
            <div className="s">{arch ? `v${arch.version}.0` : '—'}</div>
          </button>
          <button type="button" className="readiness-card" onClick={() => goTo('delivery_packs')}>
            <div className="ic"><Github /></div>
            <h4>Git Integration</h4>
            <div className="m"><Badge status={git.state === 'connected' ? 'completed' : git.state === 'simulated' ? 'planned' : 'not_started'} label={git.label} /></div>
            <div className="s">{git.sub}</div>
          </button>
          <button type="button" className="readiness-card" onClick={() => goTo('delivery_packs')}>
            <div className="ic sc-orange-ic"><Package /></div>
            <h4>Delivery Packs</h4>
            <div className="m">{packs.length ? `${published} / ${packs.length}` : '—'}</div>
            <div className="s">{packs.length && published === packs.length ? 'Ready' : packs.length ? 'Publishing' : 'None generated yet'}</div>
          </button>
          <button type="button" className="readiness-card" onClick={() => goTo('quality')}>
            <div className="ic sc-green-ic"><ShieldCheck /></div>
            <h4>Quality Ready</h4>
            <div className="m">{String(qualityReady)}</div>
            <div className="s">Stories</div>
          </button>
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Recent Activity</h3>
          {activity.length === 0 ? (
            <p className="hint">No build activity yet.</p>
          ) : (
            <ul className="plain">
              {activity.map((a, i) => {
                const team = activityTeam(a, teamNames)
                return (
                  <li key={`${a.timestamp}-${i}`} className="act-row" style={{ marginBottom: '8px' }}>
                    <span className="t">{hhmm(a.timestamp)}</span>
                    <GitCommitHorizontal />
                    <span className="x clamp-2">{[a.outcome, a.artifact, a.details].filter(Boolean).join(' · ')}</span>
                    {team ? <TeamChip name={team} compact /> : null}
                  </li>
                )
              })}
            </ul>
          )}
          <button type="button" className="rail-link" onClick={() => goTo('activity')}>View all activity</button>
        </div>

        <div className="card rail-card">
          <h3>Top Blockers</h3>
          {blockers.length === 0 ? (
            <p className="hint">Nothing is blocked.</p>
          ) : (
            <ul className="plain">
              {blockers.slice(0, 3).map((b) => {
                const row = rows.find((r) => r.story_id === b.story_id)
                const sev = blockerSeverity(b.reason, row)
                return (
                  <li key={b.story_id} style={{ marginBottom: '10px' }}>
                    <div className="actions-row" style={{ justifyContent: 'space-between' }}>
                      <button type="button" className="link-btn mono" onClick={() => { selectStory(b.story_id); goTo('independent_review') }}>{b.story_id}</button>
                      <span className={`sev-chip ${sev}`}>{sev === 'critical' ? 'Critical' : sev === 'high' ? 'High' : 'Medium'}</span>
                    </div>
                    <div className="hint clamp-2">{`${b.team} — ${b.reason}`}</div>
                  </li>
                )
              })}
            </ul>
          )}
          <button type="button" className="rail-link" onClick={() => goTo('independent_review')}>View all blockers</button>
        </div>

        <div className="card rail-card">
          <h3>Next Actions</h3>
          <button type="button" className="primary sq" onClick={nextAction.go}>{nextAction.label}</button>
        </div>

        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
```

Adjustment notes the implementer must apply while wiring this in (they are requirements, not suggestions):

1. The phase-rail card block is copied verbatim from the current file (the `phase ? <div className="phase-rail">… : actions-row` card).
2. `Badge` may not accept a `label` prop — check `components/Badge.tsx`; if it doesn't, add an optional `label?: string` prop that overrides the display text only (status class unchanged).
3. `TeamChip` may not accept `compact` — check `planning/TeamChip.tsx`; if it doesn't, add optional `compact?: boolean` rendering only the initials avatar (no name text).
4. The readiness-card icon tints: add tiny CSS classes `.readiness-card .ic { background: var(--red-pale); color: var(--red); }` default plus `.sc-blue-ic { background:#e3edf6; color:#2c5f8f; }`, `.sc-orange-ic { background:#fdeadd; color:#c2570e; }`, `.sc-green-ic { background:var(--green-pale); color:var(--green); }` appended to `theme.css`.
5. Remove now-unused imports/helpers from the old render (e.g. `completeCount`) so `tsc` stays clean. `Blocks` icon is only needed if used — drop unused icon imports.
6. The old 3-card bottom grid (`Architecture / Delivery Packs / Build Summary`) is replaced by the 4-card readiness row; "View all teams" now covers the Build Summary drill-in.

- [ ] **Step 2: Build**

Run: `cd apps/control/web && npm run build`
Expected: exits 0, no unused-variable errors.

- [ ] **Step 3: Commit**

```bash
git add apps/control/web/src apps/control/web/dist
git commit -m "build-overview 3/3: control-tower overview — stat cards, team table, blockers rail, readiness cards"
```

---

### Task 4: Live verification in Chrome + Python regression check

**Files:** none created; fixes discovered here are amended into the Task 1–3 files (plus rebuilt `dist/`) in a follow-up commit.

- [ ] **Step 1: Python tests still green (no backend change expected)**

Run: `python -m pytest -q` (repo root)
Expected: all pass.

- [ ] **Step 2: Start the Control Centre fresh**

Kill any stale server on port 8720 first (known gotcha), then start:

```bash
lsof -ti :8720 | xargs kill 2>/dev/null; ./demo/run_control.sh
```

- [ ] **Step 3: Walk the page live via Chrome MCP**

Open `http://127.0.0.1:8720`, drive a demo run far enough that Build & Review has data (sign Gate 1 → generate/accept architecture → generate + publish delivery packs → simulate developer execution), then verify on the Overview page:

- six stat cards render with icons, values and percentages;
- team table shows repo names with the GitHub mark, icon+word status cells, On Track/At Risk chips, dependency counts;
- Recent Activity rows show time + text (+ team chip when attributable) and "View all activity" navigates to Activity Log;
- Top Blockers shows severity chips and deep-links into Independent Review;
- readiness cards show Architecture version/status, Git Integration `SIMULATED` (in simulation mode — it must NOT say CONNECTED), Delivery Packs `n / n`, Quality Ready count; each navigates on click;
- empty state: a fresh run with no Gate 1 sign-off still shows the "Opens when the plan is signed at Gate 1" card and zeroed cards, nothing crashes.

- [ ] **Step 4: Fix anything found, rebuild, commit**

```bash
cd apps/control/web && npm run build && cd ../../..
git add apps/control/web && git commit -m "build-overview: live-verification fixes"
```

(Skip the commit if nothing needed fixing.)

---

## Self-review notes

- Spec coverage: stat row (T3), team table incl. dependencies + risk (T2+T3), rail panels incl. severity + links (T2+T3), readiness cards incl. honest git state (T2+T3), icons pinned (T1), dist-in-same-commit (every task), live walkthrough (T4). No gaps.
- lucide-react@0.545.0 exports every icon named here, including the deprecated-but-present `Github` brand mark.
- Type names match `types.ts` exactly (`BuildSummaryRow.stale`, `GitPublication.simulated`, `PlanStory.accountable_team`, `QualityHandoffRow.ready`).
