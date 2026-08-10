/**
 * Independent Review — the governed review checkpoint before Final Gating. The
 * review is executed by an ISOLATED reviewer (simulated in demo mode, a live
 * model in live mode) that never authored the implementation; its verdict is
 * recorded immutably and re-review creates a new version. Humans route
 * rework back to the developer; nobody approves their own work here.
 *
 * Honesty: there are no Approve/Reject buttons because no such engine action
 * exists — the isolated verdict is the approval. The quality score is a
 * derived checkpoint pass rate, informational only, never stored and never
 * the decision. Reviewer names are the real reviewer role labels, badged
 * with their provenance.
 */
import { useMemo, useState } from 'react'
import {
  Circle, CircleAlert, CircleCheck, CircleX, ClipboardCheck, ClipboardList,
  Clock3, Eye, GitBranch, GitCommitHorizontal, GitFork, Github, History,
  GitPullRequest, Info, ListChecks, MonitorCog, PackageCheck, RefreshCcw, RotateCcw, Search,
  ShieldCheck, TriangleAlert, UserRound,
} from 'lucide-react'
import { Prov } from '../../components/Badge'
import { StatCard } from '../../components/StatCard'
import { useRun } from '../../state/RunContext'
import type {
  BuildTask, DeveloperWorkspace, PlanStory, ReviewRecord,
} from '../../types'
import {
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  githubLinks,
  GuidanceCard,
  hhmm,
  selectStory,
  selectedStory,
} from './buildHelpers'

type CheckState = 'passed' | 'partial' | 'failed' | 'not_reviewed'

interface Checkpoint {
  name: string
  state: CheckState
  detail: string
}

/** Derived review checkpoints — stated rules over recorded signals only. */
function checkpoints(
  task: BuildTask,
  story: PlanStory | undefined,
  ws: DeveloperWorkspace | undefined,
  review: ReviewRecord | undefined,
): Checkpoint[] {
  const tests = task.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const linked = acs.filter((a) => tests.some((t) => t.ac_id === a.ac_id)).length
  const failing = tests.filter((t) => t.current_result === 'failed').length
  const rows: Checkpoint[] = []

  rows.push({
    name: 'Requirements Traceability',
    state: review ? ((review.verified_against ?? []).length ? 'passed' : 'not_reviewed') : 'not_reviewed',
    detail: review?.verified_against?.length
      ? `Verified against ${review.verified_against.join(', ')}`
      : 'Recorded once the isolated reviewer executes',
  })
  rows.push({
    name: 'Acceptance Criteria Coverage',
    state: acs.length === 0 ? 'not_reviewed' : linked === acs.length ? 'passed' : linked > 0 ? 'partial' : 'failed',
    detail: `${linked} of ${acs.length} acceptance criteria have linked tests`,
  })
  rows.push({
    name: 'Test Evidence Validation',
    state: tests.length === 0 ? 'not_reviewed' : failing === 0 ? 'passed' : 'failed',
    detail: tests.length ? `${tests.length - failing} of ${tests.length} tests passing` : 'No test evidence yet',
  })
  rows.push({
    name: 'Code Quality & Standards',
    state: review ? (review.minor_gaps === 0 ? 'passed' : 'partial') : 'not_reviewed',
    detail: review ? `${review.minor_gaps} minor gap(s) recorded` : 'Recorded by the isolated reviewer',
  })
  rows.push({
    name: 'Independent Findings',
    state: review ? (review.critical_gaps + review.major_gaps > 0 ? 'failed' : 'passed') : 'not_reviewed',
    detail: review
      ? `${review.critical_gaps} critical · ${review.major_gaps} major`
      : 'Recorded by the isolated reviewer',
  })
  rows.push({
    name: 'Context Freshness',
    state: ws ? (ws.artifact_status === 'stale' ? 'failed' : 'passed') : 'not_reviewed',
    detail: ws?.artifact_status === 'stale'
      ? 'Workspace context is stale — refresh through the amendment path'
      : 'Delivery pack and workspace context are current',
  })
  return rows
}

/** Informational only — the isolated reviewer's verdict is authoritative. */
function scoreOf(rows: Checkpoint[]): number | null {
  const reviewed = rows.filter((r) => r.state !== 'not_reviewed')
  if (!reviewed.length) return null
  const points = reviewed.reduce(
    (n, r) => n + (r.state === 'passed' ? 1 : r.state === 'partial' ? 0.5 : 0), 0)
  return Math.round((points / reviewed.length) * 100)
}

