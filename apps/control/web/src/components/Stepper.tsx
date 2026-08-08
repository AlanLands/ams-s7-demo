import { useRun } from '../state/RunContext'

const STAGES: [string, string][] = [
  ['intake', 'Intake'],
  ['planning', 'Planning'],
  ['build_review', 'Build & Review'],
  ['quality', 'Quality'],
  ['release', 'Release'],
]

const GROUP_LANDING: Record<string, string> = {
  planning: 'epic_to_stories',
  build_review: 'build_work_queue',
}

export function Stepper() {
  const { data, goTo } = useRun()
  const stages = data?.run?.stages ?? []

  return (
    <nav className="stepper" aria-label="Delivery stages">
      {stages.map((s, i) => {
        const label = STAGES.find(([k]) => k === s.stage)?.[1] ?? s.stage
        const statusLabel = s.status === 'completed' ? 'Completed'
          : s.status === 'not_started' ? 'Pending'
          : s.status.replaceAll('_', ' ').replace(/^./, (c) => c.toUpperCase())
        const prev = i > 0 ? stages[i - 1] : null
        return (
          <div key={s.stage} style={{ display: 'contents' }}>
            {prev && <span className={`step-arrow ${prev.status === 'completed' ? 'done' : ''}`} aria-hidden="true" />}
            <button
              type="button"
              className={`step ${s.status}`}
              onClick={() => goTo(GROUP_LANDING[s.stage] ?? s.stage)}
            >
              <span className="check">✓</span>
              <span className="dot">{i + 1}</span>
              <span className="step-txt">
                <span>{label}</span>
                <span className="step-sub">{statusLabel}</span>
              </span>
            </button>
          </div>
        )
      })}
    </nav>
  )
}
