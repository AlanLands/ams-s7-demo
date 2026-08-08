// Ported verbatim from `function teamChip(name)` in apps/control/static/app.js
// (~line 811-816). Kept as a small local component here (mirroring the same
// local copy in RoutingByTeam.tsx) rather than promoted to `components/` —
// no shared team-chip component exists yet and this page shouldn't be the one
// to invent it while sibling planning pages are still mid-port.
export function TeamChip({ name }: { name?: string }) {
  if (!name) return <span>—</span>
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  return (
    <span className="team-chip">
      <span className="avatar">{initials}</span>
      {name}
    </span>
  )
}