type ReviewStatus = 'not_ready' | 'in_review' | 'approved' | 'rework'

function statusOf(task: BuildTask): ReviewStatus {
  if (task.status === 'completed') return 'approved'
  if (task.status === 'blocked') return 'rework'
  if (task.status === 'waiting_for_approval') return 'in_review'
  return 'not_ready'
}

const STATUS_UI: Record<ReviewStatus, [string, string]> = {
  not_ready: ['NOT READY', 'st-planned'],
  in_review: ['IN REVIEW', 'st-waiting_for_approval'],
  approved: ['APPROVED', 'st-passed'],
  rework: ['REWORK REQUIRED', 'st-blocked'],
}

const CHECK_UI: Record<CheckState, [string, string]> = {
  passed: ['Passed', 'st-passed'],
  partial: ['Partially Passed', 'st-planned'],
  failed: ['Failed', 'st-failed'],
  not_reviewed: ['Not Reviewed', 'st-planned'],
}

function CheckIcon({ state }: { state: CheckState }) {
  if (state === 'passed') return <CircleCheck className="val-ico ok" />
  if (state === 'partial') return <CircleAlert className="val-ico warn" />
  if (state === 'failed') return <CircleX className="val-ico bad" />
  return <Circle className="val-ico" style={{ color: 'var(--muted)' }} />
}

