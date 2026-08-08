import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'

export function AdvancedAnalysisSection() {
  const { data, act } = useRun()
  const [open, setOpen] = useState(false)
  const [clarAnswers, setClarAnswers] = useState<string[]>([])
  const [newAppAnswers, setNewAppAnswers] = useState<string[]>([])
  const [routeOverride, setRouteOverride] = useState('')
  const [repoUrl, setRepoUrl] = useState('')

  if (!data) return null
  const isLive = data.run?.mode === 'live'
  const req = data.intake?.requirement
  const analysis = data.intake?.analysis
  const gate = (data.gates ?? []).find((g) => g.gate_id === 'G0')
  const clar = data.intake?.clarifications
  const repos = data.intake?.repos ?? []
  const routing = data.intake?.routing
  const newApp = data.intake?.new_app
  const scaffold = data.intake?.scaffold

  return (
    <details className="card advanced-section" open={open} onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>Advanced: Live Analysis &amp; Governance</summary>
      <div style={{ marginTop: 14 }}>

        {req && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Requirement Summary</h3><Prov provenance={req.provenance} /></div>
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
              <b>Request ID</b><span className="mono">{req.request_id}</span>
              <b>Title</b><span>{req.title}</span>
              <b>Priority</b><span><span className={`chip priority-${(req.priority || 'low').toLowerCase()}`}>{req.priority}</span></span>
              <b>Business Owner</b><span>{req.business_owner}</span>
              <b>Domain</b><span>{req.domain}</span>
              <b>Description</b><span className="clamp-2">{req.description}</span>
            </div>
          </div>
        )}

        <div className="card" style={{ marginBottom: 12 }}>
          {analysis ? (
            <>
              <div className="section-title"><h3>AI Analysis (Completed)</h3><Prov provenance={analysis.provenance} /></div>
              <ul className="checklist">
                <li><span className={`tick ${analysis.problem_understood ? 'ok' : 'no'}`}>{analysis.problem_understood ? '✓' : '·'}</span>Problem understood</li>
                <li><span className="tick ok">✓</span>Affected applications <span className="state ok mono">{analysis.affected_applications.length}</span></li>
                <li><span className="tick ok">✓</span>Stakeholders <span className="state ok mono">{analysis.stakeholders.length}</span></li>
                <li><span className="tick ok">✓</span>Dependencies <span className="state ok mono">{analysis.dependencies.length}</span></li>
                <li><span className="tick ok">✓</span>Risks <span className="state ok mono">{analysis.risks.length}</span></li>
              </ul>
              {analysis.confidence != null && (
                <div className="conf-row"><b>AI Confidence</b><span className="info conf-v">{analysis.confidence}% ⓘ</span></div>
              )}
            </>
          ) : <p>No analysis yet — run the intake analysis.</p>}
        </div>

        {clar?.pending?.length ? (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>AI Clarification</h3><span className="chip">round {clar.rounds_used} of {clar.max_rounds}</span></div>
            {clar.pending.map((q, i) => (
              <div key={q} style={{ marginBottom: 8 }}>
                <p>{q}</p>
                <input
                  type="text"
                  placeholder="Answer (blank = stated assumption)"
                  value={clarAnswers[i] ?? ''}
                  onChange={(e) => setClarAnswers((prev) => { const next = [...prev]; next[i] = e.target.value; return next })}
                />
              </div>
            ))}
            <button type="button" className="primary sq" onClick={() => act('/intake/clarify-answer', { answers: clarAnswers }, 'Answers recorded')}>
              Submit answers
            </button>
          </div>
        ) : null}

        {isLive && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Connected Repositories</h3><span className="chip">{repos.length} connected</span></div>
            <ul className="plain">
              {repos.map((r) => (
                <li key={r.name}><span className="mono">{r.name}</span> <span className="hint">@ {r.head_sha.slice(0, 10)} · {r.file_count} files</span></li>
              ))}
            </ul>
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <input type="text" placeholder="https://github.com/<owner>/<repo>" value={repoUrl} onChange={(e) => setRepoUrl(e.target.value)} />
              <button type="button" className="outline" onClick={() => repoUrl.trim() && act('/intake/connect-repo', { url: repoUrl.trim() }, 'Repository connected')}>
                Connect repository
              </button>
            </div>
          </div>
        )}

        {isLive && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="section-title"><h3>Requirement Routing</h3>{routing && <Prov provenance={routing.provenance} />}</div>
            {routing ? (
              <>
                <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
                  <b>Verdict</b>
                  <span><span className={`chip ${routing.verdict === 'routable' ? 'priority-low' : 'priority-high'}`}>
                    {routing.verdict === 'routable' ? 'Fits connected repos' : 'New application needed'}
                  </span></span>
                  <b>Reasoning</b><span>{routing.reasoning}</span>
                </div>
                <div style={{ marginTop: 10, display: 'flex', gap: 8, alignItems: 'center' }}>
                  <span className="hint">Override:</span>
                  <select value={routeOverride || routing.verdict} onChange={(e) => setRouteOverride(e.target.value)}>
                    <option value="routable">Routable</option>
                    <option value="new_application_needed">New application needed</option>
                  </select>
                  <button type="button" className="outline" onClick={() => act('/intake/override-route', { verdict: routeOverride || routing.verdict }, 'Routing verdict overridden')}>
                    Apply override
                  </button>
                </div>
              </>
            ) : (
              <button type="button" className="outline block" onClick={() => act('/intake/route', {}, 'Requirement routed')}>Route Requirement</button>
            )}
          </div>
        )}

        {isLive && routing?.verdict === 'new_application_needed' && (
          <div className="card" style={{ marginBottom: 12 }}>
            <h3>New Application Setup</h3>
            {newApp?.name ? (
              <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
                <b>Name</b><span className="mono">{newApp.name}</span>
                <b>Description</b><span>{newApp.description}</span>
                <b>Stack</b><span>{newApp.stack}</span>
              </div>
            ) : newApp?.pending?.length ? (
              <div>
                {newApp.pending.map((q, i) => (
                  <div key={q} style={{ marginBottom: 8 }}>
                    <p>{q}</p>
                    <input type="text" placeholder="Answer" value={newAppAnswers[i] ?? ''}
                      onChange={(e) => setNewAppAnswers((prev) => { const next = [...prev]; next[i] = e.target.value; return next })} />
                  </div>
                ))}
                <button type="button" className="primary sq" onClick={() => act('/intake/new-app-answer', { answers: newAppAnswers }, 'Answers recorded')}>
                  Submit answers
                </button>
              </div>
            ) : (
              <button type="button" className="outline block" onClick={() => act('/intake/new-app-setup', {}, 'Setup started')}>
                Start New Application Setup
              </button>
            )}
            {newApp?.name && !scaffold && (
              <button type="button" className="outline block" style={{ marginTop: 10 }} onClick={() => act('/intake/generate-scaffold', {}, 'Scaffold generated')}>
                Generate Scaffold
              </button>
            )}
            {scaffold && (
              <button type="button" className="primary sq block" style={{ marginTop: 10 }} onClick={() => act('/intake/create-new-app-repo', {}, 'New application repository created')}>
                Create Repository
              </button>
            )}
          </div>
        )}

        <div className="card">
          <div className="section-title"><h3>Intake Gate (G0)</h3></div>
          <p className="hint">{gate?.status ?? 'not_started'}</p>
          <ul className="checklist">
            {(gate?.conditions ?? []).map((c) => (
              <li key={c.condition}><span className={`tick ${c.met ? 'ok' : 'no'}`}>{c.met ? '✓' : '·'}</span>{c.condition}</li>
            ))}
          </ul>
          <div className="actions-row" style={{ marginTop: 10 }}>
            {isLive && <button type="button" className="outline" onClick={() => act('/intake/clarify', {}, 'Clarifying questions requested')}>Ask AI Clarification</button>}
            <button type="button" className="outline" onClick={() => act('/intake/analyse', {}, isLive ? 'Live analysis regenerated' : 'Intake analysis regenerated')}>⟳ Regenerate Analysis</button>
            <button type="button" className="outline" onClick={() => act('/intake/create-epic', {}, 'Epic created')}>Generate Epic</button>
            <button type="button" className="outline approve" onClick={() => act('/intake/pass-gate', {}, 'Intake gate passed')}>✓ Pass Intake Gate</button>
          </div>
        </div>
      </div>
    </details>
  )
}
