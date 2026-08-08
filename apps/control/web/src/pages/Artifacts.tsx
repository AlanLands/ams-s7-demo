import { Badge } from '../components/Badge'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Artifacts() {
  const { data } = useRun()
  if (!data) return null

  const rows = data.provenance ?? []

  return (
    <section>
      <SectionTitle title="Artifacts" hint="Current version of every artifact this run has produced" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Artifact', 'Type', 'Version', 'Author', 'Created', 'Status'].map((heading) => (
                <th key={heading}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.artifact_id}>
                <td className="mono">{row.artifact_id}</td>
                <td>{row.artifact_type}</td>
                <td>{`v${row.version}`}</td>
                <td>{row.author}</td>
                <td className="mono">{row.timestamp}</td>
                <td>{row.stale ? <Badge status="stale" /> : <Badge status="completed" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
