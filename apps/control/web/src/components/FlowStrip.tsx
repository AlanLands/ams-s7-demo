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
 */

type NodeStatus = 'completed' | 'current' | 'pending'

interface FlowNodeDef {
  /** `goTo` section id — reuses existing Stepper/SideNav landing ids only. */
  id: string
  label: string
  /** Parent stage id in `data.run.stages`, used for status fallback. */
  stage: string
  /** Optional finer-grained artifact presence check. Undefined result
   * (node omits `done`) means "defer to the parent stage's status". */
  done?: (data: RunState) => boolean
}

const NODES: FlowNodeDef[] = [
  { id: 'intake', label: 'Unstructured Docs', stage: 'intake', done: (d) => Boolean(d.intake?.source) },
  { id: 'intake', label: 'Extraction', stage: 'intake', done: (d) => Boolean(d.intake?.extraction) },
  { id: 'intake', label: 'Epic', stage: 'intake', done: (d) => Boolean(d.intake?.epic) },
  { id: 'epic_to_stories', label: 'Stories', stage: 'planning', done: (d) => Boolean(d.planning?.stories?.length) },
  { id: 'plan_summary', label: 'Sprint Planning', stage: 'planning', done: (d) => Boolean(d.planning?.plan) },
  { id: 'epic_to_stories', label: 'Design', stage: 'planning', done: (d) => d.design?.version !== undefined },
  { id: 'build_overview', label: 'Build', stage: 'build_review' },
  { id: 'quality', label: 'Final Gating', stage: 'quality' },
  { id: 'release', label: 'Release', stage: 'release', done: (d) => Boolean(d.release?.deployment) },
  { id: 'release', label: 'Transition to Maintenance', stage: 'release', done: (d) => Boolean(d.release?.handover) },
]

export function FlowStrip() {
  const { data, goTo } = useRun()
  if (!data) return null

  const stages = data.run?.stages ?? []
  const stageStatus = (stage: string) => stages.find((s) => s.stage === stage)?.status ?? 'not_started'

  let currentAssigned = false
  const nodes = NODES.map((node) => {
    const parentStatus = stageStatus(node.stage)
    const finer = node.done ? node.done(data) : undefined
    const isDone = finer !== undefined ? finer : parentStatus === 'completed'
    let state: NodeStatus = 'pending'
    if (isDone) {
      state = 'completed'
    } else if (!currentAssigned && (parentStatus === 'in_progress' || parentStatus === 'ready')) {
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
                className={`flow-connector ${nodes[i - 1].state === 'completed' ? 'done' : ''}`}
                aria-hidden="true"
              />
            )}
            <button
              type="button"
              className={`flow-node ${node.state}`}
              onClick={() => goTo(node.id)}
              title={node.label}
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
