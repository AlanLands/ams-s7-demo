import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowRight, Check, ChevronDown, ChevronRight, GraduationCap, RefreshCw, Sparkles, X } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import {
  Badge, Button, Card, ConfirmPanel, DetailDrawer, Empty, Field, Loading, Notice, PageHeader, SectionHead, TableWrap, fmtTime,
} from '../components/ui'
import { DiffView } from '../components/Versions'
import { useAdmin } from '../state/AdminContext'
import type { Correction, LearningOverview, LearningTarget, LlmDescribe, Proposal, ProposalStatus } from '../types'

/* Correction learning — the admin-only loop where the product learns from
 * people who corrected its output. Three honesty rules shape the page:
 * corrections are recorded by the engine (never typed here); a proposal
 * is one real model call and is badged LIVE_AI or REPLAYED_AI, never
 * anything else; and nothing is applied until an operator accepts it,
 * which records a version through the ordinary ledger. The Control
 * Centre's users never see any of this. */

const WINDOWS: { value: string; label: string }[] = [
  { value: '7', label: 'Last 7 days' },
  { value: '30', label: 'Last 30 days' },
  { value: '90', label: 'Last 90 days' },
  { value: 'all', label: 'All time' },
]
const CLIP = 480
const AI = new Set(['live_ai', 'replayed_ai'])

const daysOf = (w: string): number | undefined => (w === 'all' ? undefined : Number(w))

/** A correction value as text: strings as they are, anything else pretty JSON. */
function valueText(v: unknown): string {
  if (v == null) return ''
  if (typeof v === 'string') return v
  try { return JSON.stringify(v, null, 2) } catch { return String(v) }
}

function Tile({ label, value, sub }: { label: string; value: string | number; sub?: React.ReactNode }) {
  return (
    <div className="tile">
      <div className="l">{label}</div>
      <div className="v">{value}</div>
      {sub ? <div className="s">{sub}</div> : null}
    </div>
  )
}

/** The original's provenance. Model output is learnable and reads as info;
 * a seed, a rule-based rendering or human text is neutral and says so. */
function OriginBadge({ p }: { p: string }) {
  const k = (p || '').toLowerCase()
  if (AI.has(k)) return <Badge variant="info" mono label={k.toUpperCase()} title="The original was model output — learnable" />
  return <Badge variant="neutral" mono label={`${(k || 'unknown').toUpperCase()} · not learnable`} title="The original was not model output; teaching a prompt to reproduce it is not learning" />
}

/** A proposal is always a genuine call. Anything other than the two real
 * provenances would be a contract breach, so it renders loudly rather
 * than being dressed as one of them. */
function ProposalProvenance({ p }: { p: string }) {
  const k = (p || '').toLowerCase()
  if (AI.has(k)) return <Badge variant="info" mono label={k.toUpperCase()} title={k === 'live_ai' ? 'A real model call' : 'Served from a committed recording'} />
  return <Badge variant="danger" mono label={(k || 'unknown').toUpperCase()} title="Not a recognised proposal provenance" />
}

const STATUS_VARIANT: Record<ProposalStatus, 'warning' | 'success' | 'neutral'> = { proposed: 'warning', accepted: 'success', rejected: 'neutral' }

function StatusBadge({ s }: { s: ProposalStatus }) {
  return <Badge variant={STATUS_VARIANT[s] ?? 'neutral'} label={s} />
}

function ReRecordChip({ state }: { state: Proposal['state'] }) {
  if (!state?.re_record) return null
  const ok = state.re_record === 're-recorded'
  return <Badge variant={ok ? 'success' : 'warning'} label={state.re_record} title={ok ? 'Committed recordings carry the accepted text' : 'The accepted text misses the old recordings until a record run refreshes them'} />
}

function StaleChip({ state }: { state: Proposal['state'] }) {
  if (!state?.stale) return null
  return <Badge variant="danger" label="stale" title={state.file_exists ? `The file changed since this proposal (now v${state.current_version ?? '?'})` : 'The target file no longer exists'} />
}

/** Long values fold at CLIP characters with a show-all toggle. */
function Clipped({ text, id }: { text: string; id: string }) {
  const [all, setAll] = useState(false)
  const long = text.length > CLIP
  return (
    <>
      <pre id={id}>{long && !all ? `${text.slice(0, CLIP)}…` : text || <span className="muted">(empty)</span>}</pre>
      {long ? <Button variant="link" size="sm" aria-controls={id} aria-expanded={all} onClick={() => setAll((a) => !a)}>{all ? 'Show less' : `Show all (${text.length.toLocaleString()} characters)`}</Button> : null}
    </>
  )
}

/** Effective mode / provider / model for the prompt-improve stage, as the
 * LLM settings page computes them: the stage override, then the default,
 * then the environment. */
