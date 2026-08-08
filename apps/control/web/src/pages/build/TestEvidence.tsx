import { Fragment, useState } from 'react'
import { SectionTitle } from '../../components/SectionTitle'
import { Prov } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import type { BuildTask, TaskTestResult } from '../../types'
import {
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  GuidanceCard,
  hhmm,
  OwnershipChips,
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

export function TestEvidence() {
  const { data, act, goTo } = useRun()
  const [selId, setSelId] = useState<string | null>(selectedStory())
  if (!data) return null

  const build = buildOf(data)
  const tasks = build.tasks ?? []
  if (!tasks.length) {
    return (
      <section>
        <SectionTitle title="Build & Test Evidence" />
        <div className="card">
          <p>The work queue is seeded when the plan is signed at Gate 1.</p>
        </div>
      </section>
    )
  }

  const task = pickTask(tasks, selId)
  const workspaces = build.workspaces ?? []
  const ws = workspaces.find((w) => w.story_id === task.story_id)
  const stories = data.planning?.stories ?? []
  const story = stories.find((s) => s.story_id === task.story_id)
  const storyTitle = (id: string) => stories.find((s) => s.story_id === id)?.title ?? id

  const select = (storyId: string) => {
    selectStory(storyId)
    setSelId(storyId)
  }

  const tests: TaskTestResult[] = task.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const acText = (id: string) => acs.find((a) => a.ac_id === id)?.text ?? ''
  const initialFailures = tests.filter((t) => t.initial_result === 'failed').length
  const passes = tests.filter((t) => t.current_result === 'passed').length
  const failing = tests.filter((t) => t.current_result === 'failed')

  // Latest independent review for this task — its findings sharpen the
  // customer-safe failure analysis when one matches the failing AC.
  const reviews = (build.reviews ?? []).filter((r) => r.task_id === task.task_id)
  const latestReview = reviews.length ? reviews[reviews.length - 1] : undefined

  // Red → Code → Green timestamps from the activity ledger.
  const taskActivity = (data.activity ?? []).filter((a) => a.artifact === task.task_id)
  const at = (wf: string) => taskActivity.find((a) => a.workflow === wf)?.timestamp
  const timelineSteps: Array<[string, string, string | undefined, string]> = [
    ['red', 'Red', at('test-first'), `Initial tests written · ${initialFailures} failures expected`],
    ['code', 'Code', at('development'), 'Developer implements in their own workspace'],
    ['green', 'Green', at('developer-verification'), `${passes} of ${tests.length} passing`],
  ]

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Build &amp; Test Evidence <OwnershipChips /></h2>
          <span className="hint">
            Engineering evidence collected from developer workspaces — commits, CI, and acceptance-criteria-to-test traceability.
          </span>
          <div style={{ marginTop: 10 }}>
            <select
              value={task.task_id}
              onChange={(e) => {
                const next = tasks.find((t) => t.task_id === e.target.value)
                if (next) select(next.story_id)
              }}
            >
              {tasks.map((t) => (
                <option key={t.task_id} value={t.task_id}>
                  {`${t.task_id} — ${storyTitle(t.story_id)}`}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <h3>Workspace Evidence</h3>
            <Prov provenance={task.provenance} />
          </div>
          <div className="grid cols-3">
            <div className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
              <b>Story</b><span className="mono">{task.story_id}</span>
              <b>Task</b><span className="mono">{task.task_id}</span>
              <b>Developer</b><span>{ws?.developer || '—'}</span>
            </div>
            <div className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
              <b>Repository</b><span className="mono">{ws?.repository ?? story?.target_repository ?? '—'}</span>
              <b>Branch</b><span className="mono">{ws?.branch ?? '—'}</span>
              <b>Commit</b><span className="mono">{ws?.current_commit ?? task.commit_ref ?? '—'}</span>
            </div>
            <div className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
              <b>PR</b><span className="mono">{ws?.pull_request ?? task.pr_ref ?? '—'}</span>
              <b>CI</b>
              <span>
                <span className={`badge ${(ws?.ci_status ?? task.ci_status) === 'passed' ? 'st-passed' : (ws?.ci_status ?? task.ci_status) === 'failed' ? 'st-failed' : 'st-planned'}`}>
                  {ws?.ci_status ?? task.ci_status ?? '—'}
                </span>
              </span>
              <b>Artifacts</b>
              <span>
                <span className={`badge ${ws?.artifact_status === 'stale' ? 'st-stale' : 'st-passed'}`}>
                  {ws?.artifact_status === 'stale' ? '⚠ stale' : 'current'}
                </span>
              </span>
            </div>
          </div>
        </div>

        <div className="tiles">
          <div className="tile t-blue"><div className="v">{acs.length}</div><div className="l">Acceptance Criteria</div></div>
          <div className="tile t-blue"><div className="v">{tests.length}</div><div className="l">Tests</div></div>
          <div className="tile t-amber"><div className="v">{initialFailures}</div><div className="l">Initial Failures</div></div>
          <div className="tile t-green"><div className="v">{passes}</div><div className="l">Passing Now</div></div>
          <div className="tile t-red"><div className="v">{failing.length}</div><div className="l">Open Failures</div></div>
          <div className="tile t-blue"><div className="v">{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</div><div className="l">Coverage</div></div>
        </div>

        <div className="card">
          <h3>AC → Test Evidence</h3>
          {tests.length ? (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    {['AC ID', 'Acceptance Criterion', 'Test', 'Initial', 'Current', 'Status'].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tests.map((t) => {
                    const passed = t.current_result === 'passed'
                    return (
                      <tr key={t.test_id}>
                        <td className="mono">{t.ac_id}</td>
                        <td style={{ maxWidth: 360 }}>{acText(t.ac_id)}</td>
                        <td className="mono">{t.name}</td>
                        <td>
                          <span className={`dotlbl ${t.initial_result === 'failed' ? 'red' : 'green'}`}>
                            {t.initial_result === 'failed' ? 'Failed (red baseline)' : 'Passed baseline'}
                          </span>
                        </td>
                        <td>
                          <span className={`dotlbl ${passed ? 'green' : 'red'}`}>
                            {passed ? 'Passed' : 'Failing'}
                          </span>
                        </td>
                        <td>
                          <span className={`badge ${passed ? 'st-passed' : 'st-failed'}`}>{passed ? 'PASS' : 'FAIL'}</span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="hint">No tests recorded yet — evidence appears once the red baseline is captured in the developer workspace.</p>
          )}
        </div>

        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>⚠ Failure Analysis</h3>
            {failing.length ? (
              <>
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
                <div className="actions-row" style={{ marginTop: 10 }}>
                  <button
                    type="button"
                    className="outline"
                    onClick={() => { select(task.story_id); goTo('workspaces') }}
                  >
                    Open Developer Workspace →
                  </button>
                  {task.status === 'blocked' ? (
                    <button
                      type="button"
                      className="outline"
                      title="A blocked task is returned to the developer from the Independent Review page"
                      onClick={() => { select(task.story_id); goTo('independent_review') }}
                    >
                      Open Independent Review →
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="primary sq"
                      disabled={!task.files_changed}
                      title={task.files_changed ? 'Re-runs the targeted tests for this task' : 'No implementation changes recorded yet — nothing to verify'}
                      onClick={() => act(`/tasks/${task.task_id}/verify`, {}, 'Targeted tests re-executed')}
                    >
                      ▶ Re-run Tests
                    </button>
                  )}
                </div>
              </>
            ) : (
              <p className="hint">No open failures for this task.</p>
            )}
          </div>

          <div className="card">
            <h3>Red → Code → Green Timeline</h3>
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
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Evidence Sources</h3>
          <p className="hint">
            Commits, PRs and CI signals are collected from the developer workspace. In this demo they are
            produced by the deterministic simulation engine and badged SIMULATED.
          </p>
        </div>
        <div className="card rail-card">
          <button
            type="button"
            className="outline block"
            onClick={() => { select(task.story_id); goTo('independent_review') }}
          >
            ◈ View Independent Review
          </button>
        </div>
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
