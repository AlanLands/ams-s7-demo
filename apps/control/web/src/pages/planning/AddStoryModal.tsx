import { useRef, useState } from 'react'
import { Modal } from '../../components/Modal'
import { useRun } from '../../state/RunContext'
import { TEAMS, type PlanStory } from './depGraph'

// Ported from `function openAddStoryModal()` in apps/control/static/app.js
// (~line 933-992). The vanilla version reads every field from live DOM node
// references at submit time — including the "Depends on" multi-select, which
// stays uncontrolled here via a ref for the same reason (a plain
// `[...select.selectedOptions]` read is the simplest faithful port of that
// one field; every other field becomes controlled `useState`, matching this
// project's established form pattern — see AddStoryModal's sibling forms).
const SPRINTS = [1, 2, 3]
const ESTIMATES = [2, 3, 5, 8, 13]
const TASK_TYPES: [string, string][] = [
  ['feature', 'Feature'],
  ['test', 'Test / regression'],
  ['operational', 'Operational readiness'],
]

export function AddStoryModal({ stories, onClose }: { stories: PlanStory[]; onClose: () => void }) {
  const { act } = useRun()
  const [title, setTitle] = useState('')
  const [purpose, setPurpose] = useState('')
  const [team, setTeam] = useState(TEAMS[0])
  const [contributing, setContributing] = useState('')
  const [component, setComponent] = useState('')
  const [repository, setRepository] = useState('')
  const [sprint, setSprint] = useState(SPRINTS[0])
  const [estimate, setEstimate] = useState(3)
  const [taskType, setTaskType] = useState(TASK_TYPES[0][0])
  const [acs, setAcs] = useState('')
  const depsRef = useRef<HTMLSelectElement>(null)

  function submit() {
    const dependencies = depsRef.current ? [...depsRef.current.selectedOptions].map((o) => o.value) : []
    const story = {
      title,
      purpose,
      accountable_team: team,
      contributing_teams: contributing.split(',').map((t) => t.trim()).filter(Boolean),
      target_component: component,
      target_repository: repository,
      sprint,
      estimate,
      task_type: taskType,
      dependencies,
      acceptance_criteria: acs.split('\n').map((t) => t.trim()).filter(Boolean),
    }
    act('/stories', { story }, 'Story added to the draft plan').then((ok) => {
      if (ok) onClose()
    })
  }

  return (
    <Modal title="Add Story" onClose={onClose}>
      <p className="hint">
        Manual stories join the draft plan with HUMAN provenance and the same Gate 1 validation as AI-drafted ones.
      </p>
      <div className="grid cols-2">
        <div>
          <label className="fld">Title *</label>
          <input
            type="text"
            autoFocus
            placeholder="e.g. Notify the sponsor when intake opens the file" aria-label="e.g. Notify the sponsor when intake opens the file"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <div>
          <label className="fld">Accountable team *</label>
          <select value={team} onChange={(e) => setTeam(e.target.value)}>
            {TEAMS.map((t) => (
              <option value={t} key={t}>{t}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="fld">Component / application *</label>
          <input
            type="text"
            placeholder="e.g. notification service" aria-label="e.g. notification service"
            value={component}
            onChange={(e) => setComponent(e.target.value)}
          />
        </div>
        <div>
          <label className="fld">Repository *</label>
          <input
            type="text"
            placeholder="e.g. sponsorconnect-api" aria-label="e.g. sponsorconnect-api"
            value={repository}
            onChange={(e) => setRepository(e.target.value)}
          />
        </div>
        <div>
          <label className="fld">Sprint</label>
          <select value={sprint} onChange={(e) => setSprint(Number(e.target.value))}>
            {SPRINTS.map((n) => (
              <option value={n} key={n}>{`Sprint ${n}`}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="fld">Estimate</label>
          <select value={estimate} onChange={(e) => setEstimate(Number(e.target.value))}>
            {ESTIMATES.map((n) => (
              <option value={n} key={n}>{`${n} pts`}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="fld">Story type</label>
          <select value={taskType} onChange={(e) => setTaskType(e.target.value)}>
            {TASK_TYPES.map(([value, label]) => (
              <option value={value} key={value}>{label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="fld">Contributing teams</label>
          <input
            type="text"
            placeholder="Comma-separated, optional" aria-label="Comma-separated, optional"
            value={contributing}
            onChange={(e) => setContributing(e.target.value)}
          />
        </div>
        <div>
          <label className="fld">Depends on</label>
          <select multiple size={4} ref={depsRef}>
            {stories.map((s) => (
              <option value={s.story_id} key={s.story_id}>{`${s.story_id} — ${s.title}`}</option>
            ))}
          </select>
        </div>
      </div>
      <label className="fld">Purpose</label>
      <textarea
        rows={2}
        placeholder="Why this story exists (defaults to the title)" aria-label="Why this story exists (defaults to the title)"
        value={purpose}
        onChange={(e) => setPurpose(e.target.value)}
      />
      <label className="fld">Acceptance criteria *</label>
      <textarea
        rows={4}
        placeholder="One acceptance criterion per line (at least one)" aria-label="One acceptance criterion per line (at least one)"
        value={acs}
        onChange={(e) => setAcs(e.target.value)}
      />
      <div className="actions-row">
        <button type="button" className="primary sq" onClick={submit}>Add to draft plan</button>
        <button type="button" className="ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  )
}
