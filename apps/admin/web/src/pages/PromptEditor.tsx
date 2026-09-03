import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Eye, Plus, RefreshCw, Save, Search, Undo2 } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, ConfirmPanel, DetailDrawer, Empty, Field, Loading, Modal, Notice, PageHeader, fmtTime } from '../components/ui'
import { VersionChip, VersionsCard } from '../components/Versions'
import { useAdmin } from '../state/AdminContext'
import type { FileDetail, FileRow, Layer, SetDetail, WorkflowPreview } from '../types'

const LAYERS: { key: Layer; list: keyof Pick<SetDetail, 'rules' | 'skills' | 'tasks' | 'playbooks'>; title: string }[] = [
  { key: 'rules', list: 'rules', title: 'Rules' },
  { key: 'skill', list: 'skills', title: 'Skills' },
  { key: 'task', list: 'tasks', title: 'Tasks' },
  { key: 'playbook', list: 'playbooks', title: 'Playbooks' },
]

// Task bodies use `{{name}}` (factory/layers.py `placeholders_of`); the
// server's own list is authoritative for the saved text, this is the
// live check on what is being typed.
const PLACEHOLDER = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}/g

function usedPlaceholders(body: string): string[] {
  const out = new Set<string>()
  for (const m of body.matchAll(PLACEHOLDER)) out.add(m[1])
  return [...out].sort()
}

/** `llm` is `{provider?, model?}` per the contract; the backend today keys
 * it by the workflow's stage (`{"intake-analysis": {...}}`). Accept both. */
function effectiveLlm(wf: WorkflowPreview): { provider?: string | null; model?: string | null } {
  const llm = (wf.llm ?? {}) as Record<string, unknown>
  if ('provider' in llm || 'model' in llm) return llm as { provider?: string | null; model?: string | null }
  const first = Object.values(llm)[0]
  return (first && typeof first === 'object' ? first : {}) as { provider?: string | null; model?: string | null }
}

function FileTree({ detail, selected, onSelect }: { detail: SetDetail; selected: string | null; onSelect: (id: string) => void }) {
  const [q, setQ] = useState('')
  const needle = q.trim().toLowerCase()
  const match = (r: FileRow) => !needle || [r.id, r.title, r.stage, r.summary].some((v) => (v ?? '').toLowerCase().includes(needle))
  return (
    <div className="file-panel">
      <div className="search-box">
        <Search aria-hidden="true" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter files…" aria-label="Filter files by id, title or stage" />
      </div>
      <div className="file-tree" role="list" aria-label="Files">
        {LAYERS.map((l) => {
          const all = detail[l.list] ?? []
          const rows = all.filter(match)
          if (needle && rows.length === 0) return null
          return (
            <Fragment key={l.key}>
              <div className="layer-head"><span>{l.title}</span><span className="count">{needle ? `${rows.length}/${all.length}` : all.length}</span></div>
              {all.length === 0 && <div className="hint sm" style={{ padding: '2px 10px 6px' }}>None in this set.</div>}
              {rows.map((r) => (
                <button key={r.id} type="button" role="listitem" className="file-btn" aria-current={selected === r.id ? 'true' : undefined} onClick={() => onSelect(r.id)}>
                  <span className="t"><span className="name" title={r.title || r.id}>{r.title || r.id}</span><VersionChip row={r} /></span>
                  <span className="m"><span className="id">{r.id}</span>{r.stage ? <Badge variant="neutral" soft label={r.stage} /> : null}</span>
                </button>
              ))}
            </Fragment>
          )
        })}
        {needle && LAYERS.every((l) => (detail[l.list] ?? []).filter(match).length === 0) && (
          <div className="hint" style={{ padding: 12 }}>No file matches “{q}”.</div>
        )}
      </div>
    </div>
  )
}

/** Monospace editor with a line-number gutter, a resize handle and
 * Ctrl/Cmd+S. Prompt bodies are prose, so soft wrap is the default; the
 * gutter numbers logical lines and is shown only when wrapping is off,
 * where its rows line up with what is on screen. */
