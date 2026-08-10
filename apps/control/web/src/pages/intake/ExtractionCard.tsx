import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'
import { EditExtractionDrawer } from './EditExtractionDrawer'

interface Props {
  extracting: boolean
  extractError: string | null
  onRetry: () => void
}

export function ExtractionCard({ extracting, extractError, onRetry }: Props) {
  const { data, act } = useRun()
  const [expanded, setExpanded] = useState(false)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [finalizing, setFinalizing] = useState(false)
  const source = data?.intake?.source
  const ext = data?.intake?.extraction
  const isLive = data?.run?.mode === 'live'

  const done = Boolean(source && ext)
  const title = done
    ? (ext!.method === 'live_llm' ? '2. AI Extraction' : '2. Extraction (Rule-Based)')
    : '2. AI Extraction'

  return (
    <div className="card">
      <div className="section-title">
        <h3>
          {title}
          {done && !extracting && <span className="title-status"> (Completed)</span>}
        </h3>
        {ext && !extracting && (
          <span className="chip success">✓ Extraction Complete</span>
        )}
      </div>

      {!source && (
        <p className="hint">Upload or paste a requirement to begin.</p>
      )}

      {source && extracting && (
        <ul className="checklist">
          <li>Reading document…</li>
          <li>Extracting requirement…</li>
          <li>Structuring Epic…</li>
        </ul>
      )}

      {source && !extracting && extractError && !ext && (
        <div>
          <p className="hint">Extraction could not be completed.</p>
          <button type="button" className="outline" onClick={onRetry}>Retry Extraction</button>
        </div>
      )}

      {ext && !extracting && (
        <div>
          <p className="hint">AI has extracted and structured the requirement.</p>
          <div className="ext-kv" style={{ marginTop: 10 }}>
            <b>Title</b><span>{ext.epic_title}</span>
            <b>Business Objective</b><span><span className={expanded ? undefined : 'clamp-3'}>{ext.business_objective}</span></span>
            <b>Requirement Summary</b><span><span className={expanded ? undefined : 'clamp-3'}>{ext.requirement_summary}</span></span>
          </div>

          <h4 style={{ marginTop: 14, fontSize: 12.5, color: 'var(--muted)' }}>Extracted Requirements</h4>
          <ul className="plain req-rows">
            {ext.extracted_requirements.slice(0, expanded ? undefined : 3).map((r) => (
              <li key={r.rule_id} className="req-row">
                <span className="chip req-id">{r.rule_id}</span>
                <span>{r.text}</span>
              </li>
            ))}
          </ul>
          {(ext.extracted_requirements.length > 3
            || ext.business_objective.length > 220
            || ext.requirement_summary.length > 220) && (
            <button type="button" className="link-btn" onClick={() => setExpanded((v) => !v)}>
              {expanded ? 'Show less ↑' : 'View Full Extracted Content ↓'}
            </button>
          )}

          {ext.edited_by ? (
            <p className="hint" style={{ marginTop: 8 }}>
              <span className="chip tag">AI Generated • Human Edited</span>{' '}
              by {ext.edited_by} at {ext.edited_at}
            </p>
          ) : (
            <p style={{ marginTop: 8 }}><Prov provenance={ext.provenance} /></p>
          )}

          <div className="actions-row split" style={{ marginTop: 14 }}>
            <button type="button" className="outline" onClick={() => setDrawerOpen(true)}>✎ Edit Extracted Epic</button>
            <span className="btns">
              <button
                type="button"
                className="primary sq"
                disabled={finalizing}
                onClick={async () => {
                  setFinalizing(true)
                  await act('/intake/finalize-epic', {}, 'Epic created — Business Owner signs off the intake gate')
                  setFinalizing(false)
                }}
              >
                Create Epic →
              </button>
              <button
                type="button"
                className="outline approve"
                disabled={finalizing}
                onClick={() => act('/intake/pass-gate', {}, 'Intake gate passed')}
              >
                ✓ Pass Intake Gate
              </button>
            </span>
          </div>
          <p className="hint" style={{ marginTop: 8 }}>
            The intake gate sign-off is the Business Owner's decision — switch to the Business Owner
            role to pass it.
          </p>

          {!isLive && (
            <p className="hint" style={{ marginTop: 10 }}>
              Simulation mode demonstrates extraction from your actual document; downstream planning still
              follows the rehearsed demo scenario, exactly as it does for every run in simulation mode today.
            </p>
          )}
        </div>
      )}

      {ext && <EditExtractionDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} extraction={ext} />}
    </div>
  )
}
