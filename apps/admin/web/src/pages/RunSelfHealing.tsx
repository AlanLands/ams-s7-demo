import { useEffect } from 'react'
import { ArrowUpRight, Check, CircleDot, Clock3, OctagonPause, RefreshCw, X } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, DetailDrawer, Empty, Loading, fmtTime, humanize } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { RunRow, SelfHealChange, SelfHealEvent, SelfHealStep, SelfHealView } from '../types'

/* Runs → Self-healing: every human change a run absorbed after plan lock,
 * the versioned playbook pinned to it, and how far it has run. The engine
 * derives all of it on read (factory/self_heal.py, RULE_BASED); this drawer
 * only observes. Gates are signed in the Control Centre by the named role —
 * nothing here signs, advances or retries. */

const ROLE_LABEL: Record<string, string> = {
  business_owner: 'Business Owner',
  delivery_lead: 'Delivery Lead',
  product_analyst: 'Product Analyst',
  engineering_lead: 'Engineering Lead',
  qa_lead: 'QA Lead',
  independent_reviewer: 'Independent Reviewer',
  release_manager: 'Release Manager',
  support_lead: 'Support Lead',
}
export const roleLabel = (r?: string | null): string => (r ? ROLE_LABEL[r] ?? humanize(r) : '')

function hhmm(iso?: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false })
}

/* --- shape tolerance: read the flat fields or their nested aliases -------- */

const playbookOf = (c: SelfHealChange) => ({
  id: c.playbook_id ?? c.playbook?.id ?? null,
  version: c.playbook_version ?? c.playbook?.version ?? null,
})
const triggerOf = (c: SelfHealChange) => ({
  artifact: c.trigger?.artifact_id ?? c.trigger_artifact ?? null,
  version: c.trigger?.version ?? c.trigger_version ?? null,
})
const staleOf = (c: SelfHealChange): string[] => c.impact?.stale ?? c.stale ?? []
const stepTime = (s: SelfHealStep) => s.executed_at ?? s.at ?? null
const eventTime = (e: SelfHealEvent) => e.timestamp ?? e.at ?? null

/** One badge per change: the four states the engine's summary counts. */
function changeStatus(c: SelfHealChange): { variant: 'success' | 'danger' | 'warning' | 'accent'; label: string } {
  const steps = c.steps ?? []
  if (c.status === 'completed') return { variant: 'success', label: 'completed' }
  if (steps.some((s) => s.status === 'failed')) return { variant: 'danger', label: 'failed' }
  if (c.waiting_on) return { variant: 'warning', label: `waiting on ${roleLabel(c.waiting_on)}` }
  return { variant: 'accent', label: 'open' }
}

const STEP_VARIANT: Record<string, 'success' | 'danger' | 'warning' | 'neutral'> = {
  done: 'success', failed: 'danger', waiting: 'warning', pending: 'neutral',
}

/** Chips for the Runs table cell — only once the drawer has fetched. */
export function HealSummaryChips({ view }: { view: SelfHealView }) {
  const s = view.summary ?? {}
  const open = s.open ?? 0, waiting = s.waiting_on_human ?? 0, failed = s.failed ?? 0, completed = s.completed ?? 0
  if (!open && !waiting && !failed && !completed) return <Badge variant="neutral" label="no changes" title="No self-healing change records on this run" />
  return (
    <span className="chips sh-chips">
      {open ? <Badge variant="accent" label={`${open} open`} title={`${open} open change${open === 1 ? '' : 's'}`} /> : null}
      {waiting ? <Badge variant="warning" label={`${waiting} waiting`} title={`${waiting} waiting on a human gate`} /> : null}
      {failed ? <Badge variant="danger" label={`${failed} failed`} title={`${failed} change${failed === 1 ? '' : 's'} with a failed step`} /> : null}
      {!open && !failed && completed ? <Badge variant="success" label={`${completed} completed`} /> : null}
    </span>
  )
}

/* --- pieces ----------------------------------------------------------------- */

