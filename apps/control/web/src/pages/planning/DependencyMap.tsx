import { useEffect, useRef, useState } from 'react'
import { NotBuilt } from '../../components/NotBuilt'
import { useRun } from '../../state/RunContext'
import { depGraph, drawDepArrows, teamColor, type PlanStory } from './depGraph'

// Ported from `renderDependencyMap` in apps/control/static/app.js
// (~line 1406-1489). See depGraph.ts for the ported `depGraph`, `teamColor`
// and `drawDepArrows` helpers this component calls.
//
// Page-local UI state (state.depFilter / state.depLayout / state.depLegend in
// the vanilla source) becomes local useState here — it was only global
// because vanilla JS had no per-component state mechanism.

export function DependencyMap() {
  const { data } = useRun()
  const [filter, setFilter] = useState('')
  const [vertical, setVertical] = useState(true) // vanilla default: state.depLayout ?? "ttb"
  const [showLegend, setShowLegend] = useState(true) // vanilla default: state.depLegend ?? true
  const graphRef = useRef<HTMLDivElement>(null)

  // Double cast: RunState.planning is already typed in ../../types.ts as
  // PlanningState/PlanStory with every field this page needs (dependencies,
  // estimate, sprint, provenance, ...) — identical to the local PlanStory
  // this page imports from depGraph.ts. Casting through the local type
  // instead of the shared one is a deliberate, still-open cleanup deferred to
  // a follow-up. See depGraph.ts's PlanStory doc comment.
  const all = ((data?.planning as unknown) as { stories: PlanStory[] } | undefined)?.stories ?? []
  const stories = filter ? all.filter((s) => s.accountable_team === filter) : all
  const { depth, edges } = depGraph(stories)
  const graphAll = depGraph(all)
  const teams = [...new Set(all.map((s) => s.accountable_team))]
  const maxDepth = Math.max(0, ...Object.values(depth))

  // Stories at the same depth can never depend on one another (a dependency
  // always puts the dependent strictly deeper), so each column is a set of
  // stories that can run in parallel — surfaced as a numbered "wave".
  const columns: { wave: number; col: PlanStory[] }[] = []
  for (let d = 0; d <= maxDepth; d++) {
    const col = stories.filter((s) => depth[s.story_id] === d)
    if (col.length) columns.push({ wave: d + 1, col })
  }

  const waves: PlanStory[][] = []
  all.forEach((s) => {
    const d = graphAll.depth[s.story_id]
    ;(waves[d] ??= []).push(s)
  })
  const maxParallel = Math.max(0, ...waves.map((w) => w.length))

  // The vanilla version calls `requestAnimationFrame(() => drawDepArrows(...))`
  // unconditionally on every render. No dependency array here reproduces that
  // exactly: the arrows are re-measured and redrawn after every commit, which
  // is what "run after paint, measure the real DOM, draw" requires — filter,
  // layout, and any story-data change are already covered because they all
  // cause a re-render.
  useEffect(() => {
    const container = graphRef.current
    if (!container) return
    const raf = requestAnimationFrame(() => drawDepArrows(container, edges, vertical))
    return () => cancelAnimationFrame(raf)
  })

  if (!data) return null
  if (!all.length) {
    return <NotBuilt name="Dependency Map" phase="the Planning stage — generate the draft plan first" />
  }

  const allSimulated = all.every((s) => s.provenance === 'simulated')
  const crossCount = graphAll.edges.filter((e) => e.cross).length

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '16px' }}>
          <h2>{`Dependency Map ${allSimulated ? '(AI Generated)' : '(AI + Human)'}`}</h2>
          <span className="hint">
            The planning model identified the dependencies and delivery sequence; human stories join the same graph.
          </span>
        </div>
        <div className="card">
          <div className="card-head">
            <div className="btns">
              <label className="hdr-field">
                <span className="hdr-label">View</span>
                <select value={filter} onChange={(e) => setFilter(e.target.value)}>
                  <option value="">All Stories</option>
                  {teams.map((t) => (
                    <option value={t} key={t}>
                      {t}
                    </option>
                  ))}
                </select>
              </label>
              <label className="hdr-field">
                <span className="hdr-label">Layout</span>
                <select
                  value={vertical ? 'Top to Bottom' : 'Left to Right'}
                  onChange={(e) => setVertical(e.target.value === 'Top to Bottom')}
                >
                  <option>Left to Right</option>
                  <option>Top to Bottom</option>
                </select>
              </label>
            </div>
            <button className="outline" onClick={() => setShowLegend((v) => !v)}>
              ⚑ Legend
            </button>
          </div>
          <div className={`dep-graph${vertical ? ' vertical' : ''}`} ref={graphRef}>
            <svg className="dep-arrows" />
            {columns.map(({ wave, col }) => (
              <div className="dep-wave" key={wave}>
                <div className="wave-head">
                  <span className="wave-name">Wave {wave}</span>
                  <span className="wave-note">
                    {col.length > 1 ? `${col.length} stories in parallel` : '1 story'}
                  </span>
                </div>
                <div className="dep-col">
                {col.map((s) => (
                  <div
                    className="dep-card"
                    data-story={s.story_id}
                    key={s.story_id}
                    style={{ borderColor: teamColor(s.accountable_team) }}
                  >
                    <div className="mono dep-id" style={{ color: teamColor(s.accountable_team) }}>
                      {s.story_id}
                    </div>
                    <div className="dep-title">{s.title}</div>
                    <div className="dep-meta">
                      <span className="hint">{s.accountable_team}</span>
                      <span className="sprint-chip">{`S${s.sprint}`}</span>
                    </div>
                  </div>
                ))}
                </div>
              </div>
            ))}
          </div>
          {showLegend ? (
            <div className="dep-legend">
              {teams.map((t) => (
                <span className="legend-item" key={t}>
                  <span className="legend-dot" style={{ background: teamColor(t) }} />
                  {t}
                </span>
              ))}
              <span className="legend-item">
                <span className="legend-line solid" />
                Dependency
              </span>
              <span className="legend-item">
                <span className="legend-line dashed" />
                Cross Dependency
              </span>
            </div>
          ) : null}
        </div>
      </div>
      <aside className="rail">
        <div className="card rail-card">
          <h3>Map Summary</h3>
          <ul className="checklist">
            {(
              [
                ['Total Stories', all.length],
                ['Dependencies', graphAll.edges.length],
                ['Cross Dependencies', crossCount],
                ['Teams Involved', teams.length],
                ['Planned Sprints', new Set(all.map((s) => s.sprint)).size],
                ['Execution Waves', waves.filter(Boolean).length],
                ['Max Parallelism', maxParallel],
              ] as [string, number][]
            ).map(([label, v]) => (
              <li key={label}>
                {label}
                <span className="state ok">{String(v)}</span>
              </li>
            ))}
          </ul>
        </div>
        <div className="card rail-card">
          <h3>Parallel Execution</h3>
          <p className="hint">
            Stories in the same wave have no dependencies on each other — they can start together
            once the previous wave completes.
          </p>
          <ul className="checklist">
            {waves.map((w, d) =>
              w ? (
                <li key={d}>
                  <span>
                    Wave {d + 1}&ensp;
                    <span className="mono hint">{w.map((s) => s.story_id).join(', ')}</span>
                  </span>
                  <span className={`state ${w.length > 1 ? 'ok' : ''}`}>
                    {w.length > 1 ? `${w.length} parallel` : 'solo'}
                  </span>
                </li>
              ) : null,
            )}
          </ul>
        </div>
        <div className="card rail-card">
          <h3>Critical Path</h3>
          <p className="hint">The longest dependency chain — computed from the plan's edges.</p>
          <ol className="critical-path">
            {graphAll.critical.map((id) => (
              <li key={id}>
                <span className="mono">{id}</span>
              </li>
            ))}
          </ol>
        </div>
      </aside>
    </section>
  )
}
