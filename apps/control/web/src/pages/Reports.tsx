import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

const STAGE_LABELS = new Map([
  ['intake', 'Intake'],
  ['planning', 'Planning'],
  ['build_review', 'Build & Review'],
  ['quality', 'Final Gating'],
  ['release', 'Release'],
])

function stageLabel(key: string) {
  return STAGE_LABELS.get(key) ?? key
}

export function Reports() {
  const { data } = useRun()
  if (!data) return null

  const s = data.activity_summary ?? {}
  const run = data.run
  const stageTime = s.stage_time_s ?? {}
  const total = Object.values(stageTime).reduce((a, b) => a + b, 0)

  return (
    <section>
      <SectionTitle
        title="Reports"
        hint="Computed from the activity ledger — durations are simulated workflow durations"
      />
      <div className="grid cols-4">
        <div className="card metric">
          <div className="v">{`${Math.round(total)}s`}</div>
          <div className="l">Total workflow time</div>
        </div>
        <div className="card metric">
          <div className="v">{String(s.counters?.ai_workflows ?? 0)}</div>
          <div className="l">AI workflows (live)</div>
        </div>
        <div className="card metric">
          <div className="v">{String(s.counters?.human_approvals ?? 0)}</div>
          <div className="l">Human decisions</div>
        </div>
        <div className="card metric">
          <div className="v">{run.status.replaceAll('_', ' ')}</div>
          <div className="l">Run outcome</div>
        </div>
      </div>
      <SectionTitle title="Bottleneck insights" hint="Where workflow time accrued, by stage" />
      <div className="card">
        <ul className="plain">
          {Object.entries(stageTime).map(([k, v]) => (
            <li key={k}>
              <b>{stageLabel(k) + ': '}</b>{`${Math.round(v)}s`}<span className="hint">{total ? ` — ${Math.round((100 * v) / total)}%` : ''}</span>
            </li>
          ))}
        </ul>
      </div>
      <SectionTitle title="Ledger counters" />
      <div className="grid cols-3">
        {Object.entries(s.counters ?? {}).map(([k, v]) => (
          <div className="card metric" key={k}>
            <div className="v">{String(v)}</div>
            <div className="l">{k.replaceAll('_', ' ')}</div>
          </div>
        ))}
      </div>
    </section>
  )
}
