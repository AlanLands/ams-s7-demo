import { Prov } from '../../components/Badge'
import type { CoverageBreakdown } from '../../types'

/** The client-facing coverage answer: which streams the AI executes, which
 * it prepares for externally owned teams, and which stay manual — rule-based
 * derivation from the plan, effort-weighted, never an AI claim. */

const LANE_LABELS: Record<string, [string, string]> = {
  agentic: ['Agentic', 'executed in the governed lane'],
  ai_assisted_external: ['AI-assisted · externally owned', 'AI prepares; another team delivers'],
  manual: ['Manual', 'human work; AI assists documentation only'],
}

export function CoveragePanel({ coverage }: { coverage: CoverageBreakdown }) {
  const lanes = coverage.by_coverage
  return (
    <div>
      <div className="section-title">
        <h3>AI coverage by delivery stream</h3>
        <Prov provenance={coverage.provenance} />
      </div>
      <p className="hint">
        Effort-weighted over story estimates — a heavy manual stream cannot hide behind a story
        count. Derived from the plan by fixed rules; not an AI assessment.
      </p>
      <div className="grid cols-3">
        {Object.entries(LANE_LABELS).map(([key, [label, hint]]) => {
          const lane = lanes[key]
          return (
            <div className="card metric" key={key}>
              <div className="v">{`${lane?.effort_pct ?? 0}%`}</div>
              <div className="l">{label}</div>
              <div className="hint">{`${lane?.stories ?? 0} stories · ${lane?.effort_points ?? 0} pts — ${hint}`}</div>
            </div>
          )
        })}
      </div>
      <div className="table-wrap" style={{ marginTop: 14 }}>
        <table>
          <thead>
            <tr>{['Story', 'Team', 'Stream', 'Coverage', 'Why'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {coverage.stories.map((row) => (
              <tr key={row.story_id}>
                <td className="mono">{row.story_id}</td>
                <td>{row.team}</td>
                <td className="mono">{row.stream}</td>
                <td>{LANE_LABELS[row.coverage]?.[0] ?? row.coverage}</td>
                <td className="hint">{row.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {coverage.integration_note ? (
        <div className="card" style={{ marginTop: 14 }}>
          <h3>Integration point</h3>
          <p>{coverage.integration_note}</p>
        </div>
      ) : null}
    </div>
  )
}
