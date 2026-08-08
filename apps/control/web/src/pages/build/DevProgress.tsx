import { useState } from 'react'
import { Badge, Prov } from '../../components/Badge'
import { Modal } from '../../components/Modal'
import { SectionTitle } from '../../components/SectionTitle'
import { useRun } from '../../state/RunContext'
import type { ActivityEvent, Provenance } from '../../types'

// --- build task / review / story shapes ------------------------------------
// Ported from the task/review/story objects produced by `buildTasks()` /
// `reviewsFor()` / `storyOf()` in apps/control/static/app.js (see
// renderDevProgress, ~line 2184-2327, and openTechnicalDetailModal just
// above it). Defined locally for now because RunState has no typed `build`
// or `planning` section yet — see this page's port report for the exact
// types.ts additions needed to promote these into the shared types module.
// NOTE: the planning pages (depGraph.ts / planningHelpers.ts) are defining
// their own local story shape concurrently (as `PlanStory` / `StoryRecord`,
// mid-rename at the time this page was ported) — deliberately not importing
// either here, since both are moving targets from a different in-flight
// port. `PlanningStory` below carries only the fields this page reads and
// should be reconciled with whichever shared Story type wins centrally.

export interface AcceptanceCriterion {
  ac_id: string
  text: string
}

export interface FeatureFlag {
  name: string
}

export interface RollbackPlan {
  method: string
}

export interface PlanningStory {
  story_id: string
  title: string
  target_component?: string
  target_repository?: string
  feature_flag?: FeatureFlag | null
  rollback_plan?: RollbackPlan | null
  acceptance_criteria?: AcceptanceCriterion[]
}

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
  change_summary?: string
  changed_files?: string[]
  commit_ref?: string
  pr_ref?: string
  version?: number
  last_activity?: string
  provenance?: Provenance
}

export interface ReviewFinding {
  finding_id: string
  severity: string
  ac_id: string
  summary: string
  detail: string
  expected?: string
  observed?: string
  impact?: string
  recommendation?: string
  evidence?: string[]
}

export interface BuildReview {
  review_id: string
  task_id: string
  reviewer: string
  result: string
  critical_gaps: number
  major_gaps: number
  minor_gaps: number
  findings?: ReviewFinding[]
  verified_against?: string[]
  created_at?: string
  version?: number
  provenance?: Provenance
}

// ActivityEvent in types.ts does not yet carry `skill` / `duration_s`
// (it already has `artifact`) — the shared server-side ActivityEvent model
// has all three (s7_delivery/factory/models.py), but the React port of the
// shared type hasn't picked up `skill`/`duration_s` yet. Extended locally;
// see this page's port report.
export interface TaskActivityEvent extends ActivityEvent {
  artifact?: string
  skill?: string
  duration_s?: number
}

const TECHNICAL_ROLES = new Set(['engineering_lead', 'qa_lead'])

const WORKFLOW_STEPS: Array<[string, string, string]> = [
  ['task-start', 'Task Selected', 'AI Developer'],
  ['test-first', 'Test-First (Generate Tests)', 'AI Test Engineer'],
  ['development', 'Development (Implement)', 'AI Developer'],
  ['developer-verification', 'Dev Verify (Self-Check)', 'AI Test Engineer'],
  ['independent-review-gate', 'Independent Review', 'Independent AI Reviewer'],
  ['human-approval', 'Human Approval', 'Human'],
]

const WORKFLOW_LABELS: Record<string, string> = {
  'task-start': 'Workspace created and context analysed',
  'test-first': 'Tests generated and red baseline captured',
  development: 'Code changes implemented',
  'developer-verification': 'Build and targeted tests executed',
  'submit-review': 'Submitted for independent review',
  'independent-review-gate': 'Independent review executed',
  'return-to-development': 'Returned to development',
}

// Ordered developer-workflow checklist: every step is shown — Completed with
// its time, the next one In Progress, the rest Pending.
const DEV_CHECKLIST: Array<[string, string]> = [
  ['task-start', 'Context analysed'],
  ['test-first', 'Tests generated & red baseline captured'],
  ['development', 'Code changes implemented'],
  ['developer-verification', 'Build and targeted tests executed'],
  ['submit-review', 'Submitted for independent review'],
]

