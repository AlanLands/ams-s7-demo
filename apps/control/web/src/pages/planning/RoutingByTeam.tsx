import { useState } from 'react'
import { Badge, Prov } from '../../components/Badge'
import { Modal } from '../../components/Modal'
import { NotBuilt } from '../../components/NotBuilt'
import { useRun } from '../../state/RunContext'
import type { Provenance, RunState } from '../../types'

// --- planning story shape ---------------------------------------------------
// `types.ts` now has a `PlanStory` with every field this page needs —
// target_application, target_repository, dependencies, sprint, estimate,
// risk, status, provenance, impacts, feature_flag, and a structured
// rollback_plan ({method, tested} rather than a bare string) — matching the
// actual backend schema (`s7_delivery/factory/models.py::Story`). This page
// still defines its own local copy rather than importing from types.ts, the
// same pattern the other planning pages use (./depGraph.ts,
// ./planningHelpers.ts each keep their own field-for-field-identical copy).
// Centralizing on the shared `PlanStory` is a deliberate, still-open cleanup
// deferred to a follow-up, not a blocker.

export interface PlanAcceptanceCriterion {
  ac_id: string
  text: string
  covered_by_code?: boolean
  covered_by_test?: boolean
}

export interface PlanFeatureFlag {
  name: string
  default_state: string
}

export interface PlanRollbackPlan {
  method: string
  tested: boolean
}

export interface PlanStory {
  story_id: string
  epic_id: string
  title: string
  purpose: string
  accountable_team: string
  contributing_teams: string[]
  owner?: string
  target_application: string
  target_component: string
  target_repository: string
  acceptance_criteria: PlanAcceptanceCriterion[]
  dependencies: string[]
  impacts: string[]
  feature_flag: PlanFeatureFlag | null
  rollback_plan: PlanRollbackPlan | null
  task_type: string
  estimate: number
  sprint: number
  status: string
  risk: string
  version?: number
  traces_to?: string[]
  provenance: Provenance
}

interface PlanningStoriesState {
  stories: PlanStory[]
}

// --- helpers (mirrors apps/control/static/app.js) ---------------------------

const TEAMS = [
  'Portal Team', 'Services Team', 'Data Team',
  'Intake Integration Team', 'QA Automation', 'Platform Team', 'Support Team',
]

const TEAM_COLORS = ['#2c5f8f', '#7a4b9b', '#1e7a46', '#a8781f', '#b0243a', '#0f766e', '#5a6b7d']

function teamColor(name: string): string {
  let i = TEAMS.indexOf(name)
  if (i === -1) i = [...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0)
  return TEAM_COLORS[i % TEAM_COLORS.length]
}

function planningStories(data: RunState | null): PlanStory[] {
  const planning = data?.planning as PlanningStoriesState | undefined
  return planning?.stories ?? []
}

function storyGaps(s: PlanStory): string[] {
  const gaps: string[] = []
  if (!s.purpose) gaps.push('purpose missing')
  if (!s.acceptance_criteria?.length) gaps.push('no acceptance criteria')
  if (!s.accountable_team) gaps.push('no accountable team')
  if (!s.target_component) gaps.push('no target component')
  if (!s.rollback_plan) gaps.push('no rollback plan')
  if (!s.task_type) gaps.push('no task type')
  return gaps
}

interface PlanKpis {
  stories: number
  teams: number
  acs: number
  deps: number
  sprints: number
  completeness: number
}

function planKpis(stories: PlanStory[]): PlanKpis {
  const teams = new Set<string>()
  stories.forEach((s) => {
    teams.add(s.accountable_team)
    ;(s.contributing_teams ?? []).forEach((t) => teams.add(t))
  })
  const complete = stories.filter((s) => storyGaps(s).length === 0).length
  return {
    stories: stories.length,
    teams: teams.size,
    acs: stories.flatMap((s) => s.acceptance_criteria).length,
    deps: stories.flatMap((s) => s.dependencies).length,
    sprints: new Set(stories.map((s) => s.sprint)).size,
    completeness: stories.length ? Math.round((100 * complete) / stories.length) : 0,
  }
}

