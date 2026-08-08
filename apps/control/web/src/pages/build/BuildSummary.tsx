import { useState } from 'react'
import { SectionTitle } from '../../components/SectionTitle'
import { Prov } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import type { BuildSummaryRow, BuildTask } from '../../types'
import {
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  DEV_STATUS_BADGE,
  DEV_STATUS_LABELS,
  GuidanceCard,
  hhmm,
  selectStory,
  selectedStory,
} from './buildHelpers'

// Shared story-selection fallback (same chain on every build page): explicit
// selection first, then in_progress → blocked → waiting_for_approval → first.
function pickTask(tasks: BuildTask[], sel: string | null): BuildTask {
  return (
    tasks.find((t) => t.story_id === sel)
    ?? tasks.find((t) => t.status === 'in_progress')
    ?? tasks.find((t) => t.status === 'blocked')
    ?? tasks.find((t) => t.status === 'waiting_for_approval')
    ?? tasks[0]
  )
}

const OVERALL_BADGE: Record<BuildSummaryRow['overall'], [string, string]> = {
  ready_for_quality: ['st-passed', 'READY FOR QUALITY'],
  blocked: ['st-blocked', 'BLOCKED'],
  complete: ['st-completed', 'COMPLETE'],
  in_development: ['st-in_progress', 'IN DEVELOPMENT'],
  not_started: ['st-not_started', 'NOT STARTED'],
}

const TESTING_BADGE: Record<BuildSummaryRow['testing'], string> = {
  passed: 'st-passed',
  failing: 'st-failed',
  waiting: 'st-planned',
}

const REVIEW_BADGE: Record<BuildSummaryRow['review'], string> = {
  passed: 'st-passed',
  blocked: 'st-blocked',
  pending: 'st-planned',
}

// Status-distribution donut colors (match the totals fields).
const STATUS_SEGMENTS: Array<[label: string, key: 'complete' | 'in_progress' | 'blocked' | 'not_started', color: string]> = [
  ['Complete', 'complete', '#125c43'],
  ['In Progress', 'in_progress', '#7d5f13'],
  ['Blocked', 'blocked', '#850822'],
  ['Not Started', 'not_started', '#85847a'],
]

