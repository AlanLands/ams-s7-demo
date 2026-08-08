import type { PlanStory } from './depGraph'

// Ported verbatim from `function sprintPlanCard(stories)` in
// apps/control/static/app.js (~line 1557-1574). `.sort()` is called with no
// comparator, matching the vanilla source exactly (works because sprint
// numbers are small positive integers, so lexicographic and numeric order
// agree) rather than "fixing" it into a numeric sort.
export function SprintPlanCard({ stories }: { stories: PlanStory[] }) {
  const sprints = [...new Set(stories.map((s) => s.sprint))].sort()
  const totalPts = stories.reduce((a, s) => a + s.estimate, 0) || 1
  return (
    <div className="card">
      <h3>Sprint Plan</h3>
      {sprints.map((sp) => {
        const own = stories.filter((s) => s.sprint === sp)
        const pts = own.reduce((a, s) => a + s.estimate, 0)
        return (
          <div className="sprint-row" key={sp}>
            <div className="sprint-row-head">
              <b>{`Sprint ${sp}`}</b>
              <span className="hint">{`${own.length} ${own.length === 1 ? 'story' : 'stories'} · ${pts} pts`}</span>
            </div>
            <div className="bar">
              <div className="bar-fill" style={{ width: `${Math.round((100 * pts) / totalPts)}%` }} />
            </div>
          </div>
        )
      })}
      <p className="hint">Bar shows each sprint's share of planned points. Sprint dates are set at execution, not invented here.</p>
    </div>
  )
}
