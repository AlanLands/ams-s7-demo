import { useRef, useState } from 'react'
import { Prov } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import { AddStoryModal } from './AddStoryModal'
import type { PlanStory } from './depGraph'

// Ported from `function epicDetailsCard()` in apps/control/static/app.js
// (~line 842-895), plus the file-picking half of `function
// importStoriesDialog()` (~line 994-1018), wired to this card's "Import
// Stories" button exactly as the vanilla version wires it. The "+ Add Story"
// button owns local modal-open state instead of vanilla's document.body
// append, per this project's Modal convention.
export function EpicDetailsCard({ stories }: { stories: PlanStory[] }) {
  const { data, act, notify } = useRun()
  const [showAdd, setShowAdd] = useState(false)
  const importRef = useRef<HTMLInputElement>(null)

  if (!data) return null
  const epic = data.intake?.epic
  const req = data.intake?.requirement
  const locked = Boolean(data.run.plan_locked)

  if (!epic) {
    return (
      <div className="card">
        <p>No epic yet — complete the Intake stage first (analyse, create epic, pass gate G0).</p>
      </div>
    )
  }

  const priority = (req?.priority ?? '').toLowerCase()

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

  return (
    <div className="card">
      <div className="card-head">
        <h3>Epic Details</h3>
        <div className="btns">
          <button
            type="button"
            className="outline"
            disabled={locked}
            title={
              locked
                ? 'Plan locked at sign-off — changes require an amendment'
                : 'Generates the draft decomposition through the engine (simulation mode is deterministic)'
            }
            onClick={() => act('/planning/generate', {}, 'Draft stories generated')}
          >
            ✦ AI Suggest Stories
          </button>
          <button
            type="button"
            className="outline"
            disabled={locked}
            title={
              locked
                ? 'Plan locked at sign-off — changes require an amendment'
                : 'Upload a JSON file of stories (the Export format works). Imported stories carry HUMAN provenance.'
            }
            onClick={() => importRef.current?.click()}
          >
            ⬆ Import Stories
          </button>
          <input
            ref={importRef}
            type="file"
            accept=".json,application/json"
            style={{ display: 'none' }}
            onChange={(e) => {
              const file = e.target.files?.[0]
              if (file) handleImportFile(file)
              e.target.value = ''
            }}
          />
          <button
            type="button"
            className="primary sq"
            disabled={locked}
            title={locked ? 'Plan locked at sign-off — changes require an amendment' : 'Add a story by hand. Manual stories carry HUMAN provenance.'}
            onClick={() => setShowAdd(true)}
          >
            + Add Story
          </button>
        </div>
      </div>
      <div className="epic-grid">
        <div className="kv">
          <b>Epic ID</b><span className="mono">{epic.epic_id}</span>
          <b>Epic Title</b><span>{epic.title}</span>
          <b>Business Outcome</b><span>{epic.business_outcome}</span>
        </div>
        <div className="kv">
          <b>Domain</b><span>{req?.domain ?? '—'}</span>
          <b>Business Owner</b><span>{req?.business_owner ?? '—'}</span>
          <b>Priority</b><span><span className={`chip priority-${priority || 'low'}`}>{req?.priority ?? '—'}</span></span>
        </div>
        <div className="kv">
          <b>Estimated Stories</b><span>{String(epic.estimated_stories)}</span>
          <b>Created On</b><span>{(epic.created_at ?? '').slice(0, 10)}</span>
          <b>Created By</b><span>{epic.created_by} <Prov provenance={epic.provenance} /></span>
        </div>
      </div>
      {showAdd ? <AddStoryModal stories={stories} onClose={() => setShowAdd(false)} /> : null}
    </div>
  )
}
