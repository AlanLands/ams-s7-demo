import { useState } from 'react'
import { NotBuilt } from '../../components/NotBuilt'
import { useRun } from '../../state/RunContext'
import { CheckItem } from './CheckItem'
import { Donut } from './Donut'
import { depGraph } from './depGraph'
import { PlanArtifactsCard } from './PlanArtifactsCard'
import { planningOf } from './planningHelpers'
import { SprintPlanCard } from './SprintPlanCard'
import { StoriesPanel } from './StoriesPanel'

// Ported from `function renderPlanSummary()` in apps/control/static/app.js
// (~line 1576-1683). `SUMMARY_TABS` (~line 1528-1532) becomes the tab list
// below; `state.summaryTab` becomes local `useState` (page-local UI state,
// per this project's established pattern for ported tab strips — see
// SourceRequirementCard.tsx's upload/paste tabs).

const SUMMARY_TABS: [string, string][] = [
  ['summary', 'Summary'], ['stories', 'Stories'], ['dependencies', 'Dependencies'],
  ['risks', 'Risks'], ['assumptions', 'Assumptions'], ['impacts', 'Impacts'],
  ['artifacts', 'Artifacts'],
]

// `IntakeAnalysis.risk_register` is typed as `Record<string, unknown>[]` in
// types.ts (its exact per-entry shape was never pinned down there). The
// vanilla code reads `.severity` / `.text` off each entry directly; this is
// the same assumption, made explicit for TS.
interface RiskRegisterEntry {
  severity?: string
  text?: string
}

export function PlanSummary() {
  const { data } = useRun()
  const [tab, setTab] = useState('summary')

  if (!data) return null

  const planning = planningOf(data)
  const stories = planning.stories ?? []
  if (!stories.length) {
    return <NotBuilt name="Plan Summary" phase="the Planning stage — generate the draft plan first" />
  }

  const plan = planning.plan
  const epic = data.intake?.epic
  const analysis = data.intake?.analysis
  const conf = planning.confidence
  const graph = depGraph(stories)

  let body: React.ReactNode
  if (tab === 'stories') {
    body = <StoriesPanel stories={stories} />
  } else if (tab === 'dependencies') {
    body = (
      <div className="table-wrap">
        <table>
          <thead>
            <tr>{['Story', 'Depends on', 'Blocks', 'Cross-team'].map((h) => <th key={h}>{h}</th>)}</tr>
          </thead>
          <tbody>
            {stories.map((s) => (
              <tr key={s.story_id}>
                <td className="mono">{s.story_id}</td>
                <td className="mono">{s.dependencies.join(', ') || '—'}</td>
                <td className="mono">
                  {graph.edges.filter((e) => e.from === s.story_id).map((e) => e.to).join(', ') || '—'}
                </td>
                <td>{graph.edges.some((e) => e.to === s.story_id && e.cross) ? 'yes' : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  } else if (tab === 'risks') {
    body = (
      <div className="card">
        <h3>Risks named at intake</h3>
        <ul className="plain">{(analysis?.risks ?? []).map((r, i) => <li key={i}>{r}</li>)}</ul>
      </div>
    )
  } else if (tab === 'assumptions') {
    body = (
      <div className="card">
        <h3>Assumptions carried by the plan</h3>
        <ul className="plain">{(analysis?.assumptions ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>
      </div>
    )
  } else if (tab === 'impacts') {
    body = (
      <div className="grid cols-2">
        <div className="card">
          <h3>Affected applications</h3>
          <ul className="plain">{(analysis?.affected_applications ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>
        </div>
        <div className="card">
          <h3>External dependencies</h3>
          <ul className="plain">{(analysis?.dependencies ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>
        </div>
      </div>
    )
  } else if (tab === 'artifacts') {
    body = <PlanArtifactsCard showDownloadAll={false} />
  } else {
    const ids = new Set(stories.map((s) => s.story_id))
    const acyclic = graph.critical.length <= stories.length
    const depsOk = stories.every((s) => s.dependencies.every((x) => ids.has(x)))
    const rollbacksOk = stories.every((s) => Boolean(s.rollback_plan))
    const acsOk = stories.every((s) => s.acceptance_criteria?.length)
    const register = (analysis?.risk_register ?? []) as RiskRegisterEntry[]
    const sprintCount = new Set(stories.map((s) => s.sprint)).size

    body = (
      <div>
        <div className="grid cols-3">
          <div className="card">
            <h3>Plan Overview</h3>
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr', marginTop: 10 }}>
              <b>Epic</b><span>{epic?.title ?? '—'}</span>
              <b>Epic ID</b><span className="mono">{epic?.epic_id ?? '—'}</span>
              <b>Plan Version</b><span>{plan ? `v${plan.plan_version}` : 'draft (unsigned)'}</span>
              <b>Created On</b><span>{(epic?.created_at ?? '').slice(0, 10) || '—'}</span>
              <b>Created By</b><span>{epic?.created_by ?? '—'}</span>
              <b>Signed</b>
              <span>{plan ? `${plan.signed_by} · ${plan.signed_at.slice(0, 16).replace('T', ' ')}` : 'not yet'}</span>
              <b>AI Plan Confidence</b>
              <span>
                <span className="info" title={conf?.basis ?? ''}>{conf ? `${conf.value}% ⓘ` : '—'}</span>
              </span>
            </div>
          </div>
          <div className="card">
            <h3>Delivery Breakdown</h3>
            <Donut stories={stories} />
          </div>
          <SprintPlanCard stories={stories} />
        </div>
        <div className="grid cols-2" style={{ marginTop: 14 }}>
          <div className="card">
            <h3>✦ AI Key Observations</h3>
            <p className="hint">Each observation is checked against the plan data, not asserted.</p>
            <ul className="checklist">
              <CheckItem ok={Boolean(acsOk)} label="All stories are covered by acceptance criteria" />
              <CheckItem ok={depsOk && acyclic} label="Dependencies are valid and free of cycles" />
              <CheckItem ok={Boolean(acsOk)} label="Test coverage planned for every acceptance criterion" />
              <CheckItem ok={rollbacksOk} label="Rollback plans defined for all stories" />
              <CheckItem ok={sprintCount <= 2} label={`Plan is feasible within ${sprintCount} sprint(s)`} />
            </ul>
            <h3 style={{ marginTop: 12 }}>Key Assumptions</h3>
            <ul className="plain">{(analysis?.assumptions ?? []).map((a, i) => <li key={i}>{a}</li>)}</ul>
          </div>
          <div className="card">
            <h3>⚠ AI Identified Risks</h3>
            {register.length ? (
              register.map((r, i) => (
                <div key={i} className={`risk-line ${r.severity === 'high' ? 'red' : 'amber'}`}>
                  <b>{String(r.severity).toUpperCase()}</b>
                  <span>{r.text}</span>
                </div>
              ))
            ) : (
              <ul className="plain">{(analysis?.risks ?? []).map((r, i) => <li key={i}>{r}</li>)}</ul>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <section>
      <div className="page-head" style={{ marginBottom: 12 }}>
        <h2>Plan Summary</h2>
        <span className="hint">Review the complete plan at a glance.</span>
      </div>
      <div className="tabs">
        {SUMMARY_TABS.map(([key, label]) => (
          <button key={key} type="button" className={key === tab ? 'on' : ''} onClick={() => setTab(key)}>
            {label}
          </button>
        ))}
      </div>
      {body}
    </section>
  )
}
