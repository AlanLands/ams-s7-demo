/**
 * Build & Test Evidence — engineering evidence collected back from developer
 * workspaces: commits, CI, tests, coverage, quality gates and AC→test
 * traceability. Evidence-focused: no IDE, no terminal, no raw AI reasoning.
 *
 * Honesty: in simulation every signal is produced by the deterministic demo
 * engine and badged SIMULATED; build/pipeline ids are the engine's task ids
 * labelled "Simulated CI" — never a fake external provider. Review readiness
 * is the story's deterministic quality-handoff conditions, never a score.
 */
import { Fragment, useMemo, useState } from 'react'
import {
  Circle, CircleCheck, CircleX, ClipboardCheck, Download, ExternalLink,
  FlaskConical, GitBranch, GitCommitHorizontal, Github, Hammer, Info,
  LoaderCircle, MonitorCog, RefreshCw, RotateCcw, Search, ShieldCheck,
  TriangleAlert, Workflow,
} from 'lucide-react'
import { Prov } from '../../components/Badge'
import { StatCard } from '../../components/StatCard'
import { useRun } from '../../state/RunContext'
import type { BuildTask, DeveloperWorkspace, PlanStory, QualityHandoffRow } from '../../types'
import {
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  GuidanceCard,
  hhmm,
  relTime,
  selectStory,
  selectedStory,
} from './buildHelpers'

function CiBadge({ ci }: { ci?: string }) {
  if (ci === 'passed') return <span className="cell-status cs-ok"><CircleCheck />Passed</span>
  if (ci === 'running') return <span className="cell-status cs-run"><LoaderCircle className="spin" />Running</span>
  if (ci === 'failed') return <span className="cell-status cs-bad"><CircleX />Failed</span>
  return <span className="cell-status cs-idle"><Circle />Not Started</span>
}

/** Inspector header status — a stated derivation over real signals. */
function buildStatus(task: BuildTask, ws?: DeveloperWorkspace, handoff?: QualityHandoffRow): [string, string] {
  if (ws?.artifact_status === 'stale') return ['CONTEXT STALE', 'st-stale']
  if (task.status === 'blocked') return ['BLOCKED', 'st-blocked']
  if (ws?.ci_status === 'failed') return ['FAILED', 'st-failed']
  if (ws?.ci_status === 'running') return ['RUNNING', 'st-in_progress']
  if (handoff?.ready) return ['READY FOR REVIEW', 'st-passed']
  if (ws?.ci_status === 'passed') return ['PASSED', 'st-passed']
  return ['NOT STARTED', 'st-planned']
}

