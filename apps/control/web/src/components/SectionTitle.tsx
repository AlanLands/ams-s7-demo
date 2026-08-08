export function SectionTitle({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="section-title">
      <h2>{title}</h2>
      {hint ? <span className="hint">{hint}</span> : null}
    </div>
  )
}
