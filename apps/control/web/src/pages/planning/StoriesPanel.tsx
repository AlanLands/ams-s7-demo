import { useRef, useState } from 'react'
import { Badge } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import { AddStoryModal } from './AddStoryModal'
import { type PlanStory } from './depGraph'
import { EditStoryDrawer } from './EditStoryDrawer'
import { planningOf } from './planningHelpers'
import { TeamChip } from './TeamChip'

// Rewritten 2026-08-09 (Epic to Stories redesign): one toolbar owns every
// story-list action — search, team filter, import/export, view toggle, add —
// absorbing the buttons the deleted EpicDetailsCard used to carry. Clicking a
// row or card opens EditStoryDrawer, which replaces both the read-only
// StoryDetailModal (still used by Routing by Team) and the old per-row
// dropdown edit strip: viewing and editing are now the same lightweight
// gesture. When the plan is locked the drawer opens read-only.

// Only sprint 1 stories come out of planning as "ready" (s7_delivery/factory
// engine.py: `Status.READY if sprint <= 1 else Status.PLANNED`); every later
// sprint is "planned" until its turn comes up. Spelled out here since the
// badge text alone reads as ambiguous.
const STORY_STATUS_HINT: Record<string, string> = {
  ready: 'In Sprint 1 — ready to pull now.',
  planned: 'Scheduled into a future sprint — not ready to pull yet.',
}

