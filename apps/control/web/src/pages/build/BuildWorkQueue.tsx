import { Fragment, useState } from 'react'
import { Badge } from '../../components/Badge'
import { SectionTitle } from '../../components/SectionTitle'
import { useRun } from '../../state/RunContext'
import type { ActivityEvent, RunState } from '../../types'

// --- local shapes -----------------------------------------------------------
// Mirrors the task / story / review objects produced by `buildTasks()`,
// `planningStories()` and `reviewsFor()` in apps/control/static/app.js (see
// renderBuildWorkQueue, ~line 1936-2080), which in turn mirror
// `s7_delivery/factory/models.py` (TaskRecord, Story, ReviewReport).
// `RunState` has no typed `build` / `planning` section yet — `data.build` and
// `data.planning` fall through its index signature as `unknown`, so these are
// applied with a local cast, the same pattern every other Phase-3 page under
// concurrent construction uses (TestEvidence.tsx, DevProgress.tsx,
// RoutingByTeam.tsx, IndependentReview.tsx all define their own local
// shapes rather than share one, because the shared shape has been rewritten
// several times mid-flight). See the port report for the exact types.ts
// additions this page needs once that churn settles.

export interface TestCaseRecord {
  test_id: string
  name: string
  ac_id: string
  initial_result: string
  current_result: string
  evidence_ref?: string
}

export interface BuildTask {
  task_id: string
  story_id: string
  summary: string
  accountable_team: string
  owner?: string
  status: string
  dependencies?: string[]
  progress_pct: number
  current_activity?: string
  files_changed: number
  lines_added: number
  lines_removed: number
  tests?: TestCaseRecord[]
  coverage_pct?: number
  last_activity?: string
}

export interface BuildReview {
  review_id: string
  task_id: string
  major_gaps: number
}

interface BuildStateLocal {
  tasks?: BuildTask[]
  reviews?: BuildReview[]
}

interface PlanFeatureFlag {
  name: string
  default_state?: string
}

interface PlanRollbackPlan {
  method: string
  tested?: boolean
}

export interface PlanStoryLite {
  story_id: string
  target_component?: string
  feature_flag?: PlanFeatureFlag | null
  rollback_plan?: PlanRollbackPlan | null
}

interface PlanningStateLocal {
  stories?: PlanStoryLite[]
  plan?: { story_ids?: string[] } | null
}

// ActivityEvent in types.ts already carries `artifact`; kept as a local alias
// since nothing else here needs a full import-and-rename.
type TaskActivityEvent = ActivityEvent

const WORKFLOW_LABELS: Record<string, string> = {
  'task-start': 'Workspace created and context analysed',
  'test-first': 'Tests generated and red baseline captured',
  development: 'Code changes implemented',
  'developer-verification': 'Build and targeted tests executed',
  'submit-review': 'Submitted for independent review',
  'independent-review-gate': 'Independent review executed',
  'return-to-development': 'Returned to development',
}

// Mirrors apps/control/static/app.js TEAMS / TEAM_COLORS (~line 805, 1308) —
// duplicated per-page like everywhere else in this porting phase; order
// matters, it is what keeps a team's color stable across the app.
const TEAMS = [
  'Portal Team', 'Services Team', 'Data Team',
  'Intake Integration Team', 'QA Automation', 'Platform Team', 'Support Team',
]

const TEAM_COLORS = ['#2c5f8f', '#7a4b9b', '#1e7a46', '#a8781f', '#b0243a', '#0f766e', '#5a6b7d']

function teamColor(name: string): string {
  let i = TEAMS.indexOf(name)
  if (i === -1) i = [...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0)
  return TEAM_COLORS[i % TEAM_COLORS.length]
}

function TeamChip({ name }: { name?: string }) {
  if (!name) return <span>—</span>
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  return (
    <span className="team-chip">
      <span className="avatar">{initials}</span>
      {name}
    </span>
  )
}

function hhmm(iso?: string | null): string {
  return (iso ?? '').slice(11, 16) || '—'
}

function relTime(iso: string): string {
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000)
  if (s < 90) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  if (s < 86400) return `${Math.round(s / 3600)}h ago`
  return iso.slice(0, 10)
}

function checkItem(ok: boolean, label: string, extra?: string | number) {
  return (
    <li>
      <span className={`tick ${ok ? 'ok' : 'no'}`}>{ok ? '✓' : '·'}</span>
      {label}
      {extra != null ? <span className="state ok mono">{String(extra)}</span> : null}
    </li>
  )
}

function GuidanceCard() {
  return (
    <div className="card rail-card guidance">
      <h3>✓ Customer-safe guidance</h3>
      <p className="hint">This is a customer-safe view. No IDE, code, CLI, logs, or system internals are shown.</p>
      <p className="hint">Only governed execution evidence and status are visible.</p>
      <p className="hint">All work is traceable, human-approved and audit-ready.</p>
    </div>
  )
}

