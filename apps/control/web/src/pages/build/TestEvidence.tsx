import { Fragment } from 'react'
import { SectionTitle } from '../../components/SectionTitle'
import { useRun } from '../../state/RunContext'

// --- local shapes -----------------------------------------------------
// `types.ts` is under concurrent edit by other pages in this migration and
// its `Task`/`Story`/`ActivityEvent` shapes have changed underneath this
// page more than once while porting it. Kept fully local (mirroring
// `s7_delivery/factory/models.py`: TaskRecord, TestCaseRecord, Story,
// AcceptanceCriterion) so this file's correctness does not depend on that
// churn. See the report back to the integrator for the consolidated
// `types.ts` additions this page (and likely sibling build/* pages) need
// centrally — reconcile against whatever shape `types.ts` has landed on.

interface TestCaseEvidence {
  test_id: string
  name: string
  ac_id: string
  initial_result: string
  current_result: string
  evidence_ref: string
}

interface BuildTaskLocal {
  task_id: string
  story_id: string
  status: string
  tests?: TestCaseEvidence[]
  coverage_pct?: number | null
}

interface AcceptanceCriterionLocal {
  ac_id: string
  text: string
}

interface StoryLocal {
  story_id: string
  acceptance_criteria: AcceptanceCriterionLocal[]
}

interface ActivityEventLocal {
  timestamp: string
  workflow?: string
  artifact?: string
}