function StepRail({ change }: { change: SelfHealChange }) {
  const steps = change.steps ?? []
  if (!steps.length) return <p className="hint">This change carries no steps.</p>
  return (
    <ol className="sh-rail" aria-label={`Playbook steps for ${change.change_id}`}>
      {steps.map((s) => {
        const status = s.status ?? 'pending'
        const gate = s.kind === 'gate'
        const blocked = change.blocked_step === s.step_id && gate && change.status !== 'completed' && status !== 'failed'
        const marker = status === 'done' ? <Check aria-hidden="true" /> : status === 'failed' ? <X aria-hidden="true" /> : gate ? <OctagonPause aria-hidden="true" /> : <CircleDot aria-hidden="true" />
        const when = stepTime(s)
        return (
          <li key={s.step_id} className={`sh-step ${gate ? 'gate' : 'mechanical'} ${status}`}>
            <span className="marker" aria-hidden="true">{marker}</span>
            <div className="sh-step-head">
              <b>{s.label || humanize(s.action)}</b>
              <Badge variant={gate ? 'warning' : 'neutral'} soft label={gate ? 'gate' : 'mechanical'} title={gate ? 'Stops the playbook until the named role records the action' : 'Runs on its own when reached'} />
              <Badge variant={STEP_VARIANT[status] ?? 'neutral'} label={status} />
              <span className="mono sm muted">{s.action}</span>
            </div>
            {blocked ? (
              <div className="waiting"><Clock3 aria-hidden="true" />Waiting on {roleLabel(s.role)} to record <span className="mono">{s.action}</span> in the Control Centre</div>
            ) : gate && s.role ? (
              <div className="detail">Signed by {roleLabel(s.role)}</div>
            ) : s.as_role ? (
              <div className="detail">Runs as {roleLabel(s.as_role)}</div>
            ) : null}
            {s.detail ? <div className="detail">{s.detail}</div> : null}
            {s.outcome ? <div className="outcome">{s.outcome}</div> : null}
            {when || s.provenance ? (
              <div className="when">
                {when ? fmtTime(when) : null}
                {when && s.provenance ? ' · ' : null}
                {s.provenance ? <span className="mono sm">{String(s.provenance).toUpperCase()}</span> : null}
              </div>
            ) : null}
          </li>
        )
      })}
    </ol>
  )
}