function exportStories(stories: PlanStory[]) {
  const blob = new Blob([JSON.stringify(stories, null, 2)], { type: 'application/json' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = 'plan-stories.json'
  a.click()
  URL.revokeObjectURL(a.href)
}

export function StoriesPanel({ stories, editable = false }: { stories: PlanStory[]; editable?: boolean }) {
  const { act, notify, data } = useRun()
  const originals = planningOf(data).original_stories ?? []
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('')
  const [view, setView] = useState<'table' | 'board'>('table')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showAdd, setShowAdd] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  const q = query.trim().toLowerCase()
  const shown = stories.filter((s) =>
    (!filter || s.accountable_team === filter)
    && (!q || s.story_id.toLowerCase().includes(q) || s.title.toLowerCase().includes(q)),
  )
  const teams = [...new Set(stories.map((s) => s.accountable_team))]
  const totalPts = shown.reduce((sum, s) => sum + (s.estimate || 0), 0)
  const editing = editingId ? stories.find((s) => s.story_id === editingId) ?? null : null

  function handleImportFile(file: File) {
    const reader = new FileReader()
    reader.onload = () => {
      let items: unknown
      try {
        const parsed = JSON.parse(String(reader.result))
        items = Array.isArray(parsed) ? parsed : (parsed as { stories?: unknown }).stories
      } catch {
        notify('Not a JSON file — export from this page for the expected shape', true)
        return
      }
      if (!Array.isArray(items) || items.length === 0) {
        notify('The file has no stories — expected an array or {"stories": [...]}', true)
        return
      }
      act('/stories/import', { stories: items }, `${items.length} stories imported`)
    }
    reader.readAsText(file)
  }

  const toolbar = (
    <div className="stories-toolbar">
      <div className="search-box">
        <input
          type="search"
          placeholder="Search stories…"
          aria-label="Search stories"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>
      <select value={filter} aria-label="Filter by team" onChange={(e) => setFilter(e.target.value)}>
        <option value="">All teams</option>
        {teams.map((t) => <option value={t} key={t}>{t}</option>)}
      </select>
      <span className="toolbar-spring" />
      <button type="button" className="outline" onClick={() => importRef.current?.click()} disabled={!editable}
        title={editable ? 'Upload a JSON file of stories (the Export format works). Imported stories carry HUMAN provenance.' : 'Plan locked at sign-off'}>
        ⬆ Import
      </button>
      <input
        ref={importRef} type="file" accept=".json,application/json" style={{ display: 'none' }}
        onChange={(e) => { const f = e.target.files?.[0]; if (f) handleImportFile(f); e.target.value = '' }}
      />
      <button type="button" className="outline" onClick={() => { exportStories(shown); notify('Stories exported as plan-stories.json') }}>
        ⬇ Export
      </button>
      <span className="view-toggle">
        <button type="button" className={view === 'table' ? 'on' : ''} onClick={() => setView('table')}>Table</button>
        <button type="button" className={view === 'board' ? 'on' : ''} onClick={() => setView('board')}>Board</button>
      </span>
      <button type="button" className="primary sq" disabled={!editable} onClick={() => setShowAdd(true)}
        title={editable ? 'Add a story by hand. Manual stories carry HUMAN provenance.' : 'Plan locked at sign-off'}>
        + Add Story
      </button>
    </div>
  )

  const overlays = (
    <>
      {editing ? (
        <EditStoryDrawer
          key={editing.story_id}
          story={editing}
          original={originals.find((o) => o.story_id === editing.story_id)}
          stories={stories}
          locked={!editable}
          onClose={() => setEditingId(null)}
        />
      ) : null}
      {showAdd ? <AddStoryModal stories={stories} onClose={() => setShowAdd(false)} /> : null}
    </>
  )

  if (view === 'board') {
    const sprints = [...new Set(stories.map((s) => s.sprint))].sort()
    return (
      <div className="card">
        {toolbar}
        <div className="board">
          {sprints.map((sp) => {
            const col = shown.filter((s) => s.sprint === sp)
            const pts = col.reduce((sum, s) => sum + (s.estimate || 0), 0)
            return (
              <div className="board-col" key={sp}>
                <h4>{`Sprint ${sp}`}<span className="col-meta">{`${col.length} ${col.length === 1 ? 'story' : 'stories'} · ${pts} pts`}</span></h4>
                {col.map((s) => (
                  <div
                    className="board-card row-click" key={s.story_id}
                    onClick={() => setEditingId(s.story_id)}
                    title={editable ? 'Click to edit' : 'Click to view'}
                  >
                    <div className="bc-head">
                      <span className="mono">{s.story_id}</span>
                      <TeamChip name={s.accountable_team} />
                    </div>
                    <div className="t">{s.title}</div>
                    <div className="bc-foot">
                      <span className="hint">{`S${s.sprint} · ${s.estimate} pts`}</span>
                      <span className="chip req-id">{`${(s.acceptance_criteria ?? []).length} AC`}</span>
                      <Badge status={s.status} title={STORY_STATUS_HINT[s.status]} />
                    </div>
                  </div>
                ))}
              </div>
            )
          })}
        </div>
        {overlays}
      </div>
    )
  }

  return (
    <div className="card">
      {toolbar}
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              {['Story ID', 'Title', 'Accountable Team', 'Sprint', 'Estimate', 'Status', ''].map((h, i) => <th key={h || i}>{h}</th>)}
            </tr>
          </thead>
          <tbody>
            {shown.map((s) => (
              <tr className="row-click" key={s.story_id} onClick={() => setEditingId(s.story_id)}>
                <td className="mono">{s.story_id}</td>
                <td>{s.title}</td>
                <td><TeamChip name={s.accountable_team} /></td>
                <td>{`S${s.sprint}`}</td>
                <td>{`${s.estimate} pts`}</td>
                <td><Badge status={s.status} title={STORY_STATUS_HINT[s.status]} /></td>
                <td>
                  <button
                    type="button"
                    className="kebab"
                    title={editable ? `Edit ${s.story_id}` : `View ${s.story_id} (plan locked)`}
                    aria-label={editable ? `Edit ${s.story_id}` : `View ${s.story_id}`}
                    onClick={(e) => { e.stopPropagation(); setEditingId(s.story_id) }}
                  >
                    ✎
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-foot">
        <span className="hint">{shown.length ? `Showing 1 to ${shown.length} of ${shown.length} stories` : 'No stories match'}</span>
        <span className="chip tag">{`Total Estimate: ${totalPts} pts`}</span>
      </div>
      {overlays}
    </div>
  )
}
