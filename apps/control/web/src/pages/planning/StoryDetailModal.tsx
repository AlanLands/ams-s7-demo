import { Badge, Prov } from '../../components/Badge'
import { Modal } from '../../components/Modal'
import type { PlanStory } from './depGraph'
import { TeamChip } from './TeamChip'

// Ported verbatim from `function storyDetailModal(s)` in
// apps/control/static/app.js (~line 1020-1054). The vanilla version calls the
// global `openModal()`; here it renders through the shared `Modal` component
// RoutingByTeam.tsx already established for the same "story detail" pattern.
export function StoryDetailModal({ story: s, onClose }: { story: PlanStory; onClose: () => void }) {
  const acceptanceCriteria = s.acceptance_criteria ?? []
  const impacts = s.impacts ?? []
  return (
    <Modal title={`${s.story_id} — ${s.title}`} onClose={onClose}>
      <Prov provenance={s.provenance} />
      <div className="kv" style={{ gridTemplateColumns: '160px 1fr', marginTop: 10 }}>
        <b>Purpose</b><span>{s.purpose || '—'}</span>
        <b>Accountable Team</b><span><TeamChip name={s.accountable_team} /></span>
        <b>Contributing Teams</b><span>{(s.contributing_teams ?? []).join(', ') || '—'}</span>
        <b>Target Application</b><span>{s.target_application || '—'}</span>
        <b>Component</b><span>{s.target_component}</span>
        <b>Repository</b><span><code>{s.target_repository}</code></span>
        <b>Depends On</b><span className="mono">{(s.dependencies ?? []).join(', ') || '—'}</span>
        <b>Sprint</b><span>{`S${s.sprint}`}</span>
        <b>Estimate</b><span>{`${s.estimate} pts`}</span>
        <b>Task Type</b><span>{s.task_type}</span>
        <b>Risk</b><span>{s.risk}</span>
        <b>Status</b><span><Badge status={s.status} /></span>
        <b>Routing Rationale</b>
        <span className="hint">
          {s.provenance === 'human' ? 'Added by a person' : `Owns ${s.target_component} in ${s.target_repository}`}
        </span>
        {s.feature_flag ? (
          <>
            <b>Feature Flag</b>
            <span className="mono">{`${s.feature_flag.name} (default: ${s.feature_flag.default_state})`}</span>
          </>
        ) : null}
        {s.rollback_plan ? (
          <>
            <b>Rollback Plan</b>
            <span>{`${s.rollback_plan.method}${s.rollback_plan.tested ? ' — tested' : ''}`}</span>
          </>
        ) : null}
      </div>
      <h4 style={{ marginTop: 16, fontSize: 12.5, color: 'var(--muted)' }}>Acceptance Criteria</h4>
      {acceptanceCriteria.length ? (
        <ul className="plain">
          {acceptanceCriteria.map((ac) => (
            <li key={ac.ac_id}>
              <span className="chip priority-high" style={{ marginRight: 8 }}>{ac.ac_id}</span>
              {ac.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">None defined.</p>
      )}
      {impacts.length ? (
        <>
          <h4 style={{ marginTop: 16, fontSize: 12.5, color: 'var(--muted)' }}>Impacts</h4>
          <ul className="plain">
            {impacts.map((i, idx) => <li key={idx}>{i}</li>)}
          </ul>
        </>
      ) : null}
    </Modal>
  )
}
