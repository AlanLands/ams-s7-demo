import { useRun } from '../../state/RunContext'
import type { PlanStory } from './depGraph'
import { planningOf } from './planningHelpers'

// Ported from `function kpiTiles(k)` + `function planKpis(stories)` in
// apps/control/static/app.js (~line 820-832, 897-913). The two vanilla
// functions are combined into one component here since nothing else in this
// port calls `planKpis` independently of rendering the tiles. `completeness`
// (computed by vanilla's `planKpis` but never read by `kpiTiles`) is dropped
// for the same reason — it isn't rendered anywhere in `renderEpicToStories`.
export function KpiTiles({ stories }: { stories: PlanStory[] }) {
  const { data } = useRun()
  const conf = planningOf(data).confidence

  const teams = new Set<string>()
  stories.forEach((s) => {
    teams.add(s.accountable_team)
    ;(s.contributing_teams ?? []).forEach((t) => teams.add(t))
  })
  const acs = stories.flatMap((s) => s.acceptance_criteria ?? []).length
  const deps = stories.flatMap((s) => s.dependencies).length
  const sprints = new Set(stories.map((s) => s.sprint)).size

  return (
    <div className="tiles">
      <div className="tile t-red"><div className="v">{stories.length}</div><div className="l">Total Stories</div></div>
      <div className="tile t-green"><div className="v">{teams.size}</div><div className="l">Teams Involved</div></div>
      <div className="tile t-red"><div className="v">{acs}</div><div className="l">Acceptance Criteria</div></div>
      <div className="tile t-amber"><div className="v">{deps}</div><div className="l">Dependencies</div></div>
      <div className="tile t-amber"><div className="v">{sprints}</div><div className="l">Planned Sprints</div></div>
      <div className="tile t-blue">
        <div className="v">{conf ? `${conf.value}%` : '—'}</div>
        <div className="l">
          <span className="info" title={conf?.basis ?? 'Available once the AI plan draft exists.'}>AI Plan Confidence ⓘ</span>
        </div>
      </div>
    </div>
  )
}