function CodeEditor({ id, value, onChange, onSave, dirty, invalid, ariaLabel, height, wrap }: {
  id: string
  value: string
  onChange: (v: string) => void
  onSave?: () => void
  dirty?: boolean
  invalid?: boolean
  ariaLabel: string
  height?: number
  wrap: boolean
}) {
  const gutter = useRef<HTMLDivElement>(null)
  const lines = useMemo(() => value.split('\n').length, [value])
  const onScroll = (e: React.UIEvent<HTMLTextAreaElement>) => {
    if (gutter.current) gutter.current.scrollTop = e.currentTarget.scrollTop
  }
  const onKey = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') { e.preventDefault(); onSave?.() }
  }
  return (
    <div className={`code-editor${dirty ? ' dirty' : ''}${invalid ? ' invalid' : ''}${wrap ? ' wrap' : ''}`} style={height ? { height } : undefined}>
      <div className="gutter" ref={gutter} aria-hidden="true">
        {Array.from({ length: lines }, (_, i) => <div key={i}>{i + 1}</div>)}
      </div>
      <textarea id={id} value={value} onChange={(e) => onChange(e.target.value)} onScroll={onScroll} onKeyDown={onKey} spellCheck={false} aria-label={ariaLabel} aria-invalid={invalid || undefined} />
    </div>
  )
}

function NewFileForm({ set, onClose, onCreated }: { set: string; onClose: () => void; onCreated: (id: string) => void }) {
  const { run, busy } = useAdmin()
  const [layer, setLayer] = useState<Layer>('skill')
  const [id, setId] = useState('')
  const [title, setTitle] = useState('')
  const [stage, setStage] = useState('')
  const [summary, setSummary] = useState('')
  const [variables, setVariables] = useState('')
  const [body, setBody] = useState('')
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)
  const [wrap, setWrap] = useState(true)

  const idErr = !id ? 'An id is required.' : !/^[a-z0-9][a-z0-9_-]*$/.test(id) ? 'Lowercase letters, digits, hyphens and underscores only.' : null
  const noteErr = !note.trim() ? 'A note is required — it becomes the v1 ledger line.' : null
  const bodyErr = !body.trim() ? 'A body is required.' : null
  const vars = variables.split(',').map((v) => v.trim()).filter(Boolean)
  const used = usedPlaceholders(body)
  const undeclared = layer === 'task' ? used.filter((u) => !vars.includes(u)) : []

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setTouched(true)
    if (idErr || noteErr || bodyErr || undeclared.length) return
    const created = await run(() => api.promptSets.createFile(set, {
      layer, id, title, stage, summary, body, note, variables: layer === 'task' ? vars : undefined,
    }), `${id} created as v1`)
    if (created) onCreated(created.id)
  }

  return (
    <Modal title={`New file in ${set}`} description="Adds a file to this set only and records it as v1 in the set's ledger." onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Layer" htmlFor="nf-layer">
            <select id="nf-layer" data-autofocus value={layer} onChange={(e) => setLayer(e.target.value as Layer)}>
              {LAYERS.map((l) => <option key={l.key} value={l.key}>{l.title}</option>)}
            </select>
          </Field>
          <Field label="Id" htmlFor="nf-id" required error={touched && idErr ? idErr : undefined} help="Becomes the file name.">
            <input id="nf-id" type="text" className={`mono-input${touched && idErr ? ' invalid' : ''}`} value={id} onChange={(e) => setId(e.target.value.trim())} placeholder="e.g. claims-reviewer" autoComplete="off" spellCheck={false} aria-invalid={Boolean(touched && idErr)} />
          </Field>
          <Field label="Title" htmlFor="nf-title" optional>
            <input id="nf-title" type="text" value={title} onChange={(e) => setTitle(e.target.value)} />
          </Field>
          <Field label="Stage" htmlFor="nf-stage" optional>
            <input id="nf-stage" type="text" value={stage} onChange={(e) => setStage(e.target.value)} placeholder="e.g. intake, planning, downstream" />
          </Field>
          <Field label="Summary" htmlFor="nf-summary" optional className="full">
            <input id="nf-summary" type="text" value={summary} onChange={(e) => setSummary(e.target.value)} />
          </Field>
          {layer === 'task' && (
            <Field label="Variables" htmlFor="nf-vars" className="full" help={<>Comma-separated. A task body may only use placeholders declared here, written as {'{{name}}'}.</>}>
              <input id="nf-vars" type="text" className="mono-input" value={variables} onChange={(e) => setVariables(e.target.value)} placeholder="epic_text, repo_context" spellCheck={false} />
            </Field>
          )}
          <Field label={layer === 'playbook' ? 'Body (JSON)' : 'Body'} htmlFor="nf-body" required className="full"
            error={touched && bodyErr ? bodyErr : undeclared.length > 0 ? `Undeclared placeholders: ${undeclared.map((u) => `{{${u}}}`).join(', ')}` : undefined}
            help={layer === 'playbook' ? 'Playbook bodies must be valid JSON — the server refuses anything else.' : undefined}>
            <CodeEditor id="nf-body" value={body} onChange={setBody} onSave={() => void submit()} invalid={Boolean(touched && bodyErr)} ariaLabel="File body" height={260} wrap={wrap} />
            <div className="editor-status">
              <label className="check"><input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} /> Wrap lines</label>
              <span>{body.split('\n').length} line{body.split('\n').length === 1 ? '' : 's'}, {body.length} chars</span>
            </div>
          </Field>
          <Field label="Note" htmlFor="nf-note" required className="full" error={touched && noteErr ? noteErr : undefined} help="Becomes the v1 ledger line.">
            <input id="nf-note" type="text" className={touched && noteErr ? 'invalid' : ''} value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this file exists" aria-invalid={Boolean(touched && noteErr)} />
          </Field>
        </div>
        <div className="btn-row right" style={{ marginTop: 24 }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" icon={<Plus />} busy={busy}>Create file</Button>
        </div>
      </form>
    </Modal>
  )
}

