import { Fragment, useState } from 'react'
import { Pencil, Plus, RefreshCw, Trash2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { ActionMenu, Badge, Button, ConfirmPanel, Empty, Field, Loading, Modal, Notice, PageHeader, TableWrap, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { SetSummary } from '../types'

const KEBAB = /^[a-z0-9]+(-[a-z0-9]+)*$/

function CreateForm({ sets, onDone, onClose }: { sets: SetSummary[]; onDone: () => void; onClose: () => void }) {
  const { run, openEditor, busy } = useAdmin()
  const [name, setName] = useState('')
  const [clonedFrom, setClonedFrom] = useState('default')
  const [description, setDescription] = useState('')
  const [note, setNote] = useState('')
  const [touched, setTouched] = useState(false)

  const nameErr = !name ? 'A name is required.'
    : !KEBAB.test(name) ? 'Use kebab-case: lowercase letters, digits and single hyphens (e.g. claims-experiment).'
      : sets.some((s) => s.name === name) ? 'That name is already taken.' : null

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setTouched(true)
    if (nameErr) return
    const created = await run(() => api.promptSets.create({
      name, cloned_from: clonedFrom, description: description || undefined, note: note || undefined,
    }), `Prompt set “${name}” created from ${clonedFrom}`)
    if (created) { onDone(); openEditor(created.name) }
  }

  return (
    <Modal title="New prompt set" description="A full copy of an existing set — every rules, skill, task and playbook file — with its own version ledger starting at v1. Runs choose a set at creation." onClose={onClose}>
      <form onSubmit={submit}>
        <div className="form-grid">
          <Field label="Name" htmlFor="ps-name" required
            help="kebab-case; becomes the directory name under config/prompt-sets/"
            error={touched && nameErr ? nameErr : undefined}>
            <input id="ps-name" data-autofocus type="text" className={touched && nameErr ? 'invalid' : ''} value={name} placeholder="e.g. claims-experiment"
              autoComplete="off" spellCheck={false} aria-invalid={Boolean(touched && nameErr)}
              onChange={(e) => setName(e.target.value.trim())} onBlur={() => setTouched(true)} />
          </Field>
          <Field label="Clone from" htmlFor="ps-clone">
            <select id="ps-clone" value={clonedFrom} onChange={(e) => setClonedFrom(e.target.value)}>
              {sets.map((s) => <option key={s.name} value={s.name}>{s.name}{s.is_default ? ' (default)' : ''} — {s.files} files</option>)}
            </select>
          </Field>
          <Field label="Description" htmlFor="ps-desc" optional className="full">
            <input id="ps-desc" type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="What this set is for" />
          </Field>
          <Field label="Note" htmlFor="ps-note" optional help="Recorded in the audit." className="full">
            <input id="ps-note" type="text" value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why it was created" />
          </Field>
        </div>
        <div className="btn-row right" style={{ marginTop: 24 }}>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" disabled={Boolean(nameErr) && touched} busy={busy}>Create set</Button>
        </div>
      </form>
    </Modal>
  )
}

export function PromptSets() {
  const { run, openEditor, fail, busy } = useAdmin()
  const { data, error, loading, reload } = useLoad(() => api.promptSets.list())
  const [creating, setCreating] = useState(false)
  const [editingDesc, setEditingDesc] = useState<{ name: string; value: string } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [deleteRefused, setDeleteRefused] = useState<{ name: string; message: string } | null>(null)

  const saveDesc = async () => {
    if (!editingDesc) return
    const ok = await run(() => api.promptSets.update(editingDesc.name, editingDesc.value), 'Description saved')
    if (ok) { setEditingDesc(null); reload() }
  }

  const doDelete = async (name: string) => {
    try {
      await api.promptSets.remove(name)
      setConfirmDelete(null)
      setDeleteRefused(null)
      reload()
    } catch (err) {
      setConfirmDelete(null)
      if (err instanceof ApiError && err.status === 409) setDeleteRefused({ name, message: err.message })
      else fail(err)
    }
  }

  const COLS = 7

  return (
    <>
      <PageHeader
        title="Prompt Sets"
        description="Named copies of the four file-backed layers — rules, skills, tasks, playbooks. A run pins one set; edits are versioned in the set's own ledger."
        actions={<>
          <Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={reload} disabled={loading}>Refresh</Button>
          <Button variant="primary" size="sm" icon={<Plus />} onClick={() => setCreating(true)} disabled={!data}>New set</Button>
        </>}
      />

      {loading && !data ? <Loading what="Loading prompt sets" /> : null}
      {error ? <LoadError what="prompt sets" error={error} onRetry={reload} /> : null}
      {data && data.length === 0 ? (
        <Empty title="No prompt sets" hint="The backend should always report at least the default set — check the admin API." />
      ) : null}

      {data && data.length > 0 ? (
        <TableWrap label="Prompt sets">
          <table>
            <thead>
              <tr>
                <th>Set</th><th>Description</th><th className="num">Files</th><th className="num">Versions</th><th>Recorded</th><th>Created</th><th className="actions-col"><span className="sr-only">Actions</span></th>
              </tr>
            </thead>
            <tbody>
              {data.map((s) => (
                <Fragment key={s.name}>
                  <tr>
                    <td>
                      <div className="inline">
                        <button type="button" className="btn btn-link mono" onClick={() => openEditor(s.name)}>{s.name}</button>
                        {s.is_default && <Badge variant="info" label="Default" />}
                      </div>
                      <span className="sub mono trunc" title={s.root} style={{ maxWidth: 240 }}>{s.root}</span>
                      {s.cloned_from ? <span className="sub">cloned from <span className="mono">{s.cloned_from}</span></span> : null}
                    </td>
                    <td style={{ minWidth: 240, maxWidth: 420 }}>
                      {editingDesc?.name === s.name ? (
                        <div className="stack tight">
                          <input type="text" value={editingDesc.value} autoFocus aria-label={`Description of ${s.name}`}
                            onChange={(e) => setEditingDesc({ name: s.name, value: e.target.value })}
                            onKeyDown={(e) => { if (e.key === 'Enter') void saveDesc(); if (e.key === 'Escape') setEditingDesc(null) }} />
                          <div className="btn-row">
                            <Button variant="primary" size="sm" onClick={saveDesc} busy={busy}>Save</Button>
                            <Button variant="secondary" size="sm" onClick={() => setEditingDesc(null)}>Cancel</Button>
                          </div>
                        </div>
                      ) : (
                        <div style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                          <span className="grow">{s.description || <span className="muted">No description</span>}</span>
                          <button type="button" className="icon-btn sm plain" aria-label={`Edit description of ${s.name}`} title="Edit description" onClick={() => setEditingDesc({ name: s.name, value: s.description ?? '' })}><Pencil /></button>
                        </div>
                      )}
                    </td>
                    <td className="num" title={`${s.counts.rules} rules, ${s.counts.skill} skills, ${s.counts.task} tasks, ${s.counts.playbook} playbooks`}>
                      {s.files}
                      <span className="sub">{s.counts.rules}r / {s.counts.skill}s / {s.counts.task}t / {s.counts.playbook}p</span>
                    </td>
                    <td className="num">{s.versions}</td>
                    <td>
                      {s.unrecorded.length === 0
                        ? <Badge variant="success" label="All recorded" />
                        : <Badge variant="warning" label={`${s.unrecorded.length} unrecorded`} title={s.unrecorded.join(', ')} />}
                    </td>
                    <td className="nowrap">
                      {fmtTime(s.created_at)}
                      {s.created_by ? <span className="sub">{s.created_by}</span> : null}
                    </td>
                    <td className="actions-col">
                      <div className="cell-actions">
                        <Button variant="secondary" size="sm" onClick={() => openEditor(s.name)}>Open editor</Button>
                        <ActionMenu label={`More actions for ${s.name}`} items={[
                          { label: 'Delete set', icon: <Trash2 />, danger: true, disabled: s.is_default, title: s.is_default ? 'The default set cannot be deleted' : undefined,
                            onSelect: () => { setDeleteRefused(null); setConfirmDelete(s.name) } },
                        ]} />
                      </div>
                    </td>
                  </tr>
                  {confirmDelete === s.name && (
                    <tr className="sel">
                      <td colSpan={COLS} style={{ paddingTop: 0 }}>
                        <ConfirmPanel
                          danger
                          message={<>Delete <b className="mono">{s.name}</b> and its {s.files} files and ledger? A set named by any run is refused by the server.</>}
                          confirmLabel="Delete set"
                          onConfirm={() => doDelete(s.name)}
                          onCancel={() => setConfirmDelete(null)}
                        />
                      </td>
                    </tr>
                  )}
                  {deleteRefused?.name === s.name && (
                    <tr>
                      <td colSpan={COLS} style={{ paddingTop: 0 }}>
                        <Notice tone="danger" title="Not deleted (409)." actions={<Button variant="secondary" size="sm" onClick={() => setDeleteRefused(null)}>Dismiss</Button>}>{deleteRefused.message}</Notice>
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </TableWrap>
      ) : null}

      {creating && data ? <CreateForm sets={data} onDone={() => { setCreating(false); reload() }} onClose={() => setCreating(false)} /> : null}
    </>
  )
}
