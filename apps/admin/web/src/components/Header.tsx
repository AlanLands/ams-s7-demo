import { useId, useRef, useState } from 'react'
import { ChevronDown, Eye, EyeOff, Lock, LockOpen, RefreshCw, ShieldAlert, ShieldCheck, ShieldOff } from 'lucide-react'
import { useAdmin } from '../state/AdminContext'
import { Button, Field, IconButton, useClickOutside, useFocusTrap } from './ui'

function initials(name: string): string {
  const n = name.trim()
  if (!n) return 'AD'
  return n.split(/\s+/).map((w) => w[0]).join('').slice(0, 2).toUpperCase()
}

/** Identity control: one button ("Acting as <name>" + lock state) that
 * opens a popover to edit the actor name (sent as X-Admin-User on every
 * request, written into every audit and ledger line) and the optional
 * admin token (X-Admin-Token, only needed when the backend was started
 * with S7_ADMIN_TOKEN). Both persist in localStorage as they are typed. */
function IdentityControl() {
  const { actor, setActor, token, setToken } = useAdmin()
  const [open, setOpen] = useState(false)
  const [showToken, setShowToken] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const pop = useRef<HTMLDivElement>(null)
  const id = useId()
  const close = () => { setOpen(false); setShowToken(false) }
  useClickOutside(wrap, close, open)
  useFocusTrap(pop, close, open)

  const shown = actor.trim() || 'admin'

  return (
    <div className="identity" ref={wrap}>
      <button type="button" className="identity-btn" aria-haspopup="dialog" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)}>
        <span className="role-avatar" aria-hidden="true">{initials(shown)}</span>
        <span className="who">
          <span className="name">Acting as {shown}</span>
          <span className={`lock${token ? ' on' : ''}`}>
            {token ? <Lock aria-hidden="true" /> : <LockOpen aria-hidden="true" />}
            {token ? 'Token set' : 'No token'}
          </span>
        </span>
        <ChevronDown className="chev" aria-hidden="true" />
      </button>
      {open ? (
        <div ref={pop} className="popover" role="dialog" aria-label="Identity and token" id={id} tabIndex={-1}>
          <h3>Identity</h3>
          <p className="lead">Recorded on every change you make here.</p>
          <Field label="Acting as" htmlFor="id-actor" help="Sent as X-Admin-User. Author on prompt ledger lines, actor on audit rows. Blank means “admin”.">
            <input
              id="id-actor"
              data-autofocus
              type="text"
              value={actor}
              placeholder="admin"
              autoComplete="off"
              spellCheck={false}
              onChange={(e) => setActor(e.target.value)}
            />
          </Field>
          <Field label="Admin token" htmlFor="id-token" optional help="Sent as X-Admin-Token. Only needed when the server was started with S7_ADMIN_TOKEN.">
            <div className="provider-row">
              <input
                id="id-token"
                type={showToken ? 'text' : 'password'}
                value={token}
                placeholder="paste the token"
                autoComplete="off"
                spellCheck={false}
                onChange={(e) => setToken(e.target.value)}
              />
              <IconButton label={showToken ? 'Hide token' : 'Show token'} icon={showToken ? <EyeOff /> : <Eye />} onClick={() => setShowToken((s) => !s)} />
            </div>
          </Field>
          <div className="popover-foot">
            <span className="hint sm">Changes apply to the next request.</span>
            <Button variant="primary" size="sm" onClick={close}>Done</Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export function Header() {
  const { health, recheckHealth } = useAdmin()

  const status = health === 'ok'
    ? { cls: 'safe', icon: <ShieldCheck aria-hidden="true" />, text: 'API reachable' }
    : health === 'unauthorized'
      ? { cls: 'bad', icon: <ShieldAlert aria-hidden="true" />, text: 'Token rejected (401)' }
      : health === 'down'
        ? { cls: 'bad', icon: <ShieldOff aria-hidden="true" />, text: 'API unreachable' }
        : { cls: '', icon: <ShieldOff aria-hidden="true" />, text: 'Checking…' }

  return (
    <header className="top">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">MS</span>
        <div>
          <div className="brand-kicker">MapleSure Insurance</div>
          <div className="brand-name">S7 Admin</div>
        </div>
      </div>
      <div className="top-controls">
        <span className={`pill ${status.cls}`} title="GET /api/admin/health" role="status">{status.icon}{status.text}</span>
        <IconButton label="Re-check the admin API" icon={<RefreshCw />} size="sm" onClick={recheckHealth} />
        <IdentityControl />
      </div>
    </header>
  )
}
