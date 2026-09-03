import { useEffect, useState } from 'react'
import { useRun } from '../state/RunContext'
import { RoleSwitcher } from './RoleSwitcher'
import { apiPost } from '../api'
import type { RunState } from '../types'

function useClock(): string {
  const [now, setNow] = useState(() => new Date().toLocaleTimeString())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date().toLocaleTimeString()), 1000)
    return () => clearInterval(t)
  }, [])
  return now
}

export function Header() {
  const { data, runs, refresh } = useRun()
  const run = data?.run
  const clock = useClock()

  return (
    <header className="top">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">MS</span>
        <div>
          <div className="brand-kicker">MapleSure Insurance</div>
          <h1>S7 Delivery Control Centre</h1>
        </div>
      </div>
      <div className="hdr-fields">
        <label className="hdr-field">
          <span className="hdr-label">Scenario</span>
          <select disabled value={data?.scenario?.title ?? ''}>
            <option>{data?.scenario?.title ?? '—'}</option>
          </select>
        </label>
        <div className="hdr-field">
          <span className="hdr-label">Run ID</span>
          <span className="run-id-wrap">
            <select
              className="mono"
              value={run?.run_id ?? ''}
              onChange={(e) => {
                localStorage.setItem('s7cc.runId', e.target.value)
                window.location.reload()
              }}
            >
              {runs.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
            <button
              type="button"
              className="icon-btn"
              title="Copy run id"
              aria-label="Copy run id"
              onClick={() => run && navigator.clipboard.writeText(run.run_id)}
            >⧉</button>
          </span>
        </div>
        <label className="hdr-field">
          <span className="hdr-label">Environment</span>
          <select
            value={run?.mode ?? 'simulation'}
            onChange={async (e) => {
              const mode = e.target.value
              if (mode === run?.mode) return
              const created = await apiPost<{ run: { run_id: string } } & RunState>('/api/runs', { mode })
              localStorage.setItem('s7cc.runId', created.run.run_id)
              window.location.reload()
            }}
          >
            <option value="demo">Demo</option>
            <option value="simulation">Simulation</option>
            <option value="replay">Replay</option>
            <option value="live">Live</option>
          </select>
        </label>
      </div>
      <div className="top-controls">
        <span className="pill safe" title="No IDE, terminal, prompts, credentials or raw logs are exposed on this surface">✓ Customer-safe view</span>
        <div className="hdr-clock">
          <span>{clock}</span>
          <button type="button" className="icon-btn" title="Re-fetch run state" aria-label="Refresh" onClick={() => refresh()}>⟳</button>
        </div>
        <RoleSwitcher />
      </div>
    </header>
  )
}
