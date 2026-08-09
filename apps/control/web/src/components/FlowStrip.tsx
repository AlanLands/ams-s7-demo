import { useRun } from '../state/RunContext'
import type { RunState } from '../types'

/**
 * Compact horizontal "moves from one stage to the other" visual for the
 * Overview page — the end-to-end flow recited in the rehearsal: unstructured
 * docs → extraction → epic → stories → sprint planning → design → build →
 * final gating → release → transition to maintenance.
 *
 * Node states are never hardcoded. Each node either reads a real artifact
 * already in the run payload (e.g. whether `intake.epic` exists) or, when no
 * finer-grained signal is exposed yet, falls back to its parent stage's own
 * status from `data.run.stages` — the same source `Stepper.tsx` uses. No
 * backend state is added for this component.
 *
 * Ordering guarantee. Some artifacts are written out of narrative order by
 * the engine — e.g. in simulation, `design.json` and `stories.json` are
 * written in the same batch, *before* the human sign-off that produces
 * `plan.json` (the Sprint Planning signal). Left uncorrected, that lets
 * "Design" render completed while "Sprint Planning", to its left, is still
 * current — a strip that no longer reads left-to-right. To prevent that, a
 * fixed subset of nodes is `required`: they define a left-to-right
 * "frontier" (the first not-yet-done required node, by array position).
 * Every node at or after the frontier can only render current/pending,
 * never completed — that caps both required nodes and optional ones whose
 * artifact happened to appear early.
 *
 * The frontier alone is *not* enough to decide "skipped" vs "pending" for an
 * optional node with no artifact: on a brand-new run the frontier already
 * sits at index 2 (Epic, the first required node) purely because nothing
 * required can exist before it — that is not evidence anything has actually
 * happened yet. So "skipped" additionally requires real forward evidence:
 * either a required node *later* than this optional one is done, or this
 * optional node's own parent stage is fully `completed` (covers Design,
 * whose parent stage — planning — can finish before any later-array
 * required node, which lives in a different stage, has started). Absent
 * that evidence, the node is `pending` like anything else not yet reached,
 * and — like any pending node — is eligible to be the single `current`
 * pulse if its own stage is active. That is what lets a genuinely fresh,
 * zero-artifact run correctly start the pulse at "Unstructured Docs"
 * instead of jumping to "Epic".
 */

type NodeStatus = 'completed' | 'current' | 'pending' | 'skipped'

interface FlowNodeDef {
  /** `goTo` section id — reuses existing Stepper/SideNav landing ids only. */
  id: string
  label: string
  /** Parent stage id in `data.run.stages`, used for status fallback and for
   * the "skipped" evidence check below. */
  stage: string
  /** Required nodes define the left-to-right completion frontier and are
   * never `skipped` — every run produces them once its stage genuinely
   * progresses. Optional nodes (an upload that may never happen, a design
   * artifact live mode never writes) never block or advance the frontier. */
  required: boolean
  /** Optional finer-grained artifact presence check. Undefined result
   * (node omits `done`) means "defer to the parent stage's status". */
  done?: (data: RunState) => boolean
}

const NODES: FlowNodeDef[] = [
  { id: 'intake', label: 'Unstructured Docs', stage: 'intake', required: false, done: (d) => Boolean(d.intake?.source) },
  { id: 'intake', label: 'Extraction', stage: 'intake', required: false, done: (d) => Boolean(d.intake?.extraction) },
  { id: 'intake', label: 'Epic', stage: 'intake', required: true, done: (d) => Boolean(d.intake?.epic) },
  { id: 'epic_to_stories', label: 'Stories', stage: 'planning', required: true, done: (d) => Boolean(d.planning?.stories?.length) },
  { id: 'plan_summary', label: 'Sprint Planning', stage: 'planning', required: true, done: (d) => Boolean(d.planning?.plan) },
  { id: 'epic_to_stories', label: 'Design', stage: 'planning', required: false, done: (d) => d.design?.version !== undefined },
  { id: 'build_overview', label: 'Build', stage: 'build_review', required: true },
  { id: 'quality', label: 'Final Gating', stage: 'quality', required: true },
  { id: 'release', label: 'Release', stage: 'release', required: true, done: (d) => Boolean(d.release?.deployment) },
  { id: 'release', label: 'Transition to Maintenance', stage: 'release', required: true, done: (d) => Boolean(d.release?.handover) },
]

const isActiveStatus = (status: string) => status === 'in_progress' || status === 'ready'

export function FlowStrip() {
  const { data, goTo } = useRun()
  if (!data) return null

  const stages = data.run?.stages ?? []
  const stageStatus = (stage: string) => stages.find((s) => s.stage === stage)?.status ?? 'not_started'

  const checked = NODES.map((node) => {
    const parentStatus = stageStatus(node.stage)
    const finer = node.done ? node.done(data) : undefined
    const checkDone = finer !== undefined ? finer : parentStatus === 'completed'
    return { ...node, parentStatus, checkDone }
  })

  // Frontier: index of the first required node not yet done (or past the
  // end once every required node is). Nothing before it can be trusted as
  // "not yet happened" — every required node before it is, by construction
  // of this scan, checkDone === true.
  let frontierIndex = checked.length
  for (let i = 0; i < checked.length; i++) {
    if (checked[i].required && !checked[i].checkDone) {
      frontierIndex = i
      break
    }
  }

  // Base state per node, without "current" yet (assigned in a second pass
  // below so it can land on the first eligible node regardless of whether
  // that node is required or optional).
  const base: NodeStatus[] = checked.map((node, i) => {
    const capped = i >= frontierIndex
    if (node.required) {
      return capped ? 'pending' : 'completed'
    }
    if (node.checkDone && !capped) return 'completed'
    if (!node.checkDone) {
      const laterRequiredDone = checked.some((n, j) => n.required && j > i && n.checkDone)
      if (node.parentStatus === 'completed' || laterRequiredDone) return 'skipped'
    }
    return 'pending'
  })

  let currentAssigned = false
  const nodes = checked.map((node, i) => {
    let state = base[i]
    if (state === 'pending' && !currentAssigned && isActiveStatus(node.parentStatus)) {
      state = 'current'
      currentAssigned = true
    }
    return { ...node, state }
  })

  return (
    <div className="flow-strip-wrap">
      <div className="flow-strip" aria-label="Delivery flow, requirement through transition to maintenance">
        {nodes.map((node, i) => (
          <div key={`${node.id}-${node.label}`} style={{ display: 'contents' }}>
            {i > 0 && (
              <span
                className={`flow-connector ${nodes[i - 1].state === 'completed' || nodes[i - 1].state === 'skipped' ? 'done' : ''}`}
                aria-hidden="true"
              />
            )}
            <button
              type="button"
              className={`flow-node ${node.state}`}
              onClick={() => goTo(node.id)}
              title={node.state === 'skipped' ? `${node.label} — not exercised this run` : node.label}
            >
              <span className="flow-dot" aria-hidden="true" />
              <span className="flow-label">{node.label}</span>
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}
