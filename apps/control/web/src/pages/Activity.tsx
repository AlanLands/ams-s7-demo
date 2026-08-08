import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Activity() {
  const { data } = useRun()
  if (!data) return null

  const rows = [...(data.activity ?? [])].reverse()
  const s = data.activity_summary ?? {}

  return (
    <section>
      <SectionTitle title="Factory activity log" hint="Every workflow, gate event and human decision" />
      <div className="grid cols-3">
        {Object.entries(s.counters ?? {}).map(([k, v]) => (
          <div className="card metric" key={k}>
            <div className="v">{String(v)}</div>
            <div className="l">{k.replaceAll('_', ' ')}</div>
          </div>
        ))}
      </div>
      <div className="table-wrap" style={{ marginTop: '14px' }}>
        <table>
          <thead>
            <tr>
              {['Time', 'Stage', 'Actor', 'Type', 'Workflow', 'Outcome', 'Details'].map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, index) => (
              <tr key={`${r.timestamp}-${index}`}>
                <td className="mono">{r.timestamp}</td>
                <td>{r.stage}</td>
                <td>{r.actor}</td>
                <td>{r.actor_type}</td>
                <td>{r.workflow || '—'}</td>
                <td>{r.outcome || '—'}</td>
                <td>{r.details || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
