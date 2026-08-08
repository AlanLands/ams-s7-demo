import type { Provenance } from '../../types'

// --- planning story shape ----------------------------------------------------
// Ported from the story objects produced by `planningStories()` in
// apps/control/static/app.js (see storyDetailModal/storyRow for the full
// field list). Defined locally for now because RunState's `planning` section
// in ../../types.ts (StoryRecord/PlanningState) is a thinner shape added by a
// concurrent port and doesn't carry `dependencies`, `estimate`, `sprint`,
// `status`, `risk`, `provenance`, etc. that this page needs.
//
// NOTE: apps/control/web/src/pages/planning/RoutingByTeam.tsx (a concurrent
// port of a sibling page) independently arrived at the same fuller shape,
// under the same name `PlanStory`. The two are field-for-field identical on
// purpose — kept as separate local copies rather than one importing from the
// other, so each page stays self-contained while both are still in flux. See
// the port report for the verbatim types.ts addition that should replace
// StoryRecord/PlanningState and let every planning page (including this one)
// drop its local copy in favor of the shared one.

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

// --- dependency graph helpers -------------------------------------------------
// Ported 1:1 from `depGraph`, `teamColor` and `TEAM_COLORS` in
// apps/control/static/app.js (~line 1308-1359).

export const TEAMS = [
  'Portal Team',
  'Services Team',
  'Data Team',
  'Intake Integration Team',
  'QA Automation',
  'Platform Team',
  'Support Team',
]

const TEAM_COLORS = ['#2c5f8f', '#7a4b9b', '#1e7a46', '#a8781f', '#b0243a', '#0f766e', '#5a6b7d']

export function teamColor(name: string): string {
  let i = TEAMS.indexOf(name)
  if (i === -1) i = [...String(name)].reduce((a, c) => a + c.charCodeAt(0), 0)
  return TEAM_COLORS[i % TEAM_COLORS.length]
}

export interface DepEdge {
  from: string
  to: string
  cross: boolean
}

export interface DepGraphResult {
  depth: Record<string, number>
  critical: string[]
  edges: DepEdge[]
}

export function depGraph(stories: PlanStory[]): DepGraphResult {
  const byId: Record<string, PlanStory> = Object.fromEntries(stories.map((s) => [s.story_id, s]))
  const depth: Record<string, number> = {}
  const resolving = new Set<string>()
  const depthOf = (id: string): number => {
    if (depth[id] != null) return depth[id]
    if (resolving.has(id)) return 0 // cycle guard; the engine prevents these
    resolving.add(id)
    const deps = (byId[id]?.dependencies ?? []).filter((x) => byId[x])
    depth[id] = deps.length ? Math.max(...deps.map(depthOf)) + 1 : 0
    resolving.delete(id)
    return depth[id]
  }
  stories.forEach((s) => depthOf(s.story_id))

  const memo: Record<string, string[]> = {}
  const chainOf = (id: string): string[] => {
    if (memo[id]) return memo[id]
    let best: string[] = []
    for (const dep of (byId[id]?.dependencies ?? []).filter((x) => byId[x])) {
      const c = chainOf(dep)
      if (c.length > best.length) best = c
    }
    memo[id] = [...best, id]
    return memo[id]
  }
  let critical: string[] = []
  stories.forEach((s) => {
    const c = chainOf(s.story_id)
    if (c.length > critical.length) critical = c
  })

  const edges: DepEdge[] = []
  for (const s of stories) {
    for (const dep of s.dependencies) {
      if (!byId[dep]) continue
      edges.push({
        from: dep,
        to: s.story_id,
        cross: byId[dep].accountable_team !== s.accountable_team,
      })
    }
  }
  return { depth, critical, edges }
}

// --- SVG arrow drawing --------------------------------------------------------
// Ported 1:1 from `drawDepArrows` in apps/control/static/app.js
// (~line 1361-1404). This is pure DOM manipulation (querySelector,
// getBoundingClientRect, createElementNS) with no vanilla-framework-specific
// APIs, so the algorithm carries over verbatim — only the caller changes
// (a React useEffect against a ref, instead of a bare requestAnimationFrame
// call inside the vanilla render function).

export function drawDepArrows(container: HTMLElement, edges: DepEdge[], vertical: boolean): void {
  const svg = container.querySelector('svg.dep-arrows') as SVGSVGElement | null
  if (!svg) return
  const ns = 'http://www.w3.org/2000/svg'
  const box = container.getBoundingClientRect()
  svg.setAttribute('width', String(container.scrollWidth))
  svg.setAttribute('height', String(container.scrollHeight))
  svg.replaceChildren()
  const defs = document.createElementNS(ns, 'defs')
  defs.innerHTML =
    '<marker id="arr" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">' +
    '<path d="M0,0 L8,4 L0,8 z" fill="#64707a"/></marker>'
  svg.appendChild(defs)
  for (const e of edges) {
    const a = container.querySelector(`[data-story="${e.from}"]`)
    const b = container.querySelector(`[data-story="${e.to}"]`)
    if (!a || !b) continue
    const ra = a.getBoundingClientRect()
    const rb = b.getBoundingClientRect()
    let x1: number, y1: number, x2: number, y2: number
    if (vertical) {
      x1 = ra.left - box.left + ra.width / 2 + container.scrollLeft
      y1 = ra.bottom - box.top + container.scrollTop
      x2 = rb.left - box.left + rb.width / 2 + container.scrollLeft
      y2 = rb.top - box.top + container.scrollTop
    } else {
      x1 = ra.right - box.left + container.scrollLeft
      y1 = ra.top - box.top + ra.height / 2 + container.scrollTop
      x2 = rb.left - box.left + container.scrollLeft
      y2 = rb.top - box.top + rb.height / 2 + container.scrollTop
    }
    const path = document.createElementNS(ns, 'path')
    const mx = (x1 + x2) / 2
    const my = (y1 + y2) / 2
    path.setAttribute(
      'd',
      vertical
        ? `M ${x1} ${y1} C ${x1} ${my}, ${x2} ${my}, ${x2} ${y2}`
        : `M ${x1} ${y1} C ${mx} ${y1}, ${mx} ${y2}, ${x2} ${y2}`,
    )
    path.setAttribute('fill', 'none')
    path.setAttribute('stroke', '#64707a')
    path.setAttribute('stroke-width', '1.6')
    path.setAttribute('marker-end', 'url(#arr)')
    if (e.cross) path.setAttribute('stroke-dasharray', '5 4')
    svg.appendChild(path)
  }
}
