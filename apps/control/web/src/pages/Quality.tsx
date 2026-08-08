import { Badge } from '../components/Badge'
import { SectionTitle } from '../components/SectionTitle'
import { useRun } from '../state/RunContext'

function GatePanel({ gateId, title, hint }: { gateId: string; title: string; hint: string }) {
  const { data } = useRun()
  const gate = (data?.gates ?? []).find((candidate) => candidate.gate_id === gateId)

  return (
    <div className={`card ${gate?.status === 'passed' ? 'ok' : 'highlight'}`} style={{ marginTop: '14px' }}>
      <div className="section-title">
        <h3>{title}</h3>
        <Badge status={gate?.status ?? 'not_started'} />
      </div>
      {(gate?.conditions ?? []).length ? (
        <ul className="plain">
          {(gate?.conditions ?? []).map((condition, index) => (
            <li key={`${condition.condition}-${index}`}>
              {`${condition.met ? '✓' : '✗'} ${condition.condition}`}
              {condition.detail ? <span className="hint">{` — ${condition.detail}`}</span> : null}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">{hint}</p>
      )}
      {gate?.decided_by ? (
        <p className="hint">{`Decided by ${gate.decided_by} at ${gate.decided_at}`}</p>
      ) : null}
    </div>
  )
}

export function Quality() {
  const { data, act } = useRun()
  if (!data) return null

  const report = data.quality

  if (!report) {
    return (
      <section>
        <SectionTitle
          title="Stage 4 — Quality"
          hint="Evidence aggregated across every story. The gate is explicit conditions, never the score."
        />
        <div className="card">
          <p>Quality aggregation opens once the independent-review gate (G2) has passed for every task.</p>
          <div className="actions-row">
            <button className="primary" onClick={() => void act('/quality/run', {}, 'Quality checks aggregated')}>
              Run quality checks
            </button>
          </div>
        </div>
      </section>
    )
  }

  const checks = report.checks ?? []
  const passed = checks.filter((check) => check.status === 'passed').length

  return (
    <section>
      <SectionTitle
        title="Stage 4 — Quality"
        hint="Evidence aggregated across every story. The gate is explicit conditions, never the score."
      />

      <div className="grid cols-4">
        <div className="card metric">
          <div className="v">{`${passed}/${checks.filter((check) => check.status !== 'not_applicable').length}`}</div>
          <div className="l">Checks passed</div>
        </div>
        <div className="card metric">
          <div className="v">{String(report.risks?.length ?? 0)}</div>
          <div className="l">Open risks</div>
        </div>
        <div className="card metric">
          <div className="v">{String(report.exceptions?.length ?? 0)}</div>
          <div className="l">Approved exceptions</div>
        </div>
        <div className="card metric">
          <div className="v">{`${report.quality_score}`}</div>
          <div className="l">Score (informational)</div>
        </div>
      </div>
      <p className="hint" style={{ marginTop: '6px' }}>{report.score_note}</p>

      <SectionTitle title="Quality evidence" />
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Check', 'Name', 'Status', 'Evidence', 'Owner'].map((heading) => (
                <th key={heading}>{heading}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {checks.map((check, index) => (
              <tr key={`${check.check_id}-${index}`}>
                <td className="mono">{check.check_id}</td>
                <td>{check.name}</td>
                <td><Badge status={check.status === 'not_applicable' ? 'not_started' : check.status} /></td>
                <td>{check.evidence || '—'}</td>
                <td>{check.owner}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid cols-2" style={{ marginTop: '14px' }}>
        <div className="card warn">
          <h3>Risks</h3>
          <ul className="plain">
            {(report.risks ?? []).map((risk, index) => (
              <li key={`${risk.risk_id}-${index}`}>
                <b>{`${risk.risk_id} (${risk.severity}): `}</b>
                {risk.description}
              </li>
            ))}
          </ul>
        </div>
        <div className="card">
          <h3>Approved exceptions</h3>
          <ul className="plain">
            {(report.exceptions ?? []).map((exception, index) => (
              <li key={`${exception.exception_id}-${index}`}>
                <b>{`${exception.exception_id}: `}</b>
                {exception.description}
                <span className="hint">{` — approved by ${exception.approved_by}`}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="card" style={{ marginTop: '14px' }}>
        <h3>Release recommendation</h3>
        <p>{report.recommendation}</p>
        <div className="actions-row">
          <button className="ghost" onClick={() => void act('/quality/run', {}, 'Quality checks re-aggregated')}>
            Re-run checks
          </button>
          <button
            className="primary approve"
            onClick={() => void act('/quality/decide', {}, 'Quality gate decided')}
          >
            Decide quality gate (QA Lead)
          </button>
        </div>
      </div>

      <GatePanel
        gateId="G3"
        title="Gate 3 — Quality"
        hint="Conditions evaluate when the QA Lead decides the gate."
      />
    </section>
  )
}
