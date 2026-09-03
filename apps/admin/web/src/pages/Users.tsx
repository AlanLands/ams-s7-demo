import { Fragment, useState } from 'react'
import { Pencil, RefreshCw, Trash2, UserCheck, UserPlus, UserX } from 'lucide-react'
import { api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { ActionMenu, Badge, Button, Card, ConfirmPanel, Empty, Field, Loading, PageHeader, TableWrap, fmtTime } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { User } from '../types'

type Draft = { name: string; email: string; role: string; active: boolean }

export function UsersPage() {
  const { run, busy } = useAdmin()
  const users = useLoad(() => api.users.list())
  const roles = useLoad(() => api.roles.get())
  const [add, setAdd] = useState<{ name: string; email: string; role: string }>({ name: '', email: '', role: '' })
  const [editing, setEditing] = useState<{ id: string; draft: Draft } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)

  const roleList = roles.data?.roles ?? []
  const roleLabel = (id: string) => roleList.find((r) => r.id === id)?.label ?? id.replaceAll('_', ' ')
  const defaultRole = add.role || roleList[0]?.id || ''

  const create = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!add.name.trim() || !defaultRole) return
    const created = await run(() => api.users.create({ name: add.name.trim(), role: defaultRole, email: add.email.trim() || undefined }), `User ${add.name.trim()} added`)
    if (created) { setAdd({ name: '', email: '', role: '' }); users.reload() }
  }

  const saveEdit = async () => {
    if (!editing) return
    const d = editing.draft
    const updated = await run(() => api.users.update(editing.id, { name: d.name.trim(), email: d.email.trim() || null, role: d.role, active: d.active }), 'User updated')
    if (updated) { setEditing(null); users.reload() }
  }

  const toggleActive = async (u: User) => {
    const updated = await run(() => api.users.update(u.id, { active: !u.active }), `${u.name} ${u.active ? 'deactivated' : 'activated'}`)
    if (updated) users.reload()
  }

  const remove = async (u: User) => {
    const ok = await run(async () => { await api.users.remove(u.id); return true }, `${u.name} deleted`)
    setConfirmDelete(null)
    if (ok) users.reload()
  }

  return (
    <>
      <PageHeader
        title="Users"
        description="Named people the Control Centre can act as. Choosing one there sets the acting role and records the person's name on approvals — the server still enforces every separation rule."
        actions={<Button variant="secondary" size="sm" icon={<RefreshCw />} onClick={() => { users.reload(); roles.reload() }} disabled={users.loading}>Refresh</Button>}
      />

      <Card title="Add a user" description="Creates an “Act as” identity for the Control Centre's role picker.">
        <form onSubmit={create}>
          <div className="form-row">
            <Field label="Name" htmlFor="u-name" required>
              <input id="u-name" type="text" value={add.name} onChange={(e) => setAdd({ ...add, name: e.target.value })} placeholder="e.g. Priya Kapoor" autoComplete="off" />
            </Field>
            <Field label="Email" htmlFor="u-email" optional>
              <input id="u-email" type="email" value={add.email} onChange={(e) => setAdd({ ...add, email: e.target.value })} placeholder="name@example.com" autoComplete="off" />
            </Field>
            <Field label="Role" htmlFor="u-role" error={roles.error ? `Could not load roles: ${roles.error}` : undefined}>
              <select id="u-role" value={defaultRole} onChange={(e) => setAdd({ ...add, role: e.target.value })} disabled={!roleList.length}>
                {roleList.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
              </select>
            </Field>
            <div className="fld-group fixed">
              <Button type="submit" variant="primary" icon={<UserPlus />} disabled={!add.name.trim() || !defaultRole} busy={busy}>Add user</Button>
            </div>
          </div>
        </form>
      </Card>

      <div style={{ height: 24 }} />
      {users.loading && !users.data ? <Loading what="Loading users" /> : null}
      {users.error ? <LoadError what="users" error={users.error} onRetry={users.reload} /> : null}
      {users.data && users.data.length === 0 ? <Empty title="No users yet" hint="Without users the Control Centre offers plain roles only. Add one above to enable “Act as”." /> : null}
      {users.data && users.data.length > 0 ? (
        <TableWrap label="Users">
          <table>
            <thead><tr><th>Id</th><th>Name</th><th>Email</th><th>Role</th><th>Status</th><th>Created</th><th className="actions-col"><span className="sr-only">Actions</span></th></tr></thead>
            <tbody>
              {users.data.map((u) => {
                const isEd = editing?.id === u.id
                const d = editing?.draft
                return (
                  <Fragment key={u.id}>
                  <tr className={isEd ? 'edit-row' : ''}>
                    <td className="mono">{u.id}</td>
                    <td>{isEd && d ? <input type="text" value={d.name} onChange={(e) => setEditing({ id: u.id, draft: { ...d, name: e.target.value } })} aria-label="Name" /> : <b>{u.name}</b>}</td>
                    <td>{isEd && d ? <input type="email" value={d.email} onChange={(e) => setEditing({ id: u.id, draft: { ...d, email: e.target.value } })} aria-label="Email" /> : (u.email || <span className="muted">—</span>)}</td>
                    <td>
                      {isEd && d ? (
                        <select value={d.role} onChange={(e) => setEditing({ id: u.id, draft: { ...d, role: e.target.value } })} aria-label="Role">
                          {roleList.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                          {!roleList.some((r) => r.id === d.role) && <option value={d.role}>{d.role}</option>}
                        </select>
                      ) : <>{roleLabel(u.role)}<span className="sub mono">{u.role}</span></>}
                    </td>
                    <td>
                      {isEd && d ? (
                        <label className="check"><input type="checkbox" checked={d.active} onChange={(e) => setEditing({ id: u.id, draft: { ...d, active: e.target.checked } })} /> Active</label>
                      ) : <Badge status={u.active ? 'active' : 'inactive'} label={u.active ? 'Active' : 'Inactive'} />}
                    </td>
                    <td className="nowrap">{fmtTime(u.created_at)}</td>
                    <td className="actions-col">
                      {isEd ? (
                        <div className="cell-actions">
                          <Button variant="primary" size="sm" onClick={saveEdit} disabled={!d?.name.trim()} busy={busy}>Save</Button>
                          <Button variant="secondary" size="sm" onClick={() => setEditing(null)}>Cancel</Button>
                        </div>
                      ) : (
                        <div className="cell-actions">
                          <Button variant="secondary" size="sm" icon={<Pencil />} onClick={() => setEditing({ id: u.id, draft: { name: u.name, email: u.email ?? '', role: u.role, active: u.active } })}>Edit</Button>
                          <ActionMenu label={`More actions for ${u.name}`} items={[
                            { label: u.active ? 'Deactivate' : 'Activate', icon: u.active ? <UserX /> : <UserCheck />, onSelect: () => toggleActive(u) },
                            { label: 'Delete', icon: <Trash2 />, danger: true, onSelect: () => setConfirmDelete(u.id) },
                          ]} />
                        </div>
                      )}
                    </td>
                  </tr>
                  {confirmDelete === u.id && (
                    <tr className="sel">
                      <td colSpan={7} style={{ paddingTop: 0 }}>
                        <ConfirmPanel danger message={<>Delete <b>{u.name}</b> ({u.id})? Approvals already recorded under this name are kept.</>} confirmLabel="Delete user" busy={busy} onConfirm={() => remove(u)} onCancel={() => setConfirmDelete(null)} />
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
    </>
  )
}