function hhmm(iso?: string): string {
  return (iso ?? '').slice(11, 16) || '—'
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

export function TestEvidence() {
  const { data, act, goTo } = useRun()
  if (!data) return null

  const tasks = ((data.build as { tasks?: BuildTaskLocal[] } | undefined)?.tasks) ?? []
  if (!tasks.length) {
    return (
      <section>
        <SectionTitle title="Test Evidence" />
        <div className="card">
          <p>The work queue is seeded when the plan is signed at Gate 1.</p>
        </div>
      </section>
    )
  }

  // Mirrors vanilla `currentTask()` minus the `state.taskId` task-switcher
  // lookup — that selector lives on the Development Progress page, which is
  // not yet ported, and there is no shared "selected task" state in
  // RunContext yet. Falls back to the same in_progress → not-completed →
  // first chain, which matches vanilla behavior whenever no task has been
  // explicitly switched to (the default demo path).
  const task = tasks.find((t) => t.status === 'in_progress')
    ?? tasks.find((t) => t.status !== 'completed')
    ?? tasks[0]

  const stories = ((data.planning as { stories?: StoryLocal[] } | undefined)?.stories) ?? []
  const story = stories.find((s) => s.story_id === task.story_id)

  const tests = task.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const initialFailures = tests.filter((t) => t.initial_result === 'failed').length
  const passes = tests.filter((t) => t.current_result === 'passed').length
  const failing = tests.filter((t) => t.current_result !== 'passed')
  const acText = (id: string) => acs.find((a) => a.ac_id === id)?.text ?? ''
  const acts = ((data.activity as ActivityEventLocal[] | undefined) ?? [])
    .filter((a) => a.artifact === task.task_id)
  const at = (wf: string) => acts.find((a) => a.workflow === wf)?.timestamp

  const timelineSteps: Array<[string, string, string | undefined, string]> = [
    ['red', 'Red', at('test-first'), `Initial tests written · ${initialFailures} failures expected`],
    ['code', 'Code', at('development'), 'Code changes implemented'],
    ['green', 'Green', at('developer-verification'), `${passes} of ${tests.length} passing`],
  ]

  const timeline = (
    <div className="card">
      <h3>Red → Code → Green Timeline (Current Task)</h3>
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
  )

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Test Evidence</h2>
          <span className="hint">Acceptance-criteria-based test-first evidence for the current build task.</span>
        </div>
        <div className="tiles">
          <div className="tile t-red"><div className="v">{acs.length}</div><div className="l">Acceptance Criteria</div></div>
          <div className="tile t-blue"><div className="v">{tests.length}</div><div className="l">Tests Generated</div></div>
          <div className="tile t-amber"><div className="v">{initialFailures}</div><div className="l">Initial Failures</div></div>
          <div className="tile t-green"><div className="v">{passes}</div><div className="l">Current Passes</div></div>
          <div className="tile t-red"><div className="v">{failing.length}</div><div className="l">Open Failures</div></div>
          <div className="tile t-blue"><div className="v">{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</div><div className="l">Coverage</div></div>
        </div>
        <div className="grid" style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(0,1fr)' }}>
          <div className="card">
            <h3>Acceptance Criteria to Test Mapping</h3>
            {tests.length ? (
              <div className="table-wrap" style={{ marginTop: 10 }}>
                <table>
                  <thead>
                    <tr>
                      {['AC ID', 'Acceptance Criterion', 'Test Name', 'Initial Result', 'Current Result', 'Evidence'].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tests.map((t) => (
                      <tr key={t.test_id}>
                        <td className="mono">{t.ac_id}</td>
                        <td>{acText(t.ac_id)}</td>
                        <td className="mono">{t.name}</td>
                        <td>
                          <span className={`dotlbl ${t.initial_result === 'failed' ? 'red' : 'green'}`}>
                            {t.initial_result === 'failed' ? 'Failed as expected' : 'Passed baseline'}
                          </span>
                        </td>
                        <td>
                          <span className={`dotlbl ${t.current_result === 'passed' ? 'green' : 'amber'}`}>
                            {t.current_result === 'passed' ? 'Passed' : 'Review issue'}
                          </span>
                        </td>
                        <td className="mono">{t.evidence_ref || t.test_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p className="hint">No tests yet — generate the red baseline first.</p>
            )}
          </div>
          <div>
            <div className="card">
              <h3>⚑ Test-First Baseline</h3>
              <div className="tile t-red" style={{ border: 0, boxShadow: 'none', textAlign: 'left', padding: '6px 0' }}>
                <div className="v">{initialFailures}</div>
                <div className="l">Expected failures established from ACs before code changes</div>
              </div>
            </div>
            <div className="card" style={{ marginTop: 14 }}>
              <h3>Test Execution Summary</h3>
              <ul className="checklist">
                <li>
                  <span className={`tick ${passes === tests.length && tests.length ? 'ok' : 'no'}`}>
                    {passes === tests.length && tests.length ? '✓' : '·'}
                  </span>
                  Targeted Tests
                  <span className="state ok mono">{`${passes} / ${tests.length}`}</span>
                </li>
                <li>
                  <span className={`tick ${task.coverage_pct ? 'ok' : 'no'}`}>{task.coverage_pct ? '✓' : '·'}</span>
                  Targeted Coverage
                  <span className="state ok mono">{task.coverage_pct ? `${task.coverage_pct}%` : '—'}</span>
                </li>
              </ul>
              <p className="hint">Only categories the demo engine actually runs are listed — nothing is padded.</p>
            </div>
          </div>
        </div>
        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>⚠ Failure &amp; Exception Detail</h3>
            {failing.length ? (
              failing.map((t) => (
                <div className="risk-line amber" key={t.test_id}>
                  <b>{`REVIEW ISSUE · ${t.ac_id}`}</b>
                  <span className="hint">{`${t.name} is not passing — ${acText(t.ac_id)}`}</span>
                </div>
              ))
            ) : (
              <p className="hint">No open failures for this task.</p>
            )}
          </div>
          {timeline}
        </div>
      </div>
      <aside className="rail">
        <GuidanceCard />
        <div className="card rail-card">
          <button
            type="button"
            className="primary sq block"
            title="Runs developer verification for the current task"
            onClick={() => act(`/tasks/${task.task_id}/verify`, {}, 'Targeted tests executed')}
          >
            ▶ Run Targeted Tests
          </button>
          <button
            type="button"
            className="outline block"
            style={{ marginTop: 8 }}
            title="The demo engine runs targeted verification only; a separate full-regression harness is not part of the demonstration and this control is honestly disabled."
            disabled
          >
            ⟳ Run Full Regression
          </button>
          <button
            type="button"
            className="outline block"
            style={{ marginTop: 8 }}
            onClick={() => goTo('dev_progress')}
          >
            ◉ View Technical Evidence
          </button>
          <button
            type="button"
            className="outline block"
            style={{ marginTop: 8 }}
            onClick={() => act(`/tasks/${task.task_id}/submit-review`, {}, 'Submitted for independent review')}
          >
            ⬆ Submit for Independent Review
          </button>
        </div>
      </aside>
    </section>
  )
}
