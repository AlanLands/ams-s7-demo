import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowDown, ArrowUp, CircleDot, OctagonPause, RefreshCw, Save, ShieldCheck, Trash2, Undo2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, Empty, Field, IconButton, Loading, Notice, PageHeader } from '../components/ui'
import { VersionChip, VersionsCard } from '../components/Versions'
import { useAdmin } from '../state/AdminContext'
import type { ActionInfo, PlaybookActions, PlaybookDetail, PlaybookStep, SaveResult, SetSummary, StepKind } from '../types'

/* Playbooks are the third file-backed layer: JSON steps the self-healing
 * engine walks (factory/self_heal.py). This page edits them as steps,
 * not text — every choice is drawn from the engine's own catalogue, and
 * the server's dry-run validator has the last word before a save. */

const KEBAB = /^[a-z0-9]+(-[a-z0-9]+)*$/

type Draft = PlaybookStep & { _key: number; _removed?: boolean }

let keySeq = 1
const draft = (s: PlaybookStep): Draft => ({ ...s, _key: keySeq++ })

/** The step as the server sees it: kind-appropriate fields only, no UI keys. */
function clean(d: Draft): PlaybookStep {
  const out: PlaybookStep = { step_id: d.step_id.trim(), kind: d.kind, action: d.action, label: d.label.trim() }
  if (d.detail?.trim()) out.detail = d.detail.trim()
  if (d.kind === 'gate' && d.role) out.role = d.role
  if (d.kind === 'mechanical' && d.as_role) out.as_role = d.as_role
  return out
}
const live = (steps: Draft[]) => steps.filter((s) => !s._removed)
const cleanAll = (steps: Draft[]) => live(steps).map(clean)

type StepErrors = Partial<Record<'step_id' | 'action' | 'label' | 'role', string>>

function stepErrors(d: Draft, all: Draft[], cat: PlaybookActions): StepErrors {
  const e: StepErrors = {}
  const id = d.step_id.trim()
  if (!id) e.step_id = 'A step id is required.'
  else if (!KEBAB.test(id)) e.step_id = 'kebab-case only: lowercase letters, digits and single hyphens.'
  else if (live(all).some((o) => o !== d && o.step_id.trim() === id)) e.step_id = 'Another step already uses this id.'
  const pool = cat[d.kind] ?? []
  if (!d.action) e.action = 'Choose an action.'
  else if (!pool.some((a) => a.action === d.action)) e.action = `Not a ${d.kind} action in the catalogue.`
  if (!d.label.trim()) e.label = 'A label is required.'
  if (d.kind === 'gate') {
    const info = pool.find((a) => a.action === d.action)
    if (!d.role) e.role = 'A gate needs the role that records it.'
    else if (info && info.permitted_roles.length && !info.permitted_roles.includes(d.role)) e.role = 'This role does not hold that action.'
  }
  return e
}

function roleLabel(cat: PlaybookActions, id: string | undefined): string {
  if (!id) return ''
  return cat.roles.find((r) => r.id === id)?.label ?? id
}

/** The engine's own words for what a step does when the playbook reaches it. */
function engineSentence(d: Draft, cat: PlaybookActions): string {
  if (d.kind === 'gate') {
    const who = d.role ? roleLabel(cat, d.role) : 'the named role'
    return `Stops the playbook until ${who} records ${d.action || 'the action'}.`
  }
  return d.as_role ? `Runs immediately when reached, acting as ${roleLabel(cat, d.as_role)}.` : 'Runs immediately when reached.'
}

function KindToggle({ value, onChange, id }: { value: StepKind; onChange: (k: StepKind) => void; id: string }) {
  const opts: { k: StepKind; label: string; icon: React.ReactNode }[] = [
    { k: 'mechanical', label: 'Mechanical', icon: <CircleDot aria-hidden="true" /> },
    { k: 'gate', label: 'Gate', icon: <OctagonPause aria-hidden="true" /> },
  ]
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    onChange(value === 'gate' ? 'mechanical' : 'gate')
  }
  return (
    <div className="seg" role="radiogroup" aria-labelledby={`${id}-kind-label`} onKeyDown={onKey}>
      {opts.map((o) => (
        <button key={o.k} type="button" role="radio" aria-checked={value === o.k} tabIndex={value === o.k ? 0 : -1} onClick={() => onChange(o.k)}>
          {o.icon}{o.label}
        </button>
      ))}
    </div>
  )
}

