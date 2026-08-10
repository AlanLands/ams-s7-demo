import { useRun } from '../state/RunContext'

export function Badge({ status, label, title }: { status?: string; label?: string; title?: string }) {
  const st = String(status ?? 'not_started')
  return <span className={`badge st-${st}`} title={title}>{label ?? st.replaceAll('_', ' ')}</span>
}

export function Prov({ provenance }: { provenance?: string }) {
  const { data } = useRun()
  if (!provenance) return null
  // Demo-mode presentation rule (spec 2026-08-10-demo-mode): non-AI
  // provenance renders as one neutral DEMO chip; stored provenance is
  // untouched. Live/replayed AI badges are never rewritten (they cannot
  // occur in a demo run).
  if (data?.run?.mode === 'demo'
      && (provenance === 'simulated' || provenance === 'rule_based')) {
    return <span className="prov prov-demo">DEMO</span>
  }
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