function PauseButton() {
  return (
    <button
      type="button"
      className="outline block"
      disabled
      title="The demo engine advances in discrete governed steps — there is no long-running process to pause, so this control is honestly disabled rather than mocked."
    >
      ⏸ Pause Run
    </button>
  )
}

const AGENT_PIPELINE: Array<[string, string, string]> = [
  ['⚗', 'AI Test Engineer', 'Generates tests from ACs'],
  ['⌨', 'AI Developer', 'Implements code against tests'],
  ['▶', 'AI Test Engineer', 'Executes tests and verifies'],
  ['◈', 'Independent AI Reviewer', 'Validates changes independently'],
  ['✍', 'Human Approval', 'Approves or returns for changes'],
]

function AgentPipelineCard() {
  return (
    <div className="card">
      <div className="section-title">
        <h3>AI agents collaborate to implement, test and independently review changes</h3>
        <span className="hint">Roles enforced by the engine — no phase self-approves</span>
      </div>
      <div className="agent-flow">
        {AGENT_PIPELINE.map(([ico, name, desc], i) => (
          <Fragment key={i}>
            {i > 0 ? <span className="agent-arrow">→</span> : null}
            <div className={`agent-box ${i === AGENT_PIPELINE.length - 1 ? 'human' : ''}`}>
              <span className="agent-ico">{ico}</span>
              <b>{name}</b>
              <span className="hint">{desc}</span>
            </div>
          </Fragment>
        ))}
      </div>
    </div>
  )
}