function StepCard({ step, index, count, all, cat, onChange, onMove, onRemove, showErrors }: {
  step: Draft
  index: number
  count: number
  all: Draft[]
  cat: PlaybookActions
  onChange: (next: Draft) => void
  onMove: (dir: -1 | 1) => void
  onRemove: () => void
  showErrors: boolean
}) {
  const id = `st-${step._key}`
  const pool: ActionInfo[] = cat[step.kind] ?? []
  const info = pool.find((a) => a.action === step.action)
  const errs = stepErrors(step, all, cat)
  const err = (k: keyof StepErrors) => (showErrors ? errs[k] : undefined)
  const gateRoles = step.kind === 'gate'
    ? (info?.permitted_roles.length ? info.permitted_roles : cat.roles.map((r) => r.id))
    : []

  const setKind = (k: StepKind) => {
    if (k === step.kind) return
    const first = (cat[k] ?? [])[0]
    onChange({ ...step, kind: k, action: first?.action ?? '', role: k === 'gate' ? first?.default_role ?? undefined : undefined, as_role: undefined })
  }
  const setAction = (action: string) => {
    const next = pool.find((a) => a.action === action)
    const role = step.kind === 'gate'
      ? (next?.default_role ?? (next?.permitted_roles.includes(step.role ?? '') ? step.role : undefined))
      : undefined
    onChange({ ...step, action, role: role ?? undefined })
  }

  return (
    <li className={`pb-step ${step.kind}`} aria-label={`Step ${index + 1} of ${count}: ${step.label || step.step_id || 'new step'}`}>
      <span className="marker" aria-hidden="true">{index + 1}</span>
      <div className="pb-step-head">
        <div className="inline">
          <Badge variant={step.kind === 'gate' ? 'warning' : 'neutral'} label={step.kind === 'gate' ? 'Gate' : 'Mechanical'} icon={step.kind === 'gate' ? <OctagonPause aria-hidden="true" /> : <CircleDot aria-hidden="true" />} />
          {step.step_id ? <span className="mono">{step.step_id}</span> : <span className="hint">unnamed step</span>}
        </div>
        <div className="cell-actions">
          <IconButton size="sm" label={`Move step ${index + 1} up`} icon={<ArrowUp />} onClick={() => onMove(-1)} disabled={index === 0} />
          <IconButton size="sm" label={`Move step ${index + 1} down`} icon={<ArrowDown />} onClick={() => onMove(1)} disabled={index === count - 1} />
          <IconButton size="sm" label={`Remove step ${index + 1}`} icon={<Trash2 />} onClick={onRemove} />
        </div>
      </div>

      <div className="pb-grid">
        <Field label="Step id" htmlFor={`${id}-id`} required error={err('step_id')} help="kebab-case; unique within the playbook.">
          <input id={`${id}-id`} type="text" className={`mono-input${err('step_id') ? ' invalid' : ''}`} value={step.step_id} spellCheck={false} autoComplete="off"
            aria-invalid={Boolean(err('step_id'))} onChange={(e) => onChange({ ...step, step_id: e.target.value })} placeholder="e.g. accept-architecture" />
        </Field>
        <div className="fld-group">
          <span className="fld" id={`${id}-kind-label`}>Kind</span>
          <KindToggle id={id} value={step.kind} onChange={setKind} />
          <div className="help">{step.kind === 'gate' ? 'A human records an action before the playbook continues.' : 'The engine runs it and moves on.'}</div>
        </div>
        <Field label="Action" htmlFor={`${id}-action`} required error={err('action')} help={info ? info.description : `${pool.length} ${step.kind} action${pool.length === 1 ? '' : 's'} in the catalogue.`}>
          <select id={`${id}-action`} value={step.action} aria-invalid={Boolean(err('action'))} onChange={(e) => setAction(e.target.value)}>
            {!step.action && <option value="">Choose an action…</option>}
            {pool.map((a) => <option key={a.action} value={a.action}>{a.label || a.action} ({a.action})</option>)}
          </select>
        </Field>
        {step.kind === 'gate' ? (
          <Field label="Recorded by" htmlFor={`${id}-role`} required error={err('role')} help={info?.default_role ? `${roleLabel(cat, info.default_role)} normally signs this.` : 'Only roles that hold the action are offered.'}>
            <select id={`${id}-role`} value={step.role ?? ''} aria-invalid={Boolean(err('role'))} onChange={(e) => onChange({ ...step, role: e.target.value || undefined })}>
              {!step.role && <option value="">Choose a role…</option>}
              {gateRoles.map((r) => <option key={r} value={r}>{roleLabel(cat, r)}</option>)}
            </select>
          </Field>
        ) : (
          <Field label="Acting as" htmlFor={`${id}-as`} optional help="The role the engine acts under while running this step.">
            <select id={`${id}-as`} value={step.as_role ?? ''} onChange={(e) => onChange({ ...step, as_role: e.target.value || undefined })}>
              <option value="">Engine (no role)</option>
              {cat.roles.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
            </select>
          </Field>
        )}
        <Field label="Label" htmlFor={`${id}-label`} required className="full" error={err('label')}>
          <input id={`${id}-label`} type="text" className={err('label') ? 'invalid' : ''} value={step.label} aria-invalid={Boolean(err('label'))}
            onChange={(e) => onChange({ ...step, label: e.target.value })} placeholder="What this step does, as the change card shows it" />
        </Field>
        <Field label="Detail" htmlFor={`${id}-detail`} optional className="full">
          <textarea id={`${id}-detail`} value={step.detail ?? ''} rows={2} onChange={(e) => onChange({ ...step, detail: e.target.value })} placeholder="Why this step is here — shown under the label on the change card" />
        </Field>
      </div>

      <div className={`pb-engine ${step.kind}`}>
        {step.kind === 'gate' ? <OctagonPause aria-hidden="true" /> : <CircleDot aria-hidden="true" />}
        <span>{engineSentence(step, cat)}</span>
      </div>
    </li>
  )
}

function PlaybookPanel({ set, id, isDefault, cat, onChanged }: { set: string; id: string; isDefault: boolean; cat: PlaybookActions; onChanged: () => void }) {
  const { run, notify, busy } = useAdmin()
  const { data: pb, setData: setPb, error, loading, reload } = useLoad(() => api.playbooks.detail(set, id), [set, id])
  const [steps, setSteps] = useState<Draft[]>([])
  const [trigger, setTrigger] = useState('')
  const [stage, setStage] = useState('')
  const [note, setNote] = useState('')
  const [showErrors, setShowErrors] = useState(false)
  const [validation, setValidation] = useState<{ ok: boolean; problems: string[]; warnings: string[] } | null>(null)
  const [rawOpen, setRawOpen] = useState(false)
  const noteRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (!pb) return
    setSteps((pb.steps ?? []).map(draft))
    setTrigger(pb.trigger ?? '')
    setStage(pb.stage ?? '')
    setNote('')
    setShowErrors(false)
    setValidation(null)
  }, [pb])

  const current = useMemo(() => cleanAll(steps), [steps])
  const baseline = useMemo(() => JSON.stringify((pb?.steps ?? []).map((s) => clean(draft(s)))), [pb])
  const dirty = pb ? JSON.stringify(current) !== baseline || trigger !== (pb.trigger ?? '') || stage !== (pb.stage ?? '') : false
  const problems = useMemo(() => live(steps).map((s) => stepErrors(s, steps, cat)).filter((e) => Object.keys(e).length > 0), [steps, cat])
  const clientOk = live(steps).length > 0 && problems.length === 0
  const firstIsAssess = live(steps)[0]?.action === 'assess_impact'

  const raw = useMemo(() => JSON.stringify({ change_type: pb?.change_type ?? id, trigger, stage, steps: current }, null, 2), [pb, id, trigger, stage, current])

  const update = (key: number, next: Draft) => setSteps((all) => all.map((s) => (s._key === key ? next : s)))
  const move = (key: number, dir: -1 | 1) => setSteps((all) => {
    const vis = all.filter((s) => !s._removed)
    const i = vis.findIndex((s) => s._key === key)
    const j = i + dir
    if (i < 0 || j < 0 || j >= vis.length) return all
    const a = all.indexOf(vis[i]), b = all.indexOf(vis[j])
    const out = [...all]
    ;[out[a], out[b]] = [out[b], out[a]]
    return out
  })
  const remove = (key: number) => setSteps((all) => all.map((s) => (s._key === key ? { ...s, _removed: true } : s)))
  const restore = (key: number) => setSteps((all) => all.map((s) => (s._key === key ? { ...s, _removed: false } : s)))
  const purge = (key: number) => setSteps((all) => all.filter((s) => s._key !== key))
  const add = (kind: StepKind) => {
    const first = (cat[kind] ?? [])[0]
    setSteps((all) => [...all, draft({ step_id: '', kind, action: first?.action ?? '', label: '', role: kind === 'gate' ? first?.default_role ?? undefined : undefined })])
  }

  const validate = async () => {
    setShowErrors(true)
    const res = await run(() => api.playbooks.validate(set, id, current))
    if (res) setValidation({ ok: res.ok, problems: res.problems ?? [], warnings: res.warnings ?? [] })
  }

  const applySave = useCallback((next: PlaybookDetail, unchanged: boolean, version: number | undefined, verb: string) => {
    if (unchanged) notify(`${id}: unchanged — nothing recorded`)
    else notify(`${id} ${verb} as v${version ?? next.version}`)
    setPb(next)
    onChanged()
  }, [id, notify, onChanged, setPb])

  const save = useCallback(async () => {
    if (!pb || !dirty) return
    setShowErrors(true)
    if (!clientOk) return
    if (!note.trim()) { noteRef.current?.focus(); return }
    const res = await run(async () => {
      try {
        return await api.playbooks.save(set, id, { trigger, stage, steps: current, note: note.trim() })
      } catch (err) {
        // A refused save lists every problem; show them where the steps are, not only in the popup.
        if (err instanceof ApiError && err.status === 400 && err.problems?.length) {
          setValidation({ ok: false, problems: err.problems, warnings: [] })
          return undefined
        }
        throw err
      }
    })
    if (res) { setValidation(null); applySave(res.playbook, res.unchanged, res.record?.version, 'saved') }
  }, [pb, dirty, clientOk, note, run, set, id, trigger, stage, current, applySave])

  // Ctrl/Cmd+S anywhere on the page while a playbook is open.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); void save() }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [save])

  const onRolledBack = useCallback((res: SaveResult, verb: string) => {
    // The file route answers with a FileDetail; the steps are in its body — reload for the parsed shape.
    notify(`${id} ${verb} as v${res.record?.version ?? res.file.version}`)
    reload()
    onChanged()
  }, [id, notify, reload, onChanged])

  if (loading && !pb) return <Card><Loading what={`Loading ${id}`} /></Card>
  if (error) return <LoadError what={`playbook ${id}`} error={error} onRetry={reload} />
  if (!pb) return null

  const visible = live(steps)
  const saveTitle = !dirty ? 'No change to save' : !clientOk ? 'Fix the marked steps first' : !note.trim() ? 'A note is required' : 'Record a new version (Ctrl+S)'

  return (
    <div className="stack">
      <Card
        title={pb.title || pb.id}
        description={pb.summary}
        actions={<div className="chips">
          <Badge variant="neutral" mono label={pb.change_type || pb.id} title="Change type — the id the engine looks up" />
          {pb.stage ? <Badge variant="neutral" label={pb.stage} /> : null}
          <VersionChip row={pb} />
        </div>}
      >
        <div className="editor-meta">
          <span className="mono" title={pb.path}>{pb.path}</span>
          <span className="mono" title={`sha256 ${pb.sha256}`}>sha256 {pb.short}</span>
          <span>used by {pb.usage?.runs ?? 0} run{pb.usage?.runs === 1 ? '' : 's'}, {pb.usage?.changes ?? 0} change{pb.usage?.changes === 1 ? '' : 's'}</span>
        </div>
        <div className="form-grid">
          <Field label="Trigger" htmlFor="pb-trigger" help="The engine method that opens this change type.">
            <input id="pb-trigger" type="text" className="mono-input" value={trigger} spellCheck={false} onChange={(e) => setTrigger(e.target.value)} placeholder="Engine.method_name" />
          </Field>
          <Field label="Stage" htmlFor="pb-stage" help="The stage the change record is filed under.">
            <input id="pb-stage" type="text" value={stage} onChange={(e) => setStage(e.target.value)} placeholder="build_review, quality…" />
          </Field>
        </div>
        {isDefault ? (
          <div style={{ marginTop: 16 }}>
            <Notice tone="warning" title="Default set.">
              Saving here changes the committed file under <code>s7_delivery/layers/playbooks/</code>. The test suite requires every default file to be recorded, so a save records a new version — clone the set first to experiment.
            </Notice>
          </div>
        ) : null}
      </Card>

      <Card
        title="Steps"
        description="In the order the engine walks them. Mechanical steps run as soon as they are reached; a gate stops the playbook until the named role records the action — the engine observes gates from the run's own records and never signs them."
        actions={<span className="hint">{visible.length} step{visible.length === 1 ? '' : 's'}</span>}
      >
        {visible.length === 0 && steps.every((s) => !s._removed) ? (
          <Empty bare title="No steps" hint="A playbook needs at least one step. The first is normally assess-impact." />
        ) : null}
        <ol className="pb-rail" aria-label="Playbook steps">
          {steps.map((s) => {
            if (s._removed) {
              return (
                <li key={s._key} className="pb-tomb" role="status">
                  <Undo2 aria-hidden="true" />
                  <span>Step <span className="mono">{s.step_id || '(unnamed)'}</span> removed.</span>
                  <Button variant="secondary" size="sm" onClick={() => restore(s._key)}>Undo</Button>
                  <Button variant="ghost" size="sm" onClick={() => purge(s._key)}>Dismiss</Button>
                </li>
              )
            }
            const idx = visible.indexOf(s)
            return (
              <StepCard key={s._key} step={s} index={idx} count={visible.length} all={steps} cat={cat} showErrors={showErrors}
                onChange={(n) => update(s._key, n)} onMove={(d) => move(s._key, d)} onRemove={() => remove(s._key)} />
            )
          })}
        </ol>
        <div className="pb-add">
          <span className="hint">Add a step</span>
          <Button variant="secondary" size="sm" icon={<CircleDot />} onClick={() => add('mechanical')} disabled={!cat.mechanical?.length}>Mechanical</Button>
          <Button variant="secondary" size="sm" icon={<OctagonPause />} onClick={() => add('gate')} disabled={!cat.gate?.length}>Gate</Button>
        </div>

        {!firstIsAssess && visible.length > 0 ? (
          <div style={{ marginTop: 16 }}>
            <Notice tone="info">The first step is normally <span className="mono">assess_impact</span> — the staleness walk that lists what the change touched. The server warns about this but does not refuse it.</Notice>
          </div>
        ) : null}

        {validation ? (
          <div style={{ marginTop: 16 }}>
            {validation.ok && validation.problems.length === 0 ? (
              <Notice tone={validation.warnings.length ? 'warning' : 'success'} title={validation.warnings.length ? 'Valid, with warnings.' : 'Valid.'}
                actions={<Button variant="ghost" size="sm" onClick={() => setValidation(null)}>Dismiss</Button>}>
                {validation.warnings.length ? <ul className="plain-list">{validation.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul> : 'The engine accepts these steps as written. Nothing was saved.'}
              </Notice>
            ) : (
              <Notice tone="danger" title={`${validation.problems.length} problem${validation.problems.length === 1 ? '' : 's'} — the save would be refused.`}
                actions={<Button variant="ghost" size="sm" onClick={() => setValidation(null)}>Dismiss</Button>}>
                <ul className="plain-list">
                  {validation.problems.map((p, i) => <li key={i}>{p}</li>)}
                  {validation.warnings.map((w, i) => <li key={`w${i}`}>{w} <span className="muted">(warning)</span></li>)}
                </ul>
              </Notice>
            )}
          </div>
        ) : null}

        <div className="editor-status" style={{ marginTop: 16 }}>
          <span className="inline">
            {dirty ? <span className="unsaved">Unsaved changes</span> : <span>No unsaved changes</span>}
            {showErrors && problems.length > 0 ? <span className="danger">{problems.length} step{problems.length === 1 ? '' : 's'} need attention</span> : null}
          </span>
          <span><kbd>Ctrl</kbd>+<kbd>S</kbd> saves.</span>
        </div>

        <div className="editor-save">
          <Field label="Note" htmlFor="pb-note" required help="Becomes the ledger line for this version.">
            <input ref={noteRef} id="pb-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this change"
              onKeyDown={(e) => { if (e.key === 'Enter') void save() }} />
          </Field>
          <div className="btn-row nowrap" style={{ paddingBottom: 20 }}>
            <Button variant="secondary" icon={<ShieldCheck />} onClick={validate} disabled={visible.length === 0} busy={busy} title="Dry run against the engine's catalogue; writes nothing">Validate</Button>
            <Button variant="secondary" icon={<Undo2 />} onClick={() => { setSteps((pb.steps ?? []).map(draft)); setTrigger(pb.trigger ?? ''); setStage(pb.stage ?? ''); setNote(''); setValidation(null); setShowErrors(false) }} disabled={!dirty}>Discard</Button>
            <Button variant="primary" icon={<Save />} onClick={save} disabled={!dirty || !clientOk || !note.trim()} busy={busy} title={saveTitle}>
              Save as v{pb.version + 1}
            </Button>
          </div>
        </div>
      </Card>

      <Card compact>
        <button type="button" className="disclosure" aria-expanded={rawOpen} onClick={() => setRawOpen((o) => !o)}>
          <span className={`chev${rawOpen ? ' open' : ''}`} aria-hidden="true" />
          Raw JSON <span className="hint">— what the PUT sends, read-only, mirrors the steps above</span>
        </button>
        {rawOpen ? <pre className="prompt-preview" style={{ marginTop: 12 }} aria-label="Playbook JSON">{raw}</pre> : null}
      </Card>

      <VersionsCard set={set} id={id} version={pb.version} recorded={pb.recorded} versions={pb.versions ?? []} onApplied={onRolledBack} />
    </div>
  )
}