function improveLlm(llm: LlmDescribe | null) {
  const stage = llm?.stages?.find((s) => s.key === 'prompt-improve')
  const env = (llm?.environment ?? {}) as Record<string, unknown>
  const s = (v: unknown) => (v == null || v === '' ? null : String(v))
  const mode = s(llm?.settings?.llm_mode) ?? s(env.effective_mode) ?? s(env.LLM_MODE)
  const provider = s(stage?.effective?.provider) ?? s(llm?.settings?.default?.provider) ?? s(env.LLM_PROVIDER)
  const model = s(stage?.effective?.model) ?? s(llm?.settings?.default?.model) ?? s(env.LLM_MODEL)
  return { mode, provider, model, known: Boolean(llm) }
}

function LlmSentence({ llm }: { llm: ReturnType<typeof improveLlm> }) {
  const target = <span className="mono">{llm.provider ?? '—'}{llm.model ? ` / ${llm.model}` : ''}</span>
  if (!llm.known) return <>A proposal is one real model call through the <span className="mono">prompt-improve</span> stage. LLM settings could not be read, so the effective provider is unknown here.</>
  if (llm.mode === 'replay') return <>In <b>replay</b> mode a proposal is served from a committed recording for {target} — a missing recording fails loudly (502) rather than calling out.</>
  if (llm.mode === 'record') return <>In <b>record</b> mode a proposal is one real model call to {target}, and the response is recorded for replay.</>
  return <>In <b>{llm.mode ?? 'live'}</b> mode a proposal is one real model call to {target}. It is stored as a draft; nothing changes until you accept it.</>
}

/* --- propose ----------------------------------------------------------------- */

type Intent = { target_id: string; correction_ids?: string[]; count: number }

function ProposePanel({ intent, promptSet, days, learnableOnly, llm, onCancel, onDone }: {
  intent: Intent
  promptSet: string
  days: number | undefined
  learnableOnly: boolean
  llm: ReturnType<typeof improveLlm>
  onCancel: () => void
  onDone: (p: Proposal) => void
}) {
  const { fail, notify } = useAdmin()
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<{ status: number; detail: string } | null>(null)

  const go = async () => {
    setBusy(true); setErr(null)
    try {
      const p = await api.learning.propose({
        prompt_set: promptSet, target_id: intent.target_id, days, learnable_only: learnableOnly,
        correction_ids: intent.correction_ids, note: note.trim() || undefined,
      })
      notify(`${p.proposal_id} proposed for ${p.target_id} (${String(p.provenance).toUpperCase()})`)
      onDone(p)
    } catch (e) {
      if (e instanceof ApiError && (e.status === 502 || e.status === 400 || e.status === 404)) setErr({ status: e.status, detail: e.message })
      else fail(e)
    } finally {
      setBusy(false)
    }
  }

  const which = intent.correction_ids
    ? `${intent.count} selected correction${intent.count === 1 ? '' : 's'}`
    : `${intent.count} ${learnableOnly ? 'learnable ' : ''}correction${intent.count === 1 ? '' : 's'} in the window (newest first, at most 40)`

  return (
    <div className="sub-panel" style={{ margin: 16 }}>
      <div className="card-head"><h4>Propose a revision of <span className="mono">{intent.target_id}</span></h4></div>
      <ConfirmPanel
        message={<>Learns from {which}. <LlmSentence llm={llm} /></>}
        confirmLabel={busy ? 'Calling the model…' : 'Propose revision'}
        busy={busy}
        onConfirm={go}
        onCancel={onCancel}
      >
        <Field label="Note" htmlFor="prp-note" optional help="Kept on the proposal; the ledger line is written at acceptance, not now.">
          <input data-autofocus id="prp-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why propose now"
            onKeyDown={(e) => { if (e.key === 'Enter' && !busy) void go() }} />
        </Field>
        {err ? (
          <Notice tone="danger" title={err.status === 502 ? 'The model call did not produce a proposal.' : 'Refused.'}>
            {err.detail}{err.status === 502 && llm.mode === 'replay' ? ' — in replay mode this usually means no committed recording matches; run once with LLM_MODE=record.' : ''}
          </Notice>
        ) : null}
      </ConfirmPanel>
    </div>
  )
}

/* --- corrections --------------------------------------------------------- */

