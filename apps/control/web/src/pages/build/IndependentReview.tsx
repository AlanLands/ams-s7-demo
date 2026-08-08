import { useRun } from '../../state/RunContext'
import { SectionTitle } from '../../components/SectionTitle'
import { Badge } from '../../components/Badge'
import type { BuildState, BuildTask, PlanningState, ReviewRecord } from '../../types'

function hhmm(iso?: string) {
  return (iso ?? '').slice(11, 16) || '—'
}

const SEV_CLASS: Record<string, string> = { critical: 'red', major: 'red', minor: 'amber', info: '' }

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

function ReviewFindingsBlock({ rv, task }: { rv: ReviewRecord; task: BuildTask }) {
  const findings = rv.findings ?? []
  const artifactsReviewed = (rv.verified_against ?? []).length || '—'
  return (
    <>
      <div className="kv" style={{ gridTemplateColumns: '130px 1fr', marginTop: '8px' }}>
        <b>Review ID</b><span className="mono">{rv.review_id}</span>
        <b>Reviewer Agent</b><span>{rv.reviewer}</span>
        <b>Author Agent</b><span>{task.owner || 'AI developer (simulated)'}</span>
        <b>Reviewed On</b><span className="mono">{(rv.created_at ?? '').slice(0, 16).replace('T', ' ')}</span>
        <b>Artifacts Reviewed</b><span>{artifactsReviewed}</span>
        <b>Result</b><span><Badge status={rv.result === 'passed' ? 'passed' : 'blocked'} /></span>
      </div>
      <div className="findings-grid">
        {([['Critical', rv.critical_gaps], ['Major', rv.major_gaps], ['Minor', rv.minor_gaps], ['Info', 0]] as const).map(([label, n]) => (
          <div className="finding-cell" key={label}>
            <b>{label}</b>
            <span className="v">{String(n)}</span>
          </div>
        ))}
      </div>
      {findings.map((f, i) => (
        <div className={`risk-line ${SEV_CLASS[f.severity] ?? 'amber'}`} key={f.finding_id ?? i}>
          <b>{`${f.finding_id ?? ''} ${f.severity.toUpperCase()} · ${f.ac_id} — ${f.summary}`}</b>
          {f.expected ? (
            <div className="finding-detail">
              <div><b>Acceptance Criterion: </b>{f.ac_id}</div>
              <div><b>Expected Behaviour: </b>{f.expected}</div>
              <div><b>Observed Implementation: </b>{f.observed}</div>
              <div><b>Impact: </b>{f.impact}</div>
              <div><b>Recommendation: </b>{f.recommendation}</div>
              {(f.evidence ?? []).length ? (
                <div>
                  <b>Evidence: </b>
                  {(f.evidence ?? []).map((e, ei) => (
                    <span key={e}>
                      {ei > 0 ? ', ' : null}
                      <code>{e}</code>
                    </span>
                  ))}
                </div>
              ) : null}
            </div>
          ) : (
            <span className="hint">{f.detail}</span>
          )}
        </div>
      ))}
      {findings.length === 0 ? <p className="hint">No findings — the change verified clean against the criteria.</p> : null}
    </>
  )
}

