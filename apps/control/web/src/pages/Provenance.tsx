import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Provenance() {
  const { data } = useRun()
  if (!data) return null

  const rows = data.provenance_ledger ?? []

  return (
    <section>
      <SectionTitle
        title="Provenance ledger"
        hint="Append-only. Every artifact version, hashed. History is never rewritten."
      />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Event', 'Artifact', 'Type', 'v', 'SHA-256', 'Author', 'Stage', 'Action', 'Outcome', 'Inputs'].map(
                (heading) => <th key={heading}>{heading}</th>,
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.event_id}>
                <td className="mono nowrap">{r.event_id}</td>
                <td className="mono nowrap">{r.artifact_id}</td>
                <td>{r.artifact_type}</td>
                <td>{String(r.version)}</td>
                <td className="mono" title={r.sha256}>{r.sha256.slice(0, 10) + '…'}</td>
                <td>{r.author}</td>
                <td>{r.stage}</td>
                <td>{r.action}</td>
                <td>{r.outcome}</td>
                <td className="mono">{(r.inputs ?? []).join(', ') || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
