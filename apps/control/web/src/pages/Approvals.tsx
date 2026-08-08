import { Badge } from '../components/Badge'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Approvals() {
  const { data } = useRun()
  if (!data) return null

  const rows = data.approvals ?? []

  return (
    <section>
      <SectionTitle title="Approvals" hint="Append-only record of every human decision" />
      {rows.length === 0 ? (
        <div className="card">
          <p>No approvals recorded yet in this run.</p>
        </div>
      ) : (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                {['Id', 'Subject', 'Role', 'Approver', 'Decision', 'Note', 'When'].map((heading) => (
                  <th key={heading}>{heading}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.approval_id}>
                  <td className="mono">{row.approval_id}</td>
                  <td>{row.subject}</td>
                  <td>{row.role}</td>
                  <td>{row.approver}</td>
                  <td><Badge status={row.decision === 'approved' ? 'passed' : 'failed'} /></td>
                  <td>{row.note || '—'}</td>
                  <td className="mono">{row.decided_at}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
