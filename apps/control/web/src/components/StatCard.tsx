import type { ReactNode } from 'react'

/** Mockup-style metric card: colored icon tile, big value, label, sub-line. */
export function StatCard({ icon, value, label, sub, accent }: {
  icon: ReactNode
  value: string
  label: string
  sub?: string
  accent: 'green' | 'blue' | 'orange' | 'purple' | 'violet' | 'red'
}) {
  return (
    <div className={`stat-card sc-${accent}`}>
      <div className="ic">{icon}</div>
      <div className="v">{value}</div>
      <div className="l">{label}</div>
      {sub ? <div className="s">{sub}</div> : null}
    </div>
  )
}
