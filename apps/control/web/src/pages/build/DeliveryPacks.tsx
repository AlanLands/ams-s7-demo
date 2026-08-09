/**
 * Delivery Packs — the bridge between approved S7 engineering context and
 * human-controlled developer workspaces. S7 generates and publishes governed
 * context only; implementation happens in the developer's own IDE/CLI/Git.
 *
 * Honesty: every simulated publication is badged SIMULATED and never labelled
 * "Synced to Git"; counts and sizes come from the artifact store via state;
 * publication display states are a mapping over the stored statuses plus the
 * staleness ledger — nothing invented is persisted.
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Archive, BookOpen, Boxes, CircleCheck, CircleCheckBig, CloudUpload, Download,
  Eye, FileCog, FileJson, FlaskConical, Github, GitBranch, Info, Layers3,
  ListChecks, LoaderCircle, MonitorCog, RefreshCw, RotateCcw, Search,
  ShieldCheck, SquareCheckBig, TriangleAlert, Undo2, UsersRound,
} from 'lucide-react'
import { useRun } from '../../state/RunContext'
import { Modal } from '../../components/Modal'
import { StatCard } from '../../components/StatCard'
import { Prov } from '../../components/Badge'
import type { DeliveryPack, GitPublication, PlanStory } from '../../types'
import { buildOf, CONTROL_PLANE_GUIDANCE, GuidanceCard, hhmm, phaseAtLeast } from './buildHelpers'

/** Stated derivation: repository category from its name suffix. */
function repoCategory(repo: string): string {
  if (repo.endsWith('-db')) return 'data store'
  if (repo.endsWith('-tests')) return 'automation'
  if (repo.endsWith('-platform')) return 'platform'
  if (repo.endsWith('-portal')) return 'web'
  if (repo.endsWith('-api')) return 'microservices'
  return 'service'
}

/** Per-team pastel avatar class — stable hash over the team name. */
function teamTone(team: string): string {
  let h = 0
  for (const c of team) h = (h * 31 + c.charCodeAt(0)) % 997
  return `tc-${h % 5}`
}

function TeamAvatar({ team }: { team: string }) {
  const initials = team.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  return <span className={`team-avatar ${teamTone(team)}`}>{initials}</span>
}

