import { useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import type { RequirementExtraction } from '../../types'

interface Props {
  open: boolean
  onClose: () => void
  extraction: RequirementExtraction
}

export function EditExtractionDrawer({ open, onClose, extraction }: Props) {
  const { patchAct } = useRun()
  const [title, setTitle] = useState(extraction.epic_title)
  const [objective, setObjective] = useState(extraction.business_objective)
  const [summary, setSummary] = useState(extraction.requirement_summary)
  const [reqText, setReqText] = useState(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  const [saving, setSaving] = useState(false)

  // Reset local edit state whenever the drawer is (re)opened against fresh data —
  // avoids carrying stale edits from a previous open/close cycle.
  useEffect(() => {
    if (!open) return
    setTitle(extraction.epic_title)
    setObjective(extraction.business_objective)
    setSummary(extraction.requirement_summary)
    setReqText(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  }, [open, extraction])

  if (!open) return null

  function resetToAiExtraction() {
    setTitle(extraction.epic_title)
    setObjective(extraction.business_objective)
    setSummary(extraction.requirement_summary)
    setReqText(extraction.extracted_requirements.map((r) => r.text).join('\n'))
  }

  async function save() {
    const lines = reqText.split('\n').map((t) => t.trim()).filter(Boolean)
    setSaving(true)
    const ok = await patchAct('/intake/extraction', {
      epic_title: title.trim(),
      business_objective: objective.trim(),
      requirement_summary: summary.trim(),
      extracted_requirements: lines.map((text, i) => ({ rule_id: `REQ-${String(i + 1).padStart(2, '0')}`, text })),
    }, 'Extraction updated')
    setSaving(false)
    if (ok) onClose()
  }

  return (
    <div className="drawer-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <aside className="drawer" role="dialog" aria-label="Edit Extracted Epic">
        <div className="card-head">
          <h3>Edit Extracted Epic</h3>
          <button type="button" className="kebab" onClick={onClose} aria-label="Close">✕</button>
        </div>
        <p className="hint"><span className="chip tag">AI-generated — Editable</span></p>

        <label className="fld" htmlFor="edit-title">Title</label>
        <input id="edit-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} />

        <label className="fld" htmlFor="edit-objective">Business Objective</label>
        <textarea id="edit-objective" rows={3} value={objective} onChange={(e) => setObjective(e.target.value)} />

        <label className="fld" htmlFor="edit-summary">Requirement Summary</label>
        <textarea id="edit-summary" rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />

        <label className="fld" htmlFor="edit-reqs">Extracted Requirements (one per line)</label>
        <textarea id="edit-reqs" rows={8} value={reqText} onChange={(e) => setReqText(e.target.value)} />

        <div className="actions-row" style={{ marginTop: 14 }}>
          <button type="button" className="ghost" onClick={resetToAiExtraction}>Reset to AI Extraction</button>
          <button type="button" className="ghost" onClick={onClose}>Cancel</button>
          <button type="button" className="primary sq" disabled={saving || !title.trim() || !objective.trim() || !summary.trim()} onClick={save}>
            Save Changes
          </button>
        </div>
      </aside>
    </div>
  )
}
