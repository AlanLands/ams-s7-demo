import { useEffect, useRef, useState } from 'react'
import { Check, ChevronDown } from 'lucide-react'
import { useRun } from '../state/RunContext'

function initials(label: string): string {
  return label.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

/** Header role picker. Replaces the bare `<select>`: every role shows its
 * label, one line on what it owns and the decisions it signs, so a
 * presenter can pick the right actor without knowing the permission table.
 *
 * Switching is not a bypass. Every action is recorded under the acting
 * role and the server keeps enforcing separation — the picker only makes
 * the choice legible. */
export function RoleSwitcher() {
  const { role, setRole, roles, roleLabel, users, actingUser, actAsUser } = useRun()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const current = roles.find((r) => r.role === role)
  // Acting as a named person shows the person; the role rides underneath.
  const label = actingUser ? actingUser.name : roleLabel(role)
  const sublabel = actingUser ? roleLabel(actingUser.role) : null

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false)
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    // Focus the selected option so arrow keys work straight away.
    const selected = listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')
      ?? listRef.current?.querySelector<HTMLElement>('[role="option"]')
    selected?.focus()
    return () => {
      document.removeEventListener('mousedown', onDoc)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  const onListKey = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp' && e.key !== 'Home' && e.key !== 'End') return
    const items = Array.from(listRef.current?.querySelectorAll<HTMLElement>('[role="option"]') ?? [])
    if (!items.length) return
    const idx = items.indexOf(document.activeElement as HTMLElement)
    let next = idx
    if (e.key === 'ArrowDown') next = Math.min(items.length - 1, idx + 1)
    if (e.key === 'ArrowUp') next = Math.max(0, idx - 1)
    if (e.key === 'Home') next = 0
    if (e.key === 'End') next = items.length - 1
    items[next]?.focus()
    e.preventDefault()
  }

  const choose = (next: string) => {
    setRole(next)
    setOpen(false)
  }

  const chooseUser = (u: (typeof users)[number]) => {
    actAsUser(u)
    setOpen(false)
  }

  return (
    <div className="role-switcher" ref={rootRef}>
      <button
        type="button"
        className="role-trigger"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={actingUser
          ? `Acting as ${label} (${sublabel}). Change`
          : `Acting role: ${label}. Change role`}
        title={current?.summary}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="role-avatar" aria-hidden="true">{initials(label)}</span>
        <span className="role-trigger-text">
          <span className="hdr-label">{actingUser ? `Acting as · ${sublabel}` : 'Acting as'}</span>
          <span className="role-name">{label}</span>
        </span>
        <ChevronDown size={14} aria-hidden="true" />
      </button>
      {open && (
        <div
          className="role-menu"
          role="listbox"
          aria-label="Acting role"
          ref={listRef}
          onKeyDown={onListKey}
        >
          {users.length > 0 && (
            <>
              <div className="role-menu-group">People</div>
              {users.map((u) => {
                const selected = actingUser?.id === u.id
                return (
                  <button
                    key={u.id}
                    type="button"
                    role="option"
                    aria-selected={selected}
                    className={`role-opt${selected ? ' selected' : ''}`}
                    onClick={() => chooseUser(u)}
                  >
                    <span className="role-avatar sm" aria-hidden="true">{initials(u.name)}</span>
                    <span className="role-opt-body">
                      <b>Act as {u.name} · {roleLabel(u.role)}</b>
                      <small>{u.email ? `${u.email} · ` : ''}Approvals and activity record this name.</small>
                    </span>
                    {selected && <Check size={14} className="role-check" aria-hidden="true" />}
                  </button>
                )
              })}
              <div className="role-menu-group">Roles</div>
            </>
          )}
          {roles.map((r) => {
            const selected = !actingUser && r.role === role
            return (
              <button
                key={r.role}
                type="button"
                role="option"
                aria-selected={selected}
                className={`role-opt${selected ? ' selected' : ''}`}
                onClick={() => choose(r.role)}
              >
                <span className="role-avatar sm" aria-hidden="true">{initials(r.label)}</span>
                <span className="role-opt-body">
                  <b>{r.label}</b>
                  <small>{r.summary}</small>
                  {r.signs.length > 0 && (
                    <span className="role-signs">Signs: {r.signs.join(' · ')}</span>
                  )}
                </span>
                {selected && <Check size={14} className="role-check" aria-hidden="true" />}
              </button>
            )
          })}
          <div className="role-menu-foot">
            Actions are recorded under the acting role. Gates keep their separation
            rules whichever role is chosen — switching changes who signs, never what is checked.
          </div>
        </div>
      )}
    </div>
  )
}