export function IndependentReview() {
  const { data, act, goTo } = useRun()
  const [selId, setSelId] = useState<string | null>(selectedStory())
  const [query, setQuery] = useState('')
  const [fTeam, setFTeam] = useState('all')
  const [fStatus, setFStatus] = useState('all')
  const [openCheck, setOpenCheck] = useState<string | null>(null)

  const build = buildOf(data)
  const tasks = build.tasks ?? []
  const reviews = build.reviews ?? []
  const workspaces = build.workspaces ?? []
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const storyById = useMemo(() => new Map(stories.map((s) => [s.story_id, s])), [stories])
  const wsByStory = useMemo(() => new Map(workspaces.map((w) => [w.story_id, w])), [workspaces])
  const reviewsFor = (taskId: string) => reviews.filter((r) => r.task_id === taskId)
  const latestFor = (taskId: string) => {
    const rs = reviewsFor(taskId)
    return rs.length ? rs[rs.length - 1] : undefined
  }

  if (!data) return null

  const select = (storyId: string) => { selectStory(storyId); setSelId(storyId) }
  const teamOf = (t: BuildTask) => t.accountable_team || storyById.get(t.story_id)?.accountable_team || '—'

  // Review items = tasks that have reached the review lifecycle.
  const items = tasks.filter((t) =>
    ['waiting_for_approval', 'blocked', 'completed'].includes(t.status) || reviewsFor(t.task_id).length > 0,
  )

  const approved = items.filter((t) => statusOf(t) === 'approved').length
  const inReview = items.filter((t) => statusOf(t) === 'in_review').length
  const rework = items.filter((t) => statusOf(t) === 'rework').length
  const scores = items
    .map((t) => scoreOf(checkpoints(t, storyById.get(t.story_id), wsByStory.get(t.story_id), latestFor(t.task_id))))
    .filter((s): s is number => s != null)
  const avgScore = scores.length ? Math.round(scores.reduce((a, b) => a + b, 0) / scores.length) : null

  const teams = [...new Set(items.map(teamOf).filter((t) => t !== '—'))]
  const filtered = items.filter((t) => {
    if (fTeam !== 'all' && teamOf(t) !== fTeam) return false
    if (fStatus !== 'all' && statusOf(t) !== fStatus) return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      if (!`${t.story_id} ${t.task_id} ${teamOf(t)}`.toLowerCase().includes(q)) return false
    }
    return true
  })

  const task = filtered.find((t) => t.story_id === selId)
    ?? items.find((t) => t.story_id === selId)
    ?? filtered.find((t) => statusOf(t) === 'in_review')
    ?? filtered.find((t) => statusOf(t) === 'rework')
    ?? filtered[0]
    ?? items[0]

  if (!task) {
    return (
      <section className="page-with-rail bo-compact">
        <div>
          <div className="page-head" style={{ marginBottom: '8px' }}>
            <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Independent Review</span>
          </div>
          <div className="card">
            <h3><ShieldCheck className="btn-ico" /> No Items Ready for Independent Review</h3>
            <p>Build &amp; Test Evidence must meet the deterministic readiness checks before a review can begin.</p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="primary" onClick={() => goTo('test_evidence')}>
                <ClipboardCheck className="btn-ico" /> View Build &amp; Test Evidence
              </button>
            </div>
          </div>
        </div>
        <aside className="rail"><GuidanceCard lines={CONTROL_PLANE_GUIDANCE} /></aside>
      </section>
    )
  }

  // --- selected item ---------------------------------------------------------
  const story = storyById.get(task.story_id)
  const ws = wsByStory.get(task.story_id)
  const links = githubLinks(ws, data.intake?.repos)
  const review = latestFor(task.task_id)
  const history = reviewsFor(task.task_id)
  const pack = (build.delivery_packs ?? []).find((p) => p.team === teamOf(task))
  const checks = checkpoints(task, story, ws, review)
  const score = scoreOf(checks)
  const [statusLabel, statusCls] = STATUS_UI[statusOf(task)]
  const counts = {
    passed: checks.filter((c) => c.state === 'passed').length,
    partial: checks.filter((c) => c.state === 'partial').length,
    failed: checks.filter((c) => c.state === 'failed').length,
    notReviewed: checks.filter((c) => c.state === 'not_reviewed').length,
  }
  const findings = review?.findings ?? []
  const stale = ws?.artifact_status === 'stale'
  const reviewerLabel = review?.reviewer
    ?? (data.run.mode === 'live'
      ? 'independent-reviewer (live model, isolated from development)'
      : data.run.mode === 'demo'
        ? 'independent-reviewer (demo, isolated from development)'
        : 'independent-reviewer (simulated, isolated from development)')
  const trace = [
    ['REQ', 'REQ-2026-114'],
    ['Plan', `PLAN v${data.planning?.plan?.plan_version ?? '—'}`],
    ['Arch', build.architecture ? `ARCH v${build.architecture.version}` : '—'],
    ['Pack', pack ? `${pack.delivery_pack_id} v${pack.version}` : '—'],
    ['Story', task.story_id],
    ['Task', task.task_id],
    ['Commit', ws?.current_commit ? ws.current_commit.slice(0, 7) : '—'],
    ['Review', review?.review_id ?? '—'],
  ]

  return (
    <section className="page-with-rail bo-compact dp-page">
      <div>
        <div className="page-head" style={{ marginBottom: '4px' }}>
          <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Independent Review</span>
        </div>
        <div className="page-head" style={{ marginBottom: '10px' }}>
          <h2>Independent Review <ShieldCheck className="ir-title-ico" /></h2>
          <span className="hint">
            Structured review of implementation quality, test evidence and adherence to the approved engineering
            context — executed by a reviewer isolated from development.
          </span>
        </div>

        <div className="stat-row">
          <StatCard accent="blue" icon={<ClipboardList />} value={String(items.length)} label="Reviews" sub="All review items" />
          <StatCard accent="green" icon={<CircleCheck />} value={String(approved)} label="Approved" sub={items.length ? `${Math.round((approved / items.length) * 100)}% approved` : '—'} />
          <StatCard accent="orange" icon={<Clock3 />} value={String(inReview)} label="In Review" sub="Awaiting isolated reviewer" />
          <StatCard accent="purple" icon={<RefreshCcw />} value={String(rework)} label="Rework Required" sub={rework ? 'Returned to developers' : 'None'} />
          <StatCard accent="red" icon={<CircleX />} value="0" label="Rejected" sub="No reject path in this flow" />
          <StatCard accent="teal" icon={<ShieldCheck />} value={avgScore != null ? `${avgScore}%` : '—'} label="Avg. Quality Score" sub="Derived — verdict is authoritative" />
        </div>

        <div className="card dp-filters">
          <span className="dp-search">
            <Search className="dp-search-ico" />
            <input type="text" placeholder="Search by story, task, team…"
              value={query} onChange={(e) => setQuery(e.target.value)} />
          </span>
          <label className="dp-filter"><span>Team</span>
            <select value={fTeam} onChange={(e) => setFTeam(e.target.value)}>
              <option value="all">All</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <label className="dp-filter"><span>Review Status</span>
            <select value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
              <option value="all">All</option>
              <option value="in_review">In Review</option>
              <option value="approved">Approved</option>
              <option value="rework">Rework Required</option>
            </select>
          </label>
          <button className="ghost" onClick={() => { setQuery(''); setFTeam('all'); setFStatus('all') }}>
            <RotateCcw className="btn-ico" /> Reset
          </button>
        </div>

        <div className="card">
          <div className="table-wrap">
            <table className="dp-table dw-table">
              <colgroup>
                <col style={{ width: '17%' }} /><col style={{ width: '13%' }} /><col style={{ width: '20%' }} />
                <col style={{ width: '14%' }} /><col style={{ width: '12%' }} /><col style={{ width: '12%' }} />
                <col style={{ width: '12%' }} />
              </colgroup>
              <thead>
                <tr>
                  <th>Review Item</th><th>Team</th><th>Reviewer</th><th>Review Status</th>
                  <th>Quality Score</th><th>Started At</th><th>Completed At</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((t) => {
                  const r = latestFor(t.task_id)
                  const [lbl, cls] = STATUS_UI[statusOf(t)]
                  const s = scoreOf(checkpoints(t, storyById.get(t.story_id), wsByStory.get(t.story_id), r))
                  const team = teamOf(t)
                  const initials = team.split(/\s+/).map((x) => x[0]).join('').slice(0, 2).toUpperCase()
                  const reviewed = r != null
                  return (
                    <tr key={t.task_id}
                      className={task.task_id === t.task_id ? 'dp-row-selected' : ''}
                      onClick={() => select(t.story_id)}>
                      <td>
                        <b className="mono">{t.story_id}</b>
                        <span className="hint dp-sub dw-title clamp-2">{storyById.get(t.story_id)?.title ?? ''}</span>
                        <span className="hint dp-sub mono"><ListChecks className="dp-badge-ico" />{t.task_id}</span>
                      </td>
                      <td>
                        <span className="dp-team">
                          <span className={`team-avatar ${['tc-0', 'tc-1', 'tc-2', 'tc-3', 'tc-4'][team.length % 5]}`}>{initials}</span>
                          <span className="hint">{team}</span>
                        </span>
                      </td>
                      <td>
                        <span className="dp-team">
                          <span className="team-avatar tc-1"><ShieldCheck style={{ width: 13, height: 13 }} /></span>
                          <span>
                            Independent Reviewer
                            <span className="hint dp-sub">{reviewed ? 'Isolated from development' : 'Executes on submission'}</span>
                          </span>
                        </span>
                      </td>
                      <td><span className={`badge ${cls}`}>{lbl}</span></td>
                      <td>
                        {s != null ? (
                          <>
                            <span className="mono">{`${s}%`}</span>
                            <div className="cov-bar ir-score-bar"><div className={`cov-fill${s < 60 ? ' bad' : ''}`} style={{ width: `${s}%` }} /></div>
                          </>
                        ) : <span className="hint">—</span>}
                      </td>
                      <td>{r ? hhmm(r.created_at) : t.last_activity ? hhmm(t.last_activity) : '—'}</td>
                      <td>{statusOf(t) === 'approved' && r ? hhmm(r.created_at) : '—'}</td>
                    </tr>
                  )
                })}
                {filtered.length === 0 ? (
                  <tr><td colSpan={7}><span className="hint">No review items match the current filters.</span></td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="dp-table-foot hint">{`Showing ${filtered.length} of ${items.length} review items · select a row to inspect`}</div>
        </div>

        <div className="card info-banner" style={{ marginTop: '10px' }}>
          <Info className="btn-ico" style={{ marginTop: '1px' }} />
          <span>
            Independent Review is isolated from development: the reviewer never authored the implementation and
            the run's operators cannot approve their own work. AI assistance is advisory only — findings and
            verdicts are recorded immutably, and rework routing is a human decision.
          </span>
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card dp-inspector">
          <h3>{`${task.story_id} — ${task.task_id}`}</h3>
          {story?.title ? <p className="hint" style={{ marginBottom: '6px' }}>{story.title}</p> : null}
          <div className="drawer-badges" style={{ marginBottom: '8px' }}>
            <span className={`badge ${statusCls}`}>{statusLabel}</span>
            {review ? <Prov provenance={task.provenance} /> : null}
            {review ? <span className="hint">{`Reviewed ${hhmm(review.created_at)}`}</span> : null}
          </div>

          {stale ? (
            <p className="hint dw-stale-note">
              <TriangleAlert className="dp-badge-ico" style={{ color: 'var(--amber-text)' }} />
              Context is stale — the review package must be refreshed through the amendment path before this
              item can progress.
            </p>
          ) : null}

          <div className="dp-ins-block">
            <span className="as-label">Review Summary</span>
            <div className="ir-summary">
              <div className="ir-ring" style={{
                background: score != null
                  ? `conic-gradient(var(--green) ${score * 3.6}deg, var(--surface-2) 0deg)`
                  : 'var(--surface-2)',
              }}>
                <span>{score != null ? `${score}%` : '—'}</span>
              </div>
              <ul className="plain ir-summary-list">
                <li><b style={{ color: 'var(--green)' }}>{counts.passed}</b> Passed</li>
                <li><b style={{ color: 'var(--amber-text)' }}>{counts.partial}</b> Partially Passed</li>
                <li><b style={{ color: 'var(--red-dark)' }}>{counts.failed}</b> Failed</li>
                <li><b className="hint">{counts.notReviewed}</b> Not Reviewed</li>
              </ul>
            </div>
            <span className="hint">Derived checkpoint pass rate — informational; the verdict is authoritative.</span>
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Review Details</span>
            <div className="kv" style={{ gridTemplateColumns: '105px 1fr' }}>
              <b>Reviewer</b><span><UserRound className="dp-badge-ico" />{reviewerLabel}</span>
              <b>Team</b><span>{teamOf(task)}</span>
              <b>Repository</b><span className="repo-cell"><Github />
                {links.repoUrl
                  ? <a className="mono" href={links.repoUrl} target="_blank" rel="noopener noreferrer">{ws?.repository || '—'}</a>
                  : <span className="mono">{ws?.repository || '—'}</span>}
              </span>
              <b>Branch</b><span className="repo-cell"><GitBranch />
                {links.branchUrl
                  ? <a className="mono" href={links.branchUrl} target="_blank" rel="noopener noreferrer">{ws?.branch || '—'}</a>
                  : <span className="mono">{ws?.branch || '—'}</span>}
              </span>
              <b>Pull Request</b><span className="mono"><GitPullRequest className="dp-badge-ico" />
                {links.prUrl
                  ? <a href={links.prUrl} target="_blank" rel="noopener noreferrer">{ws?.pull_request}</a>
                  : (ws?.pull_request || '—')}
                {!links.prUrl && ws?.pull_request
                  ? (data.run.mode === 'demo'
                    ? <span className="hint" title="Demo PR — no remote to open"> (demo)</span>
                    : <span className="hint" title="Simulated PR — no remote to open"> (simulated)</span>)
                  : null}
              </span>
              <b>Commit</b><span className="mono"><GitCommitHorizontal className="dp-badge-ico" />
                {links.commitUrl
                  ? <a href={links.commitUrl} target="_blank" rel="noopener noreferrer">{ws?.current_commit?.slice(0, 7) ?? '—'}</a>
                  : (ws?.current_commit ? ws.current_commit.slice(0, 7) : '—')}
              </span>
              <b>Delivery Pack</b>
              <span><PackageCheck className="dp-badge-ico" />{pack ? `v${pack.version}` : '—'}{' '}
                {stale ? <span className="badge st-stale">STALE</span> : <span className="badge st-ready">CURRENT</span>}</span>
              <b>Evidence</b>
              <span><ClipboardCheck className="dp-badge-ico" />
                {(task.tests ?? []).length ? `${(task.tests ?? []).length} tests` : '—'}</span>
            </div>
          </div>

          <div className="dp-ins-block">
            <span className="as-label">Review Checkpoints</span>
            <ul className="plain dp-contents">
              {checks.map((c) => {
                const [lbl, cls] = CHECK_UI[c.state]
                const open = openCheck === c.name
                return (
                  <li key={c.name} style={{ flexDirection: 'column', alignItems: 'stretch' }}>
                    <button type="button" className="ir-check-row"
                      onClick={() => setOpenCheck(open ? null : c.name)} aria-expanded={open}>
                      <CheckIcon state={c.state} />
                      <span className="val-label">{c.name}</span>
                      <span className={`badge ${cls}`}>{lbl}</span>
                    </button>
                    {open ? <p className="hint" style={{ margin: '2px 0 4px 20px' }}>{c.detail}</p> : null}
                  </li>
                )
              })}
            </ul>
            <span className="hint">Derived from recorded evidence and the isolated reviewer's findings.</span>
          </div>

          {findings.length ? (
            <div className="dp-ins-block">
              <span className="as-label">Findings</span>
              {findings.map((f, i) => (
                <div className="ir-finding" key={f.finding_id ?? i}>
                  <b>
                    <span className={`sev-chip ${f.severity === 'critical' ? 'critical' : f.severity === 'major' ? 'high' : 'medium'}`}>
                      {f.severity.toUpperCase()}
                    </span>{' '}
                    {`${f.ac_id}${f.summary ? ` — ${f.summary}` : ''}`}
                  </b>
                  <div className="finding-detail">
                    {f.expected ? <div><b>Expected: </b>{f.expected}</div> : null}
                    {f.observed ? <div><b>Observed: </b>{f.observed}</div> : null}
                    {f.impact ? <div><b>Impact: </b>{f.impact}</div> : null}
                    {f.recommendation ? <div><b>Reviewer note: </b>{f.recommendation}</div> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}

          {history.length ? (
            <div className="dp-ins-block">
              <span className="as-label"><History className="dp-badge-ico" /> Review History</span>
              <ul className="plain dp-contents">
                {history.map((r) => (
                  <li key={r.review_id}>
                    <span className="mono val-label" style={{ flex: 'none' }}>{r.review_id}</span>
                    <span className="hint" style={{ flex: 1 }}>{hhmm(r.created_at)}</span>
                    <span className={`badge ${r.result === 'passed' ? 'st-passed' : 'st-blocked'}`}>
                      {r.result === 'passed' ? 'APPROVED' : 'REWORK REQUIRED'}
                    </span>
                  </li>
                ))}
              </ul>
              <span className="hint">Each re-review is a new immutable version — history is never overwritten.</span>
            </div>
          ) : null}

          <div className="dp-ins-block">
            <span className="as-label"><GitFork className="dp-badge-ico" /> Traceability</span>
            <div className="ir-trace">
              {trace.map(([k, v], i) => (
                <span key={k}>
                  {i > 0 ? <span className="hint"> → </span> : null}
                  <span className="chip mono" title={k}>{v}</span>
                </span>
              ))}
            </div>
          </div>

          <div className="dp-ins-actions">
            <button className="outline block" onClick={() => { select(task.story_id); goTo('test_evidence') }}>
              <Eye className="btn-ico" /> View Evidence
            </button>
            {task.status === 'waiting_for_approval' ? (
              <button className="primary block"
                title="Runs the isolated independent reviewer (requires the independent reviewer role)"
                onClick={() => act(`/reviews/${task.task_id}/execute`, {}, 'Independent review executed')}>
                <ShieldCheck className="btn-ico" /> Execute Independent Review
              </button>
            ) : null}
            {task.status === 'blocked' ? (
              <>
                <button className="outline block"
                  onClick={() => { select(task.story_id); goTo('developer_workspaces') }}>
                  <MonitorCog className="btn-ico" /> Open Developer Workspace
                </button>
                <button className="primary block"
                  title="Returns the task to the developer with the findings attached"
                  onClick={() => act(`/reviews/${task.task_id}/return-to-development`, {}, 'Returned to development with findings')}>
                  <RefreshCcw className="btn-ico" /> Request Rework
                </button>
              </>
            ) : null}
            {statusOf(task) === 'approved' ? (
              <p className="hint">
                <CircleCheck className="dp-badge-ico" style={{ color: 'var(--green)' }} />
                Approved by the isolated reviewer{review ? ` (${review.review_id})` : ''} — progresses to
                Final Gating via the deterministic handoff conditions.
              </p>
            ) : null}
          </div>
        </div>
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
