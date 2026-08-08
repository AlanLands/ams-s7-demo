import { useRun } from '../../state/RunContext'

// Compact one-row replacement for the old EpicDetailsCard on the Epic to
// Stories page (2026-08-09 redesign). The full epic record — business outcome,
// priority, created-by, provenance — still lives on the Plan Summary page;
// this strip carries only what a reader needs while working the story list.
export function EpicSummaryStrip() {
  const { data } = useRun()
  if (!data) return null
  const epic = data.intake?.epic
  const req = data.intake?.requirement
  if (!epic) return null

  const owner = req?.business_owner ?? '—'
  const initials = owner
    .split(/\s+/)
    .map((w) => w[0] ?? '')
    .slice(0, 2)
    .join('')
    .toUpperCase()

  return (
    <div className="card epic-strip">
      <div><span className="strip-l">Epic ID</span><span className="mono">{epic.epic_id}</span></div>
      <div><span className="strip-l">Title</span><span>{epic.title}</span></div>
      <div>
        <span className="strip-l">Owner</span>
        <span className="team-chip"><span className="avatar">{initials || '—'}</span>{owner}</span>
      </div>
      <div><span className="strip-l">Domain</span><span>{req?.domain ?? '—'}</span></div>
      <div><span className="strip-l">Est. Stories</span><span>{String(epic.estimated_stories)}</span></div>
      <div><span className="strip-l">AI Status</span><span className="strip-ok">✓ Analysed</span></div>
    </div>
  )
}