export function TestEvidence() {
  const { data, act, refresh, goTo, runId } = useRun()
  const [selId, setSelId] = useState<string | null>(selectedStory())
  const [query, setQuery] = useState('')
  const [fTeam, setFTeam] = useState('all')
  const [fCi, setFCi] = useState('all')
  const [syncing, setSyncing] = useState(false)

  const build = buildOf(data)
  const tasks = build.tasks ?? []
  const workspaces = build.workspaces ?? []
  const handoffs = build.quality_handoff ?? []
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const storyById = useMemo(() => new Map(stories.map((s) => [s.story_id, s])), [stories])
  const wsByStory = useMemo(() => new Map(workspaces.map((w) => [w.story_id, w])), [workspaces])

  if (!data) return null

  const select = (storyId: string) => { selectStory(storyId); setSelId(storyId) }
  const teamOf = (t: BuildTask) => t.accountable_team || storyById.get(t.story_id)?.accountable_team || '—'

  // --- metrics ---------------------------------------------------------------
  const executed = tasks.filter((t) => (t.tests ?? []).length > 0 || t.files_changed > 0)
  const ciOf = (t: BuildTask) => wsByStory.get(t.story_id)?.ci_status ?? ''
  const passedBuilds = tasks.filter((t) => ciOf(t) === 'passed').length
  const failedBuilds = tasks.filter((t) => ciOf(t) === 'failed').length
  const runningBuilds = tasks.filter((t) => ciOf(t) === 'running').length
  const totalTests = tasks.reduce((n, t) => n + (t.tests ?? []).length, 0)
  const covered = tasks.filter((t) => t.coverage_pct != null)
  const avgCoverage = covered.length
    ? (covered.reduce((n, t) => n + (t.coverage_pct ?? 0), 0) / covered.length).toFixed(1)
    : null

  const teams = [...new Set(tasks.map(teamOf).filter((t) => t !== '—'))]
  const filtered = tasks.filter((t) => {
    const ws = wsByStory.get(t.story_id)
    if (fTeam !== 'all' && teamOf(t) !== fTeam) return false
    if (fCi !== 'all' && (ws?.ci_status || 'not_started') !== fCi) return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      const hay = `${t.story_id} ${t.task_id} ${teamOf(t)} ${ws?.repository ?? ''}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })

  const task = filtered.find((t) => t.story_id === selId)
    ?? tasks.find((t) => t.story_id === selId)
    ?? filtered.find((t) => t.status === 'in_progress')
    ?? filtered.find((t) => t.status === 'blocked')
    ?? filtered[0]
    ?? tasks[0]

  if (!task) {
    return (
      <section className="page-with-rail bo-compact">
        <div>
          <div className="page-head" style={{ marginBottom: '8px' }}>
            <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Build &amp; Test Evidence</span>
          </div>
          <div className="card">
            <h3><ClipboardCheck className="btn-ico" /> No Build Evidence Yet</h3>
            <p>Developer workspaces are provisioned when delivery packs publish; evidence appears once development activity is recorded.</p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="primary" onClick={() => goTo('developer_workspaces')}>
                <MonitorCog className="btn-ico" /> View Developer Workspaces
              </button>
            </div>
          </div>
        </div>
        <aside className="rail"><GuidanceCard lines={CONTROL_PLANE_GUIDANCE} /></aside>
      </section>
    )
  }

  // --- selected evidence -----------------------------------------------------
  const ws = wsByStory.get(task.story_id)
  const story = storyById.get(task.story_id)
  const handoff = handoffs.find((h) => h.story_id === task.story_id)
  const tests = task.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const acText = (id: string) => acs.find((a) => a.ac_id === id)?.text ?? ''
  const passes = tests.filter((t) => t.current_result === 'passed').length
  const failing = tests.filter((t) => t.current_result === 'failed')
  const initialFailures = tests.filter((t) => t.initial_result === 'failed').length
  const evidencedAcs = new Set(tests.map((t) => t.ac_id))
  const acCovered = acs.filter((a) => evidencedAcs.has(a.ac_id)).length
  const [statusLabel, statusCls] = buildStatus(task, ws, handoff)
  const canSubmit = task.status === 'in_progress' && task.progress_pct >= 90

  const reviews = (build.reviews ?? []).filter((r) => r.task_id === task.task_id)
  const latestReview = reviews.length ? reviews[reviews.length - 1] : undefined

  const taskActivity = (data.activity ?? []).filter((a) => a.artifact === task.task_id)
  const at = (wf: string) => taskActivity.find((a) => a.workflow === wf)?.timestamp
  const timelineSteps: Array<[string, string, string | undefined, string]> = [
    ['red', 'Red', at('test-first'), `${initialFailures} failures expected`],
    ['code', 'Code', at('development'), 'Developer implements'],
    ['green', 'Green', at('developer-verification'), `${passes}/${tests.length} passing`],
  ]

  const doSync = async () => {
    setSyncing(true)
    await refresh()
    setSyncing(false)
  }

  return (
    <section className="page-with-rail bo-compact dp-page">
      <div>
        <div className="page-head" style={{ marginBottom: '4px' }}>
          <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Build &amp; Test Evidence</span>
        </div>
        <div className="page-head" style={{ marginBottom: '10px' }}>
          <h2>Build &amp; Test Evidence</h2>
          <span className="hint">Engineering evidence collected from CI pipelines, automated tests and quality checks.</span>
          <span className="arch-head-actions">
            <button className="outline" disabled={syncing} onClick={() => void doSync()}>
              {syncing ? <LoaderCircle className="btn-ico spin" /> : <RefreshCw className="btn-ico" />} Sync Now
            </button>
            <button className="primary" disabled={!(task.tests ?? []).length && !task.files_changed}
              title="Downloads this task's canonical evidence files"
              onClick={() => window.open(`/api/runs/${runId}/tasks/${task.task_id}/evidence.zip`, '_blank')}>
              <Download className="btn-ico" /> Export Evidence
            </button>
          </span>
        </div>

        <div className="stat-row">
          <StatCard accent="green" icon={<Hammer />} value={String(executed.length)} label="Builds" sub="Total executed" />
          <StatCard accent="green" icon={<CircleCheck />} value={String(passedBuilds)} label="Passed" sub={executed.length ? `${Math.round((passedBuilds / executed.length) * 100)}% success rate` : '—'} />
          <StatCard accent="red" icon={<CircleX />} value={String(failedBuilds)} label="Failed" sub={failedBuilds ? 'Needs attention' : 'None'} />
          <StatCard accent="blue" icon={<LoaderCircle />} value={String(runningBuilds)} label="Running" sub="In progress" />
          <StatCard accent="purple" icon={<FlaskConical />} value={String(totalTests)} label="Tests" sub="Across all builds" />
          <StatCard accent="teal" icon={<ShieldCheck />} value={avgCoverage ? `${avgCoverage}%` : '—'} label="Coverage" sub="Average line coverage" />
        </div>

        <div className="card dp-filters">
          <span className="dp-search">
            <Search className="dp-search-ico" />
            <input type="text" placeholder="Search by story, task, team, repository…"
              value={query} onChange={(e) => setQuery(e.target.value)} />
          </span>
          <label className="dp-filter"><span>Team</span>
            <select value={fTeam} onChange={(e) => setFTeam(e.target.value)}>
              <option value="all">All</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="dp-filter"><span>CI Status</span>
            <select value={fCi} onChange={(e) => setFCi(e.target.value)}>
              <option value="all">All</option>
              <option value="passed">Passed</option>
              <option value="running">Running</option>
              <option value="failed">Failed</option>
              <option value="not_started">Not Started</option>
            </select>
          </label>
          <button className="ghost" onClick={() => { setQuery(''); setFTeam('all'); setFCi('all') }}>
            <RotateCcw className="btn-ico" /> Reset
          </button>
        </div>

        <div className="card">
          <div className="table-wrap">
            <table className="dp-table dw-table">
              <colgroup>
                <col style={{ width: '9%' }} /><col style={{ width: '13%' }} /><col style={{ width: '11%' }} />
                <col style={{ width: '15%' }} /><col style={{ width: '11%' }} /><col style={{ width: '11%' }} />
                <col style={{ width: '10%' }} /><col style={{ width: '9%' }} /><col style={{ width: '11%' }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Time</th><th>Story / Task</th><th>Team</th><th>Repository / Commit</th><th>Build</th>
                  <th>CI Status</th><th>Tests</th><th>Coverage</th><th>Quality Gates</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => {
                  const w = wsByStory.get(t.story_id)
                  const h = handoffs.find((x) => x.story_id === t.story_id)
                  const tt = t.tests ?? []
                  const p = tt.filter((x) => x.current_result === 'passed').length
                  const met = h ? h.checks.filter((c) => c.met).length : 0
                  const initials = teamOf(t).split(/\s+/).map((x) => x[0]).join('').slice(0, 2).toUpperCase()
                  return (
                    <tr key={t.task_id}
                      className={task.task_id === t.task_id ? 'dp-row-selected' : ''}
                      onClick={() => select(t.story_id)}>
                      <td>
                        <span>{t.last_activity ? hhmm(t.last_activity) : '—'}</span>
                        <span className="hint dp-sub">{t.last_activity ? relTime(t.last_activity) : ''}</span>
                      </td>
                      <td>
                        <b className="mono">{t.story_id}</b>
                        <span className="hint dp-sub mono">{t.task_id}</span>
                      </td>
                      <td>
                        <span className="dp-team">
                          <span className={`team-avatar ${['tc-0', 'tc-1', 'tc-2', 'tc-3', 'tc-4'][teamOf(t).length % 5]}`}>{initials}</span>
                          <span className="hint">{teamOf(t)}</span>
                        </span>
                      </td>
                      <td>
                        <span className="repo-cell"><Github /><span className="mono">{w?.repository || '—'}</span></span>
                        <span className="repo-cell dw-branch-line"><GitCommitHorizontal />
                          <span className="mono">{w?.current_commit ? w.current_commit.slice(0, 7) : '—'}</span></span>
                      </td>
                      <td>
                        <span className="repo-cell"><Workflow /><span className="mono">{t.task_id.replace('TASK', 'BUILD')}</span></span>
                        <span className="hint dp-sub">Simulated CI</span>
                      </td>
                      <td><CiBadge ci={w?.ci_status} /></td>
                      <td>
                        {tt.length ? (
                          <>
                            <span className="mono">{`${p} / ${tt.length}`}</span>
                            <span className="hint dp-sub">{`${Math.round((p / tt.length) * 100)}%`}</span>
                          </>
                        ) : <span className="hint">—</span>}
                      </td>
                      <td>{t.coverage_pct != null ? <span className="mono">{`${t.coverage_pct}%`}</span> : <span className="hint">—</span>}</td>
                      <td>
                        {h ? (
                          h.ready
                            ? <span className="badge st-passed">PASSED</span>
                            : <span className="badge st-planned">{`${met}/${h.checks.length} MET`}</span>
                        ) : <span className="hint">—</span>}
                      </td>
                    </tr>
                  )
                })}
                {filtered.length === 0 ? (
                  <tr><td colSpan={9}><span className="hint">No evidence matches the current filters.</span></td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="dp-table-foot hint">{`Showing ${filtered.length} of ${tasks.length} evidence records · select a row to inspect`}</div>
        </div>

        {failing.length ? (
          <div className="card" style={{ marginTop: '10px' }}>
            <h3><TriangleAlert className="btn-ico" style={{ color: 'var(--red-dark)' }} /> Failure Analysis — {task.task_id}</h3>
            {failing.map((t) => {
              const finding = latestReview?.findings?.find((f) => f.ac_id === t.ac_id)
              return (
                <div className="risk-line red" key={t.test_id}>
                  <b>{`${t.name} — ${t.ac_id}`}</b>
                  <div className="finding-detail">
                    <div><b>Acceptance Criterion: </b>{`${t.ac_id} — ${acText(t.ac_id) || '—'}`}</div>
                    <div><b>Expected: </b>{finding?.expected ?? (acText(t.ac_id) || '—')}</div>
                    <div><b>Observed: </b>{finding?.observed ?? 'The implementation does not satisfy this criterion.'}</div>
                    {finding?.impact ? <div><b>Impact: </b>{finding.impact}</div> : null}
                    <div><b>Likely Component: </b>{story?.target_component ?? '—'}</div>
                    <div><b>Recommended Action: </b>{`Return ${task.task_id} to the developer workspace.`}</div>
                  </div>
                </div>
              )
            })}
            <div className="actions-row" style={{ marginTop: '10px' }}>
              <button type="button" className="outline" onClick={() => { select(task.story_id); goTo('developer_workspaces') }}>
                <MonitorCog className="btn-ico" /> Open Developer Workspace
              </button>
              {task.status === 'blocked' ? (
                <button type="button" className="outline" onClick={() => { select(task.story_id); goTo('independent_review') }}>
                  <ShieldCheck className="btn-ico" /> Open Independent Review
                </button>
              ) : (
                <button type="button" className="primary sq" disabled={!task.files_changed}
                  title={task.files_changed ? 'Re-runs the targeted tests for this task (simulated CI)' : 'No implementation changes recorded yet'}
                  onClick={() => act(`/tasks/${task.task_id}/verify`, {}, 'Targeted tests re-executed')}>
                  <RefreshCw className="btn-ico" /> Re-run Tests
                </button>
              )}
            </div>
          </div>
        ) : null}

        <div className="card info-banner" style={{ marginTop: '10px' }}>
          <Info className="btn-ico" style={{ marginTop: '1px' }} />
          <span>
            Evidence is collected from configured CI/CD systems — in this demo, from the deterministic
            simulation engine, badged SIMULATED. Select a build to inspect test results, quality metrics,
            acceptance-criteria coverage and generated artifacts.
          </span>
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card dp-inspector">
          <h3>{`${task.story_id} — ${task.task_id}`}</h3>
          {story?.title ? <p className="hint" style={{ marginBottom: '6px' }}>{story.title}</p> : null}
          <div className="drawer-badges" style={{ marginBottom: '8px' }}>
            <span className={`badge ${statusCls}`}>{statusLabel}</span>
            <Prov provenance={task.provenance} />
          </div>

          {ws?.artifact_status === 'stale' ? (
            <p className="hint dw-stale-note">
              <TriangleAlert className="dp-badge-ico" style={{ color: 'var(--amber-text)' }} />
              Workspace context is stale — evidence stays visible but the story cannot progress until the
              context is refreshed through the amendment path.
            </p>
          ) : null}

          <div className="dp-ins-block">
            <span className="as-label">Build Information</span>
            <div className="kv" style={{ gridTemplateColumns: '95px 1fr' }}>
              <b>Repository</b><span className="repo-cell"><Github /><span className="mono">{ws?.repository || '—'}</span></span>
              <b>Branch</b><span className="repo-cell"><GitBranch /><span className="mono">{ws?.branch || '—'}</span></span>
              <b>Commit</b><span className="mono">{ws?.current_commit ? ws.current_commit.slice(0, 7) : '—'}</span>
              <b>Committer</b><span>{ws?.developer || '—'}</span>
              <b>Pipeline</b><span className="mono">{task.task_id.replace('TASK', 'BUILD')}</span>
              <b>CI System</b><span>Simulated CI <Prov provenance="simulated" /></span>
              <b>Last Run</b><span>{task.last_activity ? hhmm(task.last_activity) : '—'}</span>
            </div>
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Test Summary</span>
            <div className="dp-ins-metrics">
              <span><span className="as-label">Passed</span><b style={{ color: 'var(--green)' }}>{String(passes)}</b></span>
              <span><span className="as-label">Failed</span><b style={{ color: failing.length ? 'var(--red-dark)' : 'inherit' }}>{String(failing.length)}</b></span>
              <span><span className="as-label">Total</span><b>{String(tests.length)}</b></span>
              <span><span className="as-label">Pass %</span><b>{tests.length ? `${Math.round((passes / tests.length) * 100)}%` : '—'}</b></span>
            </div>
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Coverage</span>
            {task.coverage_pct != null ? (
              <>
                <div className="cov-bar"><div className="cov-fill" style={{ width: `${task.coverage_pct}%` }} /></div>
                <span className="hint">{`Line coverage ${task.coverage_pct}%`}</span>
              </>
            ) : <span className="hint">Not measured yet.</span>}
          </div>

          <div className="dp-ins-block">
            <span className="as-label">{`Acceptance Criteria Coverage — ${acCovered} / ${acs.length}`}</span>
            <ul className="plain dp-contents">
              {acs.map((ac) => {
                const row = tests.find((t) => t.ac_id === ac.ac_id)
                return (
                  <li key={ac.ac_id} title={ac.text}>
                    <span className="mono val-label" style={{ flex: 'none' }}>{ac.ac_id}</span>
                    <span className="hint" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {row?.name ?? 'no linked test'}
                    </span>
                    {row
                      ? (row.current_result === 'passed'
                        ? <span className="badge st-passed">PASS</span>
                        : <span className="badge st-failed">FAIL</span>)
                      : <span className="badge st-planned">NOT COVERED</span>}
                  </li>
                )
              })}
              {acs.length === 0 ? <li className="hint">No acceptance criteria on the story.</li> : null}
            </ul>
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Quality Gates</span>
            {handoff ? (
              <ul className="plain dp-contents">
                {handoff.checks.map((c) => (
                  <li key={c.condition} title={c.detail}>
                    {c.met ? <CircleCheck className="val-ico ok" /> : <Circle className="val-ico" style={{ color: 'var(--muted)' }} />}
                    <span className="val-label">{c.condition}</span>
                    <span className={`badge ${c.met ? 'st-passed' : 'st-planned'}`}>{c.met ? 'PASSED' : 'NOT MET'}</span>
                  </li>
                ))}
              </ul>
            ) : <span className="hint">Gates appear once the build summary is computed.</span>}
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Red → Code → Green</span>
            <div className="rcg">
              {timelineSteps.map(([cls, label, ts, note], i) => (
                <Fragment key={cls}>
                  {i > 0 ? <span className="rcg-line" /> : null}
                  <div className={`rcg-node ${cls} ${ts ? '' : 'pending'}`}>
                    <span className="rcg-dot" />
                    <b>{label}</b>
                    <span className="mono hint">{ts ? hhmm(ts) : 'pending'}</span>
                    <span className="hint">{note}</span>
                  </div>
                </Fragment>
              ))}
            </div>
          </div>

          <div className="dp-ins-actions">
            <button className="outline block" onClick={() => window.open(`/api/runs/${runId}/tasks/${task.task_id}/evidence.zip`, '_blank')}
              disabled={!(task.tests ?? []).length && !task.files_changed}>
              <Download className="btn-ico" /> Export Evidence ZIP
            </button>
            <button className="outline block" disabled title="No external CI to open in simulation">
              <ExternalLink className="btn-ico" /> Open CI Pipeline
            </button>
            {task.status === 'waiting_for_approval' ? (
              <button className="primary block" onClick={() => { select(task.story_id); goTo('independent_review') }}>
                <ShieldCheck className="btn-ico" /> In Independent Review — open
              </button>
            ) : (
              <button className="primary block" disabled={!canSubmit}
                title={canSubmit ? undefined : 'Enabled when the build is verified (deterministic checks), never by AI confidence'}
                onClick={() => act(`/tasks/${task.task_id}/submit-review`, {}, 'Submitted for independent review')}>
                <ShieldCheck className="btn-ico" /> Submit for Independent Review
              </button>
            )}
          </div>
        </div>
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
