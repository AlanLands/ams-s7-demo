import { Fragment, useState } from 'react'
import { Badge } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import { TEAMS, type PlanStory } from './depGraph'
import { StoryDetailModal } from './StoryDetailModal'
import { TeamChip } from './TeamChip'

// Ported from `function storiesPanel(stories, editable)` in
// apps/control/static/app.js (~line 1096-1150), plus the row-click handler
// and inline edit row from `storyRow` (~line 1056-1094). `editable` defaults
// to `false` for `renderPlanSummary`'s read-only call site (it never passes
// the argument in vanilla); "Epic to Stories" (`renderEpicToStories`, ~line
// 1295) is the caller that passes `editable = !locked` and lights up the
// per-row team/estimate/sprint dropdowns behind the kebab button, each a
// `patchAct` PATCH exactly like vanilla's `act(..., "PATCH")` calls.
//
// Page-local UI state (state.storyFilter / state.storyView / state.editStory
// in the vanilla source) becomes local useState, per this project's pattern.

const ESTIMATES = [2, 3, 5, 8, 13]
const SPRINTS = [1, 2, 3]

function exportStories(stories: PlanStory[]) {
  const blob = new Blob([JSON.stringify(stories, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'plan-stories.json'
  a.click()
  URL.revokeObjectURL(a.href)
}

export function StoriesPanel({ stories, editable = false }: { stories: PlanStory[]; editable?: boolean }) {
  const { patchAct, notify } = useRun()
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<'table' | 'board'>('table')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [detailStory, setDetailStory] = useState<PlanStory | null>(null)

  const shown = filter ? stories.filter((s) => s.accountable_team === filter) : stories
  const teams = [...new Set(stories.map((s) => s.accountable_team))]

  const head = (
    <div className="card-head">
      <h3>{`User Stories (${shown.length})`}</h3>
      <div className="btns">
        <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="">All teams</option>
          {teams.map((t) => <option value={t} key={t}>{t}</option>)}
        </select>
        <button type="button" className="outline" onClick={() => { exportStories(shown); notify('Stories exported as plan-stories.json') }}>⬇ Export</button>
        <span className="view-toggle">
          <button type="button" className={view === 'table' ? 'on' : ''} onClick={() => setView('table')}>Table View</button>
          <button type="button" className={view === 'board' ? 'on' : ''} onClick={() => setView('board')}>Board View</button>
        </span>
      </div>
    </div>
  )

  if (view === 'board') {
    const sprints = [...new Set(stories.map((s) => s.sprint))].sort()
    return (
      <div className="card">
        {head}
        <div className="board">
          {sprints.map((sp) => (
            <div className="board-col" key={sp}>
              <h4>{`Sprint ${sp}`}</h4>
              {shown.filter((s) => s.sprint === sp).map((s) => (
                <div className="board-card" key={s.story_id} onClick={() => setDetailStory(s)}>
                  <div className="mono">{s.story_id}</div>
                  <div className="t">{s.title}</div>
                  <TeamChip name={s.accountable_team} />
                  <div style={{ marginTop: 6, display: 'flex', gap: 6, alignItems: 'center' }}>
                    <Badge status={s.status} /> <span className="hint">{`${s.estimate} pts`}</span>
                  </div>
                </div>
              ))}
            </div>
          ))}
        </div>
        {detailStory ? <StoryDetailModal story={detailStory} onClose={() => setDetailStory(null)} /> : null}
      </div>
    )
  }

  return (
    <div className="card">
      {head}
      <p className="hint" style={{ margin: '-4px 0 10px' }}>
        Click a row for the full story detail — purpose, targets, dependencies and acceptance criteria.
      </p>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Story ID', 'Title', 'Accountable Team', 'Sprint', 'Estimate', 'Status', 'Actions'].map((h) => <th key={h}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => {
              const editing = editable && editingId === s.story_id
              return (
                <Fragment key={s.story_id}>
                  <tr className="row-click" onClick={() => setDetailStory(s)}>
                    <td className="mono">{s.story_id}</td>
                    <td>{s.title}</td>
                    <td><TeamChip name={s.accountable_team} /></td>
                    <td>{`S${s.sprint}`}</td>
                    <td>{`${s.estimate} pts`}</td>
                    <td><Badge status={s.status} /></td>
                    <td>
                      <button
                        type="button"
                        className="kebab"
                        title={editable ? 'Edit team / sprint / estimate' : 'Plan locked at sign-off — changes require an amendment'}
                        onClick={(e) => {
                          e.stopPropagation()
                          if (!editable) { notify('Plan locked at sign-off — changes require an amendment', true); return }
                          setEditingId(editingId === s.story_id ? null : s.story_id)
                        }}
                      >
                        ⋯
                      </button>
                    </td>
                  </tr>
                  {editing ? (
                    <tr className="edit-row">
                      <td colSpan={7}>
                        <div className="actions-row" style={{ margin: 0 }}>
                          <b>{`Edit ${s.story_id}:`}</b>
                          <label>
                            Team{' '}
                            <select
                              defaultValue={s.accountable_team}
                              onChange={(e) => patchAct(`/stories/${s.story_id}`, { accountable_team: e.target.value }, `${s.story_id} reassigned`)}
                            >
                              {TEAMS.map((t) => <option value={t} key={t}>{t}</option>)}
                            </select>
                          </label>
                          <label>
                            Estimate{' '}
                            <select
                              defaultValue={s.estimate}
                              onChange={(e) => patchAct(`/stories/${s.story_id}`, { estimate: Number(e.target.value) }, `${s.story_id} re-estimated`)}
                            >
                              {ESTIMATES.map((n) => <option value={n} key={n}>{`${n} pts`}</option>)}
                            </select>
                          </label>
                          <label>
                            Sprint{' '}
                            <select
                              defaultValue={s.sprint}
                              onChange={(e) => patchAct(`/stories/${s.story_id}`, { sprint: Number(e.target.value) }, `${s.story_id} moved`)}
                            >
                              {SPRINTS.map((n) => <option value={n} key={n}>{`S${n}`}</option>)}
                            </select>
                          </label>
                          <button type="button" className="ghost" onClick={() => setEditingId(null)}>Close</button>
                        </div>
                      </td>
                    </tr>
                  ) : null}
                </Fragment>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="table-foot">
        <span className="hint">{shown.length ? `Showing 1 to ${shown.length} of ${shown.length} stories` : 'No stories match the filter'}</span>
        <span className="pager">
          <button type="button" className="icon-btn" disabled>‹</button>
          <span className="page-chip">1</span>
          <button type="button" className="icon-btn" disabled>›</button>
        </span>
      </div>
      {detailStory ? <StoryDetailModal story={detailStory} onClose={() => setDetailStory(null)} /> : null}
    </div>
  )
}