function EventList({ events }: { events: SelfHealEvent[] }) {
  if (!events.length) return <p className="hint sm" style={{ marginTop: 12 }}>No activity recorded for this change yet.</p>
  return (
    <ul className="sh-events" aria-label="Activity for this change">
      {events.map((e, i) => (
        <li key={`${eventTime(e) ?? ''}-${i}`}>
          <span className="t" title={fmtTime(eventTime(e))}>{hhmm(eventTime(e))}</span>
          <span>
            {e.outcome ? <b>{humanize(String(e.outcome))}</b> : null}
            {e.outcome && e.details ? ' — ' : null}
            {e.details ? String(e.details) : null}
            {e.actor ? <span className="muted"> · {String(e.actor)}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  )
}

function ChangeCard({ change, promptSet }: { change: SelfHealChange; promptSet?: string | null }) {
  const { openPlaybook } = useAdmin()
  const st = changeStatus(change)
  const pb = playbookOf(change)
  const trig = triggerOf(change)
  const stale = staleOf(change)
  const steps = change.steps ?? []
  const done = change.done_steps ?? steps.filter((s) => s.status === 'done').length
  return (
    <Card compact className="sh-change" title={change.title || (change.change_type ? humanize(change.change_type) : change.change_id)}
      description={<><span className="mono">{change.change_id}</span>{change.created_at ? ` · opened ${fmtTime(change.created_at)}` : ''}{change.completed_at ? ` · completed ${fmtTime(change.completed_at)}` : ''}</>}
      actions={<Badge variant={st.variant} label={st.label} />}>
      {change.reason ? <blockquote className="sh-reason">{change.reason}</blockquote> : null}
      <div className="kv tight">
        <div className="k">Initiator</div>
        <div className="v">{change.initiator ? roleLabel(change.initiator) : <span className="na">unreported</span>}</div>
        <div className="k">Trigger</div>
        <div className="v">
          {trig.artifact ? <span className="mono">{trig.artifact}{trig.version != null ? ` @ v${trig.version}` : ''}</span> : <span className="na">unreported</span>}
          {change.scope?.story_id ? <span className="sub">Scope: {change.scope.story_id}{change.scope.pack_id ? ` · pack ${change.scope.pack_id}${change.scope.pack_version != null ? ` v${change.scope.pack_version}` : ''}` : ''}</span> : null}
        </div>
        <div className="k">Playbook</div>
        <div className="v">
          {pb.id ? (
            <span className="inline">
              <Button variant="link" size="sm" className="mono" icon={<ArrowUpRight />} onClick={() => openPlaybook(pb.id as string, promptSet)} title="Open this playbook on the Playbooks page">
                {pb.id}{pb.version != null ? `@v${pb.version}` : ''}
              </Button>
              {change.playbook_recorded === false ? <Badge variant="warning" label="unrecorded" title="Pinned to a version with no ledger line" /> : null}
            </span>
          ) : <span className="na">unreported</span>}
          {change.playbook_sha256 ? <span className="sub mono">{change.playbook_sha256.slice(0, 12)}</span> : null}
        </div>
        <div className="k">Impact</div>
        <div className="v">
          {stale.length ? (
            <span className="chips">{stale.map((id) => <Badge key={id} variant="danger" mono label={id} />)}</span>
          ) : change.impact?.assessed_at ? 'Nothing downstream was stale when assessed.' : <span className="na">not assessed yet</span>}
        </div>
        <div className="k">Progress</div>
        <div className="v">{done} of {steps.length} steps done{change.blocked_step && change.status !== 'completed' ? <span className="sub">Stopped at <span className="mono">{change.blocked_step}</span></span> : null}</div>
      </div>
      <StepRail change={change} />
      <EventList events={change.events ?? []} />
    </Card>
  )
}

function Tile({ label, value, tone }: { label: string; value: number; tone?: 'warning' | 'danger' | 'success' | 'accent' }) {
  return (
    <div className={`tile${value && tone ? ` sh-tile-${tone}` : ''}`}>
      <div className="l">{label}</div>
      <div className="v">{value}</div>
    </div>
  )
}

/* --- the drawer --------------------------------------------------------------- */

export function SelfHealingDrawer({ run, onClose, onLoaded }: {
  run: RunRow
  onClose: () => void
  /** Hands the fetched view back so the Runs table can show its counts. */
  onLoaded?: (view: SelfHealView) => void
}) {
  const { openPlaybook } = useAdmin()
  const view = useLoad(() => api.runs.selfHealing(run.run_id), [run.run_id])
  useEffect(() => { if (view.data && onLoaded) onLoaded(view.data) }, [view.data, onLoaded])

  const data = view.data
  const changes = [...(data?.changes ?? [])].sort((a, b) => (b.created_at ?? '').localeCompare(a.created_at ?? ''))
  const stale = data?.stale_now ?? []
  const playbooks = data?.playbooks ?? []
  const s = data?.summary ?? {}

  return (
    <DetailDrawer
      ariaLabel={`Self-healing for ${run.run_id}`}
      title={<>Self-healing <span className="mono">{run.run_id}</span></>}
      subtitle="Read-only. Gates are signed in the Control Centre by the named role; this view observes them."
      onClose={onClose}
    >
      <div className="sh-prov">
        <Badge variant="neutral" mono label={(data?.provenance ?? 'rule_based').toUpperCase()} title="Derived on read from the run's own records — never stored twice, never an AI claim" />
        <span>Counted from the run's change records, activity ledger and current staleness.</span>
        <span className="grow" />
        <Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={view.reload} disabled={view.loading}>Refresh</Button>
      </div>

      {view.loading && !data ? <Loading what="Loading self-healing records" /> : null}
      {view.error ? <LoadError what={`self-healing for ${run.run_id}`} error={view.error} onRetry={view.reload} /> : null}

      {data ? (
        <>
          <div className="tiles sh-tiles">
            <Tile label="Open" value={s.open ?? 0} tone="accent" />
            <Tile label="Waiting on a human" value={s.waiting_on_human ?? 0} tone="warning" />
            <Tile label="Completed" value={s.completed ?? 0} tone="success" />
            <Tile label="Failed" value={s.failed ?? 0} tone="danger" />
          </div>

          <div>
            <h4 className="sh-h">Stale now</h4>
            {stale.length ? (
              <div className="chips">{stale.map((id) => <Badge key={id} variant="danger" mono label={id} />)}</div>
            ) : <p className="hint">Nothing in this run is stale right now.</p>}
          </div>

          <div>
            <h4 className="sh-h">Changes <span className="muted">({changes.length})</span></h4>
            {changes.length ? (
              <div className="stack">
                {changes.map((c) => <ChangeCard key={c.change_id} change={c} promptSet={run.prompt_set} />)}
              </div>
            ) : (
              <Empty bare title="No self-healing changes on this run"
                hint="A change record opens when, after plan lock, a lead revises the architecture, the QA Lead amends a test plan, or an upstream ruling lands — all from the Control Centre. Nothing has happened here yet." />
            )}
          </div>

          {playbooks.length ? (
            <div>
              <h4 className="sh-h">Playbooks this run would follow</h4>
              <p className="hint sm" style={{ marginBottom: 4 }}>From prompt set <span className="mono">{run.prompt_set ?? 'default'}</span>. A change pins the version current when it opens.</p>
              <ul className="sh-books" aria-label="Playbooks">
                {playbooks.map((p) => (
                  <li key={p.playbook_id}>
                    <div className="grow">
                      <div><b>{p.title ?? p.playbook_id}</b></div>
                      <div className="hint sm">{p.change_type ? <span className="mono sm">{p.change_type}</span> : null}{p.change_type && p.steps?.length ? ' · ' : ''}{p.steps?.length ? `${p.steps.length} steps, ${p.steps.filter((x) => x.kind === 'gate').length} gates` : ''}</div>
                    </div>
                    {p.version != null ? <Badge variant={p.recorded === false ? 'warning' : 'success'} label={p.recorded === false ? 'unrecorded' : `v${p.version}`} /> : null}
                    <Button variant="link" size="sm" className="mono" icon={<ArrowUpRight />} onClick={() => openPlaybook(p.playbook_id, run.prompt_set)}>{p.playbook_id}</Button>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </>
      ) : null}
    </DetailDrawer>
  )
}
