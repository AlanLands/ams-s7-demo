export function Badge({ status, label }: { status?: string; label?: string }) {
  const st = String(status ?? 'not_started')
  return <span className={`badge st-${st}`}>{label ?? st.replaceAll('_', ' ')}</span>
}

export function Prov({ provenance }: { provenance?: string }) {
  if (!provenance) return null
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