function kb(bytes?: number): string {
  if (bytes == null) return '—'
  return bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(1)} MB` : `${Math.round(bytes / 1024)} KB`
}

function dmy(iso?: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleDateString([], { day: '2-digit', month: 'short', year: 'numeric' })
}

type PubDisplay = { cls: string; label: string; sub: string }

/** Display mapping over stored status + staleness — see spec: no invented
 * enum is persisted; PUBLISHING is a transient client-side state. */
function pubDisplay(pack: DeliveryPack, pub: GitPublication | undefined, stale: boolean): PubDisplay {
  if (pack.publication_status === 'published') {
    if (stale) return { cls: 'st-stale', label: 'OUT OF DATE', sub: 'Pack changed since publish' }
    if ((pack.published_version ?? 0) < pack.version) {
      return {
        cls: 'st-planned',
        label: 'UPDATE PENDING',
        sub: `v${pack.published_version} on branch — publish v${pack.version} to sync assignments`,
      }
    }
    return {
      cls: 'st-passed',
      label: 'PUBLISHED',
      sub: pub?.simulated ? 'Simulated — no git touched' : 'Synced to Git',
    }
  }
  if (pack.publication_status === 'failed') return { cls: 'st-blocked', label: 'FAILED', sub: 'See publication record' }
  return { cls: 'st-planned', label: 'READY TO PUBLISH', sub: 'Not published' }
}

const PREVIEW_TABS = [
  ['overview', 'Overview'],
  ['stories', 'Stories'],
  ['tasks', 'Tasks'],
  ['dependencies', 'Dependencies'],
  ['teststrategy', 'Test Strategy'],
  ['manifest', 'Manifest'],
  ['agents', 'AGENTS.md'],
] as const
type PreviewTab = (typeof PREVIEW_TABS)[number][0]

const TAB_FILES: Partial<Record<PreviewTab, string>> = {
  dependencies: 'team-dependencies.json',
  teststrategy: 'test-strategy.md',
  manifest: 'workspace-manifest.json',
  agents: 'AGENTS.md',
}

export function DeliveryPacks() {
  const { data, runId, act, goTo } = useRun()

  const build = buildOf(data)
  const packs = build.delivery_packs ?? []
  const publications = build.publications ?? []
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const arch = build.architecture
  const phase = build.phase

  const [selected, setSelected] = useState<string | null>(null)
  const [query, setQuery] = useState('')
  const [fArtifact, setFArtifact] = useState('all')
  const [fPub, setFPub] = useState('all')
  const [fTeam, setFTeam] = useState('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [publishing, setPublishing] = useState<Set<string>>(new Set())
  const [generating, setGenerating] = useState(false)
  const [confirmPublish, setConfirmPublish] = useState<string | null>(null)
  const [confirmAll, setConfirmAll] = useState(false)
  const [successFor, setSuccessFor] = useState<string | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [previewTab, setPreviewTab] = useState<PreviewTab>('overview')
  const [tabText, setTabText] = useState('')

  const storyById = useMemo(() => new Map(stories.map((s) => [s.story_id, s])), [stories])
  const staleIds = useMemo(() => new Set((data?.staleness ?? []).map((s) => s.artifact_id)), [data])
  const pubFor = (packId: string): GitPublication | undefined =>
    [...publications].reverse().find((p) => p.delivery_pack_id === packId)

  const selectedPack = packs.find((p) => p.delivery_pack_id === selected) ?? packs[0] ?? null
  const previewPack = packs.find((p) => p.delivery_pack_id === preview) ?? null
  const previewSlug = previewPack?.team_slug
  const tabFile = TAB_FILES[previewTab]

  useEffect(() => {
    if (!runId || !previewSlug || !tabFile) return
    setTabText('Loading…')
    fetch(`/api/runs/${runId}/artifact-file/build/packs/${previewSlug}/${tabFile}`)
      .then((r) => (r.ok ? r.text() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then(setTabText)
      .catch((err: Error) => setTabText(`Could not load ${tabFile}: ${err.message}`))
  }, [runId, previewSlug, tabFile])

  if (!data) return null

  // --- derived ---------------------------------------------------------------
  const teams = [...new Set(packs.map((p) => p.team))]
  const storiesCovered = packs.reduce((n, p) => n + p.story_ids.length, 0)
  const artifactsLinked = packs.reduce((n, p) => n + (p.artifact_count ?? 0), 0)
  const totalBytes = packs.reduce((n, p) => n + (p.size_bytes ?? 0), 0)
  const publishErrors = packs.filter((p) => p.publication_status === 'failed').length
  const readyPacks = packs.filter(
    (p) => p.publication_status !== 'published' || (p.published_version ?? 0) < p.version,
  )
  const canGenerate = phaseAtLeast(phase, 'architecture_accepted')
  const allStories = stories.length

  const packState = (p: DeliveryPack) => ({
    stale: staleIds.has(p.delivery_pack_id),
    pub: pubFor(p.delivery_pack_id),
    published: p.publication_status === 'published',
  })

  const filtered = packs.filter((p) => {
    const { stale, published } = packState(p)
    if (fTeam !== 'all' && p.team !== fTeam) return false
    if (fArtifact === 'current' && stale) return false
    if (fArtifact === 'stale' && !stale) return false
    if (fPub === 'ready' && (published || p.publication_status === 'failed')) return false
    if (fPub === 'published' && !published) return false
    if (fPub === 'failed' && p.publication_status !== 'failed') return false
    if (fPub === 'out_of_date' && !(published && stale)) return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      const hay = `${p.team} ${p.repository} ${p.story_ids.join(' ')}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })

  const packAcs = (p: DeliveryPack) =>
    p.story_ids.reduce((m, id) => m + (storyById.get(id)?.acceptance_criteria ?? []).length, 0)
  const packDeps = (p: DeliveryPack) =>
    p.story_ids.reduce((m, id) => m + (storyById.get(id)?.dependencies ?? []).length, 0)
  const branchFor = (p: DeliveryPack) => `s7/${(runId ?? '').toLowerCase()}-${p.team_slug}`

  const doPublish = async (p: DeliveryPack) => {
    setConfirmPublish(null)
    setPublishing((s) => new Set(s).add(p.delivery_pack_id))
    const ok = await act(`/delivery-packs/${p.delivery_pack_id}/publish`, {}, `${p.team} pack published`)
    setPublishing((s) => {
      const next = new Set(s)
      next.delete(p.delivery_pack_id)
      return next
    })
    if (ok) setSuccessFor(p.delivery_pack_id)
  }

  const doGenerate = async () => {
    setGenerating(true)
    await act('/delivery-packs/generate', {}, 'Delivery packs generated')
    setGenerating(false)
  }

  const successPack = packs.find((p) => p.delivery_pack_id === successFor) ?? null
  const successPub = successFor ? pubFor(successFor) : undefined

  // --- empty states ----------------------------------------------------------
  if (packs.length === 0) {
    return (
      <section className="page-with-rail bo-compact">
        <div>
          <div className="page-head" style={{ marginBottom: '8px' }}>
            <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Delivery Packs</span>
          </div>
          <div className="page-head" style={{ marginBottom: '10px' }}>
            <h2>Delivery Packs</h2>
            <span className="hint">Governed engineering context generated for each team and ready to publish or download.</span>
          </div>
          <div className="card">
            <h3><Boxes className="btn-ico" /> No Delivery Packs Yet</h3>
            {canGenerate ? (
              <>
                <p>
                  Architecture {arch ? `v${arch.version}` : ''} is accepted. Delivery packs are generated
                  <b> per team</b>: each team receives its stories, acceptance criteria, dependencies,
                  engineering rules and workspace manifest as one governed, versioned package that
                  references the canonical architecture — never a copy of it.
                </p>
                <div className="actions-row" style={{ marginTop: '12px' }}>
                  <button className="primary" disabled={generating} onClick={() => void doGenerate()}>
                    {generating ? <LoaderCircle className="btn-ico spin" /> : null}
                    {generating ? 'Generating…' : '✦ Generate Delivery Packs'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <p>Architecture approval is required before team delivery packs can be generated.</p>
                <div className="actions-row" style={{ marginTop: '12px' }}>
                  <button className="outline" onClick={() => goTo('architecture')}>View Architecture</button>
                </div>
              </>
            )}
          </div>
        </div>
        <aside className="rail">
          <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
        </aside>
      </section>
    )
  }

  return (
    <section className="page-with-rail bo-compact dp-page">
      <div>
        <div className="page-head" style={{ marginBottom: '4px' }}>
          <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Delivery Packs</span>
        </div>
        <div className="page-head" style={{ marginBottom: '10px' }}>
          <h2>Delivery Packs</h2>
          <span className="hint">Governed engineering context generated for each team and ready to publish or download.</span>
          <span className="arch-head-actions">
            <button
              className="outline"
              onClick={() => window.open(`/api/runs/${runId}/delivery-packs/download-all.zip`, '_blank')}
            >
              <Download className="btn-ico" /> Download All Packs
            </button>
            <button
              className="primary"
              disabled={readyPacks.length === 0}
              onClick={() => setConfirmAll(true)}
            >
              <CloudUpload className="btn-ico" /> Publish All Packs to Git
            </button>
          </span>
        </div>

        <div className="stat-row">
          <StatCard accent="purple" icon={<UsersRound />} value={String(teams.length)} label="Teams" sub="All teams covered" />
          <StatCard accent="blue" icon={<Boxes />} value={String(packs.length)} label="Delivery Packs" sub={readyPacks.length ? `${readyPacks.length} ready to publish` : 'All published'} />
          <StatCard accent="green" icon={<ShieldCheck />} value={String(storiesCovered)} label="Stories Covered" sub={allStories ? `${Math.round((storiesCovered / allStories) * 100)}% of scoped stories` : '—'} />
          <StatCard accent="orange" icon={<Layers3 />} value={String(artifactsLinked)} label="Artifacts Linked" sub="Across all packs" />
          <StatCard accent="teal" icon={<Archive />} value={kb(totalBytes)} label="Total Pack Size" sub="Uncompressed" />
          <StatCard accent={publishErrors ? 'red' : 'green'} icon={<CircleCheck />} value={String(publishErrors)} label="Publish Errors" sub={publishErrors ? 'Needs attention' : 'All good'} />
        </div>

        <div className="card dp-filters">
          <span className="dp-search">
            <Search className="dp-search-ico" />
            <input
              type="text"
              placeholder="Search by team, repository or stories…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </span>
          <label className="dp-filter">
            <span>Artifact Status</span>
            <select value={fArtifact} onChange={(e) => setFArtifact(e.target.value)}>
              <option value="all">All</option>
              <option value="current">Current</option>
              <option value="stale">Stale</option>
            </select>
          </label>
          <label className="dp-filter">
            <span>Publication Status</span>
            <select value={fPub} onChange={(e) => setFPub(e.target.value)}>
              <option value="all">All</option>
              <option value="ready">Ready to Publish</option>
              <option value="published">Published</option>
              <option value="failed">Failed</option>
              <option value="out_of_date">Out of Date</option>
            </select>
          </label>
          <label className="dp-filter">
            <span>Team</span>
            <select value={fTeam} onChange={(e) => setFTeam(e.target.value)}>
              <option value="all">All</option>
              {teams.map((t) => <option key={t} value={t}>{t}</option>)}
            </select>
          </label>
          <button
            className="ghost"
            onClick={() => { setQuery(''); setFArtifact('all'); setFPub('all'); setFTeam('all') }}
          >
            <RotateCcw className="btn-ico" /> Reset
          </button>
        </div>

        <div className="card">
          <div className="table-wrap">
            <table className="dp-table">
              <thead>
                <tr>
                  <th>Team</th>
                  <th>Stories</th>
                  <th>Repository</th>
                  <th>Pack Version</th>
                  <th>Artifact Status</th>
                  <th>Publication Status</th>
                  <th>Last Updated</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((p) => {
                  const { stale, pub, published } = packState(p)
                  const pd = pubDisplay(p, pub, stale)
                  const busy = publishing.has(p.delivery_pack_id)
                  const isSelected = selectedPack?.delivery_pack_id === p.delivery_pack_id
                  const isExpanded = expanded.has(p.delivery_pack_id)
                  const shown = isExpanded ? p.story_ids : p.story_ids.slice(0, 2)
                  const hidden = p.story_ids.length - shown.length
                  const when = p.published_at || p.created_at
                  return (
                    <tr
                      key={p.delivery_pack_id}
                      className={isSelected ? 'dp-row-selected' : ''}
                      onClick={() => setSelected(p.delivery_pack_id)}
                    >
                      <td>
                        <span className="dp-team">
                          <TeamAvatar team={p.team} />
                          <span>
                            <b>{p.team}</b>
                            <span className="hint dp-sub">{`${p.story_ids.length} ${p.story_ids.length === 1 ? 'story' : 'stories'}`}</span>
                          </span>
                        </span>
                      </td>
                      <td>
                        <span className="mono dp-stories">{shown.join(', ')}</span>
                        {hidden > 0 ? (
                          <button
                            className="link-btn"
                            onClick={(e) => {
                              e.stopPropagation()
                              setExpanded((s) => new Set(s).add(p.delivery_pack_id))
                            }}
                          >
                            {` +${hidden} more`}
                          </button>
                        ) : null}
                      </td>
                      <td>
                        <span className="repo-cell"><Github /><span className="mono">{p.repository || '—'}</span></span>
                        <span className="hint dp-sub">{p.repository ? repoCategory(p.repository) : ''}</span>
                      </td>
                      <td>
                        <span className="mono">{`v${p.version}.0`}</span>
                        <span
                          className="hint dp-sub"
                          title={`Generated from architecture v${p.architecture_version}, plan v${p.plan_version}`}
                        >
                          <Info className="dp-info-ico" />{` arch v${p.architecture_version}`}
                        </span>
                      </td>
                      <td>
                        {stale
                          ? <span className="badge st-stale"><TriangleAlert className="dp-badge-ico" />STALE</span>
                          : <span className="badge st-ready">CURRENT</span>}
                        <span className="hint dp-sub">{`${p.artifact_count ?? '—'} artifacts`}</span>
                      </td>
                      <td>
                        {busy
                          ? <span className="badge st-in_progress"><LoaderCircle className="dp-badge-ico spin" />PUBLISHING</span>
                          : <span className={`badge ${pd.cls}`}>{pd.label}</span>}
                        <span className="hint dp-sub">
                          {busy ? 'Publishing…' : pd.sub}
                          {published && pub?.simulated ? <> <Prov provenance="simulated" /></> : null}
                        </span>
                      </td>
                      <td>
                        <span>{dmy(when)}</span>
                        <span className="hint dp-sub">{hhmm(when)}</span>
                      </td>
                      <td onClick={(e) => e.stopPropagation()}>
                        <div className="dp-actions">
                          <button
                            className="outline dp-act"
                            onClick={() => { setSelected(p.delivery_pack_id); setPreview(p.delivery_pack_id); setPreviewTab('overview') }}
                          >
                            <Eye className="btn-ico" /> Preview
                          </button>
                          <button
                            className="icon-btn"
                            aria-label={`Download ${p.team} pack ZIP`}
                            title="Download ZIP"
                            onClick={() => window.open(`/api/runs/${runId}/delivery-packs/${p.delivery_pack_id}/download.zip`, '_blank')}
                          >
                            <Download className="btn-ico" />
                          </button>
                          <button
                            className="icon-btn dp-publish-ico"
                            aria-label={published ? `Republish ${p.team} pack` : `Publish ${p.team} pack to Git`}
                            title={published ? 'Republish / Sync Pack' : 'Publish to Git'}
                            disabled={busy || stale}
                            onClick={() => setConfirmPublish(p.delivery_pack_id)}
                          >
                            {busy ? <LoaderCircle className="btn-ico spin" /> : published ? <RefreshCw className="btn-ico" /> : <CloudUpload className="btn-ico" />}
                          </button>
                        </div>
                        {stale ? <span className="hint dp-sub">Refresh via amendment first</span> : null}
                      </td>
                    </tr>
                  )
                })}
                {filtered.length === 0 ? (
                  <tr><td colSpan={8}><span className="hint">No packs match the current filters.</span></td></tr>
                ) : null}
              </tbody>
            </table>
          </div>
          <div className="dp-table-foot hint">{`Showing ${filtered.length} of ${packs.length} packs`}</div>
        </div>

        <div className="card info-banner" style={{ marginTop: '10px' }}>
          <Info className="btn-ico" style={{ marginTop: '1px' }} />
          <span>
            Delivery packs contain governed engineering context only. Actual implementation is performed by
            human developers using their IDE, CLI and Git workflows.
          </span>
        </div>
      </div>

      <aside className="rail">
        {selectedPack ? (() => {
          const { stale, pub, published } = packState(selectedPack)
          const pd = pubDisplay(selectedPack, pub, stale)
          const busy = publishing.has(selectedPack.delivery_pack_id)
          const contents: [ReactIcon, string, string][] = [
            [Layers3, 'Architecture Reference', `v${selectedPack.architecture_version} (by reference)`],
            [BookOpen, 'AGENTS.md (Team Guidance)', '1'],
            [BookOpen, 'Stories', String(selectedPack.story_ids.length)],
            [ListChecks, 'Acceptance Criteria', String(packAcs(selectedPack))],
            [SquareCheckBig, 'Task Packs', String(selectedPack.task_ids.length)],
            [GitBranch, 'Dependencies', String(packDeps(selectedPack))],
            [FlaskConical, 'Test Strategy', '1'],
            [FileCog, 'Engineering Rules', 'shared'],
            [Undo2, 'Rollback Guidance', '1'],
            [FileJson, 'Workspace Manifest', '1'],
          ]
          return (
            <div className="card rail-card dp-inspector">
              <h3>Selected Pack</h3>
              <div className="dp-ins-title">
                <b>{`${selectedPack.team} Delivery Pack`}</b>
                <span className="chip mono">{`v${selectedPack.version}.0`}</span>
              </div>
              <div className="dp-ins-block">
                <span className="as-label">Repository</span>
                <span className="repo-cell"><Github /><span className="mono">{selectedPack.repository || '—'}</span></span>
              </div>
              <div className="dp-ins-block">
                <span className="as-label">Publication Status</span>
                <span>
                  {busy
                    ? <span className="badge st-in_progress"><LoaderCircle className="dp-badge-ico spin" />PUBLISHING</span>
                    : <span className={`badge ${pd.cls}`}>{pd.label}</span>}{' '}
                  <span className="hint">{busy ? '' : pd.sub}</span>
                  {published && pub?.simulated ? <> <Prov provenance="simulated" /></> : null}
                </span>
              </div>
              <div className="dp-ins-metrics">
                <span><span className="as-label">Artifacts</span><b>{String(selectedPack.artifact_count ?? '—')}</b></span>
                <span><span className="as-label">Size</span><b>{kb(selectedPack.size_bytes)}</b></span>
              </div>
              <div className="dp-ins-block">
                <span className="as-label">Stories Included</span>
                <span className="dp-chips">
                  {selectedPack.story_ids.map((id) => <span key={id} className="chip mono">{id}</span>)}
                </span>
              </div>
              <div className="dp-ins-block">
                <span className="as-label">Pack Contents</span>
                <ul className="plain dp-contents">
                  {contents.map(([IconC, label, count]) => (
                    <li key={label}>
                      <CircleCheck className="val-ico ok" />
                      <IconC className="dp-content-ico" />
                      <span className="val-label">{label}</span>
                      <span className="hint mono">{count}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="dp-ins-actions">
                <button className="outline block" onClick={() => { setPreview(selectedPack.delivery_pack_id); setPreviewTab('overview') }}>
                  <Eye className="btn-ico" /> Preview Pack
                </button>
                <button
                  className="outline block"
                  onClick={() => window.open(`/api/runs/${runId}/delivery-packs/${selectedPack.delivery_pack_id}/download.zip`, '_blank')}
                >
                  <Download className="btn-ico" /> Download ZIP
                </button>
                <button
                  className="primary block"
                  disabled={busy || stale}
                  onClick={() => setConfirmPublish(selectedPack.delivery_pack_id)}
                >
                  {busy ? <LoaderCircle className="btn-ico spin" /> : <CloudUpload className="btn-ico" />}
                  {published ? ' Republish to Git' : ' Publish to Git'}
                </button>
                {stale ? <p className="hint">Pack is stale — refresh through the amendment process before publishing.</p> : null}
              </div>
            </div>
          )
        })() : null}
        <GuidanceCard lines={CONTROL_PLANE_GUIDANCE} />
      </aside>

      {/* --- Publish confirm ---------------------------------------------- */}
      {confirmPublish ? (() => {
        const p = packs.find((x) => x.delivery_pack_id === confirmPublish)
        if (!p) return null
        return (
          <Modal title="Publish Delivery Pack to Git" onClose={() => setConfirmPublish(null)}>
            <div className="kv">
              <b>Team</b><span>{p.team}</span>
              <b>Repository</b><span className="mono">{p.repository || '—'}</span>
              <b>Branch</b><span className="mono">{branchFor(p)}</span>
              <b>Pack Version</b><span className="mono">{`v${p.version}.0`}</span>
              <b>Artifacts to Publish</b><span>{`${p.artifact_count ?? '—'} managed files`}</span>
              <b>Managed Paths</b><span className="mono">AGENTS.md · .s7/**</span>
            </div>
            <p className="hint dp-safe-note">
              <ShieldCheck className="btn-ico" style={{ color: 'var(--green)' }} />
              Only S7-managed context files will be changed. Developer source files will not be modified.
              Publication targets a fresh branch — never the default branch — and nothing is merged for you.
            </p>
            {data.run.mode !== 'live' ? (
              <p className="hint">
                <Prov provenance="simulated" /> This run is in simulation: publish records a deterministic
                pseudo-commit and touches no real git repository.
              </p>
            ) : null}
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="ghost" onClick={() => setConfirmPublish(null)}>Cancel</button>
              <button className="primary" onClick={() => void doPublish(p)}>
                <CloudUpload className="btn-ico" /> Publish to Git
              </button>
            </div>
          </Modal>
        )
      })() : null}

      {/* --- Publish success ---------------------------------------------- */}
      {successPack && successPub ? (
        <Modal title="Published Successfully" onClose={() => setSuccessFor(null)}>
          <p style={{ marginBottom: '8px' }}>
            <CircleCheckBig style={{ color: 'var(--green)', width: 22, height: 22, verticalAlign: '-5px' }} />{' '}
            <b>{`${successPack.team} pack published`}</b>{' '}
            {successPub.simulated ? <Prov provenance="simulated" /> : null}
          </p>
          <div className="kv">
            <b>Repository</b><span className="mono">{successPub.repository}</span>
            <b>Branch</b><span className="mono">{successPub.branch}</span>
            <b>Commit</b><span className="mono">{(successPub.commit || '').slice(0, 7) || '—'}</span>
            <b>Pack Version</b><span className="mono">{`v${successPack.version}.0`}</span>
            <b>Artifacts Published</b><span>{String((successPub.published_paths ?? []).length)}</span>
            <b>Published At</b><span>{`${dmy(successPub.published_at)}, ${hhmm(successPub.published_at)}`}</span>
          </div>
          {successPub.simulated ? (
            <p className="hint" style={{ marginTop: '8px' }}>
              Simulated publication — no git repository was touched; the record above is the deterministic
              demo engine's pseudo-commit.
            </p>
          ) : null}
          <div className="actions-row" style={{ marginTop: '12px' }}>
            <button className="outline" disabled={successPub.simulated} title={successPub.simulated ? 'No real repository in simulation' : undefined}>
              <Github className="btn-ico" /> View Repository
            </button>
            <button className="primary" onClick={() => { setSuccessFor(null); goTo('developer_workspaces') }}>
              <MonitorCog className="btn-ico" /> Open Developer Workspace
            </button>
          </div>
        </Modal>
      ) : null}

      {/* --- Publish all confirm ------------------------------------------ */}
      {confirmAll ? (
        <Modal title="Publish Ready Delivery Packs" onClose={() => setConfirmAll(false)}>
          <p className="hint">
            {`${packs.length} packs total · ${packs.length - readyPacks.length} already published · ${readyPacks.length} ready to publish`}
          </p>
          <ul className="plain" style={{ margin: '8px 0' }}>
            {packs.map((p) => (
              <li key={p.delivery_pack_id} className="dp-all-row">
                <TeamAvatar team={p.team} /> {p.team}
                <span className={`badge ${p.publication_status === 'published' ? 'st-passed' : 'st-planned'}`} style={{ marginLeft: 'auto' }}>
                  {p.publication_status === 'published' ? 'PUBLISHED' : 'READY'}
                </span>
              </li>
            ))}
          </ul>
          <div className="actions-row">
            <button className="ghost" onClick={() => setConfirmAll(false)}>Cancel</button>
            <button
              className="primary"
              onClick={async () => {
                setConfirmAll(false)
                setPublishing(new Set(readyPacks.map((p) => p.delivery_pack_id)))
                await act('/delivery-packs/publish-all', {}, 'All ready packs published')
                setPublishing(new Set())
              }}
            >
              <CloudUpload className="btn-ico" /> {`Publish ${readyPacks.length} Pack${readyPacks.length === 1 ? '' : 's'}`}
            </button>
          </div>
        </Modal>
      ) : null}

      {/* --- Preview modal ------------------------------------------------- */}
      {previewPack ? (
        <Modal title={`${previewPack.team} Delivery Pack — v${previewPack.version}.0`} wide onClose={() => setPreview(null)}>
          <div className="arch-tabs" role="tablist">
            {PREVIEW_TABS.map(([id, label]) => (
              <button key={id} role="tab" aria-selected={previewTab === id}
                className={`arch-tab${previewTab === id ? ' active' : ''}`}
                onClick={() => setPreviewTab(id)}>
                {label}
              </button>
            ))}
          </div>

          {previewTab === 'overview' ? (
            <div className="kv">
              <b>Team</b><span>{previewPack.team}</span>
              <b>Repository</b><span className="mono">{previewPack.repository || '—'}</span>
              <b>Pack Version</b><span className="mono">{`v${previewPack.version}.0`}</span>
              <b>Architecture Version</b><span className="mono">{`v${previewPack.architecture_version} (by reference)`}</span>
              <b>Plan Version</b><span className="mono">{`v${previewPack.plan_version}`}</span>
              <b>Artifact Status</b>
              <span>{staleIds.has(previewPack.delivery_pack_id)
                ? <span className="badge st-stale">STALE</span>
                : <span className="badge st-ready">CURRENT</span>}</span>
              <b>Artifacts</b><span>{`${previewPack.artifact_count ?? '—'} files · ${kb(previewPack.size_bytes)}`}</span>
              <b>Generated At</b><span>{`${dmy(previewPack.created_at)}, ${hhmm(previewPack.created_at)}`}</span>
              <b>Generated From</b><span>Approved Gate 1 plan</span>
              <b>Provenance</b><span><Prov provenance={previewPack.provenance} /></span>
            </div>
          ) : null}

          {previewTab === 'stories' ? (
            <div className="dp-story-cards">
              {previewPack.story_ids.map((id) => {
                const s = storyById.get(id)
                return (
                  <div className="card dp-story-card" key={id}>
                    <b className="mono">{id}</b> <b>{s?.title ?? ''}</b>
                    <p className="hint clamp-2">{s?.purpose ?? ''}</p>
                    <p className="hint">
                      {`${(s?.acceptance_criteria ?? []).length} acceptance criteria · ${(s?.dependencies ?? []).length} dependencies · ${s?.target_component || '—'}`}
                    </p>
                  </div>
                )
              })}
            </div>
          ) : null}

          {previewTab === 'tasks' ? (
            <div>
              {previewPack.task_ids.length === 0 ? <p className="hint">No tasks in this pack.</p> : null}
              {previewPack.task_ids.map((id) => (
                <div className="card dp-story-card" key={id}>
                  <b className="mono">{id}</b>
                  <p className="hint">
                    Artifacts: <span className="mono">task.md · context.json · test-plan.md · task-evidence.json</span>
                  </p>
                  <p className="hint">
                    {`Inherited by reference: architecture v${previewPack.architecture_version} · plan v${previewPack.plan_version} · ${previewPack.team} pack v${previewPack.version}`}
                  </p>
                </div>
              ))}
              <p className="hint">Task packs are thin — canonical artifacts are referenced by version, never duplicated.</p>
            </div>
          ) : null}

          {tabFile ? (
            <pre className="artifact-preview" style={{ maxHeight: '52vh' }}>{tabText}</pre>
          ) : null}
        </Modal>
      ) : null}
    </section>
  )
}

type ReactIcon = typeof CircleCheck
