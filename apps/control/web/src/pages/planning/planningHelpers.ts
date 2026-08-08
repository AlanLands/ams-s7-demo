import type { Provenance, RunState } from '../../types'
import type { PlanStory } from './depGraph'

// Shared by every planning-stage page (Dependency Map, Routing by Team, Plan
// Sign-off). `PlanStory` is defined once in `./depGraph.ts` — imported here
// rather than redefined, since that is the shape a concurrently-ported
// sibling page already established for `data.planning.stories`.

/** Spec §8E — every story must be complete before Gate 1 can pass. */
export function storyGaps(s: PlanStory): string[] {
  const gaps: string[] = []
  if (!s.purpose) gaps.push('purpose missing')
  if (!s.acceptance_criteria?.length) gaps.push('no acceptance criteria')
  if (!s.accountable_team) gaps.push('no accountable team')
  if (!s.target_component) gaps.push('no target component')
  if (!s.rollback_plan) gaps.push('no rollback plan')
  if (!s.task_type) gaps.push('no task type')
  return gaps
}

// --- planning section (plan sign-off / confidence) --------------------------
// `types.ts` now has typed `planning.plan` (`SignedPlan`) and
// `planning.confidence` (`PlanConfidence`) sections, identical to the shapes
// below. Defined here too, next to `PlanStory`, so every planning page casts
// through the same local shape instead of inventing its own — centralizing on
// the shared types.ts versions is a deliberate, still-open cleanup deferred to
// a follow-up.

export interface SignedPlan {
  plan_version: number
  signed_by: string
  signed_at: string
  note: string
  story_ids: string[]
}

export interface PlanConfidence {
  value: number
  basis: string
  provenance?: Provenance
}

export interface PlanningSection {
  stories?: PlanStory[]
  plan?: SignedPlan
  confidence?: PlanConfidence
}

export function planningOf(data: RunState | null): PlanningSection {
  return (data?.planning as PlanningSection | undefined) ?? {}
}
