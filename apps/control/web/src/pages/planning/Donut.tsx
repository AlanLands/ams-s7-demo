import type { PlanStory } from './depGraph'
import { teamColor } from './depGraph'

// Ported verbatim from `function donut(stories)` in apps/control/static/app.js
// (~line 1534-1555, just above `renderPlanSummary`). Same team-color stops and
// proportional arc math, expressed as an inline conic-gradient style object
// instead of a `style` attribute string.
export function Donut({ stories }: { stories: PlanStory[] }) {
  const teams = [...new Set(stories.map((s) => s.accountable_team))]
  let acc = 0
  const stops: string[] = []
  for (const t of teams) {
    const n = stories.filter((s) => s.accountable_team === t).length
    const from = (360 * acc) / stories.length
    acc += n
    const to = (360 * acc) / stories.length
    stops.push(`${teamColor(t)} ${from}deg ${to}deg`)
  }
  return (
    <div className="donut-wrap">
      <div className="donut" style={{ background: `conic-gradient(${stops.join(', ')})` }}>
        <div className="donut-hole">
          <div className="v">{stories.length}</div>
          <div className="l">Stories</div>
        </div>
      </div>
      <ul className="donut-legend">
        {teams.map((t) => (
          <li key={t}>
            <span className="legend-dot" style={{ background: teamColor(t) }} />
            {`${t} (${stories.filter((s) => s.accountable_team === t).length})`}
          </li>
        ))}
      </ul>
    </div>
  )
}