function WorkflowDrawer({ set, onClose }: { set: string; onClose: () => void }) {
  const { data: list, error, loading } = useLoad(() => api.promptSets.workflows(set), [set])
  const [picked, setPicked] = useState<string>('')
  const wf: WorkflowPreview | undefined = useMemo(() => list?.find((w) => w.id === picked) ?? list?.[0], [list, picked])

  return (
    <DetailDrawer title="Workflow preview" subtitle={`Assembled from the ${set} set — the exact system prompt a workflow would send, its task templates and the provider/model in effect.`} ariaLabel="Workflow preview" onClose={onClose}>
      {loading && !list ? <Loading what="Loading workflows" /> : null}
      {error ? <Notice tone="danger" title="Could not load workflows.">{error}</Notice> : null}
      {list && list.length === 0 ? <Empty title="No workflows" hint="This set declares no workflows." /> : null}
      {list && list.length > 0 && wf ? (
        <>
          <Field label="Workflow" htmlFor="wf-pick">
            <select id="wf-pick" data-autofocus value={wf.id} onChange={(e) => setPicked(e.target.value)}>
              {list.map((w) => <option key={w.id} value={w.id}>{w.label ?? w.id} — {w.stage}</option>)}
            </select>
          </Field>
          <div className="kv tight" style={{ marginTop: 8 }}>
            <span className="k">Entry</span><span className="v mono">{wf.entry}</span>
            <span className="k">Stage</span><span className="v">{wf.stage}</span>
            <span className="k">Gate</span><span className="v">{wf.gate || '—'}</span>
            <span className="k">Rules</span><span className="v mono">{wf.rules}</span>
            <span className="k">Skills</span><span className="v mono">{wf.skills?.join(', ') || '—'}</span>
            <span className="k">Provider / model</span>
            <span className="v mono">{effectiveLlm(wf).provider ?? '(environment)'} / {effectiveLlm(wf).model ?? '(environment)'}</span>
          </div>
          <div className="section-head" style={{ margin: '16px 0 4px' }}>
            <div><h3>System prompt</h3><div className="desc">rules + skill(s), in the prefix order common/prompt.py fixes — {wf.system_prompt.length} chars</div></div>
          </div>
          <pre className="prompt-preview">{wf.system_prompt}</pre>
          <div className="section-head" style={{ margin: '16px 0 4px' }}>
            <div><h3>Task templates ({wf.tasks.length})</h3></div>
          </div>
          {wf.tasks.length === 0 ? <div className="hint">No task templates are attached to this workflow.</div> : null}
          {wf.tasks.map((t) => (
            <Card compact key={t.id} title={t.title || t.id} actions={<span className="mono hint">{t.id}</span>}>
              {t.variables?.length ? <div className="chips" style={{ marginBottom: 8 }}>{t.variables.map((v) => <Badge key={v} variant="info" mono label={`{{${v}}}`} />)}</div> : null}
              <pre className="prompt-preview" style={{ maxHeight: 220 }}>{t.body}</pre>
            </Card>
          ))}
        </>
      ) : null}
    </DetailDrawer>
  )
}