function hhmm(iso?: string | null): string {
  return (iso ?? '').slice(11, 16) || '—'
}

function agentForWorkflow(workflow?: string): string {
  return WORKFLOW_STEPS.find(([key]) => key === workflow)?.[2] ?? '—'
}

function latestReviewFor(reviews: BuildReview[], taskId: string): BuildReview | undefined {
  const forTask = reviews.filter((r) => r.task_id === taskId)
  return forTask[forTask.length - 1]
}

function WorkflowStepper({ acts, review }: { acts: TaskActivityEvent[]; review?: BuildReview }) {
  const done = new Set(acts.map((a) => a.workflow))
  if (review?.result === 'passed') done.add('independent-review-gate')
  const flags = WORKFLOW_STEPS.map(([key]) => {
    if (key === 'independent-review-gate') return done.has('independent-review-gate')
    if (key === 'human-approval') return false
    return done.has(key)
  })
  const active = flags.indexOf(false)
  return (
    <div className="wf-stepper">
      {WORKFLOW_STEPS.map(([key, label, agent], i) => {
        const blocked = key === 'independent-review-gate' && review?.result === 'blocked'
        const cls = blocked ? 'blocked' : flags[i] ? 'done' : i === active ? 'active' : ''
        let status: string | null = null
        if (blocked) status = `BLOCKED · ${review?.major_gaps} Major Gap${review?.major_gaps === 1 ? '' : 's'}`
        else if (key === 'independent-review-gate' && review?.result === 'passed') status = 'Passed'
        return (
          <div key={key} className={`wf-step ${cls}`}>
            {i > 0 ? <span className={`wf-line ${flags[i - 1] ? 'done' : ''}`} /> : null}
            <span className="wf-dot">{blocked ? '!' : flags[i] ? '✓' : '●'}</span>
            <span className="wf-label">{label}</span>
            <span className="wf-agent">{agent}</span>
            {status ? <span className={`wf-status ${blocked ? 'bad' : 'ok'}`}>{status}</span> : null}
          </div>
        )
      })}
    </div>
  )
}

function DevChecklist({ task, acts }: { task: BuildTask; acts: TaskActivityEvent[] }) {
  const at = (wf: string) => acts.find((a) => a.workflow === wf)?.timestamp
  const firstMissing = DEV_CHECKLIST.findIndex(([wf]) => !at(wf))
  return (
    <ul className="checklist">
      {DEV_CHECKLIST.map(([wf, label], i) => {
        const ts = at(wf)
        const stateTxt = ts ? hhmm(ts) : i === firstMissing && task.status !== 'not_started' ? 'In Progress' : 'Pending'
        return (
          <li key={wf}>
            <span className={`tick ${ts ? 'ok' : 'no'}`}>{ts ? '✓' : '·'}</span>
            {label}
            <span className={`state ${ts ? 'ok' : 'no'} mono`}>{stateTxt}</span>
          </li>
        )
      })}
    </ul>
  )
}

