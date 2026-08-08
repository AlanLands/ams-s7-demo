import { useCallback, useEffect, useState } from 'react'
import { useRun } from '../../state/RunContext'
import { Badge, Prov } from '../../components/Badge'
import { apiPatch } from '../../api'
import { TeamChip } from '../planning/TeamChip'
import {
  buildOf,
  DEV_STATUS_LABELS,
  DEV_STATUS_BADGE,
  GuidanceCard,
  CONTROL_PLANE_GUIDANCE,
  OwnershipChips,
  relTime,
  selectStory,
} from './buildHelpers'
import type { BuildTask, DeliveryPack, DeveloperWorkspace, PlanStory, RunState } from '../../types'

// Developer Workspaces — the registry of governed engineering context S7 has
// published per team/story. Developers implement in their own IDE, CLI and
// Git; this surface only shows what S7 published and the evidence it
// collected back. The "simulate developer activity" controls exist because
// this is a demo: the deterministic engine plays the developer's part and
// every artifact it produces is badged SIMULATED. AI never autonomously
// implements production code here.

function DevBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${DEV_STATUS_BADGE[status] ?? 'st-planned'}`}>
      {DEV_STATUS_LABELS[status] ?? status.replaceAll('_', ' ')}
    </span>
  )
}

function CiBadge({ ci }: { ci: string }) {
  if (!ci) return <span>—</span>
  if (ci === 'passed') return <Badge status="passed" />
  if (ci === 'running') return <span className="badge st-waiting_for_approval">running</span>
  return <Badge status={ci} />
}

function AssignDeveloper({ ws }: { ws: DeveloperWorkspace }) {
  const { runId, role, refresh, notify } = useRun()
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const assign = async () => {
    const developer = name.trim()
    if (!developer || !runId) return
    setBusy(true)
    try {
      await apiPatch(`/api/runs/${runId}/workspaces/${ws.workspace_id}/developer`, { role, developer })
      await refresh()
      notify('Developer assigned')
    } catch (err) {
      notify((err as Error).message, true)
    } finally {
      setBusy(false)
    }
  }
  return (
    <span style={{ display: 'inline-flex', gap: '6px' }}>
      <input
        type="text"
        placeholder="Developer name"
        value={name}
        aria-label={`Assign developer to ${ws.workspace_id}`}
        onChange={(e) => setName(e.target.value)}
      />
      <button type="button" className="outline" disabled={busy || !name.trim()} onClick={() => void assign()}>
        Assign
      </button>
    </span>
  )
}

interface DrawerProps {
  ws: DeveloperWorkspace
  task?: BuildTask
  pack?: DeliveryPack
  story?: PlanStory
  onClose: () => void
}

function WorkspaceDrawer({ ws, task, pack, story, onClose }: DrawerProps) {
  const { act, goTo } = useRun()
  const [closing, setClosing] = useState(false)

  const requestClose = useCallback(() => setClosing(true), [])
  useEffect(() => {
    if (!closing) return
    const t = setTimeout(onClose, 230)
    return () => clearTimeout(t)
  }, [closing, onClose])
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') requestClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [requestClose])

  const tests = task?.tests ?? []
  const acs = story?.acceptance_criteria ?? []
  const deps = task?.dependencies ?? story?.dependencies ?? []

  return (
    <div
      className={`drawer-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) requestClose() }}
    >
      <aside className="drawer story-drawer" role="dialog" aria-label={`${ws.story_id} workspace`}>
        <div className="card-head">
          <h3><span className="mono">{ws.story_id}</span>{' — workspace'}</h3>
          <button type="button" className="kebab" onClick={requestClose} aria-label="Close">✕</button>
        </div>

        <div className="drawer-badges">
          <DevBadge status={ws.development_status} />
          {ws.artifact_status === 'stale'
            ? <span className="badge st-stale">STALE — refresh delivery context</span>
            : <Badge status={ws.artifact_status} />}
          <Prov provenance={ws.provenance} />
          <span className="own-chips">
            <span className="hint">Development Mode:</span>
            <span className="chip own-human">Human</span>
            <span className="chip own-ai">AI Assisted</span>
          </span>
        </div>

        <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
          <b>Team</b><span><TeamChip name={ws.team} /></span>
          <b>Developer</b>
          <span>{ws.developer || <AssignDeveloper ws={ws} />}</span>
          <b>Repository</b><span className="mono">{ws.repository || '—'}</span>
          <b>Branch</b><span className="mono">{ws.branch || '—'}</span>
          <b>Base commit</b><span className="mono">{ws.base_commit ? ws.base_commit.slice(0, 7) : '—'}</span>
          <b>Current commit</b><span className="mono">{ws.current_commit ? ws.current_commit.slice(0, 7) : '—'}</span>
          <b>Pull request</b><span className="mono">{ws.pull_request || '—'}</span>
          <b>CI status</b><span><CiBadge ci={ws.ci_status} /></span>
          <b>Pack</b><span className="mono">{`${ws.delivery_pack_id} v${ws.delivery_pack_version}`}</span>
          <b>Last sync</b><span>{relTime(ws.last_sync_at)}</span>
        </div>

        <div className="sub-panel">
          <h3>Task context</h3>
          {task ? (
            <p><b className="mono">{task.task_id}</b>{task.summary ? ` — ${task.summary}` : ''}</p>
          ) : (
            <p className="hint">No task is linked to this story yet.</p>
          )}
          <b className="hint">Task-specific artifacts</b>
          <ul className="checklist">
            {['task.md', 'context.json', 'test-plan.md'].map((f) => (
              <li key={f}><span className="tick ok">✓</span><span className="mono">{f}</span></li>
            ))}
          </ul>
          <b className="hint">Inherited context</b>
          <ul className="checklist">
            <li><span className="tick ok">✓</span>{`architecture v${pack?.architecture_version ?? ws.delivery_pack_version}`}</li>
            <li><span className="tick ok">✓</span>{`plan v${pack?.plan_version ?? 1}`}</li>
            <li><span className="tick ok">✓</span>{`${ws.team} delivery pack v${ws.delivery_pack_version}`}</li>
            <li><span className="tick ok">✓</span><span className="mono">AGENTS.md</span></li>
          </ul>
          {acs.length > 0 && (
            <div>
              <b className="hint">Acceptance criteria</b>
              <div className="dep-chips" style={{ marginTop: '4px' }}>
                {acs.map((ac) => <span className="chip tag mono" key={ac.ac_id}>{ac.ac_id}</span>)}
              </div>
            </div>
          )}
          {deps.length > 0 && (
            <div>
              <b className="hint">Dependencies</b>
              <div className="dep-chips" style={{ marginTop: '4px' }}>
                {deps.map((d) => <span className="chip tag mono" key={d}>{d}</span>)}
              </div>
            </div>
          )}
        </div>

        {task && (
          <div className="sub-panel">
            <h3>Simulate developer activity <Prov provenance="simulated" /></h3>
            <p className="hint">
              In production this evidence arrives from the developer's Git/CI. In this demo the deterministic engine
              produces it, badged SIMULATED.
            </p>
            <div className="actions-row">
              {task.status === 'ready' && (
                <button type="button" className="primary sq"
                  onClick={() => void act(`/tasks/${task.task_id}/start`, {}, 'Development started (simulated)')}>
                  ▶ Start development
                </button>
              )}
              {task.status === 'in_progress' && tests.length === 0 && (
                <button type="button" className="primary sq"
                  onClick={() => void act(`/tasks/${task.task_id}/generate-tests`, {}, 'Failing tests recorded (simulated)')}>
                  ⚑ Record failing tests (red baseline)
                </button>
              )}
              {task.status === 'in_progress' && tests.length > 0 && (
                <>
                  <button type="button" className="primary sq"
                    onClick={() => void act(`/tasks/${task.task_id}/develop`, {}, 'Implementation evidence recorded (simulated)')}>
                    ✦ Record implementation evidence
                  </button>
                  <button type="button" className="outline" disabled={task.files_changed <= 0}
                    onClick={() => void act(`/tasks/${task.task_id}/verify`, {}, 'Build & tests verified (simulated)')}>
                    ✓ Verify build &amp; tests
                  </button>
                  <button type="button" className="outline" disabled={task.progress_pct < 90}
                    onClick={() => void act(`/tasks/${task.task_id}/submit-review`, {}, 'Submitted for independent review')}>
                    ⬆ Submit for independent review
                  </button>
                </>
              )}
              {task.status === 'waiting_for_approval' && (
                <>
                  <span className="hint">In independent review</span>
                  <button type="button" className="outline" onClick={() => goTo('independent_review')}>
                    Open Independent Review
                  </button>
                </>
              )}
              {task.status === 'blocked' && (
                <>
                  <span className="hint" style={{ color: 'var(--red)' }}>
                    Correction requested by independent review
                  </span>
                  <button type="button" className="outline"
                    onClick={() => { selectStory(ws.story_id); goTo('independent_review') }}>
                    Open Independent Review
                  </button>
                </>
              )}
            </div>
          </div>
        )}

        <div className="actions-row drawer-foot">
          <button type="button" className="outline" onClick={() => goTo('delivery_packs')}>View delivery pack</button>
          <button type="button" className="outline" onClick={() => { selectStory(ws.story_id); goTo('test_evidence') }}>
            View build &amp; test evidence
          </button>
          <span className="toolbar-spring" />
          <button type="button" className="ghost" onClick={requestClose}>Close</button>
        </div>
      </aside>
    </div>
  )
}

