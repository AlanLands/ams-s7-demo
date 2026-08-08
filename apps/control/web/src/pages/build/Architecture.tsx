/**
 * Architecture — the AI-generated engineering blueprint produced from the
 * approved plan, reviewed and accepted by a human before any developer
 * workspace is provisioned. Rendered previews only — never an editor.
 */
import { useCallback, useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Badge, Prov } from '../../components/Badge'
import type { PlanStory } from '../../types'
import { buildOf, CONTROL_PLANE_GUIDANCE, GuidanceCard, hhmm } from './buildHelpers'

function basename(path: string): string {
  return path.split('/').pop() ?? path
}

export function Architecture() {
  const { data, runId, act, goTo } = useRun()

  const build = buildOf(data)
  const arch = build.architecture
  const phase = build.phase
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const plan = data?.planning?.plan
  const archVersion = arch?.version

  const [previewName, setPreviewName] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState('')
  const [showRevise, setShowRevise] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [approver, setApprover] = useState('')

  const loadPreview = useCallback(
    (name: string) => {
      if (!runId || archVersion == null) return
      setPreviewName(name)
      setPreviewText('Loading…')
      fetch(`/api/runs/${runId}/artifact-file/architecture/v${archVersion}/${name}`)
        .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
        .then(setPreviewText)
        .catch((err: Error) => setPreviewText(`Could not load ${name}: ${err.message}`))
    },
    [runId, archVersion],
  )

  useEffect(() => {
    if (runId && archVersion != null) loadPreview('architecture.md')
  }, [runId, archVersion, loadPreview])

  if (!data) return null

  // --- derived tiles ---------------------------------------------------------
  const apps = new Set(stories.map((s) => s.target_application).filter(Boolean))
  const repos = new Set(stories.map((s) => s.target_repository).filter(Boolean))
  const teams = new Set(stories.map((s) => s.accountable_team).filter(Boolean))
  const withDeps = stories.filter((s) => (s.dependencies ?? []).length > 0).length
  const storyById = new Map(stories.map((s) => [s.story_id, s]))
  let integrationPoints = 0
  for (const s of stories) {
    for (const dep of s.dependencies ?? []) {
      const other = storyById.get(dep)
      if (other && other.accountable_team !== s.accountable_team) integrationPoints += 1
    }
  }
  const everyStoryHasRepo = stories.length > 0 && stories.every((s) => Boolean(s.target_repository))
  const accepted = arch?.status === 'accepted'

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '16px' }}>
          <h2>Architecture</h2>
          <span className="hint">
            AI-generated engineering blueprint created from the approved plan before developer workspaces are provisioned.
          </span>
        </div>

        {!arch ? (
          <div className="card">
            <h3>◈ No architecture generated yet</h3>
            <p>
              The architecture pack is generated <b>after Gate 1 approval</b> locks the plan. It turns the signed
              stories into an engineering blueprint — component map, repository layout, integration contracts —
              that a human accepts before any delivery pack or workspace exists.
            </p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button
                className="primary"
                disabled={!phase}
                onClick={() => void act('/architecture/generate', {}, 'Architecture generated')}
              >
                ✦ Generate Architecture
              </button>
            </div>
            {!phase ? (
              <p className="hint" style={{ marginTop: '8px' }}>
                The plan has not been signed at Gate 1 yet — generation unlocks once the build phase starts.
              </p>
            ) : null}
          </div>
        ) : (
          <>
            <div className="tiles">
              <div className="tile t-blue">
                <div className="v">{`v${arch.version}`}</div>
                <div className="l">
                  Architecture Version <Badge status={arch.status} />
                </div>
              </div>
              <div className="tile t-blue">
                <div className="v">{String(apps.size)}</div>
                <div className="l">Applications</div>
              </div>
              <div className="tile t-blue">
                <div className="v">{String(repos.size)}</div>
                <div className="l">Repositories</div>
              </div>
              <div className="tile t-blue">
                <div className="v">{String(teams.size)}</div>
                <div className="l">Teams</div>
              </div>
              <div className="tile t-amber">
                <div className="v">{String(withDeps)}</div>
                <div className="l">Dependencies</div>
              </div>
              <div className="tile t-amber">
                <div className="v">{String(integrationPoints)}</div>
                <div className="l">Integration Points</div>
              </div>
            </div>

            <div className="card">
              <div className="card-head">
                <h3>
                  ▣ Generated Architecture Pack <Prov provenance={arch.provenance} />
                </h3>
                <span className="hint">
                  {`Generated ${hhmm(arch.generated_at)} by ${arch.generated_by || '—'}`}
                </span>
              </div>
              {arch.revision_note ? (
                <p className="hint" style={{ marginBottom: '8px' }}>
                  ⟳ Revision note: {arch.revision_note}
                </p>
              ) : null}
              <ul className="artifact-list">
                {arch.files.map((f) => {
                  const name = basename(f)
                  return (
                    <li key={f}>
                      <span className="file-ico">▣</span>
                      <span className="file-meta">
                        <b className="mono">{name}</b>
                        <span className="hint mono">{f}</span>
                      </span>
                      <button className="link-btn" onClick={() => loadPreview(name)}>
                        Preview
                      </button>
                    </li>
                  )
                })}
              </ul>
              {previewName ? (
                <>
                  <p className="hint" style={{ margin: '10px 0 6px' }}>
                    Rendered preview of <span className="mono">{previewName}</span> — read-only, not an editor.
                  </p>
                  <pre className="artifact-preview">{previewText}</pre>
                </>
              ) : null}
            </div>

            <div className="actions-row" style={{ marginTop: '16px' }}>
              <button
                className="outline"
                onClick={() => window.open(`/api/runs/${runId}/architecture/download.zip`, '_blank')}
              >
                ⬇ Download Architecture Pack
              </button>
              <button className="outline" onClick={() => setShowRevise((v) => !v)}>
                ⟳ Request AI Revision
              </button>
              {accepted ? (
                <span className="chip">
                  <span style={{ color: 'var(--green)' }}>✓</span> Accepted by {arch.accepted_by || '—'}
                </span>
              ) : (
                <>
                  <input
                    type="text"
                    placeholder="Approver name"
                    value={approver}
                    onChange={(e) => setApprover(e.target.value)}
                  />
                  <button
                    className="approve"
                    onClick={() => void act('/architecture/accept', { approver }, 'Architecture accepted')}
                  >
                    ✓ Accept Architecture
                  </button>
                </>
              )}
            </div>

            {showRevise ? (
              <div className="card" style={{ marginTop: '14px' }}>
                <h3>⟳ Request AI Revision</h3>
                <p className="hint">
                  Feedback goes back to the generator; the pack is re-produced as a new version. Nothing is edited in place.
                </p>
                <textarea
                  rows={4}
                  style={{ width: '100%', marginTop: '8px' }}
                  placeholder="What should the next architecture version change?"
                  value={feedback}
                  onChange={(e) => setFeedback(e.target.value)}
                />
                <div className="actions-row" style={{ marginTop: '10px' }}>
                  <button
                    className="primary"
                    disabled={!feedback.trim()}
                    onClick={async () => {
                      if (await act('/architecture/revise', { feedback }, 'Revision generated')) {
                        setFeedback('')
                        setShowRevise(false)
                      }
                    }}
                  >
                    Submit Revision Request
                  </button>
                  <button className="ghost" onClick={() => setShowRevise(false)}>
                    Cancel
                  </button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Architecture checkpoints</h3>
          <ul className="checklist">
            <li>
              <span className={`tick ${arch && plan ? 'ok' : 'no'}`}>{arch && plan ? '✓' : '·'}</span>
              Generated from locked plan
              <span className="state ok mono">{plan ? `v${plan.plan_version}` : '—'}</span>
            </li>
            <li>
              <span className={`tick ${everyStoryHasRepo ? 'ok' : 'no'}`}>{everyStoryHasRepo ? '✓' : '·'}</span>
              Every story maps to a repository
              <span className="state ok mono">{stories.length ? `${stories.length} stories` : '—'}</span>
            </li>
            <li>
              <span className={`tick ${arch ? 'ok' : 'no'}`}>{arch ? '✓' : '·'}</span>
              Cross-team integration points identified
              <span className="state ok mono">{arch ? String(integrationPoints) : '—'}</span>
            </li>
            <li>
              <span className={`tick ${accepted ? 'ok' : 'no'}`}>{accepted ? '✓' : '·'}</span>
              Human acceptance
              <span className={`state ${accepted ? 'ok' : 'no'}`}>{accepted ? 'Accepted' : 'Pending'}</span>
            </li>
          </ul>
        </div>
        <div className="card rail-card">
          <h3>Next actions</h3>
          {accepted ? (
            <button className="primary" onClick={() => goTo('delivery_packs')}>
              Continue to Delivery Packs →
            </button>
          ) : (
            <p className="hint">
              Accept the architecture to unlock per-team delivery packs. No pack is generated from an unaccepted blueprint.
            </p>
          )}
        </div>
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