function TechnicalDetailModal({ task, acts, onClose }: { task: BuildTask; acts: TaskActivityEvent[]; onClose: () => void }) {
  return (
    <Modal title={`Technical Detail — ${task.task_id}`} onClose={onClose}>
      <p className="hint" style={{ color: 'var(--red-dark)' }}>
        Engineering view — visible to engineering lead / QA lead roles only. Not part of the customer-safe surface.
      </p>
      <h4 style={{ marginTop: '14px', fontSize: '12.5px', color: 'var(--muted)' }}>Step-by-step process</h4>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Time', 'Step', 'Skill / Agent', 'Duration', 'Outcome'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {acts.map((a, i) => (
              <tr key={i}>
                <td className="mono">{hhmm(a.timestamp)}</td>
                <td>{WORKFLOW_LABELS[a.workflow ?? ''] ?? a.workflow ?? '—'}</td>
                <td>{a.skill || agentForWorkflow(a.workflow)}</td>
                <td className="mono">{a.duration_s ? `${a.duration_s}s` : '—'}</td>
                <td>{a.details || a.outcome || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4 style={{ marginTop: '16px', fontSize: '12.5px', color: 'var(--muted)' }}>Files changed</h4>
      {(task.changed_files ?? []).length ? (
        <ul className="plain">
          {(task.changed_files ?? []).map((f) => (
            <li key={f}>
              <code>{f}</code>
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">No files recorded for this task.</p>
      )}
      <h4 style={{ marginTop: '16px', fontSize: '12.5px', color: 'var(--muted)' }}>Change summary</h4>
      <p>{task.change_summary || '—'}</p>
      <div className="kv" style={{ gridTemplateColumns: '140px 1fr', marginTop: '10px' }}>
        <b>Commit</b>
        <span>
          <code>{task.commit_ref || '—'}</code>
        </span>
        <b>Pull Request</b>
        <span>
          <code>{task.pr_ref || '—'}</code>
        </span>
        <b>Coverage</b>
        <span>{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</span>
      </div>
    </Modal>
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

export function DevProgress() {
  const { data, role, act, goTo, notify } = useRun()
  const [taskId, setTaskId] = useState<string | null>(null)
  const [showTechnicalDetail, setShowTechnicalDetail] = useState(false)

  if (!data) return null

  const tasks = (data.build as { tasks?: BuildTask[] } | undefined)?.tasks ?? []
  if (!tasks.length) {
    return (
      <section>
        <SectionTitle title="Development Progress" />
        <div className="card">
          <p>The work queue is seeded when the plan is signed at Gate 1.</p>
        </div>
      </section>
    )
  }

  const task =
    tasks.find((t) => t.task_id === taskId) ??
    tasks.find((t) => t.status === 'in_progress') ??
    tasks.find((t) => t.status !== 'completed') ??
    tasks[0]

  const stories = (data.planning as { stories?: PlanningStory[] } | undefined)?.stories ?? []
  const story = stories.find((s) => s.story_id === task.story_id)
  const tests = task.tests ?? []
  const passed = tests.filter((t) => t.current_result === 'passed').length
  const acts = ((data.activity ?? []) as TaskActivityEvent[]).filter((a) => a.artifact === task.task_id)
  const reviews = (data.build as { reviews?: BuildReview[] } | undefined)?.reviews ?? []
  const review = latestReviewFor(reviews, task.task_id)

  const isTechnicalRole = TECHNICAL_ROLES.has(role)
  const planStoryIds = ((data.planning as { plan?: { story_ids?: string[] } } | undefined)?.plan?.story_ids) ?? []
  const withinPlan = planStoryIds.includes(task.story_id)

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '16px', display: 'flex', alignItems: 'flex-start', gap: '16px', flexWrap: 'wrap' }}>
          <div>
            <h2>Development Progress</h2>
            <span className="hint">
              {isTechnicalRole
                ? 'Engineering view: includes step-level technical detail alongside the customer-safe progress tracking.'
                : 'Customer-safe progress tracking for AI-assisted development and developer verification.'}
            </span>
          </div>
          <select
            className="mono"
            style={{ marginLeft: 'auto' }}
            value={task.task_id}
            onChange={(e) => setTaskId(e.target.value)}
          >
            {tasks.map((t) => (
              <option key={t.task_id} value={t.task_id}>
                {t.task_id} — {t.summary}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="outline"
            title={
              isTechnicalRole
                ? 'Skills used, files changed and the step-by-step process for this task.'
                : 'Available to engineering lead / QA lead roles — switch role to view.'
            }
            onClick={() => {
              if (!isTechnicalRole) {
                notify('Technical detail is available to engineering lead / QA lead roles', true)
                return
              }
              setShowTechnicalDetail(true)
            }}
          >
            ⚙ Technical Detail
          </button>
        </div>

        <div className="tiles">
          <div className="tile t-red">
            <div className="v mono">{task.task_id}</div>
            <div className="l">Current Task</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{task.files_changed}</div>
            <div className="l">Files Changed</div>
          </div>
          <div className="tile t-amber">
            <div className="v">{tests.length}</div>
            <div className="l">Targeted Tests</div>
          </div>
          <div className="tile t-green">
            <div className="v">{tests.length ? `${passed} / ${tests.length}` : '—'}</div>
            <div className="l">Tests Passed</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</div>
            <div className="l">Coverage</div>
          </div>
          <div className="tile t-green">
            <div className="v">{task.progress_pct}%</div>
            <div className="l">Task Progress</div>
          </div>
        </div>

        <div className="grid cols-2">
          <div className="card">
            <h3>▣ Current Development Task</h3>
            <div className="kv" style={{ gridTemplateColumns: '140px 1fr', marginTop: '10px' }}>
              <b>Task ID</b>
              <span className="mono" style={{ color: 'var(--red)' }}>{task.task_id}</span>
              <b>Story</b>
              <span>{task.story_id} — {story?.title ?? ''}</span>
              <b>Accountable Team</b>
              <span>{task.accountable_team}</span>
              <b>Target Component</b>
              <span>{story?.target_component ?? '—'}</span>
              <b>Repository</b>
              <span>
                <code>{story?.target_repository ?? '—'}</code>
              </span>
              <b>Feature Flag</b>
              <span>{story?.feature_flag ? <code>{story.feature_flag.name}</code> : '—'}</span>
              <b>Rollback Method</b>
              <span>{story?.rollback_plan?.method ?? '—'}</span>
              <b>Owner</b>
              <span>{task.owner || 'AI developer (simulated)'}</span>
              <b>Evidence</b>
              <span>
                <Prov provenance={task.provenance} />
              </span>
            </div>
          </div>

          <div className="card">
            <h3>▦ Execution Workflow</h3>
            <WorkflowStepper acts={acts} review={review} />
            <div className="grid cols-2" style={{ marginTop: '12px' }}>
              <div>
                <h3 style={{ fontSize: '13.5px' }}>Development Workflow</h3>
                <DevChecklist task={task} acts={acts} />
              </div>
              <div>
                <h3 style={{ fontSize: '13.5px' }}>Code Change Summary</h3>
                <div className="kv" style={{ gridTemplateColumns: '1fr auto', marginTop: '8px' }}>
                  <b>Files Changed</b>
                  <span>{task.files_changed}</span>
                  <b>Lines Added</b>
                  <span style={{ color: 'var(--green)' }}>+{task.lines_added}</span>
                  <b>Lines Removed</b>
                  <span style={{ color: 'var(--red-dark)' }}>−{task.lines_removed}</span>
                  <b>Components</b>
                  <span>{(task.changed_files ?? []).length}</span>
                  <b>Coverage (Targeted)</b>
                  <span>{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</span>
                  <b>Scope Status</b>
                  <span style={{ color: withinPlan ? 'var(--green)' : 'var(--red-dark)', fontWeight: 800 }}>
                    {withinPlan ? 'Within Plan' : 'Outside Plan'}
                  </span>
                  <b>Pull Request</b>
                  <span>
                    <code>{task.pr_ref || '—'}</code>
                  </span>
                  <b>Commit</b>
                  <span>
                    <code>{task.commit_ref || '—'}</code>
                  </span>
                </div>
              </div>
            </div>
            {(task.changed_files ?? []).length ? (
              <div style={{ marginTop: '10px' }}>
                <h3 style={{ fontSize: '13.5px' }}>Changed Components</h3>
                <ul className="plain">
                  {(task.changed_files ?? []).map((f) => (
                    <li key={f}>
                      <code>{f}</code>{' '}
                      <Badge status={task.status === 'completed' || task.progress_pct >= 80 ? 'completed' : 'in_progress'} />
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </div>

        <div className="grid cols-2" style={{ marginTop: '14px' }}>
          <div className="card">
            <h3>✦ AI Implementation Approach</h3>
            <p className="hint">Derived from the story's acceptance criteria — the approach is the criteria, in build order.</p>
            <ul className="plain">
              {(story?.acceptance_criteria ?? []).map((ac, i) => (
                <li key={ac.ac_id}>
                  <b>{i + 1}. </b>Implement and verify: {ac.text}
                </li>
              ))}
              <li>
                <b>{(story?.acceptance_criteria ?? []).length + 1}. </b>
                Preserve existing behaviour — rollback path: {story?.rollback_plan?.method ?? 'feature flag'}
              </li>
            </ul>
          </div>

          <div className="card">
            <h3>Acceptance Criteria Status</h3>
            <ul className="checklist">
              {(story?.acceptance_criteria ?? []).map((ac) => {
                const test = tests.find((t) => t.ac_id === ac.ac_id)
                const flagged = review?.result === 'blocked' && (review.findings ?? []).some((f) => f.ac_id === ac.ac_id)
                const done = !flagged && test?.current_result === 'passed'
                const started = Boolean(test)
                const label = ac.text.length > 56 ? `${ac.text.slice(0, 56)}…` : ac.text
                return (
                  <li key={ac.ac_id} title={ac.text}>
                    <span className={`tick ${done ? 'ok' : 'no'}`}>{done ? '✓' : flagged ? '!' : '·'}</span>
                    {ac.ac_id} — {label}
                    <span className={`state ${done ? 'ok' : 'no'}`} style={flagged ? { color: 'var(--red-dark)' } : undefined}>
                      {flagged ? 'Review' : done ? 'Completed' : started ? 'In Progress' : 'Pending'}
                    </span>
                  </li>
                )
              })}
            </ul>
            <div className="actions-row">
              <button type="button" className="outline" onClick={() => goTo('test_evidence')}>View Evidence</button>
              <button
                type="button"
                className="primary sq"
                onClick={() => act(`/tasks/${task.task_id}/verify`, {}, 'Developer verification executed')}
              >
                Run Developer Verification
              </button>
            </div>
          </div>
        </div>

        <div className="card" style={{ marginTop: '14px' }}>
          <div className="card-head">
            <h3>Activity Log</h3>
            <button type="button" className="outline" onClick={() => goTo('activity')}>View full activity log →</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  {['Time', 'Event', 'Actor', 'Details'].map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[...acts].reverse().map((a, i) => (
                  <tr key={i}>
                    <td className="mono">{hhmm(a.timestamp)}</td>
                    <td>{WORKFLOW_LABELS[a.workflow ?? ''] ?? a.workflow ?? '—'}</td>
                    <td>{a.actor}</td>
                    <td>{a.details || a.outcome || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>✓ What the customer sees</h3>
          <ul className="checklist">
            {[
              ['Stage progression', 'Real-time visibility into the AI-assisted development workflow.'],
              ['Evidence review', 'Test evidence and code-change summaries for each task.'],
              ['Approval controls', 'Human approval gates before changes move forward.'],
              ['Traceability snapshot', 'Full traceability from story to tests, code, and results.'],
              ['No IDE / CLI shown', 'All execution happens behind the scenes.'],
            ].map(([t, d]) => (
              <li key={t} title={d}>
                <span className="tick ok">✓</span>
                {t}
              </li>
            ))}
          </ul>
          {isTechnicalRole ? (
            <p className="hint" style={{ marginTop: '8px' }}>
              Acting as an engineering / QA role: the Technical Detail button above is additional and not part of the customer-safe guarantee for other roles.
            </p>
          ) : null}
        </div>
        <div className="card rail-card">
          <PauseButton />
          <button type="button" className="outline block" style={{ marginTop: '8px' }} onClick={() => goTo('test_evidence')}>
            ▤ View Test Evidence →
          </button>
          <button
            type="button"
            className="primary sq block"
            style={{ marginTop: '8px' }}
            onClick={() => act(`/tasks/${task.task_id}/submit-review`, {}, 'Submitted for independent review')}
          >
            ✓ Submit for Review
          </button>
        </div>
        <GuidanceCard />
      </aside>

      {showTechnicalDetail ? (
        <TechnicalDetailModal task={task} acts={acts} onClose={() => setShowTechnicalDetail(false)} />
      ) : null}
    </section>
  )
}
