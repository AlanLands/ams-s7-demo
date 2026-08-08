import { useRun } from '../state/RunContext'
import { apiPost } from '../api'
import { SectionTitle } from '../components/SectionTitle'
import type { RunState } from '../types'

const DEMO_SCENARIOS: [string, string][] = [
  ['happy-path', 'Happy path — full successful run to handover'],
  ['review-failure', 'Independent review failure — US-003 blocked'],
  ['missing-test-coverage', 'Missing test coverage — quality gate blocks'],
  ['staleness', 'Upstream change — downstream stale, release blocked'],
  ['release-rejected', 'Release approval rejected by Business Owner'],
]

async function newRun() {
  const created = await apiPost<{ run: { run_id: string } } & RunState>('/api/runs', { mode: 'simulation' })
  localStorage.setItem('s7cc.runId', created.run.run_id)
  window.location.reload()
}

async function loadDemo(action: string) {
  const created = await apiPost<{ run: { run_id: string } } & RunState>(`/api/demo/${action}`, {})
  localStorage.setItem('s7cc.runId', created.run.run_id)
  localStorage.setItem('s7cc.section', 'overview')
  window.location.reload()
}

export function Settings() {
  const { data, role, act } = useRun()
  if (!data) return null
  const run = data.run

  return (
    <section>
      <SectionTitle title="Settings" />
      <div className="card">
        <div className="kv">
          <b>Run id</b><span className="mono">{run.run_id}</span>
          <b>Demo mode</b><span>{run.mode}</span>
          <b>Acting role</b><span>{role.replaceAll('_', ' ')}</span>
          <b>State storage</b><code>{`artifacts/runs/${run.run_id}/`}</code>
        </div>
        <div className="actions-row">
          <button type="button" className="primary" onClick={() => newRun()}>New run</button>
          <button type="button" className="ghost danger-ghost" onClick={() => act('/reset', {}, 'Run reset to seeded state')}>Reset this run</button>
        </div>
      </div>
      <SectionTitle
        title="Load demo scenario"
        hint="Each creates a fresh run driven to a known state through the real engine — gates, roles and ledgers all execute"
      />
      <div className="grid cols-2">
        {DEMO_SCENARIOS.map(([key, label]) => (
          <div className="card" key={key}>
            <h3>{label}</h3>
            <div className="actions-row">
              <button type="button" className="primary" onClick={() => loadDemo(key)}>Load</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