function FilePanel({ set, id, isDefault, onChanged }: { set: string; id: string; isDefault: boolean; onChanged: () => void }) {
  const { run, notify, busy } = useAdmin()
  const { data: file, setData: setFile, error, loading, reload } = useLoad(() => api.promptSets.file(set, id), [set, id])
  const [body, setBody] = useState('')
  const [note, setNote] = useState('')
  const [wrap, setWrap] = useState(true)
  const noteRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (file) { setBody(file.body); setNote('') }
  }, [file])

  const dirty = file ? body !== file.body : false
  const used = useMemo(() => usedPlaceholders(body), [body])
  const declared = file?.variables ?? []
  const undeclared = file?.layer === 'task' ? used.filter((u) => !declared.includes(u)) : []
  const lines = body.split('\n').length
  const canSave = dirty && note.trim().length > 0 && undeclared.length === 0
  const applyResult = useCallback((res: { unchanged: boolean; file: FileDetail; record: { version: number } | null }, verb: string) => {
    if (res.unchanged) notify(`${id}: unchanged — nothing recorded`)
    else notify(`${id} ${verb} as v${res.record?.version ?? res.file.version}`)
    setFile(res.file)
    onChanged()
  }, [id, notify, onChanged, setFile])

  const save = async () => {
    if (!file || !dirty) return
    if (!note.trim()) { noteRef.current?.focus(); return }
    if (!canSave) return
    const res = await run(() => api.promptSets.saveFile(set, id, body, note.trim()))
    if (res) applyResult(res, 'saved')
  }

  if (loading && !file) return <Card><Loading what={`Loading ${id}`} /></Card>
  if (error) return <LoadError what={id} error={error} onRetry={reload} />
  if (!file) return null

  const saveTitle = !dirty ? 'No change to save' : !note.trim() ? 'A note is required' : undeclared.length ? 'Undeclared placeholders' : 'Record a new version (Ctrl+S)'

  return (
    <div className="stack">
      <Card
        title={file.title || file.id}
        description={file.summary}
        actions={<div className="chips">
          <Badge variant="neutral" label={file.layer} />
          {file.stage ? <Badge variant="neutral" label={file.stage} /> : null}
          <VersionChip row={file} />
        </div>}
      >
        <div className="editor-meta">
          <span className="mono" title={file.path}>{file.path}</span>
          <span className="mono" title={`sha256 ${file.sha256}`}>sha256 {file.short}</span>
          {file.recorded_at ? <span>recorded {fmtTime(file.recorded_at)}</span> : null}
          {file.workflows?.length ? <span>used by <span className="mono">{file.workflows.join(', ')}</span></span> : <span>not referenced by any workflow</span>}
        </div>

        <div className="stack tight" style={{ marginBottom: 16 }}>
          {file.layer === 'task' && (
            <div className="sub-panel" style={{ marginTop: 0 }}>
              <div className="kv tight">
                <span className="k">Declared variables</span>
                <span className="v chips">{declared.length ? declared.map((v) => <Badge key={v} variant="info" mono label={`{{${v}}}`} />) : <span className="muted">none</span>}</span>
                <span className="k">Placeholders used</span>
                <span className="v chips">
                  {used.length ? used.map((u) => <Badge key={u} variant={declared.includes(u) ? 'success' : 'danger'} mono label={`{{${u}}}`} />) : <span className="muted">none</span>}
                </span>
              </div>
              {undeclared.length > 0 && <div className="fld-group" style={{ marginTop: 8 }}><div className="err" role="alert">Undeclared placeholders will be refused on save: {undeclared.map((u) => `{{${u}}}`).join(', ')}</div></div>}
            </div>
          )}
          {file.layer === 'playbook' && <Notice tone="info">Playbook bodies must be valid JSON — the server refuses anything else.</Notice>}
          {isDefault && (
            file.recordings_pinned > 0 ? (
              <Notice tone="warning" title={`${file.recordings_pinned} committed recording${file.recordings_pinned === 1 ? '' : 's'} hash this text.`}>
                Editing means re-recording: until then replay runs miss on every call that used this file, and <code>tests/test_layers.py</code> reports the same.
              </Notice>
            ) : (
              <Notice tone="info" title="Default set.">No committed recording hashes this text, but the test suite still requires every default file to be recorded — a save here records a new version.</Notice>
            )
          )}
        </div>

        <div className="fld-group">
          <label className="fld" htmlFor="ed-body">Body</label>
          <CodeEditor id="ed-body" value={body} onChange={setBody} onSave={() => void save()} dirty={dirty} ariaLabel="File body" wrap={wrap} />
        </div>
        <div className="editor-status">
          <span className="inline">
            {dirty ? <span className="unsaved">Unsaved changes</span> : <span>No unsaved changes</span>}
            <label className="check"><input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} /> Wrap lines</label>
          </span>
          <span>{lines} line{lines === 1 ? '' : 's'}, {body.length} chars. <kbd>Ctrl</kbd>+<kbd>S</kbd> saves. Drag the bottom edge to resize.</span>
        </div>

        <div className="editor-save">
          <Field label="Note" htmlFor="ed-note" required help="Becomes the ledger line for this version.">
            <input ref={noteRef} id="ed-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this change"
              onKeyDown={(e) => { if (e.key === 'Enter' && canSave) void save() }} />
          </Field>
          <div className="btn-row nowrap" style={{ paddingBottom: 20 }}>
            <Button variant="secondary" icon={<Undo2 />} onClick={() => { setBody(file.body); setNote('') }} disabled={!dirty}>Discard</Button>
            <Button variant="primary" icon={<Save />} onClick={save} disabled={!canSave} busy={busy} title={saveTitle}>
              Save as v{file.version + 1}
            </Button>
          </div>
        </div>
      </Card>

      <VersionsCard set={set} id={id} version={file.version} recorded={file.recorded} versions={file.versions} onApplied={applyResult} />
    </div>
  )
}

