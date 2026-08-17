import { useState } from 'react'
import { Badge } from '../../components/Badge'
import { useRun } from '../../state/RunContext'
import type { GateCondition } from '../../types'
import { planningOf, storyGaps } from './planningHelpers'

export function Gate1Rail() {
  const { data, act } = useRun()
  const [approverRole, setApproverRole] = useState('business_owner')
  const [approverName, setApproverName] = useState('')
  const [note, setNote] = useState('')
  const [feedback, setFeedback] = useState('')

  if (!data) return null

  const gate = (data.gates ?? []).find((g) => g.gate_id === 'G1')
  const planning = planningOf(data)
  const plan = planning.plan
  const locked = data.run.plan_locked

  // The engine evaluates Gate 1 conditions at sign-off. Before that, show a
  // preview computed from the same plan data (same precedent as storyGaps) —
  // labelled as a preview, never presented as the gate's own verdict.
  let conditions: GateCondition[] = gate?.conditions ?? []
  let preview = false
  if (conditions.length === 0) {
    preview = true
    const stories = planning.stories ?? []
    const ids = new Set(stories.map((s) => s.story_id))
    conditions = [
      { condition: 'Epic defined', met: Boolean(data.intake?.epic), detail: '' },
      { condition: 'Stories decomposed', met: stories.length > 0, detail: '' },
      { condition: 'Acceptance criteria defined', met: stories.length > 0 && stories.every((s) => (s.acceptance_criteria?.length ?? 0) > 0), detail: '' },
      { condition: 'Teams assigned', met: stories.length > 0 && stories.every((s) => Boolean(s.accountable_team)), detail: '' },
      { condition: 'Dependencies mapped', met: stories.length > 0 && stories.every((s) => s.dependencies.every((x) => ids.has(x))), detail: '' },
      { condition: 'Estimates provided', met: stories.length > 0 && stories.every((s) => s.estimate > 0), detail: '' },
      { condition: 'Story quality validated', met: stories.length > 0 && stories.every((s) => storyGaps(s).length === 0), detail: '' },
      { condition: 'Named approver', met: false, detail: 'Recorded at sign-off' },
    ]
  }

  const checkCard = (
    <div className="card rail-card" key="check">
      <h3><span className="lock">{locked ? '🔒' : '🔓'}</span>Gate 1: Plan Sign-off</h3>
      <p className="hint">Human approval required to lock the plan and proceed to execution.</p>
      <div className="section-title" style={{ margin: '12px 0 0' }}>
        <h3>Gate Checklist</h3>
        <Badge status={gate?.status ?? 'not_started'} />
      </div>
      <p className="hint">All items must be complete</p>
      <ul className="checklist">
        {conditions.map((c) => (
          <li key={c.condition} title={c.detail || ''}>
            <span className={`tick ${c.met ? 'ok' : 'no'}`}>{c.met ? '✓' : '·'}</span>
            {c.condition}
            <span className={`state ${c.met ? 'ok' : 'no'}`}>{c.met ? 'Complete' : 'Pending'}</span>
          </li>
        ))}
        {preview ? <li><span className="hint">Preview — the gate formally evaluates these at sign-off.</span></li> : null}
      </ul>
    </div>
  )

  if (plan) {
    return [
      checkCard,
      <div className="card ok rail-card" key="signed">
        <h3>Plan Sign-off</h3>
        <div className="kv" style={{ gridTemplateColumns: '110px 1fr', marginTop: 10 }}>
          <b>Signed by</b><span>{plan.signed_by}</span>
          <b>At</b><span className="mono">{plan.signed_at}</span>
          <b>Version</b><span>{`v${plan.plan_version}`}</span>
          <b>Note</b><span>{plan.note || '—'}</span>
        </div>
        <div className="sig-box">{plan.signed_by}</div>
      </div>,
    ]
  }

  const trimmedName = approverName.trim()

  return [
    checkCard,
    <div className="card rail-card" key="sign">
      <h3>Plan Sign-off</h3>
      <label className="fld">Approver *</label>
      <select value={approverRole} onChange={(e) => setApproverRole(e.target.value)}>
        <option value="business_owner">Business Owner</option>
      </select>
      <label className="fld">Approver name *</label>
      <input
        type="text"
        placeholder="Approver name (required)" aria-label="Approver name (required)"
        value={approverName}
        onChange={(e) => setApproverName(e.target.value)}
      />
      <label className="fld">Approval Note *</label>
      <textarea
        rows={3}
        maxLength={500}
        placeholder="Approval note (required)" aria-label="Approval note (required)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      <div className="char-count">{`${note.length} / 500`}</div>
      <label className="fld">E-Signature</label>
      <div className={`sig-box${trimmedName ? '' : ' empty'}`}>
        {trimmedName || 'E-signature renders here as you type the approver name'}
      </div>
      <div className="sig-actions">
        <button type="button" onClick={() => setApproverName('')}>Clear</button>
      </div>
      <div className="actions-row">
        <button
          type="button"
          className="primary sq block"
          title="Signs Gate 1 under the Business Owner role and locks the plan"
          onClick={() => act('/planning/sign-off', { role: approverRole, approver: approverName, note }, 'Plan signed and locked')}
        >
          🔒 Approve Plan &amp; Lock
        </button>
      </div>
      <details style={{ marginTop: 12 }}>
        <summary className="hint">Request AI Revision</summary>
        <textarea
          rows={2}
          placeholder="What should the AI change? e.g. 'US-004 is underestimated'" aria-label="What should the AI change? e.g. 'US-004 is underestimated'"
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
        />
        <div className="actions-row">
          <button
            type="button"
            className="outline block"
            onClick={() => act('/planning/revise', { feedback }, 'Revision requested')}
          >
            ⟳ Request AI Revision
          </button>
        </div>
      </details>
    </div>,
  ]
}
