import { useCallback, useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import { TEAMS, type PlanAcceptanceCriterion, type PlanStory } from './depGraph'
import { TeamChip } from './TeamChip'

// The editing surface for AI-generated stories (2026-08-09 redesign, layout
// matched to the approved Edit Story mock): two-column field grid, a
// four-across workflow row, side-by-side Acceptance Criteria / Dependencies
// panels, and a footer with Reset to AI Suggestion · Cancel · Save Changes.
// Holds a local draft and issues ONE PATCH with only the changed fields on
// save — one version bump per edit session, not one per keystroke.
//
// "Reset to AI Suggestion" restores the draft from the immutable
// stories.original.json snapshot the engine writes at generate time — a real
// reset to the genuinely-generated draft, not a decorative button. It only
// renders when that snapshot holds this story.
//
// Deliberately read-only here: story identity, provenance, the routing
// targets (application / component / repository) the artifact export grounds
// against, and the feature-flag / rollback release machinery — the engine
// rejects all of them in a PATCH regardless.
//
// Mount with key={story.story_id} so the draft state re-initializes per story.

const SPRINTS = [1, 2, 3]
const ESTIMATES = [2, 3, 5, 8, 13]
const RISKS: [string, string][] = [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']]
const TASK_TYPES: [string, string][] = [
  ['feature', 'Feature'],
  ['test', 'Test / regression'],
  ['operational', 'Operational readiness'],
]
const STATUSES: [string, string][] = [
  ['planned', 'Planned'],
  ['ready', 'Ready'],
  ['in_progress', 'In progress'],
  ['blocked', 'Blocked'],
  ['completed', 'Completed'],
]
const PURPOSE_MAX = 500

function nextAcId(storyId: string, acs: PlanAcceptanceCriterion[]): string {
  const max = acs.reduce((m, ac) => {
    const n = Number(ac.ac_id.match(/(\d+)$/)?.[1] ?? 0)
    return Math.max(m, n)
  }, 0)
  return `${storyId}-AC${max + 1}`
}

interface Props {
  story: PlanStory
  original?: PlanStory
  stories: PlanStory[]
  locked: boolean
  onClose: () => void
}

export function EditStoryDrawer({ story: s, original, stories, locked, onClose }: Props) {
  const { patchAct, notify } = useRun()
  const [title, setTitle] = useState(s.title)
  const [purpose, setPurpose] = useState(s.purpose)
  const [team, setTeam] = useState(s.accountable_team)
  const [contributing, setContributing] = useState<string[]>([...(s.contributing_teams ?? [])])
  const [sprint, setSprint] = useState(s.sprint)
  const [estimate, setEstimate] = useState(s.estimate)
  const [taskType, setTaskType] = useState(s.task_type)
  const [risk, setRisk] = useState(s.risk)
  const [status, setStatus] = useState(s.status)
  const [acs, setAcs] = useState<PlanAcceptanceCriterion[]>((s.acceptance_criteria ?? []).map((ac) => ({ ...ac })))
  const [deps, setDeps] = useState<string[]>([...(s.dependencies ?? [])])
  const [saving, setSaving] = useState(false)
  const [closing, setClosing] = useState(false)

  // Slide-out before unmount: `closing` plays the exit animation, then the
  // timeout (matched to the CSS duration) actually closes.
  const requestClose = useCallback(() => setClosing(true), [])
  useEffect(() => {
    if (!closing) return
    const t = setTimeout(onClose, 230)
    return () => clearTimeout(t)
  }, [closing, onClose])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') requestClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [requestClose])

  const provChip = s.provenance === 'human'
    ? 'Human authored'
    : (s.version ?? 1) > 1
      ? 'AI Generated • Human Edited'
      : 'AI Generated — Now Editable'

  const cleanAcs = acs.filter((ac) => ac.text.trim())
  const valid = Boolean(title.trim()) && Boolean(purpose.trim()) && cleanAcs.length > 0
  const depOptions = stories.filter((o) => o.story_id !== s.story_id && !deps.includes(o.story_id))
  const contribOptions = TEAMS.filter((t) => t !== team && !contributing.includes(t))
  const titleOf = (id: string) => stories.find((o) => o.story_id === id)?.title ?? ''

  function resetToOriginal() {
    if (!original) return
    setTitle(original.title)
    setPurpose(original.purpose)
    setTeam(original.accountable_team)
    setContributing([...(original.contributing_teams ?? [])])
    setSprint(original.sprint)
    setEstimate(original.estimate)
    setTaskType(original.task_type)
    setRisk(original.risk)
    setStatus(original.status)
    setAcs((original.acceptance_criteria ?? []).map((ac) => ({ ...ac })))
    setDeps([...(original.dependencies ?? [])])
    notify('Draft restored to the AI suggestion — Save Changes to apply')
  }

  async function save() {
    const patch: Record<string, unknown> = {}
    if (title.trim() !== s.title) patch.title = title.trim()
    if (purpose.trim() !== s.purpose) patch.purpose = purpose.trim()
    if (team !== s.accountable_team) patch.accountable_team = team
    if (contributing.join('|') !== (s.contributing_teams ?? []).join('|')) patch.contributing_teams = contributing
    if (sprint !== s.sprint) patch.sprint = sprint
    if (estimate !== s.estimate) patch.estimate = estimate
    if (taskType !== s.task_type) patch.task_type = taskType
    if (risk !== s.risk) patch.risk = risk
    if (status !== s.status) patch.status = status
    if (JSON.stringify(cleanAcs) !== JSON.stringify(s.acceptance_criteria ?? [])) patch.acceptance_criteria = cleanAcs
    if (deps.join('|') !== (s.dependencies ?? []).join('|')) patch.dependencies = deps
    if (Object.keys(patch).length === 0) { requestClose(); return }
    setSaving(true)
    const ok = await patchAct(`/stories/${s.story_id}`, patch, `${s.story_id} updated`)
    setSaving(false)
    if (ok) requestClose()
  }

  return (
    <div
      className={`drawer-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) requestClose() }}
    >
      <aside className="drawer story-drawer" role="dialog" aria-label={`Edit ${s.story_id}`}>
        <div className="card-head">
          <h3>{locked ? 'Story Detail' : 'Edit Story'}{' — '}<span className="mono">{s.story_id}</span></h3>
          <button type="button" className="kebab" onClick={requestClose} aria-label="Close">✕</button>
        </div>

        <div className="drawer-badges">
          <span className={`chip ${s.provenance === 'human' ? 'tag' : 'priority-high'}`}>{provChip}</span>
          <span
            className="hint info"
            title="Every save is recorded as a versioned amendment in the provenance ledger"
          >
            {locked ? 'Plan locked at sign-off — read only' : 'Changes are tracked before Gate 1 approval'} ⓘ
          </span>
        </div>

        <div className="grid cols-2">
          <div>
            <label className="fld" htmlFor="st-title">Title *</label>
            <input id="st-title" type="text" value={title} disabled={locked} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div>
            <label className="fld" htmlFor="st-purpose">Purpose *</label>
            <textarea
              id="st-purpose" rows={3} maxLength={PURPOSE_MAX} value={purpose} disabled={locked}
              onChange={(e) => setPurpose(e.target.value)}
            />
            <div className="char-count">{`${purpose.length} / ${PURPOSE_MAX}`}</div>
          </div>
          <div>
            <label className="fld" htmlFor="st-team">Accountable Team *</label>
            <select id="st-team" value={team} disabled={locked} onChange={(e) => setTeam(e.target.value)}>
              {TEAMS.map((t) => <option value={t} key={t}>{t}</option>)}
            </select>
          </div>
          <div>
            <label className="fld">Contributing Teams</label>
            <div className="chip-field">
              {contributing.map((t) => (
                <span className="dep-chip chip tag" key={t}>
                  <TeamChip name={t} />
                  {!locked && (
                    <button type="button" aria-label={`Remove ${t}`} onClick={() => setContributing((prev) => prev.filter((x) => x !== t))}>✕</button>
                  )}
                </span>
              ))}
              {!locked && contribOptions.length > 0 && (
                <select
                  className="chip-add" value="" aria-label="Add contributing team"
                  onChange={(e) => { if (e.target.value) setContributing((prev) => [...prev, e.target.value]) }}
                >
                  <option value="">+ Add…</option>
                  {contribOptions.map((t) => <option value={t} key={t}>{t}</option>)}
                </select>
              )}
              {contributing.length === 0 && locked && <span className="hint">None</span>}
            </div>
          </div>
          <div>
            <label className="fld" htmlFor="st-app">Target Application</label>
            <input id="st-app" type="text" value={s.target_application || '—'} disabled title="Routing target — edited via Routing by Team" />
          </div>
          <div>
            <label className="fld" htmlFor="st-comp">Component</label>
            <input id="st-comp" type="text" value={s.target_component || '—'} disabled title="Routing target — edited via Routing by Team" />
          </div>
          <div>
            <label className="fld" htmlFor="st-repo">Repository</label>
            <input id="st-repo" type="text" className="mono" value={s.target_repository || '—'} disabled title="Routing target — edited via Routing by Team" />
          </div>
          <div>
            <label className="fld" htmlFor="st-sprint">Sprint *</label>
            <select id="st-sprint" value={sprint} disabled={locked} onChange={(e) => setSprint(Number(e.target.value))}>
              {SPRINTS.map((n) => <option value={n} key={n}>{`S${n}`}</option>)}
            </select>
          </div>
        </div>

        <div className="field-row-4">
          <div>
            <label className="fld" htmlFor="st-estimate">Estimate *</label>
            <select id="st-estimate" value={estimate} disabled={locked} onChange={(e) => setEstimate(Number(e.target.value))}>
              {ESTIMATES.map((n) => <option value={n} key={n}>{`${n} pts`}</option>)}
            </select>
          </div>
          <div>
            <label className="fld" htmlFor="st-type">Task Type</label>
            <select id="st-type" value={taskType} disabled={locked} onChange={(e) => setTaskType(e.target.value)}>
              {TASK_TYPES.map(([v, l]) => <option value={v} key={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="fld" htmlFor="st-risk">Risk</label>
            <select id="st-risk" value={risk} disabled={locked} onChange={(e) => setRisk(e.target.value)}>
              {RISKS.map(([v, l]) => <option value={v} key={v}>{l}</option>)}
            </select>
          </div>
          <div>
            <label className="fld" htmlFor="st-status">Status</label>
            <select id="st-status" value={status} disabled={locked} onChange={(e) => setStatus(e.target.value)}>
              {STATUSES.map(([v, l]) => <option value={v} key={v}>{l}</option>)}
            </select>
          </div>
        </div>

        <div className="grid cols-2">
          <div>
            <label className="fld">Feature Flag</label>
            {s.feature_flag ? (
              <div className="flag-ro" title="Release machinery — not editable in planning">
                <span className={`flag-dot${s.feature_flag.default_state === 'on' ? ' on' : ''}`} aria-hidden="true" />
                <span className="mono">{s.feature_flag.name}</span>
                <span className="hint">{`(default: ${s.feature_flag.default_state})`}</span>
              </div>
            ) : <div className="flag-ro"><span className="hint">None</span></div>}
          </div>
          <div>
            <label className="fld">Rollback Plan</label>
            <div className="flag-ro" title="Release machinery — not editable in planning">
              <span>{s.rollback_plan ? `${s.rollback_plan.method}${s.rollback_plan.tested ? ' — tested' : ''}` : 'None'}</span>
            </div>
          </div>
        </div>

        <div className="drawer-panels">
          <div className="sub-panel">
            <div className="section-title" style={{ margin: 0 }}>
              <h3>{`Acceptance Criteria (${cleanAcs.length})`}</h3>
            </div>
            {acs.map((ac, i) => (
              <div className="ac-edit-row" key={ac.ac_id}>
                <span className="chip priority-high">{ac.ac_id}</span>
                <input
                  type="text" value={ac.text} disabled={locked} placeholder="Acceptance criterion" aria-label="Acceptance criterion"
                  onChange={(e) => setAcs((prev) => prev.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))}
                />
                {!locked && (
                  <button type="button" className="kebab" aria-label={`Remove ${ac.ac_id}`} onClick={() => setAcs((prev) => prev.filter((_, j) => j !== i))}>
                    ✕
                  </button>
                )}
              </div>
            ))}
            {acs.length === 0 && <p className="hint">At least one acceptance criterion is required.</p>}
            {!locked && (
              <button type="button" className="outline" style={{ alignSelf: 'flex-start' }}
                onClick={() => setAcs((prev) => [...prev, { ac_id: nextAcId(s.story_id, prev), text: '' }])}>
                + Add AC
              </button>
            )}
          </div>

          <div className="sub-panel">
            <div className="section-title" style={{ margin: 0 }}>
              <h3>{`Dependencies (${deps.length})`}</h3>
            </div>
            <div className="dep-chips">
              {deps.map((d) => (
                <span className="chip tag dep-chip" key={d} title={titleOf(d)}>
                  <b className="mono">{d}</b>
                  <span className="dep-title">{titleOf(d)}</span>
                  {!locked && (
                    <button type="button" aria-label={`Remove dependency ${d}`} onClick={() => setDeps((prev) => prev.filter((x) => x !== d))}>✕</button>
                  )}
                </span>
              ))}
              {deps.length === 0 && <span className="hint">None</span>}
            </div>
            {!locked && depOptions.length > 0 && (
              <select
                value="" aria-label="Add dependency"
                onChange={(e) => { if (e.target.value) setDeps((prev) => [...prev, e.target.value]) }}
              >
                <option value="">+ Add dependency…</option>
                {depOptions.map((o) => <option value={o.story_id} key={o.story_id}>{`${o.story_id} — ${o.title}`}</option>)}
              </select>
            )}
          </div>
        </div>

        <div className="actions-row drawer-foot">
          {!locked && original && (
            <button type="button" className="outline" title="Restores this draft to the story exactly as the AI generated it — nothing is saved until Save Changes" onClick={resetToOriginal}>
              ⟲ Reset to AI Suggestion
            </button>
          )}
          <span className="toolbar-spring" />
          <button type="button" className="ghost" onClick={requestClose}>{locked ? 'Close' : 'Cancel'}</button>
          {!locked && (
            <button type="button" className="primary sq" disabled={saving || !valid} onClick={save}>
              Save Changes
            </button>
          )}
        </div>
      </aside>
    </div>
  )
}
