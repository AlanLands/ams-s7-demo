/**
 * Delivery Packs — governed engineering context generated per team from the
 * accepted architecture, ready to publish to developer workspaces. The pack
 * is published to git (AGENTS.md + .s7/** on a fresh branch); the canonical
 * artifacts always remain in the S7 artifact store.
 */
import { useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'
import type { DeliveryPack, GitPublication, PlanStory } from '../../types'
import { buildOf, CONTROL_PLANE_GUIDANCE, GuidanceCard, phaseAtLeast } from './buildHelpers'

const PACK_CONTENTS = [
  'Architecture reference',
  'AGENTS.md',
  'Assigned stories',
  'Acceptance criteria',
  'Team dependencies',
  'Task packs',
  'Test strategy',
  'Engineering rules',
  'Rollback guidance',
  'Workspace manifest',
]

function PublicationCard({ pack, pub }: { pack: DeliveryPack; pub: GitPublication }) {
  return (
    <div className="card" style={{ marginTop: '14px' }}>
      <div className="card-head">
        <h3>✓ Delivery Pack Published — {pack.team}</h3>
        {pub.simulated ? <Prov provenance="simulated" /> : null}
      </div>
      <div className="kv">
        <b>Team</b>
        <span>{pack.team}</span>
        <b>Repository</b>
        <span className="mono">{pub.repository}</span>
        <b>Branch</b>
        <span className="mono">{pub.branch}</span>
        <b>Pack Version</b>
        <span className="mono">{`v${pack.version}`}</span>
        <b>Commit</b>
        <span className="mono">{(pub.commit || '').slice(0, 7) || '—'}</span>
        <b>Artifacts Published</b>
        <span>{String((pub.published_paths ?? []).length)}</span>
        <b>Status</b>
        <span>
          <span className="badge st-passed">{(pub.status || 'published').toUpperCase()}</span>{' '}
          {pub.simulated ? <Prov provenance="simulated" /> : null}
        </span>
      </div>
      <p className="hint" style={{ marginTop: '8px' }}>
        Published; canonical artifacts remain in the S7 artifact store.
      </p>
    </div>
  )
}

export function DeliveryPacks() {
  const { data, runId, act } = useRun()

  const build = buildOf(data)
  const packs = build.delivery_packs ?? []
  const publications = build.publications ?? []
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const phase = build.phase

  const [selected, setSelected] = useState<string | null>(null)
  const [agentsText, setAgentsText] = useState('')

  const selectedPack = packs.find((p) => p.delivery_pack_id === selected) ?? null
  const selectedSlug = selectedPack?.team_slug

  useEffect(() => {
    if (!runId || !selectedSlug) return
    setAgentsText('Loading…')
    fetch(`/api/runs/${runId}/artifact-file/build/packs/${selectedSlug}/AGENTS.md`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setAgentsText)
      .catch((err: Error) => setAgentsText(`Could not load AGENTS.md: ${err.message}`))
  }, [runId, selectedSlug])

  if (!data) return null

  const storyById = new Map(stories.map((s) => [s.story_id, s]))
  const staleIds = new Set((data.staleness ?? []).map((s) => s.artifact_id))
  const pubFor = (packId: string): GitPublication | undefined =>
    [...publications].reverse().find((p) => p.delivery_pack_id === packId)

  const storiesCovered = packs.reduce((n, p) => n + p.story_ids.length, 0)
  const acsCovered = packs.reduce(
    (n, p) =>
      n + p.story_ids.reduce((m, id) => m + (storyById.get(id)?.acceptance_criteria ?? []).length, 0),
    0,
  )
  const readyCount = packs.filter((p) => p.status === 'generated').length
  const publishedCount = packs.filter((p) => p.publication_status === 'published').length
  const allPublished = packs.length > 0 && packs.every((p) => p.publication_status === 'published')
  const canGenerate = phaseAtLeast(phase, 'architecture_accepted')

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '16px' }}>
          <h2>Delivery Packs</h2>
          <span className="hint">
            Governed engineering context generated for each team and ready to publish to developer workspaces.
          </span>
        </div>

        <div className="tiles">
          <div className="tile t-blue">
            <div className="v">{String(packs.length)}</div>
            <div className="l">Teams</div>
          </div>
          <div className="tile t-green">
            <div className="v">{String(readyCount)}</div>
            <div className="l">Packs Ready</div>
          </div>
          <div className="tile t-green">
            <div className="v">{String(publishedCount)}</div>
            <div className="l">Published</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{String(storiesCovered)}</div>
            <div className="l">Stories Covered</div>
          </div>
          <div className="tile t-blue">
            <div className="v">{String(acsCovered)}</div>
            <div className="l">Acceptance Criteria</div>
          </div>
        </div>

        {packs.length === 0 ? (
          <div className="card">
            <h3>◈ No delivery packs yet</h3>
            <p>
              Delivery packs are generated <b>per team</b> from the accepted architecture: each team receives its
              assigned stories, acceptance criteria, dependencies, engineering rules and workspace manifest as one
              governed, versioned package.
            </p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button
                className="primary"
                disabled={!canGenerate}
                onClick={() => void act('/delivery-packs/generate', {}, 'Delivery packs generated')}
              >
                ✦ Generate Delivery Packs
              </button>
            </div>
            {!canGenerate ? (
              <p className="hint" style={{ marginTop: '8px' }}>
                The architecture has not been accepted yet — packs are only cut from an accepted blueprint.
              </p>
            ) : null}
          </div>
        ) : (
          <>
            <div className="card">
              <h3>▣ Team Delivery Packs</h3>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Team</th>
                      <th>Stories</th>
                      <th>ACs</th>
                      <th>Repository</th>
                      <th>Pack Version</th>
                      <th>Artifact Status</th>
                      <th>Publication</th>
                      <th>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {packs.map((pack) => {
                      const pub = pubFor(pack.delivery_pack_id)
                      const stale = staleIds.has(pack.delivery_pack_id)
                      const published = pack.publication_status === 'published'
                      const packAcs = pack.story_ids.reduce(
                        (m, id) => m + (storyById.get(id)?.acceptance_criteria ?? []).length,
                        0,
                      )
                      return (
                        <tr key={pack.delivery_pack_id}>
                          <td>{pack.team}</td>
                          <td>{String(pack.story_ids.length)}</td>
                          <td>{String(packAcs)}</td>
                          <td className="mono">{pack.repository}</td>
                          <td className="mono">{`v${pack.version}`}</td>
                          <td>
                            {stale ? (
                              <span className="badge st-stale">STALE</span>
                            ) : (
                              <span className="badge st-ready">CURRENT</span>
                            )}
                          </td>
                          <td>
                            {published ? (
                              <>
                                <span className="badge st-passed">PUBLISHED</span>{' '}
                                {pub?.simulated ? <Prov provenance="simulated" /> : null}
                              </>
                            ) : (
                              <span className="badge st-planned">NOT PUBLISHED</span>
                            )}
                          </td>
                          <td>
                            <div className="actions-row" style={{ margin: 0, flexWrap: 'nowrap' }}>
                              <button className="link-btn" onClick={() => setSelected(pack.delivery_pack_id)}>
                                Preview
                              </button>
                              <button
                                className="ghost"
                                onClick={() =>
                                  window.open(
                                    `/api/runs/${runId}/delivery-packs/${pack.delivery_pack_id}/download.zip`,
                                    '_blank',
                                  )
                                }
                              >
                                ⬇ ZIP
                              </button>
                              <button
                                className="outline"
                                disabled={published}
                                onClick={() =>
                                  void act(
                                    `/delivery-packs/${pack.delivery_pack_id}/publish`,
                                    {},
                                    'Pack published',
                                  )
                                }
                              >
                                ⬆ Publish
                              </button>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div className="actions-row" style={{ marginTop: '12px' }}>
                <button
                  className="outline"
                  onClick={() =>
                    packs.forEach((pack) =>
                      window.open(
                        `/api/runs/${runId}/delivery-packs/${pack.delivery_pack_id}/download.zip`,
                        '_blank',
                      ),
                    )
                  }
                >
                  ⬇ Download All
                </button>
                <button
                  className="primary"
                  disabled={allPublished}
                  onClick={() => void act('/delivery-packs/publish-all', {}, 'All packs published')}
                >
                  ⬆ Publish All to Git
                </button>
              </div>
            </div>

            {selectedPack ? (
              <div className="card" style={{ marginTop: '14px' }}>
                <div className="card-head">
                  <h3>
                    ◈ Pack Contents — {selectedPack.team} <Prov provenance={selectedPack.provenance} />
                  </h3>
                  <button className="ghost" onClick={() => setSelected(null)}>
                    Close
                  </button>
                </div>
                <div className="grid cols-2">
                  <div>
                    <ul className="checklist">
                      {PACK_CONTENTS.map((item) => (
                        <li key={item}>
                          <span className="tick ok">✓</span>
                          {item}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className="hint">Stories</p>
                    <p>
                      {selectedPack.story_ids.map((id) => (
                        <span className="chip mono" key={id} style={{ marginRight: '6px' }}>
                          {id}
                        </span>
                      ))}
                    </p>
                    <p className="hint" style={{ marginTop: '10px' }}>
                      Tasks
                    </p>
                    <p>
                      {selectedPack.task_ids.map((id) => (
                        <span className="chip mono" key={id} style={{ marginRight: '6px' }}>
                          {id}
                        </span>
                      ))}
                    </p>
                  </div>
                </div>
                <p className="hint" style={{ margin: '10px 0 6px' }}>
                  Rendered preview of <span className="mono">AGENTS.md</span> — read-only, not an editor.
                </p>
                <pre className="artifact-preview">{agentsText}</pre>
              </div>
            ) : null}

            {packs
              .map((pack) => ({ pack, pub: pubFor(pack.delivery_pack_id) }))
              .filter((x): x is { pack: DeliveryPack; pub: GitPublication } => Boolean(x.pub))
              .map(({ pack, pub }) => (
                <PublicationCard key={pub.publication_id} pack={pack} pub={pub} />
              ))}
          </>
        )}
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>⛓ Publication model</h3>
          <p className="hint">
            Publication writes only <span className="mono">AGENTS.md</span> and{' '}
            <span className="mono">.s7/**</span> onto a fresh{' '}
            <span className="mono">s7/&lt;run&gt;-&lt;team&gt;</span> branch — never the default branch.
          </p>
          <p className="hint">Conflicts stop publication. Nothing is force-pushed and nothing is merged for you.</p>
        </div>
        {data.run.mode !== 'live' ? (
          <div className="card rail-card">
            <h3>⚑ Simulation</h3>
            <p className="hint">
              This run is not in live mode: publish is <b>simulated</b> and no git repository is touched.{' '}
              <Prov provenance="simulated" />
            </p>
          </div>
        ) : null}
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