function GitSyncCard({ ws, data }: { ws: DeveloperWorkspace; data: RunState }) {
  return (
    <div className="card rail-card">
      <h3>Git Sync</h3>
      <div className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
        <b>Repository</b><span className="mono">{ws.repository || '—'}</span>
        <b>Branch</b><span className="mono">{ws.branch || '—'}</span>
        <b>Base commit</b><span className="mono">{ws.base_commit ? ws.base_commit.slice(0, 7) : '—'}</span>
        <b>Current commit</b><span className="mono">{ws.current_commit ? ws.current_commit.slice(0, 7) : '—'}</span>
        <b>PR</b><span className="mono">{ws.pull_request || '—'}</span>
        <b>CI</b><span><CiBadge ci={ws.ci_status} /></span>
      </div>
      {data.run.mode !== 'live' && (
        <p className="hint">
          <Prov provenance="simulated" />{' '}
          Simulated publication — no git remote is touched in this mode.
        </p>
      )}
    </div>
  )
}

export function DeveloperWorkspaces() {
  const { data, goTo } = useRun()
  const [openId, setOpenId] = useState<string | null>(null)
  if (!data) return null

  const build = buildOf(data)
  const workspaces = build.workspaces ?? []
  const tasks = build.tasks ?? []
  const packs = build.delivery_packs ?? []
  const stories = data.planning?.stories ?? []

  const open = openId ? workspaces.find((w) => w.workspace_id === openId) : undefined
  const railWs = open ?? workspaces[0]
  const count = (status: string) => workspaces.filter((w) => w.development_status === status).length

  return (
    <section className="page-with-rail">
      <div>
        <div className="page-head" style={{ marginBottom: '14px' }}>
          <h2>Developer Workspaces</h2>
          <span className="hint">
            S7 provides governed engineering context. Developers perform implementation using their normal IDE, CLI,
            Git and optional coding assistants.
          </span>
          <OwnershipChips />
        </div>

        {workspaces.length === 0 ? (
          <div className="card">
            <div className="empty">
              <p>No developer workspaces yet.</p>
              <p className="hint">Workspaces are provisioned when a delivery pack is published.</p>
              <button type="button" className="primary sq" onClick={() => goTo('delivery_packs')}>
                Go to Delivery Packs
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="tiles">
              <div className="tile">
                <div className="v">{String(workspaces.length)}</div>
                <div className="l">Workspaces</div>
              </div>
              <div className="tile">
                <div className="v">{String(workspaces.filter((w) => w.developer).length)}</div>
                <div className="l">Developers Assigned</div>
              </div>
              <div className="tile t-amber">
                <div className="v">{String(count('in_development'))}</div>
                <div className="l">In Development</div>
              </div>
              <div className="tile t-blue">
                <div className="v">{String(count('in_review'))}</div>
                <div className="l">In Review</div>
              </div>
              <div className="tile t-red">
                <div className="v">{String(count('correction_requested'))}</div>
                <div className="l">Corrections</div>
              </div>
              <div className="tile t-green">
                <div className="v">{String(count('complete'))}</div>
                <div className="l">Complete</div>
              </div>
            </div>

            <div className="card">
              <div className="card-head"><h3>Workspaces</h3></div>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Team</th><th>Story</th><th>Repository</th><th>Branch</th><th>Developer</th>
                      <th>Pack</th><th>Commit</th><th>PR</th><th>CI</th><th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {workspaces.map((ws) => (
                      <tr
                        key={ws.workspace_id}
                        className={`row-click${openId === ws.workspace_id ? ' sel' : ''}`}
                        onClick={() => setOpenId(ws.workspace_id)}
                      >
                        <td><TeamChip name={ws.team} /></td>
                        <td className="mono">{ws.story_id}</td>
                        <td className="mono">{ws.repository || '—'}</td>
                        <td className="mono">{ws.branch || '—'}</td>
                        <td>
                          {ws.developer || (
                            <>
                              <span className="hint">Unassigned</span>{' '}
                              <button
                                type="button"
                                className="link-btn"
                                onClick={(e) => { e.stopPropagation(); setOpenId(ws.workspace_id) }}
                              >
                                Assign
                              </button>
                            </>
                          )}
                        </td>
                        <td>
                          {`v${ws.delivery_pack_version}`}{' '}
                          <Badge status={ws.artifact_status} />
                        </td>
                        <td className="mono">{ws.current_commit ? ws.current_commit.slice(0, 7) : '—'}</td>
                        <td className="mono">{ws.pull_request || '—'}</td>
                        <td><CiBadge ci={ws.ci_status} /></td>
                        <td><DevBadge status={ws.development_status} /></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="hint">Click a row to open the workspace detail.</p>
            </div>
          </>
        )}
      </div>

      <aside className="rail">
        <div className="card rail-card">
          <h3>Ownership</h3>
          <ul className="plain">
            <li>The developer owns implementation.</li>
            <li>S7 owns governed context, traceability, evidence collection, artifact freshness and review orchestration.</li>
            <li>A coding assistant may assist the developer — it never acts autonomously.</li>
          </ul>
        </div>
        {railWs && <GitSyncCard ws={railWs} data={data} />}
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>

      {open && (
        <WorkspaceDrawer
          key={open.workspace_id}
          ws={open}
          task={tasks.find((t) => t.story_id === open.story_id)}
          pack={packs.find((p) => p.delivery_pack_id === open.delivery_pack_id)}
          story={stories.find((s) => s.story_id === open.story_id)}
          onClose={() => setOpenId(null)}
        />
      )}
    </section>
  )
}
