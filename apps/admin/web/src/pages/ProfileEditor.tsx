import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ArrowLeft, Download, Eye, Lock, Plus, RefreshCw, Save, Search, Undo2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, ConfirmPanel, DetailDrawer, Empty, Field, Loading, Modal, Notice, PageHeader, fmtTime } from '../components/ui'
import { CodeEditor, missingLocked, usedPlaceholders } from '../components/CodeEditor'
import { VersionChip, VersionsCard, type LedgerClient } from '../components/Versions'
import { useAdmin } from '../state/AdminContext'
import { KindBadge } from './Profiles'
import type {
  AssetBrowseResult, FileSource, Impact, ProfileDetail, ProfileFileRow, ProfileGroup,
  ProfileLayer, ProfileSaveResult, WorkflowPreview,
} from '../types'

/* The editor for every layer of a delivery profile. One file panel serves
 * all ten kinds — what differs per kind is stated on the file itself
 * (JSON body, declared variables, locked tokens, whether it enters a model
 * call) and the panel reads those, never a table of special cases. */

const LAYER_LABEL: Record<ProfileLayer, string> = {
  rules: 'Rules', skill: 'Skill', task: 'Task', playbook: 'Playbook', standard: 'Standard',
  template: 'Template', governance: 'Governance', model: 'Model', identity: 'Identity', integration: 'Integration',
  asset: 'Asset',
}
const LAYER_PLURAL: Record<ProfileLayer, string> = {
  rules: 'Rules', skill: 'Skills', task: 'Tasks', playbook: 'Playbooks', standard: 'Standards',
  template: 'Templates', governance: 'Governance', model: 'Models', identity: 'Identity', integration: 'Integrations',
  asset: 'Assets',
}
const ALL_LAYERS = Object.keys(LAYER_LABEL) as ProfileLayer[]
// Bodies the server parses as JSON before it writes anything.
const JSON_LAYERS = new Set<ProfileLayer>(['playbook', 'governance', 'model', 'identity', 'integration'])

const LEDGER: LedgerClient<ProfileSaveResult> = {
  version: (name, id, n) => api.profiles.version(name, id, n),
  diff: (name, id, from, to) => api.profiles.diff(name, id, from, to),
  rollback: (name, id, to, note) => api.profiles.rollback(name, id, to, note),
}

export function SourceBadge({ source, soft }: { source: FileSource; soft?: boolean }) {
  if (source === 'override') return <Badge variant="accent" soft={soft} label="overridden" title="Stored in this profile; the default is hidden by it" />
  if (source === 'set') return <Badge variant="info" soft={soft} label="set" title="A file of this legacy full-copy set" />
  return <Badge variant="neutral" soft={soft} label="default" title="Shows through from the committed default set" />
}

function jsonPretty(body: string): { text: string; error: string | null } {
  try {
    return { text: JSON.stringify(JSON.parse(body), null, 2) + '\n', error: null }
  } catch (err) {
    return { text: body, error: err instanceof Error ? err.message : String(err) }
  }
}

function jsonError(body: string): string | null {
  try { JSON.parse(body); return null } catch (err) { return err instanceof Error ? err.message : String(err) }
}

/** "Prompts — what the models are told" → ["Prompts", "what the models are told"]. */
function splitLabel(label: string): [string, string] {
  const i = label.indexOf(' — ')
  return i < 0 ? [label, ''] : [label.slice(0, i), label.slice(i + 3)]
}

/* --- left rail ---------------------------------------------------------- */

