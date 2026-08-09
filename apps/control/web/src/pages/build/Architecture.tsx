/**
 * Architecture — the engineering blueprint generated from the locked plan
 * after Gate 1, reviewed and accepted by a human before any delivery pack or
 * workspace exists. Rendered previews only — never an editor.
 *
 * Honesty: the generation badge is the provenance (SIMULATED / RULE_BASED);
 * the page never claims "AI Generated" for a rule-based render. Validations
 * are deterministic automated checks, not model output. The landscape
 * diagram derives from the run's own plan — no invented services.
 */
import { useCallback, useEffect, useState } from 'react'
import {
  CircleAlert, CircleCheck, Download, Eye, RefreshCw, TriangleAlert,
} from 'lucide-react'
import { useRun } from '../../state/RunContext'
import { Badge, Prov } from '../../components/Badge'
import { TeamChip } from '../planning/TeamChip'
import type { ArchLandscape, PlanStory } from '../../types'
import { buildOf, CONTROL_PLANE_GUIDANCE, GuidanceCard, hhmm } from './buildHelpers'

function basename(path: string): string {
  return path.split('/').pop() ?? path
}

function kb(bytes?: number): string {
  return bytes == null ? '' : `${(bytes / 1024).toFixed(1)} KB`
}

/** Section text of architecture.md by `## Heading` (up to the next `## `). */
function mdSection(md: string, heading: string): string {
  const marker = `## ${heading}`
  const start = md.indexOf(marker)
  if (start < 0) return ''
  const rest = md.slice(start + marker.length)
  const end = rest.indexOf('\n## ')
  return (end < 0 ? rest : rest.slice(0, end)).trim()
}

const TABS = [
  ['overview', 'Overview'],
  ['repos', 'Repository Mapping'],
  ['dependencies', 'Dependencies'],
  ['integration', 'Integration Points'],
  ['dataflow', 'Data Flow'],
  ['tech', 'Technology Stack'],
  ['security', 'Security'],
  ['deployment', 'Deployment'],
] as const
type TabId = (typeof TABS)[number][0]

const LAYER_LABELS: Record<string, string> = {
  client: 'Client Channels',
  core: 'Core Services',
  data: 'Shared Data',
  external: 'External Systems',
}

/** Customer-safe landscape diagram — pure SVG from derived run data. */
function LandscapeDiagram({ landscape }: { landscape: ArchLandscape }) {
  // Tolerate metas stored before nodes carried `label` (older versions).
  const allNodes = landscape.nodes.map((n) => ({ ...n, label: n.label || n.application }))
  const layers: (keyof typeof LAYER_LABELS)[] = ['client', 'core', 'data', 'external']
  const rows = layers
    .map((layer) => ({ layer, nodes: allNodes.filter((n) => n.layer === layer) }))
    .filter((r) => r.nodes.length > 0)
  if (rows.length === 0) return <p className="hint">No applications in the plan yet.</p>

  const NW = 190
  const NH = 46
  const GX = 26
  const GY = 46
  const LABEL_W = 92
  const maxCount = Math.max(...rows.map((r) => r.nodes.length))
  const width = LABEL_W + maxCount * (NW + GX) + 10
  const height = rows.length * (NH + GY) + 8

  const pos = new Map<string, { x: number; y: number }>()
  rows.forEach((row, ri) => {
    const rowW = row.nodes.length * (NW + GX) - GX
    const x0 = LABEL_W + (width - LABEL_W - rowW) / 2
    row.nodes.forEach((n, ni) => {
      pos.set(n.label, { x: x0 + ni * (NW + GX), y: 10 + ri * (NH + GY) })
    })
  })

  const FILL: Record<string, { bg: string; border: string; text: string }> = {
    client: { bg: '#e3edf6', border: '#2c5f8f', text: '#204566' },
    core: { bg: '#eaf3ee', border: '#2f7d5c', text: '#1d5940' },
    data: { bg: '#ede9fb', border: '#6d3fc4', text: '#4c2b8c' },
    external: { bg: '#fdf3d8', border: '#b98b1f', text: '#7d5f13' },
  }

  return (
    <div className="landscape-wrap">
      <svg viewBox={`0 0 ${width} ${height}`} className="landscape" role="img"
        aria-label="Application landscape diagram">
        {landscape.edges.map((e, i) => {
          const a = pos.get(e.from_app)
          const b = pos.get(e.to_app)
          if (!a || !b) return null
          const x1 = a.x + NW / 2
          const y1 = a.y + NH
          const x2 = b.x + NW / 2
          const y2 = b.y
          const down = y2 > y1
          return (
            <path
              key={i}
              d={down
                ? `M ${x1} ${y1} C ${x1} ${y1 + 22}, ${x2} ${y2 - 22}, ${x2} ${y2}`
                : `M ${x1} ${a.y} C ${x1} ${a.y - 22}, ${x2} ${b.y + NH + 22}, ${x2} ${b.y + NH}`}
              fill="none"
              stroke="var(--border-strong)"
              strokeWidth={1.4}
              strokeDasharray={e.kind === 'data' ? '5 4' : undefined}
            />
          )
        })}
        {rows.map((row, ri) => (
          <text key={row.layer} x={4} y={10 + ri * (NH + GY) + NH / 2 + 4}
            className="landscape-layer-label">
            {LAYER_LABELS[row.layer]}
          </text>
        ))}
        {allNodes.map((n) => {
          const p = pos.get(n.label)
          if (!p) return null
          const c = FILL[n.layer]
          const sub = n.application && n.application !== n.label ? n.application : ''
          return (
            <g key={n.label}>
              <rect x={p.x} y={p.y} width={NW} height={NH} rx={8}
                fill={c.bg} stroke={c.border} strokeWidth={1.2} />
              <text x={p.x + NW / 2} y={p.y + (sub ? 20 : 27)}
                textAnchor="middle" className="landscape-node-title" fill={c.text}>
                {n.label.length > 30 ? `${n.label.slice(0, 29)}…` : n.label}
              </text>
              {sub ? (
                <text x={p.x + NW / 2} y={p.y + 35} textAnchor="middle"
                  className="landscape-node-repo">
                  {sub.length > 38 ? `${sub.slice(0, 37)}…` : sub}
                </text>
              ) : null}
            </g>
          )
        })}
      </svg>
      <div className="landscape-legend">
        {(['client', 'core', 'data', 'external'] as const).map((l) => (
          <span key={l} className={`lg lg-${l}`}>{LAYER_LABELS[l]}</span>
        ))}
        <span className="lg"><span className="lg-line" /> Synchronous</span>
        <span className="lg"><span className="lg-line dashed" /> Data</span>
      </div>
    </div>
  )
}