export function IndependentReview() {
  const { data, act } = useRun()
  if (!data) return null

  const build = data.build as BuildState | undefined
  const tasks = build?.tasks ?? []

  if (!tasks.length) {
    return (
      <section>
        <SectionTitle title="Independent Review" />
        <div className="card">
          <p>The work queue is seeded when the plan is signed at Gate 1.</p>
        </div>
      </section>
    )
  }

  const planning = data.planning as PlanningState | undefined
  const plan = planning?.plan
  const stories = planning?.stories ?? []

  // Mirrors the vanilla app's currentTask() fallback chain. The vanilla app also honours an
  // explicitly-selected state.taskId (set by clicking a row on the Task List page); that
  // cross-page selection concept does not exist yet in RunContext, so this page falls back to
  // the same in-progress / not-completed / first-task chain the vanilla page uses absent a
  // selection.
  const task: BuildTask = tasks.find((t) => t.status === 'in_progress')
    ?? tasks.find((t) => t.status !== 'completed')
    ?? tasks[0]

  const story = stories.find((s) => s.story_id === task.story_id)
  const reviews = (build?.reviews ?? []).filter((r) => r.task_id === task.task_id)
  const review = reviews[reviews.length - 1]
  const tests = task.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const sevCount = (s: 'critical' | 'major' | 'minor') =>
    review ? ({ critical: review.critical_gaps, major: review.major_gaps, minor: review.minor_gaps }[s] ?? 0) : 0
  const trace = (data.traceability ?? []).find((r) => r.task === task.task_id)
  const totalFindings = (review?.findings ?? []).length
  const history = (data.activity ?? [])
    .filter((a) => a.artifact === task.task_id)
    .filter((a) => a.workflow && ['submit-review', 'independent-review-gate', 'return-to-development'].includes(a.workflow))

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '16px' }}>
          <h2>Independent Review</h2>
          <span className="hint">Isolated review of code, tests, and acceptance criteria. No phase self-approves.</span>
        </div>

        <div className="tiles">
          <div className="tile t-red">
            <div className="v">{review ? '1' : '0'}</div>
            <div className="l">{review ? 'Review Package · Complete' : 'Review Package'}</div>
          </div>
          <div className="tile t-red">
            <div className="v">{String(sevCount('critical'))}</div>
            <div className="l">Critical Gaps</div>
          </div>
          <div className="tile t-amber">
            <div className="v">{String(sevCount('major'))}</div>
            <div className="l">Major Gaps</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{String(sevCount('minor'))}</div>
            <div className="l">Minor Gaps</div>
          </div>
          <div className={`tile ${review?.result === 'passed' ? 't-green' : 't-amber'}`}>
            <div className="v">{review ? review.result.toUpperCase() : '—'}</div>
            <div className="l">Review Result</div>
          </div>
          <div className="tile t-green">
            <div className="v">{`${task.progress_pct}%`}</div>
            <div className="l">Task Readiness</div>
          </div>
        </div>

        <div className="grid cols-2">
          <div className="card">
            <h3>▣ Review Package</h3>
            <ul className="checklist">
              <li>
                <span className={`tick ${plan ? 'ok' : 'no'}`}>{plan ? '✓' : '·'}</span>
                Signed Plan
                <span className="state ok mono">{plan ? `v${plan.plan_version}` : '—'}</span>
              </li>
              <li>
                <span className="tick ok">✓</span>
                Story
                <span className="state ok mono">{task.story_id}</span>
              </li>
              <li>
                <span className={`tick ${acs.length ? 'ok' : 'no'}`}>{acs.length ? '✓' : '·'}</span>
                Acceptance Criteria
                <span className="state ok mono">{acs.length ? `${acs[0].ac_id} – ${acs[acs.length - 1].ac_id}` : '—'}</span>
              </li>
              <li>
                <span className={`tick ${task.files_changed ? 'ok' : 'no'}`}>{task.files_changed ? '✓' : '·'}</span>
                Change Summary
                <span className="state ok mono">{`${task.files_changed} files`}</span>
              </li>
              <li>
                <span className={`tick ${tests.length ? 'ok' : 'no'}`}>{tests.length ? '✓' : '·'}</span>
                Test Evidence
                <span className="state ok mono">{`${tests.length} targeted tests`}</span>
              </li>
              <li>
                <span className={`tick ${trace ? 'ok' : 'no'}`}>{trace ? '✓' : '·'}</span>
                Traceability Evidence
                <span className="state ok">{trace ? 'Current' : '—'}</span>
              </li>
            </ul>
          </div>
          <div className="card">
            <h3>▥ Review Findings</h3>
            {reviews.length === 0 ? (
              <p className="hint">No review executed yet for this task. Submit for review, then execute it.</p>
            ) : reviews.length === 1 ? (
              <ReviewFindingsBlock rv={reviews[0]} task={task} />
            ) : (
              reviews.map((rv, i) => (
                <div
                  key={rv.review_id}
                  style={i > 0 ? { marginTop: '18px', paddingTop: '14px', borderTop: '1px dashed var(--border)' } : undefined}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                    <b>{`Review v${rv.version ?? i + 1}`}</b>
                    {i === reviews.length - 1 ? (
                      <span className="hint">current</span>
                    ) : (
                      <span className="hint">superseded — corrected below</span>
                    )}
                  </div>
                  <ReviewFindingsBlock rv={rv} task={task} />
                </div>
              ))
            )}
          </div>
        </div>

        <div className="grid cols-2" style={{ marginTop: '14px' }}>
          <div className="card">
            <h3>⛓ Traceability Snapshot</h3>
            {trace ? (
              <div className="trace-chain">
                {[trace.requirement, trace.design, trace.story, trace.ac, trace.task, trace.pr, ...(trace.tests ?? []), trace.review]
                  .filter((id): id is string => Boolean(id))
                  .flatMap((id, i) => [
                    i > 0 ? <span className="trace-arrow" key={`arrow-${id}-${i}`}>→</span> : null,
                    <span className="trace-node mono" key={`${id}-${i}`}>{id}</span>,
                  ])}
              </div>
            ) : (
              <p className="hint">The chain appears once the task has evidence.</p>
            )}
          </div>
          <div className="card">
            <h3>⚖ Approval Rule</h3>
            <p>The independent reviewer cannot change the implementation.</p>
            <p>The development workflow cannot approve its own output.</p>
            <p className="hint">Enforced by the engine's role model — not a convention.</p>
          </div>
        </div>

        <div className="actions-row" style={{ marginTop: '16px' }}>
          <button className="outline" onClick={() => void act(`/reviews/${task.task_id}/return-to-development`, {}, 'Returned to development')}>
            ← Return to Development
          </button>
          <button className="primary sq" onClick={() => void act(`/reviews/${task.task_id}/execute`, {}, 'Independent review executed')}>
            ➤ Execute Independent Review
          </button>
          {review?.result === 'blocked' ? (
            <button
              className="primary sq"
              title="Orchestrates the correction loop across its three actors — the reviewer returns the task, the developer re-implements and re-verifies, the reviewer re-executes. Each step is ledgered under its own role."
              onClick={async () => {
                if (await act(`/reviews/${task.task_id}/return-to-development`, { role: 'independent_reviewer' }, 'Reviewer returned the task to development')) {
                  if (await act(`/tasks/${task.task_id}/run-to-review`, { role: 'delivery_lead' }, 'Correction implemented and re-submitted')) {
                    await act(`/reviews/${task.task_id}/execute`, { role: 'independent_reviewer' }, 'Independent review re-executed')
                  }
                }
              }}
            >
              ⟳ Re-develop &amp; Re-submit for Review
            </button>
          ) : null}
        </div>
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Findings Summary</h3>
          <ul className="checklist">
            {([['Critical', sevCount('critical')], ['Major', sevCount('major')], ['Minor', sevCount('minor')], ['Info', 0]] as const).map(([label, n]) => (
              <li key={label}>
                {label}
                <span className="state ok mono">{String(n)}</span>
              </li>
            ))}
            <li>
              <b>Total findings</b>
              <span className="state ok mono">{String(totalFindings)}</span>
            </li>
          </ul>
        </div>
        <div className="card rail-card">
          <h3>Review Governance</h3>
          <p className="hint">Independent review runs isolated from development. Separation of duties is enforced by the role model.</p>
        </div>
        <div className="card rail-card">
          <h3>Human Approval comes next</h3>
          <p className="hint">After this review, human approvers decide at the quality and release gates.</p>
        </div>
        <div className="card rail-card">
          <h3>No code editor exposed</h3>
          <p className="hint">Only evidence and status are visible. Implementation details remain behind the surface.</p>
        </div>
        {history.length ? (
          <div className="card rail-card">
            <h3>Review History</h3>
            <ul className="checklist">
              {history.map((a, i) => (
                <li key={`${a.timestamp}-${i}`}>
                  <span className="mono hint" style={{ marginRight: '6px' }}>{hhmm(a.timestamp)}</span>
                  {a.details || a.outcome || a.workflow}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        <GuidanceCard />
      </aside>
    </section>
  )
}
