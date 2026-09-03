import { Fragment, useEffect, useMemo, useState } from 'react'
import { RotateCcw, Save, Undo2 } from 'lucide-react'
import { ApiError, api } from '../api'
import { useLoad, LoadError } from '../hooks'
import { Badge, Button, Card, ConfirmPanel, Field, Loading, Notice, PageHeader, SectionHead, TableWrap, humanize } from '../components/ui'
import { useAdmin } from '../state/AdminContext'
import type { RolesPayload } from '../types'

const GROUP_ORDER = ['intake', 'planning', 'build_review', 'quality', 'release', 'governance', 'run']

type Profile = { label: string; summary: string; signs: string }

function same(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false
  const s = new Set(a)
  return b.every((x) => s.has(x))
}

/** Two-line column header: the label wraps, the summary is the hover text. */
function shortLabel(label: string): string {
  return label.replace(/^Independent /, 'Indep. ').replace(/^Engineering /, 'Eng. ')
}

export function RolesPage() {
  const { run, fail, notify, busy } = useAdmin()
  const { data, setData, error, loading, reload } = useLoad(() => api.roles.get())
  const [perms, setPerms] = useState<Record<string, string[]>>({})
  const [profiles, setProfiles] = useState<Record<string, Profile>>({})
  const [validation, setValidation] = useState<string | null>(null)
  const [confirmReset, setConfirmReset] = useState(false)

  useEffect(() => {
    if (!data) return
    setPerms(Object.fromEntries(data.actions.map((a) => [a.action, [...a.roles]])))
    setProfiles(Object.fromEntries(data.roles.map((r) => [r.id, { label: r.label, summary: r.summary, signs: r.signs.join(', ') }])))
    setValidation(null)
  }, [data])

  const groups = useMemo(() => {
    if (!data) return []
    const by = new Map<string, typeof data.actions>()
    for (const a of data.actions) { const l = by.get(a.group) ?? []; l.push(a); by.set(a.group, l) }
    return [...by.keys()].sort((x, y) => {
      const ix = GROUP_ORDER.indexOf(x), iy = GROUP_ORDER.indexOf(y)
      return (ix === -1 ? 99 : ix) - (iy === -1 ? 99 : iy)
    }).map((g) => ({ group: g, rows: by.get(g)! }))
  }, [data])

  const dirty = useMemo(() => {
    if (!data) return false
    if (data.actions.some((a) => !same(perms[a.action] ?? [], a.roles))) return true
    return data.roles.some((r) => {
      const p = profiles[r.id]
      return p && (p.label !== r.label || p.summary !== r.summary || p.signs !== r.signs.join(', '))
    })
  }, [data, perms, profiles])

  const emptyActions = useMemo(() => Object.entries(perms).filter(([, v]) => v.length === 0).map(([k]) => k), [perms])

  const toggle = (action: string, role: string) => {
    setValidation(null)
    setPerms((p) => {
      const cur = p[action] ?? []
      return { ...p, [action]: cur.includes(role) ? cur.filter((r) => r !== role) : [...cur, role] }
    })
  }

  const discard = () => {
    if (!data) return
    setPerms(Object.fromEntries(data.actions.map((a) => [a.action, [...a.roles]])))
    setProfiles(Object.fromEntries(data.roles.map((r) => [r.id, { label: r.label, summary: r.summary, signs: r.signs.join(', ') }])))
    setValidation(null)
  }

  const save = async () => {
    if (!data) return
    setValidation(null)
    // Every action's current holder list is sent as a complete replacement;
    // the server treats a list identical to the default as no override.
    const body = {
      permissions: Object.fromEntries(data.actions.map((a) => [a.action, perms[a.action] ?? []])),
      profiles: Object.fromEntries(data.roles.map((r) => {
        const p = profiles[r.id]
        return [r.id, { label: p?.label ?? r.label, summary: p?.summary ?? r.summary, signs: (p?.signs ?? r.signs.join(', ')).split(',').map((s) => s.trim()).filter(Boolean) }]
      })),
    }
    try {
      await run(async () => {
        try {
          const fresh = await api.roles.save(body)
          setData(fresh)
          notify('Roles saved — the engine consults the new table on the next request')
        } catch (err) {
          if (err instanceof ApiError && err.status === 400) { setValidation(err.message); return }
          throw err
        }
      })
    } catch (err) { fail(err) }
  }

  const reset = async () => {
    const fresh = await run(() => api.roles.reset(), 'Roles reset to the built-in defaults')
    setConfirmReset(false)
    if (fresh) setData(fresh as RolesPayload)
  }

  const overriddenCount = data ? data.actions.filter((a) => a.overridden).length + data.roles.filter((r) => r.overridden).length : 0

  const header = (
    <PageHeader
      title="Roles & Permissions"
      description="Who may sign what. Rows are actions grouped by phase; columns are roles. Overrides are complete replacements per action — the checked set is the holder set. The server keeps enforcing every separation rule on every request; this table changes who signs, never what is checked."
      actions={<>
        <Button variant="secondary" size="sm" icon={<Undo2 />} onClick={discard} disabled={!dirty}>Discard changes</Button>
        <Button variant="danger" size="sm" icon={<RotateCcw />} onClick={() => setConfirmReset(true)} disabled={overriddenCount === 0}>Reset to defaults</Button>
        <Button variant="primary" size="sm" icon={<Save />} onClick={save} disabled={!dirty || emptyActions.length > 0} busy={busy}
          title={emptyActions.length ? `Every action needs at least one holder: ${emptyActions.join(', ')}` : undefined}>Save</Button>
      </>}
    />
  )

  if (loading && !data) return <>{header}<Loading what="Loading roles" /></>
  if (error) return <>{header}<LoadError what="roles" error={error} onRetry={reload} /></>
  if (!data) return null

  return (
    <>
      {header}
      {confirmReset && (
        <div style={{ marginBottom: 16 }}>
          <ConfirmPanel danger message={<>Clear every override ({overriddenCount}) and return to the built-in permission table and role profiles?</>} confirmLabel="Reset to defaults" busy={busy} onConfirm={reset} onCancel={() => setConfirmReset(false)} />
        </div>
      )}
      {validation && <div style={{ marginBottom: 16 }}><Notice tone="danger" title="Refused by validation (400).">{validation}</Notice></div>}
      {emptyActions.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="danger" title="Every action needs at least one holder.">Unassigned: <span className="mono">{emptyActions.join(', ')}</span></Notice>
        </div>
      )}
      {dirty && emptyActions.length === 0 && !validation && (
        <div style={{ marginBottom: 16 }}>
          <Notice tone="warning" title="Unsaved changes.">Rows marked “unsaved” differ from what the server holds. Save to apply, or discard.</Notice>
        </div>
      )}

      <TableWrap label="Permission matrix">
        <table className="matrix">
          <thead>
            <tr>
              <th scope="col">Action</th>
              {data.roles.map((r) => (
                <th key={r.id} scope="col" className="role">
                  <abbr title={`${profiles[r.id]?.label ?? r.label} — ${r.summary}`}>{shortLabel(profiles[r.id]?.label ?? r.label)}</abbr>
                </th>
              ))}
              <th scope="col" className="holders">Default holders</th>
            </tr>
          </thead>
          <tbody>
            {groups.map((g) => (
              <Fragment key={g.group}>
                <tr className="grp"><td colSpan={data.roles.length + 2}>{humanize(g.group)}</td></tr>
                {g.rows.map((a) => {
                  const cur = perms[a.action] ?? []
                  const differsFromDefault = !same(cur, a.default_roles)
                  return (
                    <tr key={a.action} className={a.overridden || differsFromDefault ? 'overridden' : ''}>
                      <td className="action-name">
                        <span className="mono">{a.action}</span>
                        {a.overridden && <Badge variant="warning" label="Overridden" />}
                        {!a.overridden && differsFromDefault && <Badge variant="warning" label="Unsaved" />}
                      </td>
                      {data.roles.map((r) => (
                        <td key={r.id} className="cell">
                          <label>
                            <input type="checkbox" checked={cur.includes(r.id)} onChange={() => toggle(a.action, r.id)} aria-label={`${a.action}: ${r.label}`} />
                          </label>
                        </td>
                      ))}
                      <td className="holders">{a.default_roles.map((d) => data.roles.find((r) => r.id === d)?.label ?? d).join(', ')}</td>
                    </tr>
                  )
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </TableWrap>

      <SectionHead title="Role profiles" description="What the Control Centre's role picker shows: a label, one line on what the role owns, and the decisions it signs." />
      <div className="grid cols-3">
        {data.roles.map((r) => {
          const p = profiles[r.id] ?? { label: r.label, summary: r.summary, signs: r.signs.join(', ') }
          return (
            <Card key={r.id} compact title={<span className="mono">{r.id}</span>} actions={r.overridden ? <Badge variant="warning" label="Overridden" /> : undefined}>
              <div className="stack tight">
                <Field label="Label" htmlFor={`rp-${r.id}-label`}>
                  <input id={`rp-${r.id}-label`} type="text" value={p.label} onChange={(e) => setProfiles((s) => ({ ...s, [r.id]: { ...p, label: e.target.value } }))} />
                </Field>
                <Field label="Summary" htmlFor={`rp-${r.id}-summary`}>
                  <textarea id={`rp-${r.id}-summary`} rows={2} value={p.summary} onChange={(e) => setProfiles((s) => ({ ...s, [r.id]: { ...p, summary: e.target.value } }))} />
                </Field>
                <Field label="Signs" htmlFor={`rp-${r.id}-signs`} help={`Comma-separated. ${r.actions.length} action${r.actions.length === 1 ? '' : 's'} held.`}>
                  <input id={`rp-${r.id}-signs`} type="text" value={p.signs} onChange={(e) => setProfiles((s) => ({ ...s, [r.id]: { ...p, signs: e.target.value } }))} />
                </Field>
              </div>
            </Card>
          )
        })}
      </div>
    </>
  )
}
