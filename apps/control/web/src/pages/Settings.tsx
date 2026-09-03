import { useEffect, useState } from 'react'
import { useRun } from '../state/RunContext'
import { apiGet, apiPost } from '../api'
import { SectionTitle } from '../components/SectionTitle'
import type { PromptSetInfo, RunState } from '../types'

/** Labels for known scenarios; the list itself comes from the server
 * (/api/demo-scenarios) so a scenario added or removed there never
 * silently diverges from this page. Unknown keys render prettified. */
const SCENARIO_LABELS = new Map<string, string>([
  ['happy-path', 'Happy path — full successful run to handover'],
  ['review-failure', 'Independent review failure — US-003 blocked'],
  ['missing-test-coverage', 'Missing test coverage — quality gate blocks'],
  ['staleness', 'Upstream change — downstream stale, release blocked'],
  ['release-rejected', 'Release approval rejected by Business Owner'],
  ['full-run', 'Full run — alias of the happy path'],
])

async function newRun(entryMode: 'project' | 'enhancement' = 'project', promptSet = 'default') {
  const created = await apiPost<{ run: { run_id: string } } & RunState>(
    '/api/runs', { mode: 'simulation', entry_mode: entryMode, prompt_set: promptSet })
  localStorage.setItem('s7cc.runId', created.run.run_id)
  if (entryMode === 'enhancement') localStorage.setItem('s7cc.section', 'epic_to_stories')
  window.location.reload()
}

async function loadDemo(action: string) {
  const created = await apiPost<{ run: { run_id: string } } & RunState>(`/api/demo/${action}`, {})
  localStorage.setItem('s7cc.runId', created.run.run_id)
  localStorage.setItem('s7cc.section', 'overview')
  window.location.reload()
}

export function Settings() {
  const { data, role, roles, roleLabel, act } = useRun()
  const [scenarios, setScenarios] = useState<string[]>([])
  // Prompt sets come from the admin app's configuration plane via the
  // Control Centre (GET /api/prompt-sets). An older server without the
  // route leaves only "default", which is what a run pins when unspecified.
  const [promptSets, setPromptSets] = useState<PromptSetInfo[]>([{ name: 'default' }])
  const [promptSet, setPromptSet] = useState('default')
  useEffect(() => {
    apiGet<string[]>('/api/demo-scenarios').then(setScenarios).catch(() => setScenarios([...SCENARIO_LABELS.keys()]))
    apiGet<PromptSetInfo[]>('/api/prompt-sets')
      .then((list) => {
        if (Array.isArray(list) && list.length) setPromptSets(list)
      })
      .catch(() => { /* keep the default-only list */ })
  }, [])
  if (!data) return null
  const run = data.run
  const roleInfo = roles.find((r) => r.role === role)

  return (
    <section>
      <SectionTitle title="Settings" />
      <div className="card">
        <div className="kv">
          <b>Run id</b><span className="mono">{run.run_id}</span>
          <b>Demo mode</b><span>{run.mode}</span>
          <b>Entry mode</b><span>{run.entry_mode === 'enhancement' ? 'enhancement (stories in)' : 'project (epic in)'}</span>
          <b>Prompt set</b><span className="mono">{run?.prompt_set ?? 'default'}</span>
          <b>Acting role</b><span>{roleLabel(role)}{roleInfo?.summary ? ` — ${roleInfo.summary}` : ''}</span>
          <b>State storage</b><code>{`artifacts/runs/${run.run_id}/`}</code>
        </div>
        <div className="actions-row">
          <label className="hdr-field" title="Which prompt set (rules, skills, tasks, playbooks) the new run pins. Managed in the S7 Admin app.">
            <span className="hdr-label">Prompt set for new runs</span>
            <select value={promptSet} onChange={(e) => setPromptSet(e.target.value)} aria-label="Prompt set for new runs">
              {promptSets.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.name}{p.description ? ` — ${p.description}` : ''}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className="primary" onClick={() => newRun('project', promptSet)}>New run</button>
          <button
            type="button"
            className="outline"
            title="S3-style entry: user stories in directly, converging at plan sign-off — no epic, no decomposition"
            onClick={() => newRun('enhancement', promptSet)}
          >
            New enhancement run
          </button>
          <button type="button" className="ghost danger-ghost" onClick={() => act('/reset', {}, 'Run reset to seeded state')}>Reset this run</button>
        </div>
      </div>
      <SectionTitle
        title="Load demo scenario"
        hint="Each creates a fresh run driven to a known state through the real engine — gates, roles and ledgers all execute"
      />
      <div className="grid cols-2">
        {scenarios.map((key) => (
          <div className="card" key={key}>
            <h3>{SCENARIO_LABELS.get(key) ?? key.replaceAll('-', ' ')}</h3>
            <div className="actions-row">
              <button type="button" className="primary" onClick={() => loadDemo(key)}>Load</button>
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
