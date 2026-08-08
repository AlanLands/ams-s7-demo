/**
 * Shared helpers for the Build & Review pages (mirrors planningHelpers.ts).
 *
 * The section's framing is fixed here so every page tells the same story:
 * S7 is the governed control plane — it generates context, publishes it to
 * developer workspaces, collects evidence and orchestrates review. Human
 * developers own implementation (Human Controlled · AI Assisted). No page
 * imitates an IDE.
 */
import type { BuildReviewPhase, BuildState, RunState } from '../../types'

export function buildOf(data: RunState | null): BuildState {
  return (data?.build as BuildState | undefined) ?? {}
}

export const PHASE_ORDER: BuildReviewPhase[] = [
  'gate1_approved',
  'architecture_ready',
  'architecture_accepted',
  'delivery_packs_ready',
  'workspaces_ready',
  'developer_execution',
  'build_complete',
]

export const PHASE_LABELS: Record<BuildReviewPhase, string> = {
  gate1_approved: 'Gate 1 approved',
  architecture_ready: 'Architecture ready',
  architecture_accepted: 'Architecture accepted',
  delivery_packs_ready: 'Delivery packs ready',
  workspaces_ready: 'Workspaces ready',
  developer_execution: 'Developer execution',
  build_complete: 'Build complete',
}

export function phaseAtLeast(
  phase: BuildReviewPhase | null | undefined,
  floor: BuildReviewPhase,
): boolean {
  if (!phase) return false
  return PHASE_ORDER.indexOf(phase) >= PHASE_ORDER.indexOf(floor)
}

export const DEV_STATUS_LABELS: Record<string, string> = {
  provisioned: 'Provisioned',
  ready: 'Ready',
  in_development: 'In Development',
  in_review: 'In Review',
  correction_requested: 'Correction Requested',
  complete: 'Complete',
  blocked: 'Blocked',
}

/** Badge class for a derived development status (theme.css st-*). */
export const DEV_STATUS_BADGE: Record<string, string> = {
  provisioned: 'st-planned',
  ready: 'st-ready',
  in_development: 'st-in_progress',
  in_review: 'st-waiting_for_approval',
  correction_requested: 'st-blocked',
  complete: 'st-completed',
  blocked: 'st-blocked',
}

export function hhmm(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function relTime(iso?: string): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const s = Math.max(0, Math.round((Date.now() - t) / 1000))
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.round(s / 60)}m ago`
  return `${Math.round(s / 3600)}h ago`
}

/** Cross-page story selection (Workspaces → Evidence → Review drill-down). */
const SELECTED_KEY = 's7cc.buildStory'

export function selectStory(storyId: string): void {
  try {
    localStorage.setItem(SELECTED_KEY, storyId)
  } catch {
    /* storage unavailable — selection is a convenience only */
  }
}

export function selectedStory(): string | null {
  try {
    return localStorage.getItem(SELECTED_KEY)
  } catch {
    return null
  }
}

/** The ownership statement every execution-facing page carries. */
export function OwnershipChips() {
  return (
    <span className="own-chips">
      <span className="chip own-human">Human Controlled</span>
      <span className="chip own-ai">AI Assisted</span>
    </span>
  )
}

export function GuidanceCard({ lines }: { lines: string[] }) {
  return (
    <div className="rail-card guidance">
      <h3>✓ What this surface is</h3>
      <ul className="plain">
        {lines.map((l) => (
          <li key={l}>{l}</li>
        ))}
      </ul>
    </div>
  )
}

export const CONTROL_PLANE_GUIDANCE = [
  'S7 is the governed control plane, not an IDE.',
  'Developers implement in their own IDE, CLI and Git.',
  'S7 publishes context, collects evidence, orchestrates review.',
  'No code editor, terminal or chat surface is exposed here.',
]
