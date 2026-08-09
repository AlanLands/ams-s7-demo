import { useRun } from '../state/RunContext'
import { Badge } from '../components/Badge'
import { FlowStrip } from '../components/FlowStrip'

export function Overview() {
  const { data } = useRun()
  if (!data) return null
  const run = data.run
  const summary = data.activity_summary ?? {}
  const counters = summary.counters ?? {}
  const gates = data.gates ?? []

  return (
    <section>
      <div className="section-title">
        <h2>Delivery overview</h2>
        <span className="hint">{data.scenario?.title ?? ''}</span>
      </div>
      <div className="section-title">
        <h2>Delivery flow</h2>
        <span className="hint">Requirement through transition to maintenance</span>
      </div>
      <FlowStrip />
      <div className="grid cols-4">
        <div className="card metric"><div className="v">{data.provenance?.length ?? 0}</div><div className="l">Artifacts</div></div>
        <div className="card metric"><div className="v">{counters.human_approvals ?? 0}</div><div className="l">Human approvals</div></div>
        <div className="card metric"><div className="v">{counters.gate_failures ?? 0}</div><div className="l">Gate failures</div></div>
        <div className="card metric"><div className="v">{summary.total_events ?? 0}</div><div className="l">Activity events</div></div>
      </div>
      <div className="section-title"><h2>Gates</h2><span className="hint">Progress is a set of explicit conditions, never a score</span></div>
      <div className="gate-strip">
        {gates.map((g) => (
          <div className="gate-card" key={g.gate_id}>
            <div className="gid">{g.gate_id}</div>
            <div className="glabel">{g.label}</div>
            <Badge status={g.status} />
            {g.decided_by && <div className="hint">by {g.decided_by}</div>}
          </div>
        ))}
      </div>
      <div className="section-title"><h2>Scenario</h2></div>
      <div className="card">
        <div className="kv">
          <b>Scenario</b><span>{data.scenario?.title ?? '—'}</span>
          <b>Description</b><span>{data.scenario?.description ?? '—'}</span>
          <b>Epic source</b><code>{data.scenario?.epic_source ?? '—'}</code>
          <b>Run created</b><span>{run.created_at}</span>
        </div>
      </div>
    </section>
  )
}