export function BuildSummaryPage() {
  const { data, goTo } = useRun()
  const [selId, setSelId] = useState<string | null>(selectedStory())
  if (!data) return null

  const build = buildOf(data)
  const summary = build.summary
  const handoff = build.quality_handoff ?? []
  const rows = summary?.stories ?? []

  if (!summary || !rows.length) {
    return (
      <section>
        <SectionTitle title="Build Summary" />
        <div className="card">
          <p>The build summary appears once the plan is signed at Gate 1 and developer execution begins.</p>
        </div>
      </section>
    )
  }

  const totals = summary.totals
  const blockers = summary.blockers ?? []
  const readyIds = summary.ready_story_ids ?? []
  const tasks = build.tasks ?? []

  const select = (storyId: string) => {
    selectStory(storyId)
    setSelId(storyId)
  }

  // Resolve the shared selection against this page's rows.
  const selTask = tasks.length ? pickTask(tasks, selId) : undefined
  const selStoryId = rows.some((r) => r.story_id === selId)
    ? selId
    : (selTask && rows.some((r) => r.story_id === selTask.story_id) ? selTask.story_id : rows[0].story_id)
  const selHandoff = handoff.find((h) => h.story_id === selStoryId)
  const titleOf = (id: string) => rows.find((r) => r.story_id === id)?.title ?? id

  // Status-distribution donut stops.
  let acc = 0
  const donutStops = STATUS_SEGMENTS
    .filter(([, key]) => totals[key] > 0)
    .map(([, key, color]) => {
      const from = (360 * acc) / totals.total
      acc += totals[key]
      return `${color} ${from}deg ${(360 * acc) / totals.total}deg`
    })
    .join(', ')

  // Team contribution — stories per accountable team.
  const teams = [...new Set(rows.map((r) => r.team))]

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Build Summary</h2>
          <span className="hint">
            Consolidated outcome of workspace provisioning, developer execution, testing and independent review.
          </span>
        </div>

        <div className="tiles">
          <div className="tile t-blue"><div className="v">{totals.total}</div><div className="l">Total Stories</div></div>
          <div className="tile t-green"><div className="v">{totals.complete}</div><div className="l">Completed</div></div>
          <div className="tile t-amber"><div className="v">{totals.in_progress}</div><div className="l">In Progress</div></div>
          <div className="tile t-red"><div className="v">{totals.blocked}</div><div className="l">Blocked</div></div>
          <div className="tile t-green"><div className="v">{totals.ready_for_quality}</div><div className="l">Ready for Quality</div></div>
          <div className="tile t-blue">
            <div className="v">{totals.review_pass_rate != null ? `${totals.review_pass_rate}%` : '—'}</div>
            <div className="l">Review Pass Rate</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{`${totals.tests_passed}/${totals.tests_total}`}</div>
            <div className="l">Tests</div>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Story Build &amp; Review Status</h3>
            <Prov provenance="simulated" />
          </div>
          <p className="hint" style={{ margin: '-4px 0 10px' }}>
            Click a row to focus that story across the build pages.
          </p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {['Story', 'Team', 'Developer', 'Development', 'Testing', 'Review', 'Overall', 'Last Updated'].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => {
                  const [overallCls, overallLabel] = OVERALL_BADGE[row.overall]
                  const pct = row.tests_total ? Math.round((100 * row.tests_passed) / row.tests_total) : 0
                  return (
                    <tr
                      key={row.story_id}
                      className={row.story_id === selStoryId ? 'sel' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => select(row.story_id)}
                    >
                      <td>
                        <div className="mono">{row.story_id}</div>
                        <div>{row.title}</div>
                        {row.stale ? <span className="badge st-stale">⚠ STALE</span> : null}
                      </td>
                      <td>{row.team}</td>
                      <td>{row.developer || '—'}</td>
                      <td>
                        <span className={`badge ${DEV_STATUS_BADGE[row.development] ?? 'st-planned'}`}>
                          {DEV_STATUS_LABELS[row.development] ?? row.development}
                        </span>
                      </td>
                      <td>
                        <span className={`badge ${TESTING_BADGE[row.testing]}`}>{row.testing}</span>
                        <div className="mono hint" style={{ marginTop: 4 }}>{`${row.tests_passed}/${row.tests_total}`}</div>
                        <div className="bar" style={{ marginTop: 4 }}>
                          <div className="bar-fill" style={{ width: `${pct}%` }} />
                        </div>
                      </td>
                      <td><span className={`badge ${REVIEW_BADGE[row.review]}`}>{row.review}</span></td>
                      <td><span className={`badge ${overallCls}`}>{overallLabel}</span></td>
                      <td className="mono">{hhmm(row.last_updated)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>Status Distribution</h3>
            {totals.total > 0 ? (
              <div className="donut-wrap">
                <div className="donut" style={{ background: `conic-gradient(${donutStops})` }}>
                  <div className="donut-hole">
                    <div className="v">{totals.total}</div>
                    <div className="l">Stories</div>
                  </div>
                </div>
                <ul className="donut-legend">
                  {STATUS_SEGMENTS.map(([label, key, color]) => (
                    <li key={key}>
                      <span className="legend-dot" style={{ background: color }} />
                      {`${label} — ${totals[key]} (${Math.round((100 * totals[key]) / totals.total)}%)`}
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <p className="hint">No stories in build yet.</p>
            )}
          </div>
          <div className="card">
            <h3>Team Contribution</h3>
            {teams.map((team) => {
              const n = rows.filter((r) => r.team === team).length
              return (
                <div key={team} style={{ marginTop: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
                    <span>{team}</span>
                    <span className="mono hint">{`${n} ${n === 1 ? 'story' : 'stories'}`}</span>
                  </div>
                  <div className="bar" style={{ marginTop: 4 }}>
                    <div className="bar-fill" style={{ width: `${Math.round((100 * n) / rows.length)}%` }} />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        <div className="actions-row" style={{ marginTop: 16 }}>
          <button
            type="button"
            className="approve"
            disabled={!readyIds.length}
            title={readyIds.length ? 'Open the quality handoff' : 'No story has met the handoff conditions yet'}
            onClick={() => goTo('quality')}
          >
            ✓ View Quality Handoff
          </button>
          {!readyIds.length ? (
            <span className="hint">Enabled once at least one story meets every handoff condition.</span>
          ) : null}
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>⚠ Top Blockers</h3>
          {blockers.length ? (
            blockers.map((b) => (
              <div className="risk-line red" key={b.story_id}>
                <b>{`${b.story_id} · ${b.team}`}</b>
                <span className="hint">{b.reason}</span>
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => { select(b.story_id); goTo('independent_review') }}
                >
                  Open Independent Review →
                </button>
              </div>
            ))
          ) : (
            <p className="hint">No blocked stories.</p>
          )}
        </div>

        <div className="card rail-card" style={{ borderColor: 'var(--green)' }}>
          <h3>✓ Ready for Quality Handoff</h3>
          {readyIds.length ? (
            <ul className="plain">
              {readyIds.map((id) => (
                <li key={id}>
                  <span className="mono">{`${id} `}</span>
                  {titleOf(id)}
                </li>
              ))}
            </ul>
          ) : (
            <p className="hint">No stories have met the handoff conditions yet.</p>
          )}
          {selHandoff ? (
            <>
              <p className="hint" style={{ marginTop: 10 }}>
                <b>{`Handoff conditions — ${selHandoff.story_id}`}</b>
              </p>
              <ul className="checklist">
                {selHandoff.checks.map((c) => (
                  <li key={c.condition}>
                    <span className={`tick ${c.met ? 'ok' : 'no'}`}>{c.met ? '✓' : '·'}</span>
                    <span>
                      {c.condition}
                      {!c.met && c.detail ? <span className="hint">{` — ${c.detail}`}</span> : null}
                    </span>
                  </li>
                ))}
              </ul>
              <p className="hint">Readiness is these explicit conditions being met — never a score.</p>
            </>
          ) : null}
        </div>

        <div className="card rail-card">
          <h3>Next Actions</h3>
          {blockers.length ? (
            <>
              <p className="hint">{`${blockers.length} ${blockers.length === 1 ? 'story is' : 'stories are'} blocked on review findings.`}</p>
              <button
                type="button"
                className="outline block"
                onClick={() => { select(blockers[0].story_id); goTo('independent_review') }}
              >
                Review Blocked Story →
              </button>
            </>
          ) : readyIds.length === totals.total && totals.total > 0 ? (
            <>
              <p className="hint">Every story has met its handoff conditions.</p>
              <button type="button" className="approve block" onClick={() => goTo('quality')}>
                Proceed to Quality →
              </button>
            </>
          ) : (
            <p className="hint">Development in progress — no intervention required.</p>
          )}
        </div>

        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