function FileTree({ detail, selected, onSelect }: { detail: ProfileDetail; selected: string | null; onSelect: (id: string) => void }) {
  const [q, setQ] = useState('')
  const [closed, setClosed] = useState<Record<string, boolean>>({})
  const needle = q.trim().toLowerCase()
  const match = (r: ProfileFileRow) => !needle || [r.id, r.title, r.stage, r.summary, r.layer].some((v) => (v ?? '').toLowerCase().includes(needle))
  const groups = detail.groups ?? []
  const total = groups.reduce((n, g) => n + g.files.filter(match).length, 0)

  const row = (r: ProfileFileRow) => (
    <button key={r.id} type="button" role="listitem" className="file-btn" aria-current={selected === r.id ? 'true' : undefined} onClick={() => onSelect(r.id)}>
      <span className="t"><span className="name" title={r.title || r.id}>{r.title || r.id}</span><VersionChip row={r} /></span>
      <span className="m"><span className="id">{r.id}</span><SourceBadge source={r.source} soft />{r.stage ? <Badge variant="neutral" soft label={r.stage} /> : null}</span>
    </button>
  )

  return (
    <div className="file-panel">
      <div className="search-box">
        <Search aria-hidden="true" />
        <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter files…" aria-label="Filter files by id, title, layer or stage" />
      </div>
      <div className="file-tree" role="list" aria-label="Files">
        {groups.map((g: ProfileGroup) => {
          const rows = g.files.filter(match)
          if (needle && rows.length === 0) return null
          const open = needle ? true : !closed[g.id]
          const [name, what] = splitLabel(g.label)
          const multi = g.layers.length > 1
          return (
            <Fragment key={g.id}>
              <button type="button" className="group-head" aria-expanded={open} onClick={() => setClosed((c) => ({ ...c, [g.id]: !c[g.id] }))} title={what || undefined}>
                <span className={`chev${open ? ' open' : ''}`} aria-hidden="true" />
                <span className="name">{name}</span>
                <span className="count">
                  {g.overridden > 0 ? <span className="ov" title={`${g.overridden} overridden in this profile`}>{g.overridden}▲</span> : null}
                  {needle ? `${rows.length}/${g.files.length}` : g.files.length}
                </span>
              </button>
              {open && g.files.length === 0 && <div className="hint sm" style={{ padding: '2px 10px 6px' }}>None in this profile.</div>}
              {open && (multi
                ? g.layers.map((layer) => {
                  const sub = rows.filter((r) => r.layer === layer)
                  if (needle && sub.length === 0) return null
                  return (
                    <Fragment key={layer}>
                      <div className="layer-head sub"><span>{LAYER_PLURAL[layer]}</span><span className="count">{sub.length}</span></div>
                      {sub.map(row)}
                    </Fragment>
                  )
                })
                : rows.map(row))}
            </Fragment>
          )
        })}
        {needle && total === 0 && <div className="hint" style={{ padding: 12 }}>No file matches “{q}”.</div>}
      </div>
    </div>
  )
}

/* --- impact ------------------------------------------------------------- */