export function Architecture() {
  const { data, runId, act, goTo } = useRun()

  const build = buildOf(data)
  const arch = build.architecture
  const phase = build.phase
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const plan = data?.planning?.plan
  const archVersion = arch?.version

  const [tab, setTab] = useState<TabId>('overview')
  const [archMd, setArchMd] = useState('')
  const [previewName, setPreviewName] = useState<string | null>(null)
  const [previewText, setPreviewText] = useState('')
  const [showRevise, setShowRevise] = useState(false)
  const [feedback, setFeedback] = useState('')
  const [approver, setApprover] = useState('')

  const fileUrl = useCallback(
    (name: string) => `/api/runs/${runId}/artifact-file/architecture/v${archVersion}/${name}`,
    [runId, archVersion],
  )

  useEffect(() => {
    if (!runId || archVersion == null) return
    fetch(`/api/runs/${runId}/artifact-file/architecture/v${archVersion}/architecture.md`)
      .then((r) => (r.ok ? r.text() : ''))
      .then(setArchMd)
      .catch(() => setArchMd(''))
    setPreviewName(null)
  }, [runId, archVersion])

  const loadPreview = (name: string) => {
    setPreviewName(name)
    setPreviewText('Loading…')
    fetch(fileUrl(name))
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setPreviewText)
      .catch((err: Error) => setPreviewText(`Could not load ${name}: ${err.message}`))
  }

  if (!data) return null

  // --- derived ---------------------------------------------------------------
  const checks = arch?.validations ?? []
  const mandatoryFailed = checks.filter((c) => c.mandatory && c.result === 'failed')
  const accepted = arch?.status === 'accepted'
  const stale = (data.staleness ?? []).some((s) => s.artifact_id === arch?.artifact_id)
  const statusLabel = !arch
    ? ''
    : stale ? 'STALE' : accepted ? 'CANONICAL' : 'AWAITING REVIEW'
  const statusBadge = stale ? 'blocked' : accepted ? 'completed' : 'waiting_for_approval'
  const land = arch?.landscape ?? { nodes: [], edges: [] }
  const apps = new Set(land.nodes.map((n) => n.application || n.label))
  const repos = new Set(stories.map((s) => s.target_repository).filter(Boolean))
  const teams = new Set(stories.map((s) => s.accountable_team).filter(Boolean))
  const depEdges = stories.reduce((n, s) => n + (s.dependencies ?? []).length, 0)
  const storyById = new Map(stories.map((s) => [s.story_id, s]))
  const integrationRows = stories.flatMap((s) =>
    (s.dependencies ?? [])
      .map((dep) => storyById.get(dep))
      .filter((o): o is PlanStory => Boolean(o && o.accountable_team !== s.accountable_team))
      .map((o) => ({ from: o, to: s })),
  )
  const stalePacks = (build.delivery_packs ?? []).filter(
    (p) => arch && p.architecture_version < arch.version,
  ).length
  const staleWorkspaces = (build.workspaces ?? []).filter(
    (w) => w.artifact_status === 'stale',
  ).length
  const gate1 = (data.gates ?? []).find((g) => g.gate_id === 'G1')

  const teamRows = (() => {
    const rows: { team: string; repository: string; application: string; stories: string[] }[] = []
    for (const s of stories) {
      const r = rows.find((x) => x.team === s.accountable_team && x.repository === s.target_repository)
      if (r) r.stories.push(s.story_id)
      else rows.push({
        team: s.accountable_team, repository: s.target_repository,
        application: s.target_application, stories: [s.story_id],
      })
    }
    return rows
  })()

  const sectionFor: Partial<Record<TabId, [string, string]>> = {
    dataflow: ['Data Flow', 'How submission data moves through the delivery.'],
    tech: ['Technology Standards', 'Stack and convention rules for every repository.'],
    security: ['Security Constraints', 'Non-negotiable security rules for this delivery.'],
    deployment: ['Deployment Constraints', 'How changes reach production.'],
  }

  return (
    <section className="page-with-rail bo-compact arch-page">
      <div>
        <div className="page-head arch-head" style={{ marginBottom: '8px' }}>
          <h2>Architecture</h2>
          <span className="hint">Engineering blueprint generated from the approved plan.</span>
          {arch ? (
            <span className="arch-head-actions">
              <button className="outline" onClick={() => setShowRevise((v) => !v)}>
                <RefreshCw className="btn-ico" /> Request AI Revision
              </button>
              {accepted ? (
                <span className="chip"><span style={{ color: 'var(--green)' }}>✓</span> Accepted by {arch.accepted_by || '—'}</span>
              ) : (
                <>
                  <input type="text" placeholder="Approver name" value={approver}
                    onChange={(e) => setApprover(e.target.value)} />
                  <button
                    className="approve"
                    disabled={mandatoryFailed.length > 0}
                    title={mandatoryFailed.length ? `Blocked: ${mandatoryFailed.map((c) => c.label).join(', ')}` : undefined}
                    onClick={() => void act('/architecture/accept', { approver }, 'Architecture accepted')}
                  >
                    <CircleCheck className="btn-ico" /> Accept Architecture
                  </button>
                </>
              )}
            </span>
          ) : null}
        </div>

        {arch && stale ? (
          <div className="card bad" style={{ marginBottom: '8px' }}>
            <b>⚠ Architecture is stale.</b>{' '}
            <span className="hint">
              The locked plan changed after v{arch.version} was generated
              {stalePacks || staleWorkspaces
                ? ` — ${stalePacks} delivery pack(s) and ${staleWorkspaces} workspace(s) carry stale architecture context`
                : ''}
              . Request a revision; acceptance should wait for the refreshed version.
            </span>
            <button className="link-btn" onClick={() => goTo('delivery_packs')}>Review delivery packs</button>
          </div>
        ) : null}

        {!arch ? (
          <div className="card">
            <h3>◈ No architecture generated yet</h3>
            <p>
              The architecture pack is generated <b>after Gate 1 approval</b> locks the plan. It turns the signed
              stories into an engineering blueprint — component map, repository layout, integration contracts —
              that a human accepts before any delivery pack or workspace exists.
            </p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="primary" disabled={!phase}
                onClick={() => void act('/architecture/generate', {}, 'Architecture generated')}>
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
            <div className="card info-banner">
              <span className="ib-ico">ⓘ</span>
              <span>
                This architecture is generated from the locked plan
                {arch.plan_version ? ` (v${arch.plan_version})` : ''} after Gate 1 approval and is the shared
                context for all team delivery packs — packs reference it by version, they never copy it.
              </span>
            </div>

            <div className="card arch-strip">
              <div className="as-cell">
                <div className="as-label">Architecture Version</div>
                <div className="as-main">
                  <span className="as-value mono">{`v${arch.version}`}</span>
                  <Badge status={statusBadge} label={statusLabel} />
                </div>
                <div className="as-meta">
                  <Prov provenance={arch.provenance} />
                </div>
              </div>
              <div className="as-cell">
                <div className="as-label">Status</div>
                <div className="as-main">
                  <span className={`as-value ${accepted ? 'ok' : 'warn'}`}>{accepted ? 'READY' : 'IN REVIEW'}</span>
                </div>
                <div className="as-meta hint">{`Generated ${hhmm(arch.generated_at)}`}</div>
              </div>
              <div className="as-cell"><div className="as-label">Affected Applications</div><div className="as-main"><span className="as-value">{String(apps.size)}</span></div></div>
              <div className="as-cell"><div className="as-label">Repositories</div><div className="as-main"><span className="as-value">{String(repos.size)}</span></div></div>
              <div className="as-cell"><div className="as-label">Teams</div><div className="as-main"><span className="as-value">{String(teams.size)}</span></div></div>
              <div className="as-cell"><div className="as-label">Integration Points</div><div className="as-main"><span className="as-value">{String(integrationRows.length)}</span></div></div>
              <div className="as-cell"><div className="as-label">Dependencies</div><div className="as-main"><span className="as-value">{String(depEdges)}</span></div></div>
            </div>

            <div className="card">
              <div className="card-head"><h3>Application Landscape</h3>
                <span className="hint">Derived from the plan — applications, mapped repositories and cross-team integration only.</span>
              </div>
              <LandscapeDiagram landscape={land} />
            </div>

            <div className="card" style={{ marginTop: '8px' }}>
              <div className="arch-tabs" role="tablist">
                {TABS.map(([id, label]) => (
                  <button key={id} role="tab" aria-selected={tab === id}
                    className={`arch-tab${tab === id ? ' active' : ''}`}
                    onClick={() => setTab(id)}>
                    {label}
                  </button>
                ))}
              </div>

              {tab === 'overview' ? (
                <div className="arch-overview">
                  <div>
                    <h4>Architecture Summary</h4>
                    <p className="hint">
                      {mdSection(archMd, 'Application Landscape') || 'Loading…'}
                    </p>
                    <p className="hint">{mdSection(archMd, 'Integration Boundaries').split('\n')[0]}</p>
                  </div>
                  <div>
                    <h4>Generated From</h4>
                    <ul className="plain kv">
                      <li><span>Plan Version</span><b className="mono">{arch.plan_version ? `v${arch.plan_version} (Locked)` : '—'}</b></li>
                      <li><span>Gate 1 Approved</span><b>{gate1 ? hhmm(gate1.decided_at) : '—'}</b></li>
                      <li><span>Approved By</span><b>{plan?.signed_by ?? '—'}</b></li>
                      <li><span>Content Hash</span><b className="mono">{arch.content_hash ? `${arch.content_hash.slice(0, 12)}…` : '—'}</b></li>
                    </ul>
                  </div>
                  <div className={`next-step${accepted ? '' : ' locked'}`}>
                    <h4>Next Step: Generate Delivery Packs</h4>
                    <p className="hint">
                      {accepted
                        ? 'The architecture is accepted — delivery packs can be generated per team. Packs inherit this blueprint by reference (version-pinned), never as copies.'
                        : 'Accept the architecture to unlock per-team delivery packs. No pack is generated from an unaccepted blueprint.'}
                    </p>
                    <button className="primary" disabled={!accepted} onClick={() => goTo('delivery_packs')}>
                      Go to Delivery Packs →
                    </button>
                  </div>
                </div>
              ) : null}

              {tab === 'repos' ? (
                <div className="table-wrap">
                  <table>
                    <thead><tr><th>Team</th><th>Repository</th><th>Application</th><th>Stories</th></tr></thead>
                    <tbody>
                      {teamRows.map((r) => (
                        <tr key={`${r.team}-${r.repository}`}>
                          <td><TeamChip name={r.team} /></td>
                          <td className="mono">{r.repository || '—'}</td>
                          <td>{r.application}</td>
                          <td className="mono">{r.stories.join(', ')}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : null}

              {tab === 'dependencies' ? (
                stories.some((s) => (s.dependencies ?? []).length) ? (
                  <ul className="plain">
                    {stories.flatMap((s) =>
                      (s.dependencies ?? []).map((dep) => (
                        <li key={`${dep}-${s.story_id}`}>
                          <b className="mono">{dep}</b> → <b className="mono">{s.story_id}</b>{' '}
                          <span className="hint">{storyById.get(dep)?.title ?? ''} must land before {s.title}</span>
                        </li>
                      )),
                    )}
                  </ul>
                ) : <p className="hint">No story dependencies in this plan.</p>
              ) : null}

              {tab === 'integration' ? (
                integrationRows.length ? (
                  <ul className="plain">
                    {integrationRows.map((r, i) => (
                      <li key={i}>
                        <TeamChip name={r.from.accountable_team} compact />{' '}
                        <b className="mono">{r.from.story_id}</b> →{' '}
                        <TeamChip name={r.to.accountable_team} compact />{' '}
                        <b className="mono">{r.to.story_id}</b>{' '}
                        <span className="hint">cross-team contract — agree the interface before either side implements</span>
                      </li>
                    ))}
                  </ul>
                ) : <p className="hint">Every dependency is within a single team — no cross-team integration points.</p>
              ) : null}

              {sectionFor[tab] ? (
                <div>
                  <p className="hint" style={{ marginBottom: '6px' }}>{sectionFor[tab]![1]}</p>
                  <pre className="artifact-preview" style={{ maxHeight: '260px' }}>
                    {mdSection(archMd, sectionFor[tab]![0]) || 'Not present in architecture.md'}
                  </pre>
                </div>
              ) : null}

              {previewName ? (
                <>
                  <p className="hint" style={{ margin: '10px 0 6px' }}>
                    Rendered preview of <span className="mono">{previewName}</span> — read-only, not an editor.
                  </p>
                  <pre className="artifact-preview">{previewText}</pre>
                </>
              ) : null}
            </div>

            {showRevise ? (
              <div className="card" style={{ marginTop: '8px' }}>
                <h3>⟳ Request AI Revision</h3>
                <p className="hint">
                  Your comment goes to the generator; the pack is re-produced as a new immutable version —
                  v{arch.version} is preserved and validations re-run. Nothing is edited in place.
                </p>
                <textarea rows={3} style={{ width: '100%', marginTop: '8px' }}
                  placeholder="What should the next architecture version change?"
                  value={feedback} onChange={(e) => setFeedback(e.target.value)} />
                <div className="actions-row" style={{ marginTop: '10px' }}>
                  <button className="primary" disabled={!feedback.trim()}
                    onClick={async () => {
                      if (await act('/architecture/revise', { feedback }, 'Revision generated')) {
                        setFeedback('')
                        setShowRevise(false)
                      }
                    }}>
                    Submit Revision Request
                  </button>
                  <button className="ghost" onClick={() => setShowRevise(false)}>Cancel</button>
                </div>
              </div>
            ) : null}
          </>
        )}
      </div>

      <aside className="rail">
        {arch ? (
          <>
            <div className="card rail-card">
              <h3>Architecture Pack <Prov provenance={arch.provenance} /></h3>
              <p className="hint">Generated artifacts that form the engineering blueprint.</p>
              <ul className="plain pack-files">
                {arch.files.map((f) => {
                  const name = basename(f)
                  return (
                    <li key={f}>
                      <span className="mono pf-name">{name}</span>
                      <span className="hint pf-size">{kb(arch.file_sizes?.[name])}</span>
                      <button className="icon-btn" title={`Preview ${name}`} onClick={() => loadPreview(name)}>
                        <Eye className="btn-ico" />
                      </button>
                      <a className="icon-btn" title={`Download ${name}`} href={fileUrl(name)} download={name}>
                        <Download className="btn-ico" />
                      </a>
                    </li>
                  )
                })}
              </ul>
              <div className="actions-row" style={{ marginTop: '8px' }}>
                <button className="outline" onClick={() => window.open(`/api/runs/${runId}/architecture/download.zip`, '_blank')}>
                  <Download className="btn-ico" /> Download All
                </button>
                <button className="outline" onClick={() => loadPreview('architecture.md')}>
                  <Eye className="btn-ico" /> Preview Full Pack
                </button>
              </div>
            </div>

            <div className="card rail-card">
              <h3>Architecture Validations</h3>
              <p className="hint">Automated deterministic checks on the generated architecture — not AI judgment.</p>
              <ul className="plain val-list">
                {checks.map((c) => (
                  <li key={c.check_id} title={c.detail}>
                    {c.result === 'passed' ? <CircleCheck className="val-ico ok" />
                      : c.result === 'warning' ? <TriangleAlert className="val-ico warn" />
                      : <CircleAlert className="val-ico bad" />}
                    <span className="val-label">{c.label}</span>
                    <span className={`sev-chip ${c.result === 'passed' ? 'medium ok-chip' : c.result === 'warning' ? 'medium' : 'critical'}`}>
                      {c.result === 'passed' ? 'Passed' : c.result === 'warning' ? 'Warning' : 'Failed'}
                    </span>
                  </li>
                ))}
              </ul>
              {mandatoryFailed.length ? (
                <p className="hint" style={{ color: 'var(--red-dark)' }}>
                  Acceptance is blocked until every mandatory check passes.
                </p>
              ) : null}
            </div>
          </>
        ) : null}
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>
    </section>
  )
}
