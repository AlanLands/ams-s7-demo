import type { ReactNode } from 'react'
import {
  Boxes, Building2, CircleAlert, CircleCheck, CircleDashed, CircleDot,
  FileText, FlaskConical, GitCommitHorizontal, Github, Hammer, LoaderCircle,
  MessageSquareText, Package, ShieldCheck,
} from 'lucide-react'
import { useRun } from '../../state/RunContext'
import { Badge } from '../../components/Badge'
import { StatCard } from '../../components/StatCard'
import { TeamChip } from '../planning/TeamChip'
import {
  activityTeam,
  blockerSeverity,
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  gitIntegrationState,
  GuidanceCard,
  hhmm,
  OwnershipChips,
  PHASE_LABELS,
  PHASE_ORDER,
  selectStory,
  teamDependencyCount,
  teamRisk,
} from './buildHelpers'
import type { BuildSummaryRow } from '../../types'

// Build & Review landing page — the control tower for post-planning
// execution. S7 is the governed control plane: this page aggregates delivery
// evidence per team — it never pretends to be an IDE or to show live git.
// All progress states derive from the engine's summary; the risk/severity
// chips are stated rules in buildHelpers, not stored (or invented) data.

interface TeamGroup {
  team: string
  rows: BuildSummaryRow[]
}

function groupByTeam(rows: BuildSummaryRow[]): TeamGroup[] {
  const groups: TeamGroup[] = []
  for (const r of rows) {
    const g = groups.find((x) => x.team === r.team)
    if (g) g.rows.push(r)
    else groups.push({ team: r.team, rows: [r] })
  }
  return groups
}

/** Worst-state badge status for a team's development column. */
function devWorst(rows: BuildSummaryRow[]): string {
  if (rows.some((r) => r.overall === 'blocked')) return 'blocked'
  if (rows.every((r) => r.development === 'complete')) return 'completed'
  if (rows.some((r) => r.development !== 'not_started')) return 'in_progress'
  return 'not_started'
}

function testWorst(rows: BuildSummaryRow[]): string {
  if (rows.some((r) => r.testing === 'failing')) return 'failed'
  const total = rows.reduce((n, r) => n + r.tests_total, 0)
  if (total > 0 && rows.every((r) => r.testing === 'passed')) return 'passed'
  if (total > 0) return 'running'
  return 'not_started'
}

function reviewWorst(rows: BuildSummaryRow[]): string {
  if (rows.some((r) => r.review === 'blocked')) return 'blocked'
  if (rows.every((r) => r.review === 'passed')) return 'passed'
  return 'waiting_for_approval'
}

/** Icon + word for a table status cell, mockup-style. */
function StatusCell({ status }: { status: string }) {
  const MAP: Record<string, { cls: string; icon: ReactNode; word: string }> = {
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

export function BuildOverview() {
  const { data, goTo } = useRun()
  if (!data) return null

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
  const activity = (data.activity ?? []).filter((a) => a.stage === 'build_review').slice(-5).reverse()
  const teamNames = teams.map((t) => t.team)
  const git = gitIntegrationState(pubs, data.run.mode)
  const qualityReady = (build.quality_handoff ?? []).filter((q) => q.ready).length

  const total = totals?.total ?? 0
  const pct = (n: number) => (total > 0 ? `${Math.round((n / total) * 100)}% of stories` : '0%')
  const testingCount = rows.filter((r) => r.tests_total > 0).length
  const reviewedCount = rows.filter((r) => r.review === 'passed').length
  const wsReady = workspaces.length > 0 && workspaces.every((w) => w.artifact_status === 'current')

  // Honest next action, derived from state — never a decorative button.
  let nextAction: { label: string; go: () => void }
  if (!arch) nextAction = { label: 'Generate architecture', go: () => goTo('architecture') }
  else if (arch.status !== 'accepted') nextAction = { label: 'Accept architecture', go: () => goTo('architecture') }
  else if (packs.length === 0) nextAction = { label: 'Generate delivery packs', go: () => goTo('delivery_packs') }
  else if (published < packs.length) nextAction = { label: 'Publish delivery packs', go: () => goTo('delivery_packs') }
  else if (blockers.length > 0) {
    nextAction = {
      label: 'Review blocked story',
      go: () => { selectStory(blockers[0].story_id); goTo('independent_review') },
    }
  } else nextAction = { label: 'Proceed to Final Gating', go: () => goTo('quality') }

  const repoOf = (team: string) => packs.find((p) => p.team === team)?.repository ?? '—'

  return (
    <section className="page-with-rail bo-compact">
      <div>
        <div className="page-head" style={{ marginBottom: '8px' }}>
          <h2>Build &amp; Review — Overview</h2>
          <span className="hint">
            Real-time view of delivery execution across teams and quality gates. S7 governs; developers execute in their own workspaces.
          </span>
          <OwnershipChips />
        </div>

        <div className="card" style={{ marginBottom: '8px' }}>
          {phase ? (
            <div className="phase-rail">
              {PHASE_ORDER.flatMap((p, i) => {
                const cls = i < phaseIdx ? ' done' : i === phaseIdx ? ' now' : ''
                const node = (
                  <span key={p} className={`phase${cls}`}>
                    <span className="dot" />
                    {PHASE_LABELS[p]}
                  </span>
                )
                return i > 0 ? [<span key={`line-${p}`} className="phase-line" />, node] : [node]
              })}
            </div>
          ) : (
            <div className="actions-row">
              <span className="hint">Opens when the plan is signed at Gate 1</span>
              <button type="button" className="outline" onClick={() => goTo('plan_signoff')}>Go to Plan Sign-off</button>
            </div>
          )}
        </div>

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
                      <th>Team</th>
                      <th>Stories</th>
                      <th>Workspace / Repo</th>
                      <th>Development</th>
                      <th>Testing</th>
                      <th>Review</th>
                      <th>Status</th>
                      <th>Dependencies</th>
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
                        <td>
                          <span className={`risk-chip ${teamRisk(g.rows)}`}>
                            {teamRisk(g.rows) === 'at_risk' ? 'At Risk' : 'On Track'}
                          </span>
                        </td>
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
            <div className="m">
              <Badge
                status={git.state === 'connected' ? 'completed' : git.state === 'simulated' ? 'planned' : 'not_started'}
                label={git.label}
              />
            </div>
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
            <h4>Final Gating Ready</h4>
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
                    <span className="x clamp-2">
                      {[a.outcome, a.artifact, a.details].filter(Boolean).join(' · ')}
                    </span>
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
                      <button
                        type="button"
                        className="link-btn mono"
                        onClick={() => { selectStory(b.story_id); goTo('independent_review') }}
                      >
                        {b.story_id}
                      </button>
                      <span className={`sev-chip ${sev}`}>
                        {sev === 'critical' ? 'Critical' : sev === 'high' ? 'High' : 'Medium'}
                      </span>
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
}