function BuildAiPanels({ tasks, data }: { tasks: BuildTask[]; data: RunState }) {
  const acts = ((data.activity ?? []) as TaskActivityEvent[])
    .filter((a) => a.actor_type === 'simulation' && a.artifact?.startsWith('TASK-'))
    .slice(-4)
    .reverse()
  const tests = tasks.flatMap((t) => t.tests ?? [])
  const green = tests.filter((t) => t.current_result === 'passed').length
  const reviews = ((data.build as BuildStateLocal | undefined)?.reviews) ?? []
  const majors = reviews.reduce((a, r) => a + r.major_gaps, 0)
  const plan = (data.planning as PlanningStateLocal | undefined)?.plan
  const planned = new Set(plan?.story_ids ?? [])
  const inScope = tasks.every((t) => planned.has(t.story_id))

  return (
    <div className="grid cols-2" style={{ marginTop: 14 }}>
      <div className="card">
        <h3>AI Activity (Live)</h3>
        {acts.length ? (
          <ul className="checklist">
            {acts.map((a, i) => (
              <li key={i}>
                <span className="tick ok">✓</span>
                {`${a.artifact} — ${WORKFLOW_LABELS[a.workflow ?? ''] ?? a.workflow}`}
                <span className="state ok">{relTime(a.timestamp)}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="hint">No agent activity yet — start a task.</p>
        )}
      </div>
      <div className="card">
        <h3>Key AI Insights</h3>
        <p className="hint">Computed from run evidence, never asserted.</p>
        <ul className="checklist">
          {checkItem(
            tests.length > 0,
            `${tests.length ? Math.round((100 * green) / tests.length) : 0}% of targeted tests passing across started stories`,
          )}
          {checkItem(
            majors === 0,
            majors === 0 ? 'No major findings open from independent review' : `${majors} major finding(s) raised by the reviewer`,
          )}
          {checkItem(inScope, 'All changes map to stories in the signed plan')}
        </ul>
      </div>
    </div>
  )
}

/**
 * Ports apps/control/static/app.js `renderBuildWorkQueue` (~line 1936-2080).
 *
 * Note on `openTechnicalDetailModal` (~line 2157-2182), named as this page's
 * companion in the porting brief: in the vanilla source it is only ever
 * invoked from `renderDevProgress` (the "⚙ Technical Detail" button, gated to
 * engineering_lead / qa_lead roles) — `renderBuildWorkQueue` itself never
 * calls it, confirmed by reading the full function body. A concurrent port of
 * Development Progress already exists at
 * `apps/control/web/src/pages/build/DevProgress.tsx` with a complete, working
 * local `TechnicalDetailModal` driven by `useState` + conditional rendering
 * (the pattern this page's brief also asked for). Duplicating an unreachable
 * copy here — this page has no trigger for it in the vanilla source — would
 * be dead UI, not a behavior-preserving port, so it was deliberately left out
 * of this file.
 */
export function BuildWorkQueue() {
  const { data, act, goTo } = useRun()
  const [taskSearch, setTaskSearch] = useState('')
  const [taskId, setTaskId] = useState<string | null>(null)

  if (!data) return null

  const tasks = ((data.build as BuildStateLocal | undefined)?.tasks) ?? []
  if (!tasks.length) {
    return (
      <section>
        <SectionTitle title="Build & Independent Review" />
        <div className="card">
          <p>The work queue is seeded when the plan is signed at Gate 1.</p>
        </div>
      </section>
    )
  }

  const search = taskSearch.toLowerCase()
  const shown = search
    ? tasks.filter((t) => `${t.task_id} ${t.story_id} ${t.summary} ${t.accountable_team}`.toLowerCase().includes(search))
    : tasks

  const task =
    tasks.find((t) => t.task_id === taskId) ??
    tasks.find((t) => t.status === 'in_progress') ??
    tasks.find((t) => t.status !== 'completed') ??
    tasks[0]

  const stories = ((data.planning as PlanningStateLocal | undefined)?.stories) ?? []
  const story = stories.find((s) => s.story_id === task?.story_id)

  const count = (st: string) => tasks.filter((t) => t.status === st).length
  const readiness = Math.round(tasks.reduce((a, t) => a + t.progress_pct, 0) / tasks.length)
  const depsDone = (t: BuildTask) => (t.dependencies ?? []).every((d) => tasks.find((x) => x.task_id === d)?.status === 'completed')
  const readyToStart = tasks.filter((t) => ['ready', 'not_started'].includes(t.status) && depsDone(t))
  const teams = [...new Set(tasks.map((t) => t.accountable_team))]

  let acc = 0
  const donutStops = teams
    .map((t) => {
      const n = tasks.filter((x) => x.accountable_team === t).length
      const stop = `${teamColor(t)} ${(360 * acc) / tasks.length}deg ${(360 * (acc + n)) / tasks.length}deg`
      acc += n
      return stop
    })
    .join(', ')

  const blockedTasks = tasks.filter((t) => t.status === 'blocked')
  const waitingTasks = tasks.filter((t) => t.status !== 'completed' && !depsDone(t))

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Build &amp; Independent Review</h2>
          <span className="hint">Customer-safe execution view for development, test-first validation and independent review.</span>
        </div>

        <div className="tiles">
          <div className="tile t-red"><div className="v">{count('not_started') + count('ready')}</div><div className="l">Tasks in Queue</div></div>
          <div className="tile t-blue"><div className="v">{count('in_progress') + count('waiting_for_approval')}</div><div className="l">Tasks In Progress</div></div>
          <div className="tile t-amber"><div className="v">{count('blocked')}</div><div className="l">Blocked Tasks</div></div>
          <div className="tile t-green"><div className="v">{count('completed')}</div><div className="l">Completed Tasks</div></div>
          <div className="tile t-red"><div className="v">{new Set(tasks.map((t) => t.story_id)).size}</div><div className="l">Stories in Build</div></div>
          <div className="tile t-green"><div className="v">{`${readiness}%`}</div><div className="l">Overall Build Readiness</div></div>
        </div>

        <AgentPipelineCard />
        <BuildAiPanels tasks={tasks} data={data} />

        <div style={{ marginTop: 14 }}>
          <div className="card">
            <div className="card-head">
              <h3>Work Queue</h3>
              <input
                type="text"
                className="search-box"
                placeholder="Search tasks..."
                value={taskSearch}
                onChange={(e) => setTaskSearch(e.target.value)}
              />
            </div>
            <p className="hint" style={{ margin: '-4px 0 10px' }}>
              Click a row to focus it — owner, component and dependencies appear in Current Focus.
            </p>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {['Task', 'Accountable Team', 'Status', 'Last Activity', 'Actions'].map((h) => <th key={h}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {shown.map((t) => (
                    <tr
                      key={t.task_id}
                      className={t.task_id === task?.task_id ? 'sel' : ''}
                      style={{ cursor: 'pointer' }}
                      onClick={() => setTaskId(t.task_id)}
                    >
                      <td>
                        <div className="mono">{t.task_id}</div>
                        <div>{t.summary}</div>
                        <div className="hint mono">{t.story_id}</div>
                      </td>
                      <td><TeamChip name={t.accountable_team} /></td>
                      <td><Badge status={t.status} /></td>
                      <td className="mono">{hhmm(t.last_activity)}</td>
                      <td>
                        <button
                          type="button"
                          className="kebab"
                          title="Open in Development Progress"
                          onClick={(e) => { e.stopPropagation(); setTaskId(t.task_id); goTo('dev_progress') }}
                        >
                          ⋯
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="table-foot">
              <span className="hint">{`Showing 1 to ${shown.length} of ${tasks.length} tasks`}</span>
              <span className="pager">
                <button type="button" className="icon-btn" disabled>‹</button>
                <span className="page-chip">1</span>
                <button type="button" className="icon-btn" disabled>›</button>
              </span>
            </div>
          </div>
        </div>

        <div className="grid cols-3" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>Tasks by Team</h3>
            <div className="donut-wrap">
              <div className="donut" style={{ background: `conic-gradient(${donutStops})` }}>
                <div className="donut-hole">
                  <div className="v">{tasks.length}</div>
                  <div className="l">Tasks</div>
                </div>
              </div>
              <ul className="donut-legend">
                {teams.map((t) => {
                  const n = tasks.filter((x) => x.accountable_team === t).length
                  return (
                    <li key={t}>
                      <span className="legend-dot" style={{ background: teamColor(t) }} />
                      {`${t} — ${n} (${Math.round((100 * n) / tasks.length)}%)`}
                    </li>
                  )
                })}
              </ul>
            </div>
          </div>

          <div className="card">
            <h3>⚠ Dependency Risks</h3>
            {blockedTasks.length || waitingTasks.length ? (
              <>
                {blockedTasks.map((t) => (
                  <div className="risk-line red" key={t.task_id}>
                    <b>{`${t.task_id} is blocked`}</b>
                    <span className="hint">{t.current_activity || 'Waiting on an upstream dependency'}</span>
                  </div>
                ))}
                {waitingTasks.map((t) => (
                  <div className="risk-line amber" key={t.task_id}>
                    <b>{`${t.task_id} depends on ${(t.dependencies ?? []).join(', ')}`}</b>
                    <span className="hint">{`Delays upstream may impact ${t.story_id}`}</span>
                  </div>
                ))}
              </>
            ) : (
              <p className="hint">No blocked tasks and every dependency is satisfied.</p>
            )}
          </div>

          <div className="card">
            <div className="card-head">
              <h3>Ready-to-start Tasks</h3>
              <span className="page-chip">{String(readyToStart.length)}</span>
            </div>
            {readyToStart.length ? (
              <ul className="plain">
                {readyToStart.map((t) => (
                  <li key={t.task_id} style={{ cursor: 'pointer' }} onClick={() => setTaskId(t.task_id)}>
                    <span className="mono">{`${t.task_id} `}</span>{t.summary}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="hint">Nothing waiting — tasks unlock as dependencies complete.</p>
            )}
          </div>
        </div>
      </div>

      <aside className="rail">
        {task ? (
          <div className="card rail-card">
            <h3>◎ Current Focus</h3>
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr', marginTop: 10 }}>
              <b>Task ID</b><span className="mono" style={{ color: 'var(--red)' }}>{task.task_id}</span>
              <b>Story</b><span className="mono">{task.story_id}</span>
              <b>Task Title</b><span>{task.summary}</span>
              <b>Status</b><span><Badge status={task.status} /></span>
              <b>Owner</b><span>{task.owner || '—'}</span>
              <b>Accountable Team</b><span>{task.accountable_team}</span>
              <b>Target Component</b><span>{story?.target_component ?? '—'}</span>
              <b>Dependencies</b><span className="mono">{(task.dependencies ?? []).join(', ') || '—'}</span>
              <b>Last Activity</b><span className="mono">{hhmm(task.last_activity)}</span>
              <b>Feature Flag</b><span>{story?.feature_flag ? <code>{story.feature_flag.name}</code> : '—'}</span>
              <b>Rollback Method</b><span>{story?.rollback_plan?.method ?? '—'}</span>
            </div>
            <label className="fld">Next Action</label>
            <button type="button" className="outline block" onClick={() => goTo('dev_progress')}>Open Development Progress ↗</button>
          </div>
        ) : null}
        {task ? (
          <div className="card rail-card">
            <h3>⚙ Build Controls</h3>
            <div className="actions-row" style={{ marginTop: 10 }}>
              <button
                type="button"
                className="primary sq"
                onClick={() => act(`/tasks/${task.task_id}/start`, {}, `${task.task_id} started`)}
              >
                ▶ Start Task
              </button>
              <PauseButton />
            </div>
            <button
              type="button"
              className="outline block"
              style={{ marginTop: 8 }}
              onClick={() => act(`/tasks/${task.task_id}/generate-tests`, {}, 'Red baseline recorded')}
            >
              ⚗ Generate Tests
            </button>
            <button
              type="button"
              className="outline block"
              style={{ marginTop: 8 }}
              title="start → red tests → develop → verify → submit, each step logged"
              onClick={() => act(`/tasks/${task.task_id}/run-to-review`, {}, `${task.task_id} submitted for review`)}
            >
              Run to Review (all steps)
            </button>
            <button
              type="button"
              className="outline block"
              style={{ marginTop: 8 }}
              onClick={() => act(`/tasks/${task.task_id}/submit-review`, {}, 'Submitted for independent review')}
            >
              ⬆ Submit for Review
            </button>
          </div>
        ) : null}
        <GuidanceCard />
      </aside>
    </section>
  )
}
