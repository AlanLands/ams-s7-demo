import { useRun } from '../../state/RunContext'
import { CheckItem } from './CheckItem'
import type { PlanStory } from './depGraph'
import { planningOf } from './planningHelpers'

// Ported from `function planningAssistantCards(stories)` in
// apps/control/static/app.js (~line 1253-1283).
export function PlanningAssistantCards({ stories }: { stories: PlanStory[] }) {
  const { data } = useRun()
  const conf = planningOf(data).confidence
  // `types.ts`'s `PlanningState.rationale` (`PlanRationale`) already covers
  // this field. Cast locally instead of importing it, consistent with how
  // every planning page casts through `data.planning` rather than the shared
  // type — centralizing on it is a deliberate, still-open cleanup deferred to
  // a follow-up, not a blocker.
  const rationale = (data?.planning as { rationale?: { text: string } } | undefined)?.rationale

  const allSimulated = stories.every((s) => s.provenance === 'simulated')
  const acs = stories.flatMap((s) => s.acceptance_criteria ?? []).length
  const deps = stories.flatMap((s) => s.dependencies).length
  const teams = new Set(stories.map((s) => s.accountable_team)).size
  const rollbacks = stories.filter((s) => s.rollback_plan).length
  const analysis = data?.intake?.analysis
  const risks = analysis?.risk_register?.length ?? analysis?.risks?.length ?? 0

  return (
    <div className="grid cols-2" style={{ marginTop: 14 }}>
      <div className="card">
        <div className="section-title">
          <h3>✦ AI Planning Assistant</h3>
          <span className="hint">{allSimulated ? 'AI decomposition' : 'AI + human stories'}</span>
        </div>
        <ul className="checklist">
          <CheckItem ok label="Epic analysed" />
          <CheckItem ok={stories.length > 0} label="Stories generated" extra={stories.length} />
          <CheckItem ok={acs > 0} label="Acceptance criteria generated" extra={acs} />
          <CheckItem ok label="Dependencies identified" extra={deps} />
          <CheckItem ok={teams > 0} label="Teams mapped" extra={teams} />
          <CheckItem ok label="Planned sprints" extra={new Set(stories.map((s) => s.sprint)).size} />
          <CheckItem ok={risks > 0} label="Risks identified" extra={risks} />
          <CheckItem ok={rollbacks === stories.length} label="Rollback plans defined" extra={`${rollbacks}/${stories.length}`} />
        </ul>
      </div>
      <div className="card">
        <h3>AI Planning Rationale</h3>
        <p className="hint" style={{ marginTop: 8 }}>
          {rationale?.text ?? 'The rationale is produced with the AI decomposition — generate the draft plan to see it.'}
        </p>
        {conf ? (
          <div className="conf-row">
            <b>AI Confidence</b>
            <span className="info conf-v" title={conf.basis}>{`${conf.value}% ⓘ`}</span>
          </div>
        ) : null}
      </div>
    </div>
  )
}