function ImpactCard({ impact, onRefresh, loading }: { impact: Impact; onRefresh: () => void; loading: boolean }) {
  const staleRuns = impact.runs.filter((r) => r.artifacts.length > 0)
  return (
    <Card
      title="Impact"
      description="What an edit to this file touches — read from the files and the run ledgers, never guessed."
      actions={<Button variant="ghost" size="sm" icon={<RefreshCw />} onClick={onRefresh} disabled={loading}>Refresh</Button>}
    >
      <div className="kv tight">
        <span className="k">Current pin</span><span className="v mono">{impact.current}</span>
        <span className="k">Read by</span>
        <span className="v chips">{impact.consumers.length ? impact.consumers.map((c) => <Badge key={c} variant="neutral" mono label={c} />) : <span className="muted">no consumer declares this file</span>}</span>
        <span className="k">Model calls</span>
        <span className="v">
          {impact.enters_model_call
            ? <>Enters the prompt. {impact.recordings_pinned > 0
              ? <b className="danger">{impact.recordings_pinned} committed recording{impact.recordings_pinned === 1 ? '' : 's'} hash the current text — an edit needs a re-record.</b>
              : 'No committed recording hashes the current text.'}</>
            : 'Never enters a prompt — an edit makes generated artifacts stale, nothing else.'}
        </span>
        <span className="k">Runs on this profile</span>
        <span className="v">
          {impact.runs.length === 0 ? <span className="muted">none</span> : <>{impact.runs.length} run{impact.runs.length === 1 ? '' : 's'}; {staleRuns.length} pinned this file in a generated artifact</>}
        </span>
      </div>
      {staleRuns.length > 0 ? (
        <ul className="impact-runs" aria-label="Runs whose artifacts pin this file">
          {staleRuns.map((r) => (
            <li key={r.run_id}>
              <span className="mono"><b>{r.run_id}</b></span>
              <span className="chips">
                {r.artifacts.map((a) => (
                  <Badge key={`${a.artifact}-${a.kind}`} variant={a.stale ? 'danger' : 'success'} mono
                    label={`${a.artifact}${a.artifact_version != null ? ` v${a.artifact_version}` : ''} → ${a.pinned}`}
                    title={`${a.kind}: pinned ${a.pinned}${a.stale ? ' — already behind the current version' : ' — current'}`} />
                ))}
              </span>
              {r.would_go_stale.length ? <span className="hint sm">would go stale after a save: <span className="mono">{r.would_go_stale.join(', ')}</span></span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  )
}

/* --- file panel ----------------------------------------------------------- */

function FilePanel({ name, id, isDefault, onChanged }: { name: string; id: string; isDefault: boolean; onChanged: () => void }) {
  const { run, notify, busy } = useAdmin()
  const { data, setData, error, loading, reload } = useLoad(() => api.profiles.file(name, id), [name, id])
  const [body, setBody] = useState('')
  const [note, setNote] = useState('')
  const [wrap, setWrap] = useState(true)
  const [reverting, setReverting] = useState(false)
  const [revertNote, setRevertNote] = useState('')
  const [impactBusy, setImpactBusy] = useState(false)
  const noteRef = useRef<HTMLInputElement>(null)

  const file = data?.file
  const isJson = file ? JSON_LAYERS.has(file.layer) : false
  // The loaded body: pretty-printed for JSON layers so a one-line file is
  // readable; compared against the same text so a reformat alone is not
  // "dirty".
  const loaded = useMemo(() => (file ? (isJson ? jsonPretty(file.body).text : file.body) : ''), [file, isJson])

  useEffect(() => { setBody(loaded); setNote(''); setReverting(false); setRevertNote('') }, [loaded])

  const dirty = file ? body !== loaded && body !== file.body : false
  const used = useMemo(() => usedPlaceholders(body), [body])
  const declared = file?.variables ?? []
  const undeclared = file?.layer === 'task' ? used.filter((u) => !declared.includes(u)) : []
  const missing = useMemo(() => (file ? missingLocked(body, file.locked ?? []) : []), [body, file])
  const jsonErr = isJson ? jsonError(body) : null
  const lines = body.split('\n').length
  const canSave = dirty && note.trim().length > 0 && undeclared.length === 0 && missing.length === 0 && !jsonErr

  const refreshImpact = useCallback(async () => {
    setImpactBusy(true)
    try {
      const impact = await api.profiles.impact(name, id)
      setData((d) => (d ? { ...d, impact } : d))
    } catch { /* the file's own impact stays on screen */ } finally { setImpactBusy(false) }
  }, [name, id, setData])

  const applyResult = useCallback((res: ProfileSaveResult, verb: string) => {
    if (!res.version) notify(`${id}: unchanged — nothing recorded`)
    else notify(`${id} ${verb} as v${res.version.version}`)
    // The result carries the file; versions and impact are re-read so the
    // timeline and the pins reflect the new line.
    setData((d) => (d ? { ...d, file: res.file } : d))
    reload()
    onChanged()
  }, [id, notify, onChanged, reload, setData])

  const save = async () => {
    if (!file || !dirty) return
    if (!note.trim()) { noteRef.current?.focus(); return }
    if (!canSave) return
    const res = await run(() => api.profiles.saveFile(name, id, body, note.trim()))
    if (res) applyResult(res, 'saved')
  }

  const revert = async () => {
    if (!file || !revertNote.trim()) return
    const res = await run(() => api.profiles.revert(name, id, revertNote.trim()))
    if (res) { applyResult(res, 'reverted to default'); setReverting(false) }
  }

  if (loading && !data) return <Card><Loading what={`Loading ${id}`} /></Card>
  if (error) return <LoadError what={id} error={error} onRetry={reload} />
  if (!data || !file) return null

  const pinned = data.recordings_pinned ?? 0
  const saveTitle = !dirty ? 'No change to save' : !note.trim() ? 'A note is required'
    : undeclared.length ? 'Undeclared placeholders' : missing.length ? 'A locked token is missing' : jsonErr ? 'Body is not valid JSON' : 'Record a new version (Ctrl+S)'

  return (
    <div className="stack">
      <Card
        title={file.title || file.id}
        description={file.summary}
        actions={<div className="chips">
          <Badge variant="neutral" label={LAYER_LABEL[file.layer] ?? file.layer} />
          {file.stage ? <Badge variant="neutral" label={file.stage} /> : null}
          <SourceBadge source={file.source} />
          {file.enters_model_call ? <Badge variant="warning" label="enters model call" title="Part of a prompt: an edit misses committed recordings" /> : <Badge variant="neutral" soft label="no model call" title="Read by a renderer or the engine; never part of a prompt" />}
          <VersionChip row={file} />
        </div>}
      >
        <div className="editor-meta">
          <span className="mono" title={file.path}>{file.path}</span>
          <span className="mono" title={`sha256 ${file.sha256}`}>sha256 {file.short}</span>
          {file.recorded_at ? <span>recorded {fmtTime(file.recorded_at)}</span> : null}
          {file.consumers?.length ? <span>read by <span className="mono">{file.consumers.join(', ')}</span></span> : null}
          {file.workflows?.length ? <span>used by <span className="mono">{file.workflows.join(', ')}</span></span> : file.enters_model_call ? <span>not referenced by any workflow</span> : null}
        </div>

        <div className="stack tight" style={{ marginBottom: 16 }}>
          {(file.layer === 'task' || declared.length > 0) && (
            <div className="sub-panel" style={{ marginTop: 0 }}>
              <div className="kv tight">
                <span className="k">Declared variables</span>
                <span className="v chips">{declared.length ? declared.map((v) => <Badge key={v} variant="info" mono label={`{{${v}}}`} />) : <span className="muted">none — this file takes no data from the workflow</span>}</span>
                {file.layer === 'task' && (<>
                  <span className="k">Placeholders used</span>
                  <span className="v chips">
                    {used.length ? used.map((u) => <Badge key={u} variant={declared.includes(u) ? 'success' : 'danger'} mono label={`{{${u}}}`} />) : <span className="muted">none</span>}
                  </span>
                </>)}
              </div>
              {undeclared.length > 0 && <div className="fld-group" style={{ marginTop: 8 }}><div className="err" role="alert">Undeclared placeholders will be refused on save: {undeclared.map((u) => `{{${u}}}`).join(', ')}</div></div>}
            </div>
          )}
          {file.locked?.length > 0 && (
            <div className="sub-panel" style={{ marginTop: 0 }}>
              <div className="kv tight">
                <span className="k"><span className="inline"><Lock aria-hidden="true" style={{ width: 14, height: 14 }} />Locked tokens</span></span>
                <span className="v">
                  <span className="chips">
                    {file.locked.map((t) => <Badge key={t} variant={missing.includes(t) ? 'danger' : 'success'} mono label={t} title={missing.includes(t) ? 'Missing from the body' : 'Present in the body'} />)}
                  </span>
                  <span className="hint sm" style={{ display: 'block', marginTop: 6 }}>These literal tokens must stay in the body — the Control Centre depends on them. Move them, reword around them, but a save that drops one is refused.</span>
                </span>
              </div>
              {missing.length > 0 && <div className="fld-group" style={{ marginTop: 8 }}><div className="err" role="alert">Missing locked tokens: {missing.join(', ')}</div></div>}
            </div>
          )}
          {file.layer === 'asset' && (
            <Notice tone="info" title="Project asset.">
              Published verbatim to <span className="mono">{file.publishes_to || `.s7/assets/${file.dest}`}</span> in
              every repository this profile delivers to. Nothing is rendered on the way through, so any{' '}
              <span className="mono">{'{{…}}'}</span> below is this file&rsquo;s own templating syntax and survives
              untouched. It is reference material for developers to copy from — where it disagrees with the target
              repository, the repository wins.
            </Notice>
          )}
          {isJson && <Notice tone="info" title="JSON body.">Pretty-printed on load; the server refuses anything that does not parse{file.layer === 'model' || file.layer === 'governance' || file.layer === 'identity' || file.layer === 'integration' ? ', and validates the shape its consumer expects' : ''}.</Notice>}
          {file.enters_model_call && pinned > 0 ? (
            <Notice tone="warning" title={`${pinned} committed recording${pinned === 1 ? '' : 's'} hash this text.`}>
              Editing means re-recording: until then replay runs miss on every call that used this file, and <code>tests/test_layers.py</code> reports the same.
            </Notice>
          ) : isDefault && file.enters_model_call ? (
            <Notice tone="info" title="Default set.">No committed recording hashes this text, but the test suite still requires every default file to be recorded — a save here records a new version.</Notice>
          ) : null}
          {file.source === 'override' && !reverting ? (
            <Notice tone="info" title="Overridden in this profile."
              actions={<Button variant="danger" size="sm" icon={<Undo2 />} onClick={() => { setReverting(true); setRevertNote('') }}>Revert to default</Button>}>
              The default file is hidden by this one. Reverting removes the override — the default shows through again and the ledger records the revert as a version.
            </Notice>
          ) : null}
          {reverting ? (
            <ConfirmPanel
              danger
              message={<>Remove the override of <b className="mono">{id}</b> from <b className="mono">{name}</b>? The default's current text takes effect immediately; the profile's versions of this file stay in the ledger.</>}
              confirmLabel="Revert to default"
              busy={busy}
              onConfirm={revert}
              onCancel={() => setReverting(false)}
            >
              <Field label="Note" htmlFor="rv-note" required help="Becomes the ledger line for the revert.">
                <input data-autofocus id="rv-note" type="text" value={revertNote} onChange={(e) => setRevertNote(e.target.value)} placeholder="Why revert"
                  onKeyDown={(e) => { if (e.key === 'Enter' && revertNote.trim()) void revert() }} />
              </Field>
            </ConfirmPanel>
          ) : null}
        </div>

        <div className="fld-group">
          <label className="fld" htmlFor="ed-body">Body{isJson ? ' (JSON)' : ''}</label>
          <CodeEditor id="ed-body" value={body} onChange={setBody} onSave={() => void save()} dirty={dirty} invalid={Boolean(jsonErr)} ariaLabel="File body" wrap={wrap} />
          {jsonErr ? <div className="err" role="alert">Not valid JSON: {jsonErr}</div> : null}
        </div>
        <div className="editor-status">
          <span className="inline">
            {dirty ? <span className="unsaved">Unsaved changes</span> : <span>No unsaved changes</span>}
            <label className="check"><input type="checkbox" checked={wrap} onChange={(e) => setWrap(e.target.checked)} /> Wrap lines</label>
          </span>
          <span>{lines} line{lines === 1 ? '' : 's'}, {body.length} chars. <kbd>Ctrl</kbd>+<kbd>S</kbd> saves. Drag the bottom edge to resize.</span>
        </div>

        <div className="editor-save">
          <Field label="Note" htmlFor="ed-note" required help={file.source === 'default' && !isDefault ? 'Becomes the ledger line for this version. Saving creates the override in this profile.' : 'Becomes the ledger line for this version.'}>
            <input ref={noteRef} id="ed-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this change"
              onKeyDown={(e) => { if (e.key === 'Enter' && canSave) void save() }} />
          </Field>
          <div className="btn-row nowrap" style={{ paddingBottom: 20 }}>
            <Button variant="secondary" icon={<Undo2 />} onClick={() => { setBody(loaded); setNote('') }} disabled={!dirty}>Discard</Button>
            <Button variant="primary" icon={<Save />} onClick={save} disabled={!canSave} busy={busy} title={saveTitle}>
              Save as v{file.version + 1}
            </Button>
          </div>
        </div>
      </Card>

      {data.impact ? <ImpactCard impact={data.impact} onRefresh={() => void refreshImpact()} loading={impactBusy} /> : null}

      <VersionsCard<ProfileSaveResult> set={name} id={id} version={file.version} recorded={file.recorded} versions={data.versions ?? []} onApplied={applyResult} ledger={LEDGER} />
    </div>
  )
}

/* --- import assets from a repository ------------------------------------- */

/* A loader, not a link: the chosen files are copied in and versioned in this
 * profile's ledger, and nothing re-syncs afterwards. A pinned artifact that
 * silently followed someone else's default branch would defeat the pinning
 * every other layer depends on. */
function ImportAssetsForm({ name, onClose, onImported }: { name: string; onClose: () => void; onImported: () => void }) {
  const { run, notify, busy } = useAdmin()
  const [repository, setRepository] = useState('')
  const [ref, setRef] = useState('')
  const [subdir, setSubdir] = useState('')
  const [result, setResult] = useState<AssetBrowseResult | null>(null)
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const [note, setNote] = useState('')

  const browse = async (e?: React.FormEvent) => {
    e?.preventDefault()
    if (!repository.trim()) return
    const res = await run(() => api.profiles.browseAssets(name, { repository: repository.trim(), ref: ref.trim(), subdir: subdir.trim() }))
    if (res) { setResult(res); setPicked({}) }
  }

  const chosen = result ? result.files.filter((f) => f.importable && picked[f.path]) : []

  const doImport = async () => {
    if (!chosen.length) return
    const res = await run(() => api.profiles.importAssets(name, {
      repository: repository.trim(), ref: ref.trim(), note: note.trim(),
      files: chosen.map((f) => ({ path: f.path, id: f.suggested_id, dest: f.suggested_dest })),
    }), `${chosen.length} asset${chosen.length === 1 ? '' : 's'} imported`)
    if (res) {
      res.warnings.forEach((w) => notify(`${w.id}: ${w.warnings.join('; ')}`))
      onImported()
    }
  }

  return (
    <Modal title={`Import assets into ${name}`} wide onClose={onClose}
      description="Copies text files out of a repository into this profile's Assets layer. The clone is temporary and read-only — connecting a repository to a run stays a Control Centre action.">
      <form onSubmit={browse}>
        <div className="form-grid">
          <Field label="Repository" htmlFor="ia-repo" required className="full"
            help="Must satisfy this profile's GitHub integration — host and allowed owners.">
            <input id="ia-repo" data-autofocus type="text" className="mono-input" value={repository}
              onChange={(e) => setRepository(e.target.value)} placeholder="https://github.com/owner/repo"
              autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="Branch or tag" htmlFor="ia-ref" optional>
            <input id="ia-ref" type="text" className="mono-input" value={ref} onChange={(e) => setRef(e.target.value)} placeholder="default branch" spellCheck={false} />
          </Field>
          <Field label="Subdirectory" htmlFor="ia-sub" optional help="Limit the listing to one folder.">
            <input id="ia-sub" type="text" className="mono-input" value={subdir} onChange={(e) => setSubdir(e.target.value)} placeholder="e.g. db" spellCheck={false} />
          </Field>
        </div>
        <div className="btn-row right" style={{ marginTop: 16 }}>
          <Button type="submit" variant="secondary" icon={<Search />} busy={busy} disabled={!repository.trim()}>Browse</Button>
        </div>
      </form>

      {result && (
        <>
          <div className="hint sm" style={{ margin: '12px 0 6px' }}>
            {result.importable} of {result.files.length} file{result.files.length === 1 ? '' : 's'} can be imported.
            {result.truncated ? ' Listing truncated — narrow it with a subdirectory.' : ''}
          </div>
          {result.files.length === 0 && <Empty title="No files here" hint="Check the branch and subdirectory." />}
          <div role="list" aria-label="Files in the repository" style={{ maxHeight: 300, overflowY: 'auto', borderTop: '1px solid var(--line)' }}>
            {result.files.map((f) => (
              <label key={f.path} role="listitem" className="check"
                style={{ display: 'flex', gap: 10, alignItems: 'baseline', padding: '6px 4px', borderBottom: '1px solid var(--line)', opacity: f.importable ? 1 : 0.55 }}>
                <input type="checkbox" disabled={!f.importable} checked={Boolean(picked[f.path])}
                  onChange={(e) => setPicked((m) => ({ ...m, [f.path]: e.target.checked }))} />
                <span style={{ flex: 1, minWidth: 0 }}>
                  <span className="mono">{f.path}</span>
                  <span className="hint sm" style={{ display: 'block' }}>
                    {f.importable
                      ? <>→ <span className="mono">.s7/assets/{f.suggested_dest}</span> · {f.bytes} bytes</>
                      : f.reason}
                  </span>
                </span>
              </label>
            ))}
          </div>
          <div style={{ marginTop: 14 }}>
            <Field label="Note" htmlFor="ia-note" optional help="Becomes the v1 ledger line on every file imported.">
              <input id="ia-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why these files are part of the project" />
            </Field>
          </div>
        </>
      )}

      <div className="btn-row right" style={{ marginTop: 20 }}>
        <Button variant="secondary" onClick={onClose}>Cancel</Button>
        <Button variant="primary" icon={<Download />} busy={busy} disabled={!chosen.length} onClick={() => void doImport()}>
          Import {chosen.length || ''} file{chosen.length === 1 ? '' : 's'}
        </Button>
      </div>
    </Modal>
  )
}

/* --- new file ------------------------------------------------------------- */

function NewFileForm({ name, onClose, onCreated, initialLayer = 'skill' }: { name: string; onClose: () => void; onCreated: (id: string) => void; initialLayer?: ProfileLayer }) {
  const { run, notify, busy } = useAdmin()
  const [layer, setLayer] = useState<ProfileLayer>(initialLayer)
  const [id, setId] = useState('')
  const [title, setTitle] = useState('')
  const [stage, setStage] = useState('')
  const [summary, setSummary] = useState('')
  const [variables, setVariables] = useState('')
  const [locked, setLocked] = useState('')
  const [body, setBody] = useState('')
  const [note, setNote] = useState('')
  const [dest, setDest] = useState('')
  const [touched, setTouched] = useState(false)
  const [wrap, setWrap] = useState(true)

  const isJson = JSON_LAYERS.has(layer)
  const isAsset = layer === 'asset'
  const idErr = !id ? 'An id is required.' : !/^[a-z][a-z0-9-]{1,63}$/.test(id) ? 'Lowercase letters, digits and hyphens, starting with a letter.' : null
  const destErr = !isAsset ? null
    : !dest.trim() ? 'A destination is required — where the file publishes to under .s7/assets/.'
    : !/^[A-Za-z0-9][A-Za-z0-9._/-]*\.[A-Za-z0-9]+$/.test(dest.trim()) || dest.includes('..') || dest.includes('//')
      ? 'A relative path ending in a file extension, with no leading slash and no “..”.'
      : dest.trim().split('/').length > 5 ? 'At most four directories deep.' : null
  const noteErr = !note.trim() ? 'A note is required — it becomes the v1 ledger line.' : null
  const bodyErr = !body.trim() ? 'A body is required.' : isJson ? (jsonError(body) ? `Not valid JSON: ${jsonError(body)}` : null) : null
  const vars = variables.split(',').map((v) => v.trim()).filter(Boolean)
  const locks = locked.split(',').map((v) => v.trim()).filter(Boolean)
  const used = usedPlaceholders(body)
  const undeclared = layer === 'task' ? used.filter((u) => !vars.includes(u)) : []
  const missing = missingLocked(body, locks)

  const submit = async (e?: React.FormEvent) => {
    e?.preventDefault()
    setTouched(true)
    if (idErr || destErr || noteErr || bodyErr || undeclared.length || missing.length) return
    // An asset goes through its own endpoint so the credential refusal and
    // the PII warnings apply however it was authored.
    if (isAsset) {
      const made = await run(() => api.profiles.createAsset(name, {
        id, dest: dest.trim(), title, summary, body, note, stage: stage || 'build_review',
      }), `${id} created as v1`)
      if (made) {
        if (made.warnings?.length) notify(`${id}: ${made.warnings.join('; ')}`)
        onCreated(made.file.id)
      }
      return
    }
    const created = await run(() => api.profiles.createFile(name, {
      layer, id, title, stage, summary, body, note, variables: layer === 'task' ? vars : [], locked: locks,
    }), `${id} created as v1`)
    if (created) onCreated(created.file.id)
  }

  return (
    <Modal title={`New file in ${name}`} description="Adds a file to this profile only and records it as v1 in the profile's ledger. It does not exist in the default set, so nothing shows through under it." onClose={onClose} wide>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Layer" htmlFor="nf-layer">
            <select id="nf-layer" data-autofocus value={layer} onChange={(e) => setLayer(e.target.value as ProfileLayer)}>
              {ALL_LAYERS.map((l) => <option key={l} value={l}>{LAYER_LABEL[l]}</option>)}
            </select>
          </Field>
          <Field label="Id" htmlFor="nf-id" required error={touched && idErr ? idErr : undefined} help="Becomes the file name.">
            <input id="nf-id" type="text" className={`mono-input${touched && idErr ? ' invalid' : ''}`} value={id} onChange={(e) => setId(e.target.value.trim())} placeholder="e.g. claims-reviewer" autoComplete="off" spellCheck={false} aria-invalid={Boolean(touched && idErr)} />
          </Field>
          {isAsset && (
            <Field label="Publishes to" htmlFor="nf-dest" required
              error={touched && destErr ? destErr : undefined}
              help={<>Relative to <span className="mono">.s7/assets/</span> in the developer&rsquo;s repository.</>}>
              <input id="nf-dest" type="text" className={`mono-input${touched && destErr ? ' invalid' : ''}`} value={dest}
                onChange={(e) => setDest(e.target.value.trim())} placeholder="e.g. db/baseline-schema.sql"
                autoComplete="off" spellCheck={false} aria-invalid={Boolean(touched && destErr)} />
            </Field>
          )}
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
            <Field label="Variables" htmlFor="nf-vars" help={<>Comma-separated. A task body may only use placeholders declared here, written as {'{{name}}'}.</>}>
              <input id="nf-vars" type="text" className="mono-input" value={variables} onChange={(e) => setVariables(e.target.value)} placeholder="epic_text, repo_context" spellCheck={false} />
            </Field>
          )}
          {!isAsset && <Field label="Locked tokens" htmlFor="nf-locked" optional help="Comma-separated literal strings every later edit must keep — the lines a consumer depends on."
            error={touched && missing.length ? `Not in the body: ${missing.join(', ')}` : undefined}>
            <input id="nf-locked" type="text" className="mono-input" value={locked} onChange={(e) => setLocked(e.target.value)} placeholder="e.g. ## Acceptance criteria" spellCheck={false} />
          </Field>}
          <Field label={isJson ? 'Body (JSON)' : 'Body'} htmlFor="nf-body" required className="full"
            error={touched && bodyErr ? bodyErr : undeclared.length > 0 ? `Undeclared placeholders: ${undeclared.map((u) => `{{${u}}}`).join(', ')}` : undefined}
            help={isJson ? 'This layer is JSON — the server refuses anything that does not parse.' : undefined}>
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

/* --- workflow preview ------------------------------------------------------ */

/** `llm` is `{provider?, model?}` per the contract; the backend today keys
 * it by the workflow's stage (`{"intake-analysis": {...}}`). Accept both. */
function effectiveLlm(wf: WorkflowPreview): { provider?: string | null; model?: string | null } {
  const llm = (wf.llm ?? {}) as Record<string, unknown>
  if ('provider' in llm || 'model' in llm) return llm as { provider?: string | null; model?: string | null }
  const first = Object.values(llm)[0]
  return (first && typeof first === 'object' ? first : {}) as { provider?: string | null; model?: string | null }
}

/** The prompt-set workflow routes resolve a profile name too (they are
 * aliases over the same files); a 404 shows the designed empty state. */
function WorkflowDrawer({ name, onClose }: { name: string; onClose: () => void }) {
  const { data: list, error, loading } = useLoad(() => api.promptSets.workflows(name).catch((err: unknown) => {
    if (err instanceof ApiError && err.status === 404) return null
    throw err
  }), [name])
  const [picked, setPicked] = useState<string>('')
  const wf: WorkflowPreview | undefined = useMemo(() => list?.find((w) => w.id === picked) ?? list?.[0], [list, picked])

  return (
    <DetailDrawer title="Workflow preview" subtitle={`Assembled from ${name} — the exact system prompt a workflow would send, its task templates and the provider/model in effect.`} ariaLabel="Workflow preview" onClose={onClose}>
      {loading && list === undefined ? <Loading what="Loading workflows" /> : null}
      {error ? <Notice tone="danger" title="Could not load workflows.">{error}</Notice> : null}
      {list === null ? <Empty title="No preview for this profile" hint="The workflow preview route does not resolve this name on this backend." /> : null}
      {list && list.length === 0 ? <Empty title="No workflows" hint="This profile declares no workflows." /> : null}
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

/* --- page ------------------------------------------------------------------- */

export function ProfileEditor() {
  const { editingSet, editorFileFocus, clearEditorFileFocus, goTo } = useAdmin()
  const name = editingSet ?? 'default'
  const { data, error, loading, reload } = useLoad(() => api.profiles.detail(name), [name])
  const [selected, setSelected] = useState<string | null>(null)
  const [newFile, setNewFile] = useState(false)
  const [importing, setImporting] = useState(false)
  const [preview, setPreview] = useState(false)
  const [confirmLeave, setConfirmLeave] = useState(false)

  const all = useMemo(() => (data?.groups ?? []).flatMap((g) => g.files), [data])

  // A link elsewhere (Repositories → "Edit in profile editor") may name the
  // file to open; honoured once the detail is loaded, then cleared.
  useEffect(() => {
    if (!data) return
    if (editorFileFocus) {
      clearEditorFileFocus()
      if (all.some((f) => f.id === editorFileFocus)) { setSelected(editorFileFocus); return }
    }
    if (!selected || !all.some((f) => f.id === selected)) setSelected(all[0]?.id ?? null)
  }, [data, all, selected, editorFileFocus, clearEditorFileFocus])

  const onChanged = useCallback(() => reload(), [reload])

  const overridden = data?.overridden?.length ?? 0
  const lead = data
    ? `${data.description || 'No description'} — ${data.files} files resolved${data.is_default ? '' : `, ${overridden} overridden here`}, ${data.versions} ledger line${data.versions === 1 ? '' : 's'}.`
    : undefined

  return (
    <>
      <PageHeader
        title={<span className="inline">Profile Editor <span className="mono" style={{ fontSize: 20, fontWeight: 500, color: 'var(--muted)' }}>{name}</span>{data ? <KindBadge kind={data.kind} /> : null}</span>}
        description={lead ? <>{lead} {data?.fingerprint ? <span className="mono" title="Fingerprint of the resolved file set">fingerprint {data.fingerprint}</span> : null}</> : undefined}
        actions={<>
          <Button variant="ghost" size="sm" icon={<ArrowLeft />} onClick={() => setConfirmLeave(true)}>All profiles</Button>
          <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>
          <Button variant="secondary" size="sm" icon={<Eye />} onClick={() => setPreview(true)} disabled={!data}>Workflow preview</Button>
          <Button variant="secondary" size="sm" icon={<Download />} onClick={() => setImporting(true)} disabled={!data || data.is_default}
            title={data?.is_default ? 'The default set is recording-pinned and ships no assets' : 'Copy project artifacts out of a repository'}>Import assets</Button>
          <Button variant="primary" size="sm" icon={<Plus />} onClick={() => setNewFile(true)} disabled={!data}>New file</Button>
        </>}
      />
      {confirmLeave && (
        <div style={{ marginBottom: 16 }}>
          <ConfirmPanel message="Leave the editor? Any unsaved body text is discarded." confirmLabel="Leave" onConfirm={() => { setConfirmLeave(false); goTo('profiles') }} onCancel={() => setConfirmLeave(false)} />
        </div>
      )}

      {data?.unrecorded?.length ? (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="warning" title={`${data.unrecorded.length} unrecorded file${data.unrecorded.length === 1 ? '' : 's'}.`}>
            <span className="mono">{data.unrecorded.join(', ')}</span> differ from the last ledger line. Save (with a note) to record, or roll back.
            {data.is_default ? ' The test suite refuses an unrecorded default file.' : ''}
          </Notice>
        </div>
      ) : null}

      {loading && !data ? <Loading what={`Loading ${name}`} /> : null}
      {error ? <LoadError what={`profile ${name}`} error={error} onRetry={reload} /> : null}
      {data && data.files === 0 ? <Empty title="This profile resolves no files" hint="Add the first one to start the ledger." action={<Button variant="primary" size="sm" icon={<Plus />} onClick={() => setNewFile(true)}>New file</Button>} /> : null}
      {data && data.files > 0 ? (
        <div className="editor-layout">
          <Card compact>
            <FileTree detail={data} selected={selected} onSelect={setSelected} />
          </Card>
          <div>
            {selected ? <FilePanel key={`${name}:${selected}`} name={name} id={selected} isDefault={data.is_default} onChanged={onChanged} /> : <Empty title="Select a file" hint="Pick a file on the left to read or edit it." />}
          </div>
        </div>
      ) : null}

      {newFile ? <NewFileForm name={name} onClose={() => setNewFile(false)} onCreated={(id) => { setNewFile(false); reload(); setSelected(id) }} /> : null}
      {importing ? <ImportAssetsForm name={name} onClose={() => setImporting(false)} onImported={() => { setImporting(false); reload() }} /> : null}
      {preview ? <WorkflowDrawer name={name} onClose={() => setPreview(false)} /> : null}
    </>
  )
}
