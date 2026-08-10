export function Badge({ status, label, title }: { status?: string; label?: string; title?: string }) {
  const st = String(status ?? 'not_started')
  return <span className={`badge st-${st}`} title={title}>{label ?? st.replaceAll('_', ' ')}</span>
}

export function Prov({ provenance }: { provenance?: string }) {
  if (!provenance) return null
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
