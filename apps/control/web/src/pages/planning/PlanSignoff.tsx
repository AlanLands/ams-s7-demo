import { Badge } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import { depGraph } from './depGraph'
import { Gate1Rail } from './Gate1Rail'
import { PlanArtifactsCard } from './PlanArtifactsCard'
import { planningOf, storyGaps } from './planningHelpers'

export function PlanSignoff() {
  const { data, runId, act, can } = useRun()
  if (!data) return null

  const isLive = data.run?.mode === 'live'
  const planning = planningOf(data)
  const stories = planning.stories ?? []
  const plan = planning.plan
  const conf = planning.confidence
  const analysis = data.intake?.analysis
  const graph = stories.length ? depGraph(stories) : { edges: [] as { from: string; to: string; cross: boolean }[] }
  const complete = stories.filter((s) => storyGaps(s).length === 0).length
  const acs = stories.flatMap((s) => s.acceptance_criteria ?? []).length
  const ready = stories.length > 0 && complete === stories.length

  const estimatesOk = stories.filter((s) => s.estimate > 0).length
  const rollbacksOk = stories.filter((s) => s.rollback_plan).length

  const readinessRows: [string, string][] = [
    ['Story completeness', stories.length ? `${Math.round((100 * complete) / stories.length)}%` : '—'],
    ['Stories ready', `${complete} / ${stories.length}`],
    ['Acceptance criteria testable', `${acs} / ${acs}`],
    ['Dependencies mapped', `${graph.edges.length} / ${graph.edges.length}`],
    ['Estimates provided', `${estimatesOk} / ${stories.length}`],
    ['Rollback plans defined', `${rollbacksOk} / ${stories.length}`],
    ['Risks identified', String((analysis?.risk_register ?? analysis?.risks ?? []).length)],
    ['Assumptions documented', String((analysis?.assumptions ?? []).length)],
    ['AI Plan Confidence', conf ? `${conf.value}%` : '—'],
  ]

  const approvals = (data.approvals ?? []).filter((a) => a.subject === 'plan')
  const historyRows: [string, string, string, string][] = approvals.length
    ? approvals.map((a) => [a.approver, a.role.replaceAll('_', ' '), a.decision, a.decided_at])
    : (plan ? [[plan.signed_by, 'business owner', 'approved', plan.signed_at] as [string, string, string, string]] : [])

  const repoNames = [...new Set(stories.map((s) => s.target_repository).filter((r): r is string => Boolean(r)))]
  const showHandoff = Boolean(data.run?.plan_locked) && isLive

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: 16 }}>
          <h2>Plan Sign-off (Gate 1)</h2>
          <span className="hint">Review and approve the plan to lock it and proceed to execution.</span>
        </div>

        <div className="card">
          <div className="section-title">
            <h3>✦ AI Plan Assessment</h3>
            <span className="hint">AI recommendation and human approval required to lock the plan</span>
          </div>
          <div className="readiness">
            <div className="readiness-rows">
              {readinessRows.map(([label, v]) => (
                <div className="readiness-row" key={label}>
                  <span>{label}</span><b>{v}</b>
                </div>
              ))}
            </div>
            <div className={`readiness-verdict ${ready ? 'ok' : 'warn'}`}>
              <span className="big-check">{ready ? '✓' : '…'}</span>
              <p>{ready
                ? (plan ? 'Plan is signed and locked.' : 'Plan is ready for sign-off. All mandatory requirements are complete.')
                : 'Not ready — every story must pass quality validation first.'}</p>
              <p className="hint">
                {ready && !plan
                  ? 'AI Recommendation: READY FOR PLAN APPROVAL — derived from the validation rules on the left, decided by the human on the right.'
                  : ''}
              </p>
            </div>
          </div>
        </div>

        <div style={{ marginTop: 14 }} className="card">
          <h3>Approval History</h3>
          {historyRows.length === 0 ? (
            <p className="hint">No approvals yet — the sign-off below records the first.</p>
          ) : (
            <div className="table-wrap" style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    {['Approver', 'Role', 'Status', 'Date & Time'].map((h) => <th key={h}>{h}</th>)}
                  </tr>
                </thead>
                <tbody>
                  {historyRows.map(([who, role, status, at], i) => (
                    <tr key={i}>
                      <td>{who}</td>
                      <td>{role}</td>
                      <td><Badge status={status === 'approved' ? 'passed' : 'failed'} /></td>
                      <td className="mono">{at}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {showHandoff ? (
          <div style={{ marginTop: 14 }} className="card">
            <div className="section-title">
              <h3>Delivery Handoff</h3>
              <span className="hint">Portable, per-team packages — no .claude/ tooling</span>
            </div>
            <div className="actions-row" style={{ gap: 8, flexWrap: 'wrap' }}>
              <button
          disabled={!can('export_artifacts')}
          title={can('export_artifacts') ? undefined : 'Not available to the acting role — switch role in the header'} type="button" className="outline" onClick={() => act('/planning/export-artifacts', {}, 'Artifacts exported')}>
                Export Artifacts
              </button>
              <button
          disabled={!can('write_delivery_clone')}
          title={can('write_delivery_clone') ? undefined : 'Not available to the acting role — switch role in the header'} type="button" className="outline" onClick={() => act('/planning/write-to-clone', {}, 'Committed locally to each target repo')}>
                Write to Clone
              </button>
              <button
                type="button"
                className="outline"
                onClick={() => { window.location.href = `/api/runs/${runId}/planning/export.zip` }}
              >
                ⬇ Download Zip
              </button>
            </div>
            <p className="hint" style={{ marginTop: 10 }}>
              {`Pushing creates delivery/${runId} on each target repo — a fresh, disposable branch, never the default branch. Merging it into your own working branch is a manual step; nothing here does that for you.`}
            </p>
            <div className="actions-row" style={{ gap: 8, flexWrap: 'wrap', marginTop: 8 }}>
              {repoNames.map((repo) => (
                <button
          disabled={!can('push_delivery_branch')}
          title={can('push_delivery_branch') ? undefined : 'Not available to the acting role — switch role in the header'}
                  key={repo}
                  type="button"
                  className="primary sq"
                  onClick={() => act('/planning/push-delivery-branch', { repo_name: repo }, `Pushed to ${repo}`)}
                >
                  {`Push delivery branch → ${repo}`}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <div style={{ marginTop: 14 }}>
          <PlanArtifactsCard showDownloadAll />
        </div>
      </div>
      <aside className="rail">
        <Gate1Rail />
      </aside>
    </section>
  )
}