function TeamChip({ name }: { name?: string }) {
  if (!name) return <span>—</span>
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  return (
    <span className="team-chip">
      <span className="avatar">{initials}</span>
      {name}
    </span>
  )
}

function StoryDetailModal({ story: s, onClose }: { story: PlanStory; onClose: () => void }) {
  const acceptanceCriteria = s.acceptance_criteria ?? []
  const impacts = s.impacts ?? []
  return (
    <Modal title={`${s.story_id} — ${s.title}`} onClose={onClose}>
      <Prov provenance={s.provenance} />
      <div className="kv" style={{ gridTemplateColumns: '160px 1fr', marginTop: '10px' }}>
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
      <h4 style={{ marginTop: '16px', fontSize: '12.5px', color: 'var(--muted)' }}>Acceptance Criteria</h4>
      {acceptanceCriteria.length ? (
        <ul className="plain">
          {acceptanceCriteria.map((ac) => (
            <li key={ac.ac_id}>
              <span className="chip priority-high" style={{ marginRight: '8px' }}>{ac.ac_id}</span>
              {ac.text}
            </li>
          ))}
        </ul>
      ) : (
        <p className="hint">None defined.</p>
      )}
      {impacts.length ? (
        <>
          <h4 style={{ marginTop: '16px', fontSize: '12.5px', color: 'var(--muted)' }}>Impacts</h4>
          <ul className="plain">
            {impacts.map((i, idx) => <li key={idx}>{i}</li>)}
          </ul>
        </>
      ) : null}
    </Modal>
  )
}

export function RoutingByTeam() {
  const { data } = useRun()
  const [detailStory, setDetailStory] = useState<PlanStory | null>(null)
  if (!data) return null

  const stories = planningStories(data)
  if (!stories.length) {
    return <NotBuilt name="Routing by Team" phase="the Planning stage — generate the draft plan first" />
  }

  const teams = [...new Set(stories.map((s) => s.accountable_team))]
  const k = planKpis(stories)

  return (
    <section>
      <div className="page-head" style={{ marginBottom: '16px' }}>
        <h2>Routing by Team</h2>
        <span className="hint">Stories grouped by accountable team with planned delivery.</span>
      </div>
      <div className="tiles tiles-4">
        <div className="tile t-green">
          <div className="v">{teams.length}</div>
          <div className="l">Teams Involved</div>
        </div>
        <div className="tile t-red">
          <div className="v">{k.stories}</div>
          <div className="l">Total Stories</div>
        </div>
        <div className="tile t-red">
          <div className="v">{k.acs}</div>
          <div className="l">Acceptance Criteria</div>
        </div>
        <div className="tile t-amber">
          <div className="v">{k.sprints}</div>
          <div className="l">Planned Sprints</div>
        </div>
      </div>
      <div className="team-cols">
        {teams.map((t) => {
          const own = stories.filter((s) => s.accountable_team === t)
          const pts = own.reduce((a, s) => a + s.estimate, 0)
          const color = teamColor(t)
          return (
            <div className="card team-col" key={t}>
              <div className="team-col-head" style={{ borderColor: color }}>
                <h3><span className="legend-dot" style={{ background: color }} />{t}</h3>
                <span className="hint">{own.length} {own.length === 1 ? 'Story' : 'Stories'}</span>
              </div>
              {own.map((s) => (
                <div className="board-card" key={s.story_id}>
                  <div className="mono" style={{ color }}>{s.story_id}</div>
                  <div className="t">{s.title}</div>
                  <div className="dep-meta">
                    <span className="hint mono">{s.target_component}</span>
                    <button
                      type="button"
                      className="pts-chip"
                      title="View the estimate breakdown"
                      onClick={() => setDetailStory(s)}
                    >
                      {s.estimate} pts
                    </button>
                  </div>
                </div>
              ))}
              <div className="hint" style={{ marginTop: '4px' }}>
                <b>AI Rationale: </b>
                {`Owns ${[...new Set(own.map((s) => s.target_component))].join(', ')}.`}
              </div>
              <div className="team-col-foot">{`Total: ${pts} pts`}</div>
            </div>
          )
        })}
      </div>
      {detailStory ? <StoryDetailModal story={detailStory} onClose={() => setDetailStory(null)} /> : null}
    </section>
  )
}
