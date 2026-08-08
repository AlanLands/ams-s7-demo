import { useRun } from '../../state/RunContext'
import { Badge } from '../../components/Badge'
import { TeamChip } from '../planning/TeamChip'
import {
  buildOf,
  PHASE_ORDER,
  PHASE_LABELS,
  GuidanceCard,
  CONTROL_PLANE_GUIDANCE,
  OwnershipChips,
  hhmm,
  selectStory,
} from './buildHelpers'
import type { BuildSummaryRow } from '../../types'

// Build & Review landing page. S7 is the governed control plane: this page
// aggregates delivery evidence per team — it never pretends to be an IDE or
// to show live git. All progress states derive from the engine's summary.

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
  if (total > 0) return 'in_progress'
  return 'not_started'
}

function reviewWorst(rows: BuildSummaryRow[]): string {
  if (rows.some((r) => r.review === 'blocked')) return 'blocked'
  if (rows.every((r) => r.review === 'passed')) return 'passed'
  return 'waiting_for_approval'
}

function overallWorst(rows: BuildSummaryRow[]): string {
  if (rows.some((r) => r.overall === 'blocked')) return 'blocked'
  if (rows.every((r) => r.overall === 'complete' || r.overall === 'ready_for_quality')) return 'ready'
  if (rows.some((r) => r.overall !== 'not_started')) return 'in_progress'
  return 'not_started'
}

export function BuildOverview() {
  const { data, goTo } = useRun()
  if (!data) return null

  const build = buildOf(data)
  const summary = build.summary
  const workspaces = build.workspaces ?? []
  const packs = build.delivery_packs ?? []
  const phase = build.phase ?? null
  const totals = summary?.totals
  const blockers = summary?.blockers ?? []
  const teams = groupByTeam(summary?.stories ?? [])
  const arch = build.architecture
  const published = packs.filter((p) => p.publication_status === 'published').length
  const phaseIdx = phase ? PHASE_ORDER.indexOf(phase) : -1
  const activity = (data.activity ?? []).filter((a) => a.stage === 'build_review').slice(-6).reverse()

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
  } else nextAction = { label: 'Proceed to Quality', go: () => goTo('quality') }

  const repoOf = (team: string) => packs.find((p) => p.team === team)?.repository ?? '—'
  const completeCount = (rows: BuildSummaryRow[], pred: (r: BuildSummaryRow) => boolean) =>
    `${rows.filter(pred).length}/${rows.length} complete`

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '14px' }}>
          <h2>Build &amp; Review — Overview</h2>
          <span className="hint">
            Track delivery across teams, stories and gates. S7 prepares and governs; developers execute in their own workspaces.
          </span>
          <OwnershipChips />
        </div>

        <div className="card" style={{ marginBottom: '14px' }}>
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

        <div className="tiles">
          <div className="tile">
            <div className="v">{String(workspaces.length)}</div>
            <div className="l">Workspaces · provisioned</div>
          </div>
          <div className="tile">
            <div className="v">{String(totals?.total ?? 0)}</div>
            <div className="l">Stories</div>
          </div>
          <div className="tile t-amber">
            <div className="v">{String(totals?.in_progress ?? 0)}</div>
            <div className="l">In Progress</div>
          </div>
          <div className="tile t-red">
            <div className="v">{String(totals?.blocked ?? 0)}</div>
            <div className="l">Blocked</div>
          </div>
          <div className="tile t-green">
            <div className="v">{String(totals?.ready_for_quality ?? 0)}</div>
            <div className="l">Ready for Quality</div>
          </div>
          <div className="tile">
            <div className="v">{`${totals?.tests_passed ?? 0}/${totals?.tests_total ?? 0}`}</div>
            <div className="l">Tests</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Delivery Progress by Team</h3>
          </div>
          {teams.length === 0 ? (
            <p className="hint">No stories in the build yet — teams appear once delivery packs are generated.</p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Team</th>
                    <th>Stories</th>
                    <th>Workspace</th>
                    <th>Development</th>
                    <th>Testing</th>
                    <th>Review</th>
                    <th>Status</th>
                    <th>Dependencies</th>
                  </tr>
                </thead>
                <tbody>
                  {teams.map((g) => {
                    const blockedIds = g.rows.filter((r) => r.overall === 'blocked').map((r) => r.story_id)
                    const testsPassed = g.rows.reduce((n, r) => n + r.tests_passed, 0)
                    const testsTotal = g.rows.reduce((n, r) => n + r.tests_total, 0)
                    return (
                      <tr key={g.team}>
                        <td><TeamChip name={g.team} /></td>
                        <td>{String(g.rows.length)}</td>
                        <td className="mono">{repoOf(g.team)}</td>
                        <td>
                          <span className="hint">{completeCount(g.rows, (r) => r.development === 'complete')}</span>{' '}
                          <Badge status={devWorst(g.rows)} />
                        </td>
                        <td>
                          <span className="hint">{`${testsPassed}/${testsTotal} passed`}</span>{' '}
                          <Badge status={testWorst(g.rows)} />
                        </td>
                        <td>
                          <span className="hint">{completeCount(g.rows, (r) => r.review === 'passed')}</span>{' '}
                          <Badge status={reviewWorst(g.rows)} />
                        </td>
                        <td><Badge status={overallWorst(g.rows)} /></td>
                        <td>
                          {blockedIds.length ? (
                            <span className="mono" style={{ color: 'var(--red)' }}>{blockedIds.join(', ')}</span>
                          ) : '—'}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="grid cols-3" style={{ marginTop: '14px' }}>
          <div className="card">
            <h3>▤ Architecture</h3>
            {arch ? (
              <p>
                <span className="mono">{`v${arch.version}`}</span>{' '}
                <Badge status={arch.status} />
              </p>
            ) : (
              <p className="hint">Not generated yet.</p>
            )}
            <button type="button" className="outline" onClick={() => goTo('architecture')}>View</button>
          </div>
          <div className="card">
            <h3>▣ Delivery Packs</h3>
            <p>{packs.length ? `${published} published / ${packs.length} total` : 'None generated yet.'}</p>
            <button type="button" className="outline" onClick={() => goTo('delivery_packs')}>View</button>
          </div>
          <div className="card">
            <h3>▥ Build Summary</h3>
            <p>
              {totals
                ? `${totals.complete}/${totals.total} complete · ${totals.blocked} blocked · ${totals.ready_for_quality} ready for quality`
                : 'No summary yet.'}
            </p>
            <button type="button" className="outline" onClick={() => goTo('build_summary')}>View</button>
          </div>
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Recent Activity</h3>
          {activity.length === 0 ? (
            <p className="hint">No build activity yet.</p>
          ) : (
            <ul className="checklist">
              {activity.map((a, i) => (
                <li key={`${a.timestamp}-${i}`}>
                  <span className="mono hint" style={{ marginRight: '6px' }}>{hhmm(a.timestamp)}</span>
                  <span className="clamp-2">
                    {[a.outcome, a.artifact, a.details].filter(Boolean).join(' · ')}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card rail-card">
          <h3>Blocked Items</h3>
          {blockers.length === 0 ? (
            <p className="hint">Nothing is blocked.</p>
          ) : (
            <ul className="checklist">
              {blockers.map((b) => (
                <li key={b.story_id}>
                  <div>
                    <b className="mono">{b.story_id}</b>{' '}
                    <span className="hint">{`${b.team} — ${b.reason}`}</span>
                    <div>
                      <button
                        type="button"
                        className="link-btn"
                        onClick={() => { selectStory(b.story_id); goTo('independent_review') }}
                      >
                        Open in Independent Review
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
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
