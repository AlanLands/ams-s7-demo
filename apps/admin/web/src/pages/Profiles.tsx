import { Fragment, useRef, useState } from 'react'
import { Download, Pencil, Plus, RefreshCw, Trash2, Upload } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { ActionMenu, Badge, Button, ConfirmPanel, Empty, Field, Loading, Modal, Notice, PageHeader, TableWrap, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { ProfileGroupId, ProfileKind, ProfileSummary } from '../types'

/* Delivery Profiles — one bundle of seven layers per client or project. The
 * page is a table, like every list here; the one element particular to it
 * is the layer strip: seven cells in a fixed order, so a reader can compare
 * profiles by scanning down a column. */

// Same rule as product/profiles.py `_NAME_RE`.
const NAME = /^[a-z][a-z0-9-]{1,39}$/

export const GROUP_ORDER: { id: ProfileGroupId; short: string; title: string }[] = [
  { id: 'prompts', short: 'prompts', title: 'Prompts — rules, skills, tasks, playbooks: what the models are told' },
  { id: 'standards', short: 'standards', title: 'Standards — what developers are told' },
  { id: 'templates', short: 'templates', title: 'Templates — what S7 generates mechanically' },
  { id: 'governance', short: 'governance', title: 'Governance — who may decide what' },
  { id: 'models', short: 'models', title: 'Models — provider and model per stage, pricing' },
  { id: 'identity', short: 'identity', title: 'Identity — the tenant\'s name and palette' },
  { id: 'integrations', short: 'integrations', title: 'Integrations — the tenant\'s git hosting' },
]

export function KindBadge({ kind }: { kind: ProfileKind }) {
  if (kind === 'default') return <Badge variant="info" label="Default" title="The committed default set — recording-pinned; every profile falls through to it" />
  if (kind === 'legacy-set') return <Badge variant="neutral" label="Legacy copy" title="A full-copy prompt set created before profiles existed; still resolves, cannot export" />
  return <Badge variant="success" label="Profile" title="An overlay over the default set" />
}

/** Seven cells, fixed order, one per layer group. */
export function LayerStrip({ counts }: { counts: ProfileSummary['counts'] }) {
  return (
    <span className="layer-strip" role="img" aria-label={GROUP_ORDER.map((g) => `${counts?.[g.id] ?? 0} ${g.short}`).join(', ')}>
      {GROUP_ORDER.map((g) => {
        const n = counts?.[g.id] ?? 0
        return <span key={g.id} className={n === 0 ? 'zero' : undefined} title={g.title}><b>{n}</b>{g.short}</span>
      })}
    </span>
  )
}

function CreateForm({ existing, onDone, onClose }: { existing: ProfileSummary[]; onDone: () => void; onClose: () => void }) {
  const { run, openEditor, busy } = useAdmin()
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [touched, setTouched] = useState(false)

  const nameErr = !name ? 'A name is required.'
    : !NAME.test(name) ? 'Lowercase kebab-case, 2–40 characters, starting with a letter (e.g. maplesure-claims).'
      : existing.some((p) => p.name === name) ? 'That name is already taken by a profile or a legacy set.' : null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (nameErr) return
    const created = await run(() => api.profiles.create({ name, description }), `Profile “${name}” created`)
    if (created) { onDone(); openEditor(created.name) }
  }

  return (
    <Modal title="New profile" description="An overlay: nothing is copied. Every file shows through from the default set until you edit it here, and only the files you change are stored under the profile." onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Name" htmlFor="pf-name" required
            help="Becomes the directory name under config/profiles/ and the name a run pins."
            error={touched && nameErr ? nameErr : undefined}>
            <input id="pf-name" data-autofocus type="text" className={touched && nameErr ? 'invalid' : ''} value={name} placeholder="e.g. maplesure-claims"
              autoComplete="off" spellCheck={false} aria-invalid={Boolean(touched && nameErr)}
              onChange={(e) => setName(e.target.value.trim())} onBlur={() => setTouched(true)} />
          </Field>
          <Field label="Description" htmlFor="pf-desc" optional>
            <input id="pf-desc" type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Which client or project this configures" />
          </Field>
        </div>
        <div className="btn-row right" style={{ marginTop: 24 }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={Boolean(nameErr) && touched} busy={busy}>Create profile</Button>
        </div>
      </form>
    </Modal>
  )
}

function ImportForm({ onDone, onClose }: { onDone: (name: string) => void; onClose: () => void }) {
  const { busy, fail } = useAdmin()
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [replace, setReplace] = useState(false)
  const [touched, setTouched] = useState(false)
  const [refused, setRefused] = useState<string | null>(null)
  const [working, setWorking] = useState(false)
  const input = useRef<HTMLInputElement>(null)

  const fileErr = !file ? 'Choose the exported .zip.' : null
  const nameErr = name && !NAME.test(name) ? 'Lowercase kebab-case, 2–40 characters, starting with a letter.' : null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (fileErr || nameErr || !file) return
    setRefused(null)
    setWorking(true)
    try {
      const created = await api.profiles.importZip(file, { name: name || undefined, replace })
      onDone(created.name)
    } catch (err) {
      if (err instanceof ApiError && (err.status === 400 || err.status === 409)) setRefused(err.message)
      else fail(err)
    } finally {
      setWorking(false)
    }
  }

  return (
    <Modal title="Import profile" description="Installs a profile from a zip made by Export — its overrides, ledger and snapshots, exactly as exported. Every file must parse or nothing is installed." onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Zip file" htmlFor="pf-zip" required className="full" error={touched && fileErr ? fileErr : undefined}>
            <input ref={input} id="pf-zip" data-autofocus type="file" accept=".zip,application/zip" aria-invalid={Boolean(touched && fileErr)}
              onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          </Field>
          <Field label="Name" htmlFor="pf-iname" optional help="Blank keeps the name recorded in the zip's profile.json." error={nameErr ?? undefined}>
            <input id="pf-iname" type="text" className={nameErr ? 'invalid' : ''} value={name} onChange={(e) => setName(e.target.value.trim())} placeholder="e.g. maplesure-claims" autoComplete="off" spellCheck={false} />
          </Field>
          <Field label="Replace" htmlFor="pf-replace" help="Overwrites a profile of the same name. A default or legacy set is never replaced.">
            <label className="check" htmlFor="pf-replace"><input id="pf-replace" type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} /> Replace an existing profile</label>
          </Field>
        </div>
        {refused ? (
          <div style={{ marginTop: 16 }}>
            <Notice tone="danger" title="Not imported.">{refused}</Notice>
          </div>
        ) : null}
        <div className="btn-row right" style={{ marginTop: 24 }}>
          <Button variant="secondary" onClick={onClose} disabled={working}>Cancel</Button>
          <Button type="submit" variant="primary" icon={<Upload />} busy={working || busy}>Import profile</Button>
        </div>
      </form>
    </Modal>
  )
}

