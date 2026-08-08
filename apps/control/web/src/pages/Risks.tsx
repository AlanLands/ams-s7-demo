import { Badge } from '../components/Badge'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

export function Risks() {
  const { data, act } = useRun()
  if (!data) return null

  const report = data.quality
  const risks = report?.risks ?? []
  const stale = data.staleness ?? []
  const amendments = data.amendments ?? []
  const design = data.design
  const seen = new Set<string>()
  const latestAmendments = [...amendments].reverse().filter((amendment) => {
    if (seen.has(amendment.amendment_id)) return false
    seen.add(amendment.amendment_id)
    return true
  })

  return (
    <section>
      <SectionTitle
        title="Risks & Alerts"
        hint="Staleness is detected from upstream pointers and hashes in the provenance ledger"
      />

      {risks.length === 0 && stale.length === 0 && amendments.length === 0 ? (
        <div className="card">
          <p>No open risks, staleness alerts or amendments in this run yet.</p>
        </div>
      ) : null}

      {stale.length ? (
        <>
          <div className="card bad">
            <h3>{`Release gate blocked — ${stale.length} stale artifact(s)`}</h3>
            <p className="hint">
              An upstream artifact changed after these were produced. Each must be re-validated as a new version
              before release; nothing is silently updated.
            </p>
          </div>
          <div className="table-wrap" style={{ marginTop: '10px' }}>
            <table>
              <thead>
                <tr>
                  {['Artifact', 'Type', 'Version', 'Status', 'Reason'].map((heading) => (
                    <th key={heading}>{heading}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {stale.map((artifact, index) => (
                  <tr key={`${artifact.artifact_id}-${artifact.version}-${index}`}>
                    <td className="mono">{artifact.artifact_id}</td>
                    <td>{artifact.artifact_type}</td>
                    <td>{`v${artifact.version}`}</td>
                    <td><Badge status="stale" /></td>
                    <td>{artifact.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      {risks.map((risk, index) => (
        <div className="card warn" style={{ marginTop: '10px' }} key={`${risk.risk_id}-${index}`}>
          <h3>{`${risk.risk_id} — ${risk.severity}`}</h3>
          <p>{risk.description}</p>
        </div>
      ))}

      {amendments.length ? (
        <>
          <SectionTitle title="Amendments" hint="Controlled change management — append-only" />
          {latestAmendments.map((amendment) => (
            <div
              className={`card ${amendment.implementation_status === 'completed' ? 'ok' : 'warn'}`}
              key={amendment.amendment_id}
            >
              <div className="section-title">
                <h3>{`${amendment.amendment_id} — ${amendment.reason}`}</h3>
                <Badge status={amendment.implementation_status === 'completed' ? 'completed' : 'in_progress'} />
              </div>
              <div className="kv" style={{ marginTop: '8px' }}>
                <b>Initiator</b><span>{amendment.initiator}</span>
                <b>Impact</b><span>{amendment.impact_assessment}</span>
                <b>Affected</b><span className="mono">{(amendment.affected_artifacts ?? []).join(', ') || '—'}</span>
                <b>Required changes</b>
                <span>
                  <ul className="plain">
                    {(amendment.required_changes ?? []).map((change, index) => (
                      <li key={`${change}-${index}`}>{change}</li>
                    ))}
                  </ul>
                </span>
                <b>Verification</b>
                <span>
                  <Badge status={amendment.verification_status === 'completed' ? 'passed' : amendment.verification_status} />
                </span>
              </div>
            </div>
          ))}
        </>
      ) : null}

      <div className="card" style={{ marginTop: '14px' }}>
        <h3>Demonstration controls</h3>
        <p className="hint">
          {design?.version !== undefined && design.version > 1
            ? 'Upstream change applied: DES-001 is at v2 (SME ruling on draft retention).'
            : 'Simulate the SME ruling that changes DES-001 after downstream work exists — downstream artifacts go stale and release blocks.'}
        </p>
        <div className="actions-row">
          <button
            className="primary"
            onClick={() => void act('/change/upstream', {}, 'DES-001 amended — downstream marked stale')}
          >
            Apply upstream SME ruling
          </button>
          <button
            className="primary approve"
            onClick={() => void act('/change/self-correct', {}, 'Self-correction complete')}
          >
            Run self-correction workflow
          </button>
        </div>
      </div>
    </section>
  )
}
