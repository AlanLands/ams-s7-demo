import { Prov } from '../components/Badge'
import { NotBuilt } from '../components/NotBuilt'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

/** Delivery KPI scorecard — evidence or visible absence. A KPI the run
 * cannot evidence renders "Not evidenced" with the reason, never an
 * invented number. The consolidated table maps the client's four outcome
 * dimensions, with the support-scope half explicitly attributed to S1–S6. */

const KPI_LABELS: Record<string, string> = {
  velocity: 'Velocity',
  cycle_time: 'Cycle time',
  first_time_right: 'First-time-right',
  defect_leakage: 'Defect leakage',
  estimation_accuracy: 'Estimation accuracy',
  on_time_on_budget: 'On-time / on-budget',
  cost_per_release: 'Cost per release',
}

const DIMENSION_LABELS: Record<string, string> = {
  efficiency: 'Efficiency',
  service_quality: 'Service quality',
  issue_resolution: 'Issue resolution',
  delivery_productivity: 'Delivery productivity',
}

export function Scorecard() {
  const { data } = useRun()
  if (!data) return null
  const card = data.kpi
  if (!card) {
    return (
      <section>
        <SectionTitle title="KPI Scorecard" />
        <NotBuilt name="KPI Scorecard" phase="the Planning stage — the scorecard reads the plan and downstream records" />
      </section>
    )
  }

  return (
    <section>
      <div className="section-title">
        <h2>Delivery KPI Scorecard</h2>
        <Prov provenance={card.provenance} />
      </div>
      <p className="hint">
        Computed from this run's own ledgers. A KPI the run cannot evidence says so — an honest
        absence beats an invented number.
      </p>
      <div className="grid cols-4">
        {Object.entries(card.kpis).map(([key, k]) => (
          <div className={`card metric${k.evidenced ? '' : ' muted'}`} key={key}>
            <div className="v">{k.evidenced ? `${k.value}${k.unit === '%' ? '%' : ''}` : '—'}</div>
            <div className="l">{KPI_LABELS[key] ?? key.replaceAll('_', ' ')}</div>
            <div className="hint">
              {k.evidenced ? (k.unit !== '%' ? `${k.unit} — ${k.basis}` : k.basis) : 'Not evidenced'}
              {k.note ? ` · ${k.note}` : ''}
            </div>
          </div>
        ))}
      </div>
      <SectionTitle
        title="Consolidated scorecard — four outcome dimensions"
        hint="The client's cross-scope view: delivery evidence from this run; support metrics belong to S1–S6 and are attributed, not borrowed"
      />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{['Dimension', 'Delivery scope (this run)', 'Support scope'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {card.consolidated.map((row) => (
              <tr key={row.dimension}>
                <td><b>{DIMENSION_LABELS[row.dimension] ?? row.dimension}</b></td>
                <td>
                  {row.delivery.map((k) => {
                    const item = card.kpis[k]
                    const label = KPI_LABELS[k] ?? k
                    return (
                      <div key={k}>
                        {label}
                        {': '}
                        {item?.evidenced ? `${item.value}${item.unit === '%' ? '%' : ` ${item.unit}`}` : 'not evidenced'}
                      </div>
                    )
                  })}
                </td>
                <td className="hint">{row.support}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
