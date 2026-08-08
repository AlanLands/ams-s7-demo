export function Badge({ status }: { status?: string }) {
  const label = String(status ?? 'not_started')
  return <span className={`badge st-${label}`}>{label.replaceAll('_', ' ')}</span>
}

export function Prov({ provenance }: { provenance?: string }) {
  if (!provenance) return null
  return <span className={`prov prov-${provenance}`}>{provenance.toUpperCase()}</span>
}