export function PromptEditor() {
  const { editingSet, goTo } = useAdmin()
  const set = editingSet ?? 'default'
  const { data, error, loading, reload } = useLoad(() => api.promptSets.detail(set), [set])
  const [selected, setSelected] = useState<string | null>(null)
  const [newFile, setNewFile] = useState(false)
  const [preview, setPreview] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  useEffect(() => {
    if (!data) return
    const all = [...data.rules, ...data.skills, ...data.tasks, ...data.playbooks]
    if (!selected || !all.some((f) => f.id === selected)) setSelected(all[0]?.id ?? null)
  }, [data, selected])

  const onChanged = useCallback(() => reload(), [reload])

  return (
    <>
      <PageHeader
        title={<>Prompt Editor <span className="mono" style={{ fontSize: 20, fontWeight: 500, color: 'var(--muted)' }}>{set}</span></>}
        description={data ? `${data.description || 'No description'} — ${data.files} files, ${data.versions} ledger lines${data.is_default ? ', the default set' : data.cloned_from ? `, cloned from ${data.cloned_from}` : ''}.` : undefined}
        actions={<>
          <Button variant="ghost" size="sm" icon={<ArrowLeft />} onClick={() => setConfirmLeave(true)}>All sets</Button>
          <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>
          <Button variant="secondary" size="sm" icon={<Eye />} onClick={() => setPreview(true)} disabled={!data}>Workflow preview</Button>
          <Button variant="primary" size="sm" icon={<Plus />} onClick={() => setNewFile(true)} disabled={!data}>New file</Button>
        </>}
      />
      {confirmLeave && (
        <div style={{ marginBottom: 16 }}>
          <ConfirmPanel message="Leave the editor? Any unsaved body text is discarded." confirmLabel="Leave" onConfirm={() => { setConfirmLeave(false); goTo('prompt_sets') }} onCancel={() => setConfirmLeave(false)} />
        </div>
      )}

      {data?.unrecorded?.length ? (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="warning" title="Unrecorded files."><span className="mono">{data.unrecorded.join(', ')}</span> differ from the last ledger line. Save (with a note) to record, or roll back.</Notice>
        </div>
      ) : null}

      {loading && !data ? <Loading what={`Loading ${set}`} /> : null}
      {error ? <LoadError what={`prompt set ${set}`} error={error} onRetry={reload} /> : null}
      {data && data.files === 0 ? <Empty title="This set has no files" hint="Add the first one to start the ledger." action={<Button variant="primary" size="sm" icon={<Plus />} onClick={() => setNewFile(true)}>New file</Button>} /> : null}
      {data && data.files > 0 ? (
        <div className="editor-layout">
          <Card compact>
            <FileTree detail={data} selected={selected} onSelect={setSelected} />
          </Card>
          <div>
            {selected ? <FilePanel key={`${set}:${selected}`} set={set} id={selected} isDefault={data.is_default} onChanged={onChanged} /> : <Empty title="Select a file" hint="Pick a file on the left to read or edit it." />}
          </div>
        </div>
      ) : null}

      {newFile ? <NewFileForm set={set} onClose={() => setNewFile(false)} onCreated={(id) => { setNewFile(false); reload(); setSelected(id) }} /> : null}
      {preview ? <WorkflowDrawer set={set} onClose={() => setPreview(false)} /> : null}
    </>
  )
}