function CorrectionRow({ c, open, checked, highlighted, onToggleOpen, onToggleCheck }: {
  c: Correction
  open: boolean
  checked: boolean
  highlighted: boolean
  onToggleOpen: () => void
  onToggleCheck: () => void
}) {
  const detailId = `cor-${c.correction_id}`
  return (
    <>
      <tr className={highlighted ? 'sel' : checked ? 'edit-row' : ''}>
        <td className="cell-check">
          <input type="checkbox" checked={checked} onChange={onToggleCheck} aria-label={`Select ${c.correction_id}`} />
        </td>
        <td>
          <button type="button" className="expand-btn" aria-expanded={open} aria-controls={detailId} onClick={onToggleOpen} title={open ? 'Hide before / after' : 'Show before / after'}>
            {open ? <ChevronDown aria-hidden="true" /> : <ChevronRight aria-hidden="true" />}
            <span className="mono nowrap">{fmtTime(c.timestamp)}</span>
          </button>
          <span className="sub mono">{c.correction_id}</span>
        </td>
        <td className="mono">{c.run_id}</td>
        <td><Badge variant="neutral" soft label={c.stage} /></td>
        <td>
          <span className="mono">{c.artifact_id || '—'}</span>
          {c.artifact_type ? <span className="sub">{c.artifact_type}</span> : null}
        </td>
        <td className="mono">{c.field || '—'}</td>
        <td>{c.author || <span className="muted">—</span>}{c.source ? <span className="sub">{c.source}</span> : null}</td>
        <td><OriginBadge p={c.original_provenance} /></td>
      </tr>
      {open ? (
        <tr className="cor-detail" id={detailId}>
          <td colSpan={8}>
            <div className="cor-meta">
              <span>skill <span className="mono">{c.skill_id || '—'}</span>{c.skill && c.skill !== c.skill_id ? <> (<span className="mono">{c.skill}</span>)</> : null}</span>
              <span>task <span className="mono">{c.task_id || '—'}</span></span>
              <span>prompt set <span className="mono">{c.prompt_set}</span></span>
            </div>
            <div className="ba">
              <div className="pane before">
                <div className="lbl"><span>What the model wrote</span><OriginBadge p={c.original_provenance} /></div>
                <Clipped id={`${detailId}-before`} text={valueText(c.before)} />
              </div>
              <div className="arrow" aria-hidden="true"><ArrowRight /></div>
              <div className="pane after">
                <div className="lbl"><span>What {c.author || 'the person'} changed it to</span><Badge variant="neutral" mono label="HUMAN" /></div>
                <Clipped id={`${detailId}-after`} text={valueText(c.after)} />
              </div>
            </div>
          </td>
        </tr>
      ) : null}
    </>
  )
}

/* --- proposal drawer ----------------------------------------------------- */

function UsageLine({ u }: { u: Proposal['llm']['usage'] }) {
  const n = (v: unknown) => (typeof v === 'number' ? v.toLocaleString() : null)
  const parts = [
    ['input', n(u?.input_tokens)], ['output', n(u?.output_tokens)], ['cache read', n(u?.cache_read_tokens)], ['cache write', n(u?.cache_write_tokens)],
  ] as const
  return (
    <span>
      {parts.map(([k, v], i) => <span key={k}>{i ? ' · ' : ''}{k} {v ?? <span className="na">unreported</span>}</span>)}
    </span>
  )
}