function PlaybookList({ items, selected, onSelect }: { items: PlaybookDetail[]; selected: string | null; onSelect: (id: string) => void }) {
  return (
    <div className="file-tree" role="list" aria-label="Playbooks">
      {items.map((p) => (
        <button key={p.id} type="button" role="listitem" className="file-btn" aria-current={selected === p.id ? 'true' : undefined} onClick={() => onSelect(p.id)}>
          <span className="t"><span className="name" title={p.title || p.id}>{p.title || p.id}</span><VersionChip row={p} /></span>
          <span className="m"><span className="id">{p.change_type || p.id}</span>{p.stage ? <Badge variant="neutral" soft label={p.stage} /> : null}</span>
          <span className="m">{(p.steps ?? []).length} step{(p.steps ?? []).length === 1 ? '' : 's'} · used by {p.usage?.runs ?? 0} run{p.usage?.runs === 1 ? '' : 's'} · {p.usage?.changes ?? 0} change{p.usage?.changes === 1 ? '' : 's'}</span>
        </button>
      ))}
    </div>
  )
}

type CatState = { cat: PlaybookActions | null; missing: boolean }

export function PlaybooksPage() {
  const { goTo, playbookFocus, clearPlaybookFocus } = useAdmin()
  const sets = useLoad(() => api.promptSets.list())
  const catalogue = useLoad<CatState>(() => api.playbooks.actions().then((cat) => ({ cat, missing: false })).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return { cat: null, missing: true }
    throw err
  }))
  const [set, setSet] = useState<string>(() => playbookFocus?.set || 'default')
  const list = useLoad<PlaybookDetail[] | null>(() => catalogue.data?.cat ? api.playbooks.list(set) : Promise.resolve(null), [set, catalogue.data])
  const [selected, setSelected] = useState<string | null>(null)

  useEffect(() => {
    if (sets.data && !sets.data.some((s) => s.name === set)) setSet(sets.data.find((s) => s.is_default)?.name ?? sets.data[0]?.name ?? 'default')
  }, [sets.data, set])
  useEffect(() => {
    const items = list.data ?? []
    // A link from elsewhere (a run's self-healing drawer) names the playbook
    // to open; honour it once the list that holds it has loaded.
    if (playbookFocus && list.data && items.some((p) => p.id === playbookFocus.id)) {
      setSelected(playbookFocus.id)
      clearPlaybookFocus()
      return
    }
    if (!selected || !items.some((p) => p.id === selected)) setSelected(items[0]?.id ?? null)
  }, [list.data, selected, playbookFocus, clearPlaybookFocus])

  const onChanged = useCallback(() => list.reload(), [list])
  const setRow: SetSummary | undefined = sets.data?.find((s) => s.name === set)
  const loading = (sets.loading && !sets.data) || (catalogue.loading && !catalogue.data)

  return (
    <>
      <PageHeader
        title="Playbooks"
        description="The self-healing layer, edited as steps. Every action comes from the engine's own catalogue, a gate names the role that records it, and a save is a new version in the set's ledger — the same ledger the prompt editor writes."
        actions={<>
          <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={() => { catalogue.reload(); list.reload() }} disabled={loading}>Refresh</Button>
          <Button variant="ghost" size="sm" onClick={() => goTo('prompt_sets')}>Prompt sets</Button>
        </>}
      />

      <div className="filter-row">
        <Field label="Prompt set" htmlFor="pb-set" help={setRow?.is_default ? 'The committed default — edits change files under s7_delivery/layers/.' : setRow?.cloned_from ? `Cloned from ${setRow.cloned_from}.` : undefined}>
          <select id="pb-set" value={set} onChange={(e) => setSet(e.target.value)} disabled={!sets.data}>
            {(sets.data ?? [{ name: set, is_default: set === 'default', counts: { playbook: 0 } } as unknown as SetSummary]).map((s) => (
              <option key={s.name} value={s.name}>{s.name}{s.is_default ? ' (default)' : ''} — {s.counts?.playbook ?? 0} playbook{s.counts?.playbook === 1 ? '' : 's'}</option>
            ))}
          </select>
        </Field>
      </div>

      {setRow?.is_default ? (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="warning" title="Editing the default set changes committed files."
            actions={<Button variant="secondary" size="sm" onClick={() => goTo('prompt_sets')}>Clone a set instead</Button>}>
            Playbooks make no model call, so no recording is pinned to them — but <code>tests/test_layers.py</code> still refuses an unrecorded default file. Every save here records a new version.
          </Notice>
        </div>
      ) : null}

      {loading ? <Loading what="Loading playbooks" /> : null}
      {sets.error ? <LoadError what="prompt sets" error={sets.error} onRetry={sets.reload} /> : null}
      {catalogue.error ? <LoadError what="the playbook action catalogue" error={catalogue.error} onRetry={catalogue.reload} /> : null}
      {catalogue.data?.missing ? (
        <Empty title="Playbook editing is not available on this backend yet"
          hint={<>The admin API answered 404 for <span className="mono">GET /api/admin/playbook-actions</span>. Until the routes in docs/admin-api.md land, playbooks are still editable as raw JSON in the prompt editor.</>}
          action={<div className="btn-row"><Button variant="secondary" size="sm" onClick={catalogue.reload}>Check again</Button><Button variant="ghost" size="sm" onClick={() => goTo('prompt_sets')}>Open the prompt editor</Button></div>} />
      ) : null}
      {list.error ? <LoadError what={`playbooks in ${set}`} error={list.error} onRetry={list.reload} /> : null}
      {catalogue.data?.cat && list.data && list.data.length === 0 ? (
        <Empty title={`No playbooks in ${set}`} hint="Playbooks are files under playbooks/ in the set; add one as a playbook-layer file in the prompt editor." />
      ) : null}

      {catalogue.data?.cat && list.data && list.data.length > 0 ? (
        <div className="editor-layout">
          <Card compact>
            <div className="file-panel">
              <PlaybookList items={list.data} selected={selected} onSelect={setSelected} />
            </div>
          </Card>
          <div>
            {selected ? <PlaybookPanel key={`${set}:${selected}`} set={set} id={selected} isDefault={Boolean(setRow?.is_default)} cat={catalogue.data.cat} onChanged={onChanged} /> : <Empty title="Select a playbook" hint="Pick one on the left to edit its steps." />}
          </div>
        </div>
      ) : null}
    </>
  )
}
