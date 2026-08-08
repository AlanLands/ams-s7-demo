import { useRun } from '../../state/RunContext'

export function AiActivityPanel() {
  const { data, goTo } = useRun()
  const source = data?.intake?.source
  const ext = data?.intake?.extraction
  const epic = data?.intake?.epic

  const steps: [string, boolean][] = [
    ['Document read', Boolean(source)],
    ['Content extracted', Boolean(ext)],
    ['Requirements structured', Boolean(ext?.extracted_requirements?.length)],
    ['Epic created', Boolean(epic)],
  ]

  return (
    <aside className="rail">
      <div className="card rail-card">
        <h3>AI Activity</h3>
        <p className="hint"><span className="chip priority-low">● Active</span></p>
        <ul className="checklist">
          {steps.map(([label, done]) => (
            <li key={label}>
              <span className={`tick ${done ? 'ok' : 'no'}`}>{done ? '✓' : '○'}</span>
              {done ? label : `${label} pending`}
            </li>
          ))}
        </ul>
        <button type="button" className="outline block" style={{ marginTop: 10 }} onClick={() => goTo('activity')}>
          View AI Activity Log
        </button>
      </div>
    </aside>
  )
}
