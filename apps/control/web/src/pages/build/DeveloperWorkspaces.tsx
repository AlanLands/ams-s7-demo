/**
 * Developer Workspaces — the registry of governed engineering context S7 has
 * published per team/story, and the evidence it collected back. Developers
 * implement in their own IDE, CLI and Git; S7 observes, never controls. No
 * code editor, terminal or coding chat exists on this surface.
 *
 * The "simulated developer activity" controls exist because this is a demo:
 * the deterministic engine plays the developer's part and everything it
 * produces is badged SIMULATED. AI never autonomously implements here.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity as ActivityIcon, BadgeCheck, ChevronDown, ChevronRight, CircleAlert,
  CircleCheck, Circle, CircleX, ClipboardCheck, Code2, ExternalLink, Eye,
  FileText, FlaskConical, GitBranch, GitCommitHorizontal, GitFork,
  GitPullRequest, Github, Info, Layers3, ListChecks, LoaderCircle, MonitorCog,
  PackageCheck, PackageOpen, RotateCcw, Search, ShieldCheck, Sparkles,
  TriangleAlert, UserCheck, UserPlus, UsersRound, Workflow,
} from 'lucide-react'
import { useRun } from '../../state/RunContext'
import { Prov } from '../../components/Badge'
import { Modal } from '../../components/Modal'
import { StatCard } from '../../components/StatCard'
import { apiPatch, apiPost } from '../../api'
import type { ActivityEvent, BuildTask, DeliveryPack, DeveloperWorkspace, PlanStory } from '../../types'
import {
  buildOf,
  CONTROL_PLANE_GUIDANCE,
  DEV_STATUS_BADGE,
  DEV_STATUS_LABELS,
  githubLinks,
  GuidanceCard,
  hhmm,
  relTime,
  selectStory,
} from './buildHelpers'

function DevBadge({ status }: { status: string }) {
  return (
    <span className={`badge ${DEV_STATUS_BADGE[status] ?? 'st-planned'}`}>
      {DEV_STATUS_LABELS[status] ?? status.replaceAll('_', ' ')}
    </span>
  )
}

function CiCell({ ws, task }: { ws: DeveloperWorkspace; task?: BuildTask }) {
  const tests = task?.tests ?? []
  const passed = tests.filter((t) => t.current_result === 'passed').length
  const sub = ws.ci_evidence && ws.ci_tests_total != null
    ? `${ws.ci_tests_passed ?? 0} / ${ws.ci_tests_total} tests (real)`
    : tests.length ? `${passed} / ${tests.length} tests` : ''
  if (!ws.ci_status) {
    return (
      <>
        <span className="cell-status cs-idle"><Circle />Not Started</span>
        {sub ? <span className="hint dp-sub">{sub}</span> : null}
      </>
    )
  }
  if (ws.ci_status === 'running') {
    return (
      <>
        <span className="cell-status cs-run"><LoaderCircle className="spin" />Running</span>
        {sub ? <span className="hint dp-sub">{sub}</span> : null}
      </>
    )
  }
  if (ws.ci_status === 'passed') {
    return (
      <>
        <span className="cell-status cs-ok"><CircleCheck />Passed</span>
        {sub ? <span className="hint dp-sub">{sub}</span> : null}
      </>
    )
  }
  return (
    <>
      <span className="cell-status cs-bad"><CircleX />Failed</span>
      {sub ? <span className="hint dp-sub">{sub}</span> : null}
    </>
  )
}

function DevAvatar({ name }: { name: string }) {
  const initials = name.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
  return <span className="team-avatar tc-3">{initials}</span>
}

const ACTIVITY_ICONS: [RegExp, typeof UserCheck][] = [
  [/assign/i, UserCheck],
  [/review/i, ShieldCheck],
  [/test/i, FlaskConical],
  [/ci|pipeline|verif/i, Workflow],
  [/pull|pr\b/i, GitPullRequest],
  [/commit|develop|start/i, GitCommitHorizontal],
]

function activityIcon(ev: ActivityEvent): typeof UserCheck {
  const hay = `${ev.workflow ?? ''} ${ev.details ?? ''} ${ev.outcome ?? ''}`
  return ACTIVITY_ICONS.find(([re]) => re.test(hay))?.[1] ?? ActivityIcon
}

/** Expandable drawer section with a count chip, mockup-style. */
function Section({ icon: IconC, title, count, children, defaultOpen }: {
  icon: typeof Layers3
  title: string
  count?: string
  children: React.ReactNode
  defaultOpen?: boolean
}) {
  const [open, setOpen] = useState(Boolean(defaultOpen))
  return (
    <div className="dw-section">
      <button type="button" className="dw-section-head" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <IconC className="dw-section-ico" />
        <span>{title}</span>
        {count != null ? <span className="hint mono">{count}</span> : null}
        {open ? <ChevronDown className="dw-chev" /> : <ChevronRight className="dw-chev" />}
      </button>
      {open ? <div className="dw-section-body">{children}</div> : null}
    </div>
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
  const { data, act, goTo } = useRun()
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
  const deps = story?.dependencies ?? []
  const summaryRows = buildOf(data).summary?.stories ?? []
  const depState = (depId: string): string => {
    const row = summaryRows.find((r) => r.story_id === depId)
    if (!row) return 'PENDING'
    if (row.overall === 'blocked') return 'BLOCKED'
    if (row.overall === 'complete' || row.overall === 'ready_for_quality') return 'AVAILABLE'
    return 'IN PROGRESS'
  }
  const evidenced = new Set(tests.map((t) => t.ac_id))
  const simulated = data?.run.mode !== 'live'
  const links = githubLinks(ws, data?.intake?.repos)
  const activity = (data?.activity ?? [])
    .filter((a) => a.artifact === task?.task_id || (a.details ?? '').includes(ws.story_id))
    .slice(-6)
    .reverse()
  const stale = ws.artifact_status === 'stale'
  const correction = task?.status === 'blocked'

  return (
    <div
      className={`drawer-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) requestClose() }}
    >
      <aside className="drawer story-drawer dw-drawer" role="dialog" aria-label={`${ws.story_id} workspace`}>
        <div className="card-head">
          <h3><span className="mono">{ws.story_id}</span>{' — Developer Workspace'}</h3>
          <button type="button" className="kebab" onClick={requestClose} aria-label="Close">✕</button>
        </div>
        {story?.title ? <p className="hint" style={{ marginBottom: '6px' }}>{story.title}</p> : null}

        <div className="drawer-badges">
          <span className="chip own-human"><UserCheck className="dp-badge-ico" />Human Controlled</span>
          <span className="chip own-ai"><Sparkles className="dp-badge-ico" />AI Assisted</span>
          <span className="hint">Artifact:</span>
          {stale
            ? <span className="badge st-stale"><TriangleAlert className="dp-badge-ico" />STALE</span>
            : <span className="badge st-ready">CURRENT</span>}
          <DevBadge status={ws.development_status} />
          <Prov provenance={ws.provenance} />
        </div>

        {stale ? (
          <p className="hint dw-stale-note">
            <TriangleAlert className="dp-badge-ico" style={{ color: 'var(--amber-text)' }} />
            Workspace context is out of date — the canonical plan/architecture moved on. Context refresh is a
            governed amendment: a new pack version is published, never a silent replacement.
          </p>
        ) : null}

        {correction ? (
          <p className="hint dw-stale-note" style={{ color: 'var(--red-dark)' }}>
            <CircleAlert className="dp-badge-ico" />
            Correction requested by independent review.{' '}
            <button type="button" className="link-btn" onClick={() => { selectStory(ws.story_id); goTo('independent_review') }}>
              View Review Finding
            </button>
          </p>
        ) : null}

        <div className="dw-section">
          <div className="dw-section-head static"><MonitorCog className="dw-section-ico" /><span>Workspace Details</span></div>
          <div className="dw-section-body">
            <div className="kv" style={{ gridTemplateColumns: '110px 1fr' }}>
              <b>Team</b><span>{ws.team}</span>
              <b>Developer</b>
              <span>{ws.developer
                ? <span className="dp-team"><DevAvatar name={ws.developer} />{ws.developer}</span>
                : <span className="hint">Unassigned</span>}</span>
              <b>Repository</b><span className="repo-cell"><Github />
                {links.repoUrl
                  ? <a className="mono" href={links.repoUrl} target="_blank" rel="noopener noreferrer">{ws.repository || '—'}</a>
                  : <span className="mono">{ws.repository || '—'}</span>}
              </span>
              <b>Branch</b><span className="repo-cell"><GitBranch />
                {links.branchUrl
                  ? <a className="mono" href={links.branchUrl} target="_blank" rel="noopener noreferrer">{ws.branch || '—'}</a>
                  : <span className="mono">{ws.branch || '—'}</span>}
              </span>
              <b>Base Commit</b><span className="mono">{ws.base_commit ? ws.base_commit.slice(0, 7) : '—'}</span>
              <b>Latest Commit</b>
              <span className="mono">
                {links.commitUrl
                  ? <a href={links.commitUrl} target="_blank" rel="noopener noreferrer">{ws.current_commit.slice(0, 7)}</a>
                  : (ws.current_commit ? ws.current_commit.slice(0, 7) : '—')}
                {ws.current_commit ? <span className="hint">{`  ${relTime(ws.last_sync_at)}`}</span> : null}
              </span>
              <b>Pull Request</b><span className="mono">
                {links.prUrl
                  ? <a href={links.prUrl} target="_blank" rel="noopener noreferrer">{ws.pull_request}</a>
                  : (ws.pull_request || '—')}
                {!links.prUrl && ws.pull_request
                  ? <span className="hint" title="Simulated PR — no remote to open"> (simulated)</span>
                  : null}
              </span>
              <b>CI Status</b><span><CiCell ws={ws} task={task} /></span>
              <b>Last Synced</b><span>{`${hhmm(ws.last_sync_at)}`}</span>
            </div>
          </div>
        </div>

        <Section icon={FileText} title="Task Pack" count={task ? '4' : '0'}>
          {task ? (
            <>
              <p className="hint"><b className="mono">{task.task_id}</b>{task.summary ? ` — ${task.summary}` : ''}</p>
              <ul className="plain dp-contents">
                {['task.md', 'context.json', 'test-plan.md', 'task-evidence.json'].map((f) => (
                  <li key={f}><CircleCheck className="val-ico ok" /><span className="mono val-label">{f}</span>
                    <span className="hint">{stale ? 'STALE' : 'CURRENT'}</span></li>
                ))}
              </ul>
            </>
          ) : <p className="hint">No task is linked to this story yet.</p>}
        </Section>

        <Section icon={Layers3} title="Inherited Context" count="5">
          <ul className="plain dp-contents">
            <li><CircleCheck className="val-ico ok" /><span className="mono val-label">architecture.md</span><span className="hint mono">{`v${pack?.architecture_version ?? '—'}`}</span></li>
            <li><CircleCheck className="val-ico ok" /><span className="mono val-label">plan</span><span className="hint mono">{`v${pack?.plan_version ?? '—'}`}</span></li>
            <li><CircleCheck className="val-ico ok" /><span className="val-label">{`${ws.team} Delivery Pack`}</span><span className="hint mono">{`v${ws.delivery_pack_version}`}</span></li>
            <li><CircleCheck className="val-ico ok" /><span className="mono val-label">AGENTS.md</span><span className="hint">team</span></li>
            <li><CircleCheck className="val-ico ok" /><span className="mono val-label">engineering-rules.md</span><span className="hint">shared</span></li>
          </ul>
          <p className="hint">Inherited by reference — canonical artifacts are never duplicated into the task.</p>
        </Section>

        <Section icon={ListChecks} title="Acceptance Criteria" count={String(acs.length)}>
          {acs.length === 0 ? <p className="hint">None recorded on the story.</p> : (
            <ul className="plain dp-contents">
              {acs.map((ac) => (
                <li key={ac.ac_id}>
                  <span className="mono val-label" style={{ flex: 'none' }}>{ac.ac_id}</span>
                  <span className="hint clamp-2" style={{ flex: 1 }}>{ac.text}</span>
                  {evidenced.has(ac.ac_id)
                    ? <span className="badge st-passed">evidence</span>
                    : <span className="badge st-planned">pending</span>}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section icon={GitFork} title="Dependencies" count={String(deps.length)}>
          {deps.length === 0 ? <p className="hint">No dependencies.</p> : (
            <ul className="plain dp-contents">
              {deps.map((d) => (
                <li key={d}>
                  <span className="mono val-label" style={{ flex: 'none' }}>{d}</span>
                  <span className={`badge ${depState(d) === 'AVAILABLE' ? 'st-passed' : depState(d) === 'BLOCKED' ? 'st-blocked' : 'st-planned'}`}>
                    {depState(d)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section icon={ShieldCheck} title="Scope Control" count={story?.target_component ? '2' : '0'}>
          <p className="hint"><b>Allowed Components</b></p>
          <ul className="plain dp-contents">
            <li><CircleCheck className="val-ico ok" /><span className="mono val-label">{story?.target_component || '—'}</span></li>
            <li><CircleCheck className="val-ico ok" /><span className="val-label">associated tests</span></li>
          </ul>
          <p className="hint" style={{ marginTop: '4px' }}>
            <b>Out of Scope</b> — every other component. Touching an out-of-scope component requires a new
            ticket, not a bigger diff (engineering rules).
          </p>
        </Section>

        <Section icon={Github} title="Git Handoff Status">
          <div className="kv" style={{ gridTemplateColumns: '130px 1fr' }}>
            <b>Repository</b><span className="mono">
              {links.repoUrl
                ? <a href={links.repoUrl} target="_blank" rel="noopener noreferrer">{ws.repository || '—'}</a>
                : (ws.repository || '—')}
            </span>
            <b>Branch</b><span className="mono">
              {links.branchUrl
                ? <a href={links.branchUrl} target="_blank" rel="noopener noreferrer">{ws.branch || '—'}</a>
                : (ws.branch || '—')}
            </span>
            <b>Pack Published</b><span><CircleCheck className="val-ico ok" />{` v${ws.delivery_pack_version}`}</span>
            <b>Publication Commit</b><span className="mono">{ws.base_commit ? ws.base_commit.slice(0, 7) : '—'}</span>
            <b>Developer Changes</b><span className="mono">
              {links.commitUrl
                ? <a href={links.commitUrl} target="_blank" rel="noopener noreferrer">{ws.current_commit.slice(0, 7)}</a>
                : (ws.current_commit ? ws.current_commit.slice(0, 7) : '—')}
            </span>
            <b>Pull Request</b><span className="mono">
              {links.prUrl
                ? <a href={links.prUrl} target="_blank" rel="noopener noreferrer">{ws.pull_request}</a>
                : (ws.pull_request || '—')}
            </span>
            <b>CI</b><span><CiCell ws={ws} task={task} /></span>
          </div>
          {ws.git_evidence?.commit_count ? (
            <div className="kv" style={{ gridTemplateColumns: '130px 1fr', marginTop: '8px' }}>
              <b>Pushed Commits</b>
              <span>{`${ws.git_evidence.commit_count} referencing ${ws.story_id}`}</span>
              <b>Latest Push</b>
              <span className="clamp-2">
                <span className="mono">{ws.git_evidence.latest?.sha.slice(0, 7)}</span>
                {` — ${ws.git_evidence.latest?.subject} (${ws.git_evidence.latest?.author})`}
              </span>
              <b>Developer Branch</b>
              <span className="mono">{ws.git_evidence.branches.join(', ') || '—'}</span>
              <b>Merged to Default</b>
              <span>{ws.git_evidence.merged
                ? <><CircleCheck className="val-ico ok" /> Yes — merged by a human</>
                : 'Not yet — merging stays a human action'}</span>
            </div>
          ) : null}
          {ws.git_evidence ? (
            <p className="hint">
              Real pushed work read from the repository (git fetch, read-only); commits matched by
              story/task id in the message. Last synced {hhmm(ws.last_sync_at)}.
            </p>
          ) : null}
          {simulated ? (
            <p className="hint"><Prov provenance="simulated" /> Simulated publication — no git remote is touched in this mode.</p>
          ) : null}
        </Section>

        <Section icon={ActivityIcon} title="Activity" count={String(activity.length)}>
          {activity.length === 0 ? <p className="hint">No workspace activity yet.</p> : (
            <ul className="plain">
              {activity.map((a, i) => {
                const IconC = activityIcon(a)
                return (
                  <li key={`${a.timestamp}-${i}`} className="act-row" style={{ marginBottom: '4px' }}>
                    <span className="t">{hhmm(a.timestamp)}</span>
                    <IconC />
                    <span className="x clamp-2">{[a.outcome, a.details].filter(Boolean).join(' · ')}</span>
                  </li>
                )
              })}
            </ul>
          )}
        </Section>

        {task && (
          <div className="sub-panel">
            <h3>Simulated developer activity <Prov provenance="simulated" /></h3>
            <p className="hint">
              In production this evidence arrives from the developer's Git/CI. In this demo the deterministic
              engine produces it, badged SIMULATED — S7 observes development, it never performs it.
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
                <button type="button" className="outline"
                  onClick={() => { selectStory(ws.story_id); goTo('independent_review') }}>
                  Open Independent Review
                </button>
              )}
            </div>
          </div>
        )}

        <div className="dw-drawer-actions">
          <button type="button" className="outline" onClick={() => goTo('delivery_packs')}>
            <PackageOpen className="btn-ico" /> View Delivery Pack
          </button>
          <button type="button" className="outline" disabled={!links.repoUrl}
            title={links.repoUrl ? undefined : 'No connected GitHub repository for this workspace'}
            onClick={() => { if (links.repoUrl) window.open(links.repoUrl, '_blank', 'noopener,noreferrer') }}>
            <ExternalLink className="btn-ico" /> Open Repository
          </button>
          <button type="button" className="outline" disabled={!links.prUrl}
            title={links.prUrl ? undefined : 'Simulated PR — no remote to open'}
            onClick={() => { if (links.prUrl) window.open(links.prUrl, '_blank', 'noopener,noreferrer') }}>
            <GitPullRequest className="btn-ico" /> View Pull Request
          </button>
          <button type="button" className="primary" onClick={() => { selectStory(ws.story_id); goTo('test_evidence') }}>
            <ClipboardCheck className="btn-ico" /> View Build Evidence
          </button>
        </div>
      </aside>
    </div>
  )
}

export function DeveloperWorkspaces() {
  const { data, runId, role, refresh, notify, goTo } = useRun()
  const [openId, setOpenId] = useState<string | null>(null)
  const [assignFor, setAssignFor] = useState<string | null>(null)
  const [syncing, setSyncing] = useState(false)
  const [assignName, setAssignName] = useState('')
  const [query, setQuery] = useState('')
  const [fTeam, setFTeam] = useState('all')
  const [fDev, setFDev] = useState('all')
  const [fStatus, setFStatus] = useState('all')
  const [fArtifact, setFArtifact] = useState('all')
  const [fCi, setFCi] = useState('all')
  const [perPage, setPerPage] = useState(10)
  const [page, setPage] = useState(1)

  const build = buildOf(data)
  const workspaces = build.workspaces ?? []
  const tasks = build.tasks ?? []
  const packs = build.delivery_packs ?? []
  const stories: PlanStory[] = data?.planning?.stories ?? []
  const taskById = useMemo(() => new Map(tasks.map((t) => [t.task_id, t])), [tasks])
  const storyById = useMemo(() => new Map(stories.map((s) => [s.story_id, s])), [stories])

  if (!data) return null

  const wsTask = (ws: DeveloperWorkspace) => (ws.task_id ? taskById.get(ws.task_id) : undefined)
  const teams = [...new Set(workspaces.map((w) => w.team))]
  const developers = [...new Set(workspaces.map((w) => w.developer).filter(Boolean))]
  const assigned = workspaces.filter((w) => w.developer).length
  const inDev = workspaces.filter((w) => w.development_status === 'in_development').length
  const openPrs = workspaces.filter((w) => w.pull_request && w.development_status !== 'complete').length
  const ciRunning = workspaces.filter((w) => w.ci_status === 'running').length
  const blocked = workspaces.filter((w) =>
    w.development_status === 'blocked' || w.development_status === 'correction_requested',
  ).length

  const filtered = workspaces.filter((w) => {
    if (fTeam !== 'all' && w.team !== fTeam) return false
    if (fDev !== 'all' && w.developer !== fDev) return false
    if (fStatus !== 'all' && w.development_status !== fStatus) return false
    if (fArtifact !== 'all' && w.artifact_status !== fArtifact) return false
    if (fCi !== 'all' && (w.ci_status || 'not_started') !== fCi) return false
    if (query.trim()) {
      const q = query.trim().toLowerCase()
      const hay = `${w.team} ${w.story_id} ${w.task_id ?? ''} ${w.repository} ${w.developer}`.toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })

  const pageCount = Math.max(1, Math.ceil(filtered.length / perPage))
  const safePage = Math.min(page, pageCount)
  const pageRows = filtered.slice((safePage - 1) * perPage, safePage * perPage)
  const open = openId ? workspaces.find((w) => w.workspace_id === openId) : undefined

  const doSyncGit = async () => {
    if (!runId) return
    setSyncing(true)
    try {
      await apiPost(`/api/runs/${runId}/workspaces/sync-git`, { role })
      await refresh()
      notify('Synced from Git — showing real pushed commits (story id matched in commit messages)')
    } catch (err) {
      notify((err as Error).message, true)
    } finally {
      setSyncing(false)
    }
  }

  const doAssign = async () => {
    const developer = assignName.trim()
    const ws = workspaces.find((w) => w.workspace_id === assignFor)
    if (!developer || !runId || !ws) return
    try {
      await apiPatch(`/api/runs/${runId}/workspaces/${ws.workspace_id}/developer`, { role, developer })
      await refresh()
      notify(`Assigned ${developer}. Team pack refreshed — republish in Delivery Packs to sync the assignment to Git.`)
      setAssignFor(null)
      setAssignName('')
    } catch (err) {
      notify((err as Error).message, true)
    }
  }

  if (workspaces.length === 0) {
    return (
      <section className="page-with-rail bo-compact">
        <div>
          <div className="page-head" style={{ marginBottom: '8px' }}>
            <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Developer Workspaces</span>
          </div>
          <div className="card">
            <h3><MonitorCog className="btn-ico" /> No Developer Workspaces Yet</h3>
            <p>Delivery Packs must be published to Git before developer workspaces become available.</p>
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="primary" onClick={() => goTo('delivery_packs')}>
                <PackageOpen className="btn-ico" /> Go to Delivery Packs
              </button>
            </div>
          </div>
        </div>
        <aside className="rail"><GuidanceCard lines={CONTROL_PLANE_GUIDANCE} /></aside>
      </section>
    )
  }

  return (
    <section className="bo-compact dw-page">
      <div className="page-head" style={{ marginBottom: '4px' }}>
        <span className="crumb">Build &amp; Review <span className="crumb-sep">›</span> Developer Workspaces</span>
      </div>
      <div className="page-head" style={{ marginBottom: '10px' }}>
        <h2>Developer Workspaces</h2>
        <span className="chip own-human"><UserCheck className="dp-badge-ico" />Human Controlled</span>
        <span className="chip own-ai"><Sparkles className="dp-badge-ico" />AI Assisted</span>
        <button
          className="ghost"
          style={{ marginLeft: 'auto' }}
          disabled={data.run.mode !== 'live' || syncing}
          title={data.run.mode !== 'live'
            ? 'Live runs only — simulation has no real repository clone'
            : 'git fetch + read-only inspection; commits are matched by story/task id in the message'}
          onClick={() => void doSyncGit()}
        >
          {syncing
            ? <LoaderCircle className="btn-ico spin" />
            : <GitCommitHorizontal className="btn-ico" />} Sync from Git
        </button>
        <span className="hint" style={{ flexBasis: '100%' }}>
          Human-controlled engineering workspaces provisioned from approved S7 delivery packs. Developers
          implement using their normal IDE, CLI and Git workflows.
        </span>
      </div>

      <div className="stat-row">
        <StatCard accent="green" icon={<MonitorCog />} value={String(workspaces.length)} label="Workspaces Ready" sub="Ready for developers" />
        <StatCard accent="blue" icon={<UsersRound />} value={String(assigned)} label="Developers Assigned" sub="Across teams" />
        <StatCard accent="orange" icon={<Code2 />} value={String(inDev)} label="Active Development" sub="In progress" />
        <StatCard accent="purple" icon={<GitPullRequest />} value={String(openPrs)} label="Open Pull Requests" sub="Awaiting review" />
        <StatCard accent="blue" icon={<Workflow />} value={String(ciRunning)} label="CI Pipelines Running" sub="Live pipelines" />
        <StatCard accent="red" icon={<CircleAlert />} value={String(blocked)} label="Blocked Workspaces" sub={blocked ? 'Needs attention' : 'None'} />
      </div>

      <div className="card dp-filters">
        <span className="dp-search">
          <Search className="dp-search-ico" />
          <input type="text" placeholder="Search by team, story, repository, developer…"
            value={query} onChange={(e) => setQuery(e.target.value)} />
        </span>
        <label className="dp-filter"><span>Team</span>
          <select value={fTeam} onChange={(e) => setFTeam(e.target.value)}>
            <option value="all">All</option>
            {teams.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="dp-filter"><span>Developer</span>
          <select value={fDev} onChange={(e) => setFDev(e.target.value)}>
            <option value="all">All</option>
            {developers.map((d) => <option key={d} value={d}>{d}</option>)}
          </select>
        </label>
        <label className="dp-filter"><span>Dev Status</span>
          <select value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
            <option value="all">All</option>
            {Object.keys(DEV_STATUS_LABELS).map((s) => <option key={s} value={s}>{DEV_STATUS_LABELS[s]}</option>)}
          </select>
        </label>
        <label className="dp-filter"><span>Artifact Status</span>
          <select value={fArtifact} onChange={(e) => setFArtifact(e.target.value)}>
            <option value="all">All</option>
            <option value="current">Current</option>
            <option value="stale">Stale</option>
          </select>
        </label>
        <label className="dp-filter"><span>CI Status</span>
          <select value={fCi} onChange={(e) => setFCi(e.target.value)}>
            <option value="all">All</option>
            <option value="passed">Passed</option>
            <option value="running">Running</option>
            <option value="failed">Failed</option>
            <option value="not_started">Not Started</option>
          </select>
        </label>
        <button className="ghost" onClick={() => { setQuery(''); setFTeam('all'); setFDev('all'); setFStatus('all'); setFArtifact('all'); setFCi('all') }}>
          <RotateCcw className="btn-ico" /> Reset
        </button>
      </div>

      <div className="card">
        <div className="table-wrap">
          <table className="dp-table dw-table">
            <colgroup>
              <col style={{ width: '8%' }} /><col style={{ width: '13%' }} /><col style={{ width: '16%' }} />
              <col style={{ width: '10%' }} /><col style={{ width: '10%' }} /><col style={{ width: '8%' }} />
              <col style={{ width: '7%' }} /><col style={{ width: '9%' }} /><col style={{ width: '8%' }} />
              <col style={{ width: '11%' }} />
            </colgroup>
            <thead>
              <tr>
                <th>Team</th><th>Story / Task</th><th>Repository / Branch</th><th>Developer</th>
                <th>Delivery Pack</th><th>Latest Commit</th><th>Pull Request</th><th>CI Status</th>
                <th>Dev Status</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {pageRows.map((ws) => {
                const task = wsTask(ws)
                const story = storyById.get(ws.story_id)
                const stale = ws.artifact_status === 'stale'
                const initials = ws.team.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
                const links = githubLinks(ws, data.intake?.repos)
                return (
                  <tr key={ws.workspace_id}
                    className={openId === ws.workspace_id ? 'dp-row-selected' : ''}
                    onClick={() => setOpenId(ws.workspace_id)}>
                    <td>
                      <span className="dw-team-stack">
                        <span className={`team-avatar ${['tc-0', 'tc-1', 'tc-2', 'tc-3', 'tc-4'][ws.team.length % 5]}`}>{initials}</span>
                        <b>{ws.team}</b>
                      </span>
                    </td>
                    <td>
                      <b className="mono dw-story-id">{ws.story_id}</b>
                      <span className="hint dp-sub dw-title clamp-2">{story?.title ?? ''}</span>
                      {ws.task_id ? (
                        <span className="hint dp-sub mono"><ListChecks className="dp-badge-ico" />{ws.task_id}</span>
                      ) : null}
                    </td>
                    <td>
                      <span className="repo-cell"><Github />
                        {links.repoUrl
                          ? <a className="mono" href={links.repoUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>{ws.repository || '—'}</a>
                          : <span className="mono">{ws.repository || '—'}</span>}
                      </span>
                      <span className="repo-cell dw-branch-line"><GitBranch />
                        {links.branchUrl
                          ? <a className="mono" href={links.branchUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>{ws.branch || '—'}</a>
                          : <span className="mono">{ws.branch || '—'}</span>}
                      </span>
                    </td>
                    <td onClick={(e) => e.stopPropagation()}>
                      {ws.developer ? (
                        <>
                          <span className="dp-team"><DevAvatar name={ws.developer} />{ws.developer}</span>
                          <span className="hint dp-sub">{relTime(ws.last_sync_at)}</span>
                        </>
                      ) : (
                        <>
                          <span className="hint">Unassigned</span>
                          <button type="button" className="link-btn dp-sub" onClick={() => { setAssignFor(ws.workspace_id); setAssignName('') }}>
                            <UserPlus className="dp-badge-ico" />Assign
                          </button>
                        </>
                      )}
                    </td>
                    <td>
                      <span className="mono">{`v${ws.delivery_pack_version}.0`}</span>{' '}
                      {stale
                        ? <span className="badge st-stale"><TriangleAlert className="dp-badge-ico" />STALE</span>
                        : <span className="badge st-ready"><BadgeCheck className="dp-badge-ico" />CURRENT</span>}
                      <span className="hint dp-sub"><PackageCheck className="dp-badge-ico" />Published to Git</span>
                    </td>
                    <td>
                      {ws.current_commit ? (
                        <>
                          <span className="repo-cell">
                            <GitCommitHorizontal />
                            {links.commitUrl
                              ? <a className="mono" href={links.commitUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>{ws.current_commit.slice(0, 7)}</a>
                              : <span className="mono">{ws.current_commit.slice(0, 7)}</span>}
                          </span>
                          <span className="hint dp-sub">{relTime(ws.last_sync_at)}</span>
                        </>
                      ) : <span className="hint">—</span>}
                    </td>
                    <td>
                      {ws.pull_request ? (
                        <>
                          <span className="repo-cell">
                            <GitPullRequest />
                            {links.prUrl
                              ? <a className="mono" href={links.prUrl} target="_blank" rel="noopener noreferrer" onClick={(e) => e.stopPropagation()}>{ws.pull_request}</a>
                              : <span className="mono">{ws.pull_request}</span>}
                          </span>
                          {links.prUrl
                            ? <span className="badge st-in_progress dp-sub" style={{ display: 'inline-block' }}>on GitHub</span>
                            : <span className="hint dp-sub">simulated</span>}
                        </>
                      ) : <span className="hint">—</span>}
                    </td>
                    <td><CiCell ws={ws} task={task} /></td>
                    <td><DevBadge status={ws.development_status} /></td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <div className="dp-actions">
                        <button className="icon-btn" aria-label={`View ${ws.story_id} workspace`} title="View Workspace"
                          onClick={() => setOpenId(ws.workspace_id)}><Eye className="btn-ico" /></button>
                        <button className="icon-btn" aria-label="Open repository" disabled={!links.repoUrl}
                          title={links.repoUrl ? 'Open repository on GitHub' : 'No connected GitHub repository for this workspace'}
                          onClick={() => { if (links.repoUrl) window.open(links.repoUrl, '_blank', 'noopener,noreferrer') }}>
                          <ExternalLink className="btn-ico" /></button>
                        <button className="icon-btn" aria-label={`View ${ws.story_id} pull request`} disabled={!links.prUrl}
                          title={links.prUrl ? 'View pull request on GitHub' : (ws.pull_request ? 'Simulated PR — details in the workspace drawer' : 'No pull request yet')}
                          onClick={() => { if (links.prUrl) window.open(links.prUrl, '_blank', 'noopener,noreferrer') }}>
                          <GitPullRequest className="btn-ico" /></button>
                        <button className="icon-btn" aria-label={`View ${ws.story_id} evidence`} title="View Evidence"
                          onClick={() => { selectStory(ws.story_id); goTo('test_evidence') }}>
                          <ClipboardCheck className="btn-ico" /></button>
                      </div>
                    </td>
                  </tr>
                )
              })}
              {filtered.length === 0 ? (
                <tr><td colSpan={10}><span className="hint">No workspaces match the current filters.</span></td></tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="dw-pager">
          <span className="hint">
            {filtered.length
              ? `Showing ${(safePage - 1) * perPage + 1} to ${Math.min(safePage * perPage, filtered.length)} of ${filtered.length} entries`
              : 'No entries'}
          </span>
          <span className="dw-pager-controls">
            <select value={perPage} aria-label="Rows per page"
              onChange={(e) => { setPerPage(Number(e.target.value)); setPage(1) }}>
              <option value={10}>10 per page</option>
              <option value={25}>25 per page</option>
              <option value={50}>50 per page</option>
            </select>
            <button className="icon-btn" aria-label="Previous page" disabled={safePage <= 1}
              onClick={() => setPage(safePage - 1)}>‹</button>
            <span className="dw-page-chip">{safePage}</span>
            <button className="icon-btn" aria-label="Next page" disabled={safePage >= pageCount}
              onClick={() => setPage(safePage + 1)}>›</button>
          </span>
        </div>
      </div>

      <div className="card info-banner" style={{ marginTop: '10px' }}>
        <Info className="btn-ico" style={{ marginTop: '1px' }} />
        <span>
          Developer Workspaces are human controlled. S7 provides governed context and collects engineering
          evidence; developers implement changes using their normal IDE, CLI and Git tools.
        </span>
      </div>

      {assignFor ? (() => {
        const ws = workspaces.find((w) => w.workspace_id === assignFor)
        if (!ws) return null
        return (
          <Modal title="Assign Developer" onClose={() => setAssignFor(null)}>
            <div className="kv">
              <b>Story</b><span className="mono">{ws.story_id}</span>
              <b>Team</b><span>{ws.team}</span>
            </div>
            <input type="text" placeholder="Developer name" value={assignName} style={{ width: '100%', marginTop: '10px' }}
              aria-label={`Assign developer to ${ws.workspace_id}`}
              onChange={(e) => setAssignName(e.target.value)} />
            <div className="actions-row" style={{ marginTop: '12px' }}>
              <button className="ghost" onClick={() => setAssignFor(null)}>Cancel</button>
              <button className="primary" disabled={!assignName.trim()} onClick={() => void doAssign()}>
                <UserPlus className="btn-ico" /> Assign
              </button>
            </div>
          </Modal>
        )
      })() : null}

      {open ? (
        <WorkspaceDrawer
          ws={open}
          task={wsTask(open)}
          pack={packs.find((p) => p.delivery_pack_id === open.delivery_pack_id)}
          story={storyById.get(open.story_id)}
          onClose={() => setOpenId(null)}
        />
      ) : null}
    </section>
  )
}