/** Fetch the zip with the auth headers, then hand it to the browser. */
export async function downloadExport(name: string): Promise<void> {
  const blob = await api.profiles.exportBlob(name)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${name}.profile.zip`
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export function ProfilesPage() {
  const { run, openEditor, fail, busy } = useAdmin()
  const { data, error, loading, reload } = useLoad(() => api.profiles.list())
  const [creating, setCreating] = useState(false)
  const [importing, setImporting] = useState(false)
  const [editingDesc, setEditingDesc] = useState<{ name: string; value: string } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleteRefused, setDeleteRefused] = useState<{ name: string; message: string } | null>(null)

  const saveDesc = async () => {
    if (!editingDesc) return
    const ok = await run(() => api.profiles.update(editingDesc.name, editingDesc.value), 'Description saved')
    if (ok) { setEditingDesc(null); reload() }
  }

  const doDelete = async (name: string) => {
    try {
      await api.profiles.remove(name)
      setConfirmDelete(null)
      setDeleteRefused(null)
      reload()
    } catch (err) {
      setConfirmDelete(null)
      if (err instanceof ApiError && err.status === 409) setDeleteRefused({ name, message: err.message })
      else fail(err)
    }
  }

  const doExport = (name: string) => run(() => downloadExport(name), `${name} exported`)

  const COLS = 9

  return (
    <>
      <PageHeader
        title="Delivery Profiles"
        description={<>
          One profile configures S7 for one client or project: seven layers — prompts, standards, templates, governance,
          models, identity, integrations — every setting a file, every change a version. A profile is an overlay over the default set:
          it stores only the files you change and the default shows through for the rest. A run pins the profile it was created from.
        </>}
        actions={<>
          <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>
          <Button variant="secondary" size="sm" icon={<Upload />} onClick={() => setImporting(true)}>Import profile</Button>
          <Button variant="primary" size="sm" icon={<Plus />} onClick={() => setCreating(true)} disabled={!data}>New profile</Button>
        </>}
      />

      {loading && !data ? <Loading what="Loading delivery profiles" /> : null}
      {error ? <LoadError what="delivery profiles" error={error} onRetry={reload} /> : null}
      {data && data.length === 0 ? (
        <Empty title="No profiles" hint="The backend should always report at least the default set — check the admin API." />
      ) : null}

      {data && data.length > 0 ? (
        <TableWrap label="Delivery profiles">
          <table>
            <thead>
              <tr>
                <th>Profile</th><th>Description</th><th>Layers</th><th className="num">Overridden</th><th className="num">Versions</th>
                <th>Recorded</th><th>Fingerprint</th><th>Created</th><th className="actions-col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((p) => {
                const editable = p.kind === 'profile'
                return (
                  <Fragment key={p.name}>
                    <tr>
                      <td>
                        <div className="inline">
                          <button type="button" className="btn btn-link mono" onClick={() => openEditor(p.name)}>{p.name}</button>
                          <KindBadge kind={p.kind} />
                        </div>
                        <span className="sub mono trunc" title={p.root} style={{ maxWidth: 240 }}>{p.root}</span>
                        {p.base && !p.is_default ? <span className="sub">over <span className="mono">{p.base}</span></span> : null}
                      </td>
                      <td style={{ minWidth: 220, maxWidth: 380 }}>
                        {editingDesc?.name === p.name ? (
                          <div className="stack tight">
                            <input type="text" value={editingDesc.value} autoFocus aria-label={`Description of ${p.name}`}
                              onChange={(e) => setEditingDesc({ name: p.name, value: e.target.value })}
                              onKeyDown={(e) => { if (e.key === 'Enter') void saveDesc(); if (e.key === 'Escape') setEditingDesc(null) }} />
                            <div className="btn-row">
                              <Button variant="primary" size="sm" onClick={saveDesc} busy={busy}>Save</Button>
                              <Button variant="secondary" size="sm" onClick={() => setEditingDesc(null)}>Cancel</Button>
                            </div>
                          </div>
                        ) : (
                          <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                            <span className="grow">{p.description || <span className="muted">No description</span>}</span>
                            {editable ? (
                              <button type="button" className="icon-btn sm plain" aria-label={`Edit description of ${p.name}`} title="Edit description" onClick={() => setEditingDesc({ name: p.name, value: p.description ?? '' })}><Pencil /></button>
                            ) : null}
                          </div>
                        )}
                      </td>
                      <td><LayerStrip counts={p.counts} /><span className="sub">{p.files} files resolved</span></td>
                      <td className="num" title={p.overridden.length ? p.overridden.join(', ') : p.is_default ? 'The default set has nothing to override' : 'Every file shows through from the default'}>
                        {p.is_default ? <span className="muted">—</span> : p.overridden.length}
                      </td>
                      <td className="num">{p.versions}</td>
                      <td>
                        {p.unrecorded.length === 0
                          ? <Badge variant="success" label="All recorded" />
                          : <Badge variant="warning" label={`${p.unrecorded.length} unrecorded`} title={p.unrecorded.join(', ')} />}
                      </td>
                      <td className="mono nowrap" title="One hash over the resolved file set — the profile's effective version; a run records it at creation">{p.fingerprint}</td>
                      <td className="nowrap">
                        {p.created_at ? fmtTime(p.created_at) : <span className="muted">committed</span>}
                        {p.created_by ? <span className="sub">{p.created_by}</span> : null}
                      </td>
                      <td className="actions-col">
                        <div className="cell-actions">
                          <Button variant="secondary" size="sm" onClick={() => openEditor(p.name)}>Open editor</Button>
                          <ActionMenu label={`More actions for ${p.name}`} items={[
                            { label: 'Export as zip', icon: <Download />, disabled: !editable,
                              title: !editable ? 'Only an overlay profile exports — the default is committed, a legacy copy has no overlay' : undefined,
                              onSelect: () => void doExport(p.name) },
                            { label: 'Delete profile', icon: <Trash2 />, danger: true, disabled: p.is_default, title: p.is_default ? 'The default set cannot be deleted' : undefined,
                              onSelect: () => { setDeleteRefused(null); setConfirmDelete(p.name) } },
                          ]} />
                        </div>
                      </td>
                    </tr>
                    {confirmDelete === p.name && (
                      <tr className="sel">
                        <td colSpan={COLS} style={{ paddingTop: 0 }}>
                          <ConfirmPanel
                            danger
                            message={<>Delete <b className="mono">{p.name}</b> — its {p.overridden.length} override{p.overridden.length === 1 ? '' : 's'}, ledger and snapshots? A profile named by any run is refused by the server; export first if you may want it back.</>}
                            confirmLabel="Delete profile"
                            onConfirm={() => doDelete(p.name)}
                            onCancel={() => setConfirmDelete(null)}
                          />
                        </td>
                      </tr>
                    )}
                    {deleteRefused?.name === p.name && (
                      <tr>
                        <td colSpan={COLS} style={{ paddingTop: 0 }}>
                          <Notice tone="danger" title="Not deleted (409)." actions={<Button variant="secondary" size="sm" onClick={() => setDeleteRefused(null)}>Dismiss</Button>}>{deleteRefused.message}</Notice>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </TableWrap>
      ) : null}

      {creating && data ? <CreateForm existing={data} onDone={() => { setCreating(false); reload() }} onClose={() => setCreating(false)} /> : null}
      {importing ? <ImportForm onDone={(name) => { setImporting(false); reload(); openEditor(name) }} onClose={() => setImporting(false)} /> : null}
    </>
  )
}
