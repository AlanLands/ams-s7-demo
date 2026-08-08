import { useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'
import { Modal } from '../../components/Modal'

export function AdvancedAnalysisSection() {
  const { data, act, runId } = useRun()
  const [open, setOpen] = useState(false)
  const [clarAnswers, setClarAnswers] = useState<string[]>([])
  const [newAppAnswers, setNewAppAnswers] = useState<string[]>([])
  const [routeOverride, setRouteOverride] = useState('')
  const [repoUrl, setRepoUrl] = useState('')
  const [showReqModal, setShowReqModal] = useState(false)

  if (!data) return null
  const isLive = data.run?.mode === 'live'
  const unlocked = Boolean(data.intake?.source)
  const req = data.intake?.requirement
  const analysis = data.intake?.analysis
  const epic = data.intake?.epic
  const clar = data.intake?.clarifications
  const repos = data.intake?.repos ?? []
  const routing = data.intake?.routing
  const newApp = data.intake?.new_app
  const scaffold = data.intake?.scaffold

  return (
    <details
      className={`card advanced-section${unlocked ? '' : ' locked'}`}
      open={unlocked && open}
      onToggle={(e) => {
        if (e.target === e.currentTarget) setOpen((e.target as HTMLDetailsElement).open)
      }}
    >
      <summary
        aria-disabled={!unlocked}
        title={unlocked ? undefined : 'Upload or paste a requirement to unlock this section'}
        onClick={(e) => { if (!unlocked) e.preventDefault() }}
      >
        Advanced: Live Analysis &amp; Governance
        {!unlocked && <span className="lock-hint">Unlocks after a requirement is uploaded</span>}
      </summary>
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
            <h4 style={{ marginTop: 14, fontSize: 12.5, color: 'var(--muted)' }}>Documents</h4>
            {req.source_documents?.length ? (
              <ul className="plain">
                {req.source_documents.map((name) => (
                  <li key={name}>
                    {name.includes('/')
                      ? <span className="mono">{name}</span>
                      : <a className="mono" href={`/api/runs/${runId}/intake/documents/${encodeURIComponent(name)}`} target="_blank" rel="noopener noreferrer">{name}</a>}
                  </li>
                ))}
              </ul>
            ) : <p className="hint">No documents attached yet.</p>}
            <button type="button" className="outline block" style={{ marginTop: 12 }} onClick={() => setShowReqModal(true)}>
              ⤢ View full requirement
            </button>
          </div>
        )}

        {showReqModal && req && (
          <Modal title="Requirement Summary" onClose={() => setShowReqModal(false)}>
            <Prov provenance={req.provenance} />
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
              <b>Request ID</b><span className="mono">{req.request_id}</span>
              <b>Title</b><span>{req.title}</span>
              <b>Requested By</b><span>{req.business_owner}</span>
              <b>Priority</b><span><span className={`chip priority-${(req.priority || 'low').toLowerCase()}`}>{req.priority}</span></span>
              <b>Requested On</b><span>{req.requested_date}</span>
              <b>Target Release</b><span>{req.target_release}</span>
              <b>Domain</b><span>{req.domain}</span>
              <b>Description</b><span>{req.description}</span>
            </div>
          </Modal>
        )}

        <details className="card sub-fold" style={{ marginBottom: 12 }}>
          <summary>
            <h3>AI Analysis{analysis ? ' (Completed)' : ''}</h3>
            {analysis && <Prov provenance={analysis.provenance} />}
          </summary>
          {analysis ? (
            <div className="fold-body">
              <ul className="checklist">
                <li><span className={`tick ${analysis.problem_understood ? 'ok' : 'no'}`}>{analysis.problem_understood ? '✓' : '·'}</span>Problem understood</li>
                <li><span className={`tick ${analysis.business_impact ? 'ok' : 'no'}`}>{analysis.business_impact ? '✓' : '·'}</span>Business impact identified</li>
                <li><span className={`tick ${analysis.affected_applications.length > 0 ? 'ok' : 'no'}`}>{analysis.affected_applications.length > 0 ? '✓' : '·'}</span>Affected applications identified <span className="state ok mono">{analysis.affected_applications.length}</span></li>
                <li><span className={`tick ${analysis.stakeholders.length > 0 ? 'ok' : 'no'}`}>{analysis.stakeholders.length > 0 ? '✓' : '·'}</span>Stakeholders identified <span className="state ok mono">{analysis.stakeholders.length}</span></li>
                <li><span className={`tick ${analysis.dependencies.length > 0 ? 'ok' : 'no'}`}>{analysis.dependencies.length > 0 ? '✓' : '·'}</span>Dependencies detected <span className="state ok mono">{analysis.dependencies.length}</span></li>
                <li><span className={`tick ${analysis.risks.length > 0 ? 'ok' : 'no'}`}>{analysis.risks.length > 0 ? '✓' : '·'}</span>Risks identified <span className="state ok mono">{analysis.risks.length}</span></li>
                <li><span className={`tick ${analysis.clarification_questions.length > 0 ? 'ok' : 'no'}`}>{analysis.clarification_questions.length > 0 ? '✓' : '·'}</span>Clarification questions generated <span className="state ok mono">{analysis.clarification_questions.length}</span></li>
                <li><span className={`tick ${analysis.assumptions.length > 0 ? 'ok' : 'no'}`}>{analysis.assumptions.length > 0 ? '✓' : '·'}</span>Assumptions captured <span className="state ok mono">{analysis.assumptions.length}</span></li>
              </ul>
              {analysis.confidence != null && (
                <div className="conf-row"><b>AI Confidence</b><span className="info conf-v">{analysis.confidence}% ⓘ</span></div>
              )}
            </div>
          ) : <p className="fold-body">No analysis yet — run the intake analysis.</p>}
        </details>

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

        {analysis?.business_rules?.length ? (
          <details className="card sub-fold" style={{ marginBottom: 12 }}>
            <summary>
              <h3>AI Extracted Business Rules</h3>
              <span className="chip tag">{analysis.business_rules.length}</span>
              <Prov provenance={analysis.provenance} />
            </summary>
            <ul className="plain fold-body">
              {analysis.business_rules.map((r) => (
                <li key={r.rule_id}><span className="chip priority-high" style={{ marginRight: 8 }}>{r.rule_id}</span>{r.text}</li>
              ))}
            </ul>
          </details>
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
            {repos.length === 0 && (
              <p className="hint" style={{ marginTop: 10 }}>Live analysis is grounded in the connected repos — connect them before analysing.</p>
            )}
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
                  {routing.candidate_repos?.length ? <><b>Candidate repos</b><span>{routing.candidate_repos.join(', ')}</span></> : null}
                  {routing.overridden_by ? <><b>Overridden by</b><span>{routing.overridden_by} at {routing.overridden_at}</span></> : null}
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
              <div style={{ marginTop: 10 }}>
                <p className="hint">Scaffold generated — review before creating the repository.</p>
                {Object.entries(scaffold).map(([name, content]) => (
                  <details key={name} style={{ marginTop: 6 }}>
                    <summary>{name}</summary>
                    <pre className="mono" style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{content}</pre>
                  </details>
                ))}
                <button type="button" className="primary sq block" style={{ marginTop: 10 }} onClick={() => act('/intake/create-new-app-repo', {}, 'New application repository created')}>
                  Create Repository
                </button>
              </div>
            )}
          </div>
        )}

        {epic && (
          <details className="card ok sub-fold" style={{ marginBottom: 12 }}>
            <summary>
              <h3>Created Epic</h3>
              <span className="mono hint">{epic.epic_id}</span>
              <Prov provenance={epic.provenance} />
            </summary>
            <div className="kv fold-body" style={{ gridTemplateColumns: '130px 1fr' }}>
              <b>Epic ID</b><span className="mono">{epic.epic_id}</span>
              <b>Epic Title</b><span>{epic.title}</span>
              <b>Business Outcome</b><span>{epic.business_outcome}</span>
              <b>Estimated Stories</b><span>{epic.estimated_stories}</span>
              <b>Created By</b><span>{epic.created_by}</span>
            </div>
          </details>
        )}

        <div className="actions-row">
          {isLive && <button type="button" className="outline" onClick={() => act('/intake/clarify', {}, 'Clarifying questions requested')}>Ask AI Clarification</button>}
          <button type="button" className="outline" onClick={() => act('/intake/analyse', {}, isLive ? 'Live analysis regenerated' : 'Intake analysis regenerated')}>⟳ Regenerate Analysis</button>
          <button type="button" className="outline" onClick={() => act('/intake/create-epic', {}, 'Epic created')}>Generate Epic</button>
          <button type="button" className="outline approve" onClick={() => act('/intake/pass-gate', {}, 'Intake gate passed')}>✓ Pass Intake Gate</button>
        </div>
      </div>
    </details>
  )
}