function ProposalDrawer({ set, id, onClose, onChanged, onShowCorrections, onProposeAgain }: {
  set: string
  id: string
  onClose: () => void
  onChanged: () => void
  onShowCorrections: (target: string, ids: string[]) => void
  onProposeAgain: (target: string) => void
}) {
  const { fail, notify } = useAdmin()
  const { data: p, setData, error, loading, reload } = useLoad(() => api.learning.proposal(set, id), [set, id])
  const [decision, setDecision] = useState<'accept' | 'reject' | null>(null)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<{ status: number; detail: string } | null>(null)

  const decide = async () => {
    if (!p || !decision) return
    if (!note.trim()) return
    setBusy(true); setErr(null)
    try {
      const res = decision === 'accept'
        ? await api.learning.accept(set, id, note.trim())
        : await api.learning.reject(set, id, note.trim())
      notify(decision === 'accept' ? `${id} accepted — ${res.target_id} is now v${res.resulting_version ?? '?'}` : `${id} rejected`)
      setData({ ...p, ...res })
      setDecision(null); setNote('')
      onChanged()
    } catch (e) {
      if (e instanceof ApiError && (e.status === 409 || e.status === 400)) setErr({ status: e.status, detail: e.message })
      else fail(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <DetailDrawer
      ariaLabel={`Proposal ${id}`}
      title={<span className="inline"><span className="mono">{id}</span>{p ? <StatusBadge s={p.status} /> : null}{p ? <ProposalProvenance p={p.provenance} /> : null}</span>}
      subtitle={p ? <>Revision of <span className="mono">{p.target_id}</span> ({p.target_layer}) in <span className="mono">{p.prompt_set}</span>, from v{p.base_version}</> : undefined}
      onClose={onClose}
    >
      {loading && !p ? <Loading what="Loading proposal" /> : null}
      {error ? <LoadError what={`proposal ${id}`} error={error} onRetry={reload} /> : null}
      {p ? (
        <>
          <div className="chips">
            <Badge variant="neutral" label={`v${p.base_version} → ${p.resulting_version != null ? `v${p.resulting_version}` : p.status === 'proposed' ? 'proposed' : '—'}`} title="Base version → resulting version" />
            <StaleChip state={p.state} />
            <ReRecordChip state={p.state} />
            {p.skill ? <Badge variant="neutral" mono label={p.skill} title="The improver's own skill and version" /> : null}
          </div>

          {p.state?.stale && p.status === 'proposed' ? (
            <Notice tone="warning" title="Stale."
              actions={<Button variant="secondary" size="sm" onClick={() => onProposeAgain(p.target_id)}>Propose again from the current text</Button>}>
              {p.state.file_exists
                ? <><span className="mono">{p.target_id}</span> changed since this proposal was made (v{p.base_version} → v{p.state.current_version ?? '?'}). Accepting will be refused.</>
                : <>The target file no longer exists in this set.</>}
            </Notice>
          ) : null}

          <div className="kv tight">
            <span className="k">Proposed by</span><span className="v">{p.created_by || '—'} · {fmtTime(p.created_at)}{p.note ? <span className="sub">{p.note}</span> : null}</span>
            {p.status !== 'proposed' ? (
              <>
                <span className="k">{p.status === 'accepted' ? 'Accepted by' : 'Rejected by'}</span>
                <span className="v">{p.decided_by || '—'} · {fmtTime(p.decided_at)}{p.decision_note ? <span className="sub">{p.decision_note}</span> : null}</span>
              </>
            ) : null}
            <span className="k">Model</span><span className="v mono">{p.llm?.provider ?? '—'}{p.llm?.model ? ` / ${p.llm.model}` : ''}</span>
            <span className="k">Usage</span><span className="v small"><UsageLine u={p.llm?.usage ?? {}} /></span>
          </div>

          <div>
            <h4>Rationale</h4>
            <p className="pre" style={{ marginTop: 4 }}>{p.rationale || <span className="muted">The model gave no rationale.</span>}</p>
          </div>

          <div>
            <h4>What it learned</h4>
            {p.learned?.length ? <ul className="lesson-list">{p.learned.map((l, i) => <li key={i}>{l}</li>)}</ul> : <div className="hint">No lessons listed.</div>}
          </div>

          {p.warnings?.length ? (
            <Notice tone="warning" title={`${p.warnings.length} warning${p.warnings.length === 1 ? '' : 's'} from validation.`}>
              <ul className="plain-list">{p.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
            </Notice>
          ) : null}

          <div>
            <h4>Corrections used</h4>
            <div className="chips" style={{ marginTop: 6 }}>
              {p.corrections?.length ? p.corrections.map((cid) => (
                <Button key={cid} variant="link" className="mono" size="sm" onClick={() => onShowCorrections(p.target_id, p.corrections)} title="Show these in the corrections table">{cid}</Button>
              )) : <span className="hint">None recorded.</span>}
            </div>
          </div>

          <div>
            <h4>Changes — current → proposed</h4>
            <div style={{ marginTop: 8 }}>
              <DiffView text={p.diff ?? ''} />
            </div>
          </div>

          {p.status === 'proposed' ? (
            <div className="prp-decision">
              {decision ? (
                <ConfirmPanel
                  message={decision === 'accept'
                    ? <>Accepting records the proposed body as <b>v{(p.state?.current_version ?? p.base_version) + 1}</b> of <span className="mono">{p.target_id}</span> through the ordinary ledger. Committed recordings that hash the old text will miss until a record run refreshes them.</>
                    : <>Rejecting keeps <span className="mono">{p.target_id}</span> at v{p.state?.current_version ?? p.base_version} and closes this proposal.</>}
                  confirmLabel={decision === 'accept' ? 'Accept and record version' : 'Reject proposal'}
                  busy={busy}
                  onConfirm={decide}
                  onCancel={() => { setDecision(null); setErr(null) }}
                >
                  <Field label="Note" htmlFor="prp-decide-note" required help={decision === 'accept' ? 'Becomes the ledger line, together with the rationale.' : 'Kept on the proposal record.'}>
                    <input data-autofocus id="prp-decide-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder={decision === 'accept' ? 'Why this revision is right' : 'Why not'}
                      onKeyDown={(e) => { if (e.key === 'Enter' && note.trim() && !busy) void decide() }} />
                  </Field>
                  {err ? (
                    <Notice tone="danger" title={err.status === 409 ? 'Refused by current state.' : 'Refused.'}
                      actions={err.status === 409 ? <Button variant="secondary" size="sm" onClick={() => onProposeAgain(p.target_id)}>Propose again</Button> : undefined}>
                      {err.detail}
                    </Notice>
                  ) : null}
                </ConfirmPanel>
              ) : (
                <div className="btn-row">
                  <Button variant="primary" icon={<Check />} onClick={() => { setDecision('accept'); setErr(null) }} disabled={Boolean(p.state?.stale)} title={p.state?.stale ? 'Stale — propose again from the current text' : 'Record the proposed body as a new version'}>Accept</Button>
                  <Button variant="secondary" icon={<X />} onClick={() => { setDecision('reject'); setErr(null) }}>Reject</Button>
                  <span className="hint">Either decision needs a note and is audited.</span>
                </div>
              )}
            </div>
          ) : null}
        </>
      ) : null}
    </DetailDrawer>
  )
}

/* --- page ------------------------------------------------------------------- */

type OverviewState = { data: LearningOverview | null; missing: boolean }

export function LearningPage() {
  const { goTo } = useAdmin()
  const [promptSet, setPromptSet] = useState('default')
  const [windowKey, setWindowKey] = useState('30')
  const [includeAll, setIncludeAll] = useState(false)
  const [stage, setStage] = useState('')
  const [target, setTarget] = useState('')
  const [status, setStatus] = useState('')
  const [open, setOpen] = useState<Set<string>>(new Set())
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [highlight, setHighlight] = useState<Set<string>>(new Set())
  const [selTarget, setSelTarget] = useState('')
  const [intent, setIntent] = useState<(Intent & { origin: 'target' | 'selection' }) | null>(null)
  const [drawer, setDrawer] = useState<string | null>(null)
  const correctionsRef = useRef<HTMLDivElement>(null)
  const days = daysOf(windowKey)

  const sets = useLoad(() => api.promptSets.list())
  const llmDesc = useLoad(() => api.llm.describe().catch(() => null))
  const ov = useLoad<OverviewState>(() => api.learning.overview(promptSet, days).then((data) => ({ data, missing: false })).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return { data: null, missing: true }
    throw err
  }), [promptSet, days])
  const cors = useLoad<Correction[] | null>(() => ov.data?.missing ? Promise.resolve(null) : api.learning.corrections({ promptSet, days, stage, targetId: target, learnableOnly: !includeAll }), [promptSet, days, stage, target, includeAll, ov.data?.missing])
  const props = useLoad<Proposal[] | null>(() => ov.data?.missing ? Promise.resolve(null) : api.learning.proposals(promptSet, status), [promptSet, status, ov.data?.missing])

  useEffect(() => {
    if (sets.data && !sets.data.some((s) => s.name === promptSet)) setPromptSet(sets.data.find((s) => s.is_default)?.name ?? sets.data[0]?.name ?? 'default')
  }, [sets.data, promptSet])
  useEffect(() => { setSelected(new Set()); setSelTarget('') }, [promptSet, days, stage, target, includeAll])

  const llm = useMemo(() => improveLlm(llmDesc.data ?? null), [llmDesc.data])
  const d = ov.data?.data ?? null
  const rows = cors.data ?? []
  const stages = useMemo(() => (d?.corrections.by_stage ?? []).map((s) => s.stage), [d])
  const targets = d?.targets ?? []

  const selectedRows = useMemo(() => rows.filter((r) => selected.has(r.correction_id)), [rows, selected])
  /** Targets every selected correction shares — a proposal is for one file. */
  const candidates = useMemo(() => {
    if (!selectedRows.length) return []
    let common: string[] | null = null
    for (const r of selectedRows) {
      const mine = new Set<string>([r.skill_id, r.task_id].filter(Boolean))
      common = common ? common.filter((x) => mine.has(x)) : [...mine]
    }
    return common ?? []
  }, [selectedRows])
  useEffect(() => { if (!candidates.includes(selTarget)) setSelTarget(candidates[0] ?? '') }, [candidates, selTarget])

  const refreshAll = useCallback(() => { ov.reload(); cors.reload(); props.reload() }, [ov, cors, props])
  const onProposed = useCallback((p: Proposal) => { setIntent(null); setSelected(new Set()); ov.reload(); props.reload(); setDrawer(p.proposal_id) }, [ov, props])
  const showCorrections = useCallback((tgt: string, ids: string[]) => {
    setDrawer(null); setStage(''); setTarget(tgt); setWindowKey('all'); setIncludeAll(true)
    setHighlight(new Set(ids)); setOpen(new Set())
    setTimeout(() => correctionsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 220)
  }, [])
  const proposeAgain = useCallback((tgt: string) => {
    setDrawer(null)
    setIntent({ target_id: tgt, count: targets.find((t) => t.target_id === tgt)?.[includeAll ? 'corrections_total' : 'corrections_learnable'] ?? 0, origin: 'target' })
  }, [targets, includeAll])

  const toggle = (set: Set<string>, id: string) => { const n = new Set(set); if (n.has(id)) n.delete(id); else n.add(id); return n }
  const allChecked = rows.length > 0 && rows.every((r) => selected.has(r.correction_id))

  const header = (
    <PageHeader
      title="Correction Learning"
      description="The product learns from people who corrected its output. Corrections are recorded by the engine; a proposal is one real model call; nothing is applied until you accept it. None of this is visible in the Control Centre."
      actions={<>
        <Badge variant="info" mono label="RULE_BASED" title="Counts and targets are derived from the runs' correction ledgers" />
        <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={refreshAll} disabled={ov.loading}>Refresh</Button>
      </>}
    />
  )

  const filters = (
    <div className="filter-row">
      <Field label="Prompt set" htmlFor="lrn-set">
        <select id="lrn-set" value={promptSet} onChange={(e) => setPromptSet(e.target.value)} disabled={!sets.data}>
          {(sets.data ?? [{ name: promptSet, is_default: promptSet === 'default' }]).map((s) => <option key={s.name} value={s.name}>{s.name}{s.is_default ? ' (default)' : ''}</option>)}
        </select>
      </Field>
      <Field label="Window" htmlFor="lrn-days">
        <select id="lrn-days" value={windowKey} onChange={(e) => setWindowKey(e.target.value)}>
          {WINDOWS.map((w) => <option key={w.value} value={w.value}>{w.label}</option>)}
        </select>
      </Field>
      <div className="fld-group">
        <label className="check" htmlFor="lrn-all"><input id="lrn-all" type="checkbox" checked={includeAll} onChange={(e) => setIncludeAll(e.target.checked)} /> Include non-learnable corrections</label>
        <div className="help">Corrections of seeded or rule-based originals are not model output.</div>
      </div>
    </div>
  )

  if (ov.loading && !ov.data) return <>{header}{filters}<Loading what="Reading the correction ledgers" /></>
  if (ov.error) return <>{header}{filters}<LoadError what="correction learning" error={ov.error} onRetry={ov.reload} /></>
  if (ov.data?.missing || !d) {
    return (
      <>
        {header}{filters}
        <Empty title="Correction learning is not available on this backend yet"
          hint={<>The admin API answered 404 for <span className="mono">GET /api/admin/learning/overview</span>. Until the routes in docs/admin-api.md land there is nothing to learn from here.</>}
          action={<div className="btn-row"><Button variant="secondary" size="sm" onClick={ov.reload}>Check again</Button><Button variant="ghost" size="sm" onClick={() => goTo('prompt_sets')}>Open prompt sets</Button></div>} />
      </>
    )
  }

  const noCorrectionsHint = (
    <>Corrections appear when someone edits a story, the extracted requirement or an architecture proposal, or adds a business rule the analysis missed, in the Control Centre. The engine records what the model wrote and what the person changed it to.</>
  )

  return (
    <>
      {header}
      {filters}

      <div className="tiles">
        <Tile label="Corrections" value={d.corrections.total} sub={windowKey === 'all' ? 'all time' : `last ${windowKey} days`} />
        <Tile label="Learnable" value={d.corrections.learnable} sub="originals that were model output" />
        <Tile label="Proposals pending" value={d.proposals.proposed} sub="awaiting your decision" />
        <Tile label="Accepted" value={d.proposals.accepted} sub="recorded as new versions" />
        <Tile label="Rejected" value={d.proposals.rejected} />
      </div>

      <SectionHead title="Learning targets" description="The skill or task file that produced each corrected original. A proposal rewrites one file from its corrections; you decide whether it becomes a version." />
      <Card flush>
        <div className="learn-llm">
          <Sparkles aria-hidden="true" />
          <div className="grow">
            <LlmSentence llm={llm} />
            {llm.known ? <> Stage <span className="mono">prompt-improve</span>, mode <span className="mono">{llm.mode ?? '(unset)'}</span>.</> : null}
          </div>
          <Button variant="ghost" size="sm" icon={<ArrowRight />} onClick={() => goTo('llm')}>LLM settings</Button>
        </div>
        {targets.length === 0 ? (
          <Empty bare title="Nothing to learn from yet" hint={d.corrections.total > 0 && !includeAll
            ? <>{d.corrections.total} correction{d.corrections.total === 1 ? '' : 's'} in this window, none of a model output. Tick <em>Include non-learnable corrections</em> to see them — but they cannot teach a prompt anything.</>
            : noCorrectionsHint} />
        ) : (
          <TableWrap label="Learning targets">
            <table>
              <thead>
                <tr>
                  <th>Target</th><th>Stage</th><th className="num">Learnable</th><th className="num">Total</th><th>Last correction</th><th>Version</th><th className="num">Pending</th><th className="actions-col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {targets.map((t: LearningTarget) => {
                  const usable = includeAll ? t.corrections_total : t.corrections_learnable
                  const learnableLayer = t.layer === 'skill' || t.layer === 'task'
                  const why = !learnableLayer ? `${t.layer} files are not learnable — only skills and tasks`
                    : usable === 0 ? 'No learnable corrections for this target. Tick "Include non-learnable corrections" to propose from seeded or rule-based originals anyway.'
                      : `Propose a revision from ${usable} correction${usable === 1 ? '' : 's'} — one real model call`
                  return (
                    <tr key={t.target_id}>
                      <td>
                        <span className="inline"><span className="mono">{t.target_id}</span><Badge variant={t.layer === 'skill' ? 'accent' : 'neutral'} label={t.layer} /></span>
                      </td>
                      <td>{t.stage ? <Badge variant="neutral" soft label={t.stage} /> : <span className="muted">—</span>}</td>
                      <td className="num">{t.corrections_learnable}</td>
                      <td className="num">{t.corrections_total}</td>
                      <td className="mono nowrap">{fmtTime(t.last_correction)}</td>
                      <td><Badge variant="success" label={`v${t.version}`} /></td>
                      <td className="num">{t.proposals_pending}</td>
                      <td className="actions-col">
                        <span title={why}>
                          <Button variant="primary" size="sm" icon={<GraduationCap />} disabled={!learnableLayer || usable === 0}
                            onClick={() => setIntent({ target_id: t.target_id, count: usable, origin: 'target' })}>
                            Propose revision
                          </Button>
                        </span>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </TableWrap>
        )}
        {intent?.origin === 'target' ? (
          <ProposePanel intent={intent} promptSet={promptSet} days={days} learnableOnly={!includeAll} llm={llm} onCancel={() => setIntent(null)} onDone={onProposed} />
        ) : null}
      </Card>

      <div ref={correctionsRef}>
        <SectionHead title="Corrections" description="Newest first. Expand a row to read what the model wrote beside what the person changed it to; select rows to propose from a specific set."
          right={<>
            <Field label="Stage" htmlFor="lrn-stage">
              <select id="lrn-stage" value={stage} onChange={(e) => setStage(e.target.value)}>
                <option value="">All stages</option>
                {stages.map((s) => <option key={s} value={s}>{s}</option>)}
              </select>
            </Field>
            <Field label="Target" htmlFor="lrn-target">
              <select id="lrn-target" value={target} onChange={(e) => setTarget(e.target.value)}>
                <option value="">All targets</option>
                {(d.corrections.by_target ?? []).map((t) => <option key={t.target_id} value={t.target_id}>{t.target_id}</option>)}
                {target && !(d.corrections.by_target ?? []).some((t) => t.target_id === target) ? <option value={target}>{target}</option> : null}
              </select>
            </Field>
          </>} />
      </div>
      <Card flush>
        {highlight.size ? (
          <div className="sel-bar" role="status">
            <span><b>{highlight.size}</b> correction{highlight.size === 1 ? '' : 's'} used by the proposal are highlighted{rows.filter((r) => highlight.has(r.correction_id)).length < highlight.size ? ' — some fall outside the current filters' : ''}.</span>
            <Button variant="ghost" size="sm" onClick={() => setHighlight(new Set())}>Clear highlight</Button>
          </div>
        ) : null}
        {selected.size ? (
          <div className="sel-bar">
            <span><b>{selected.size}</b> selected</span>
            {candidates.length ? (
              <>
                <label className="check" htmlFor="lrn-seltarget" style={{ minHeight: 0 }}>Propose for</label>
                <select id="lrn-seltarget" value={selTarget} onChange={(e) => setSelTarget(e.target.value)} aria-label="Target file for the proposal">
                  {candidates.map((c) => <option key={c} value={c}>{c}</option>)}
                </select>
                <Button variant="primary" size="sm" icon={<GraduationCap />} disabled={!selTarget || Boolean(intent)}
                  onClick={() => setIntent({ target_id: selTarget, correction_ids: [...selected], count: selected.size, origin: 'selection' })}>
                  Propose from selected
                </Button>
              </>
            ) : <span className="danger">The selected corrections share no skill or task — a proposal rewrites one file.</span>}
            {selectedRows.some((r) => !r.learnable) ? <span className="hint">Includes non-learnable corrections; the server needs <span className="mono">learnable_only=false</span>, which the toggle above sets.</span> : null}
            <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Clear</Button>
          </div>
        ) : null}
        {intent?.origin === 'selection' ? (
          <ProposePanel intent={intent} promptSet={promptSet} days={days} learnableOnly={!includeAll} llm={llm} onCancel={() => setIntent(null)} onDone={onProposed} />
        ) : null}
        {cors.loading && !cors.data ? <Loading what="Loading corrections" /> : null}
        {cors.error ? <div style={{ padding: 16 }}><LoadError what="corrections" error={cors.error} onRetry={cors.reload} /></div> : null}
        {cors.data && rows.length === 0 ? (
          <Empty bare title={d.corrections.total > 0 ? 'No corrections match these filters' : 'No corrections yet'}
            hint={d.corrections.total > 0
              ? (!includeAll && d.corrections.learnable === 0 ? <>{d.corrections.total} in this window, none of a model output — tick <em>Include non-learnable corrections</em> to see them.</> : 'Widen the window or clear the stage and target filters.')
              : noCorrectionsHint} />
        ) : null}
        {rows.length > 0 ? (
          <TableWrap label="Corrections">
            <table className="cor-table">
              <thead>
                <tr>
                  <th className="cell-check"><input type="checkbox" checked={allChecked} onChange={() => setSelected(allChecked ? new Set() : new Set(rows.map((r) => r.correction_id)))} aria-label="Select every correction shown" /></th>
                  <th>When</th><th>Run</th><th>Stage</th><th>Artifact</th><th>Field</th><th>Author</th><th>Original</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <CorrectionRow key={c.correction_id} c={c} open={open.has(c.correction_id)} checked={selected.has(c.correction_id)} highlighted={highlight.has(c.correction_id)}
                    onToggleOpen={() => setOpen((s) => toggle(s, c.correction_id))} onToggleCheck={() => setSelected((s) => toggle(s, c.correction_id))} />
                ))}
              </tbody>
            </table>
          </TableWrap>
        ) : null}
        {rows.length > 0 ? <div className="table-foot" style={{ padding: '10px 16px' }}><span>{rows.length} correction{rows.length === 1 ? '' : 's'}{includeAll ? '' : ', learnable only'}</span><span>{d.corrections.runs.length} run{d.corrections.runs.length === 1 ? '' : 's'} with corrections in this window</span></div> : null}
      </Card>

      <SectionHead title="Proposals" description="Every proposal is a genuine model call, stored as a draft. Accepting records a new version through the set's ledger; rejecting closes it. Both are audited."
        right={
          <Field label="Status" htmlFor="lrn-status">
            <select id="lrn-status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="">All</option>
              <option value="proposed">Proposed</option>
              <option value="accepted">Accepted</option>
              <option value="rejected">Rejected</option>
            </select>
          </Field>
        } />
      <Card flush>
        {props.loading && !props.data ? <Loading what="Loading proposals" /> : null}
        {props.error ? <div style={{ padding: 16 }}><LoadError what="proposals" error={props.error} onRetry={props.reload} /></div> : null}
        {props.data && props.data.length === 0 ? (
          <Empty bare title={status ? `No ${status} proposals` : 'No proposals yet'} hint={status ? 'Clear the status filter to see the rest.' : 'Propose a revision from a learning target above. Each proposal is one real model call and waits here for your decision.'} />
        ) : null}
        {props.data && props.data.length > 0 ? (
          <TableWrap label="Proposals">
            <table>
              <thead>
                <tr><th>Proposal</th><th>Target</th><th>Status</th><th>Provenance</th><th>Proposed by</th><th>Versions</th><th>State</th><th className="actions-col">Actions</th></tr>
              </thead>
              <tbody>
                {props.data.map((p) => (
                  <tr key={p.proposal_id}>
                    <td><Button variant="link" className="mono" onClick={() => setDrawer(p.proposal_id)}>{p.proposal_id}</Button><span className="sub">{p.corrections?.length ?? 0} correction{p.corrections?.length === 1 ? '' : 's'}</span></td>
                    <td><span className="inline"><span className="mono">{p.target_id}</span><Badge variant={p.target_layer === 'skill' ? 'accent' : 'neutral'} label={p.target_layer} /></span></td>
                    <td><StatusBadge s={p.status} /></td>
                    <td><ProposalProvenance p={p.provenance} /></td>
                    <td>{p.created_by || '—'}<span className="sub mono">{fmtTime(p.created_at)}</span></td>
                    <td className="nowrap">v{p.base_version} → {p.resulting_version != null ? `v${p.resulting_version}` : <span className="muted">—</span>}</td>
                    <td><span className="chips"><StaleChip state={p.state} /><ReRecordChip state={p.state} />{!p.state?.stale && !p.state?.re_record ? <span className="muted">—</span> : null}</span></td>
                    <td className="actions-col"><Button variant={p.status === 'proposed' ? 'primary' : 'secondary'} size="sm" onClick={() => setDrawer(p.proposal_id)}>{p.status === 'proposed' ? 'Review' : 'Open'}</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </TableWrap>
        ) : null}
      </Card>

      {drawer ? (
        <ProposalDrawer key={drawer} set={promptSet} id={drawer} onClose={() => setDrawer(null)} onChanged={() => { ov.reload(); props.reload() }}
          onShowCorrections={showCorrections} onProposeAgain={proposeAgain} />
      ) : null}
    </>
  )
}
