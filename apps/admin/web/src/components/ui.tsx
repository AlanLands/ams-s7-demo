import {
  useCallback, useEffect, useId, useRef, useState,
  type ButtonHTMLAttributes, type ReactNode, type RefObject,
} from 'react'
import {
  AlertTriangle, CheckCircle2, CircleAlert, Info, MoreHorizontal, X, XCircle,
} from 'lucide-react'
import { useAdmin } from '../state/AdminContext'

/* Shared visual vocabulary — one PageHeader, one Card, one Badge, one
 * Button, one Table wrapper — so every page reads as the same product.
 * Nothing is imported across apps; the Control Centre has its own copy. */

/* --- focus management -------------------------------------------------- */

const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/** Trap Tab inside `ref`, close on Escape, restore focus on unmount. */
export function useFocusTrap(ref: RefObject<HTMLElement | null>, onClose: () => void, active = true) {
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose
  useEffect(() => {
    if (!active) return
    const box = ref.current
    if (!box) return
    const previouslyFocused = document.activeElement as HTMLElement | null
    const first = box.querySelector<HTMLElement>('[data-autofocus]') ?? box.querySelector<HTMLElement>(FOCUSABLE)
    ;(first ?? box).focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.stopPropagation(); onCloseRef.current(); return }
      if (e.key !== 'Tab') return
      const items = [...box.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.offsetParent !== null || el === document.activeElement)
      if (!items.length) { e.preventDefault(); return }
      const firstEl = items[0], lastEl = items[items.length - 1]
      if (e.shiftKey && document.activeElement === firstEl) { e.preventDefault(); lastEl.focus() }
      else if (!e.shiftKey && document.activeElement === lastEl) { e.preventDefault(); firstEl.focus() }
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previouslyFocused?.focus?.()
    }
  }, [ref, active])
}

/** Close when a pointer lands outside `ref`. */
export function useClickOutside(ref: RefObject<HTMLElement | null>, onOutside: () => void, active = true) {
  const cb = useRef(onOutside)
  cb.current = onOutside
  useEffect(() => {
    if (!active) return
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) cb.current()
    }
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [ref, active])
}

/* --- page structure ----------------------------------------------------- */

export function PageHeader({ title, description, actions }: { title: ReactNode; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="page-head">
      <div className="text">
        <h1>{title}</h1>
        {description ? <p className="desc">{description}</p> : null}
      </div>
      {actions ? <div className="actions">{actions}</div> : null}
    </div>
  )
}

export function SectionHead({ title, description, right }: { title: ReactNode; description?: ReactNode; right?: ReactNode }) {
  return (
    <div className="section-head">
      <div>
        <h2>{title}</h2>
        {description ? <div className="desc">{description}</div> : null}
      </div>
      {right ? <div className="right">{right}</div> : null}
    </div>
  )
}

export function Card({ title, description, actions, compact, flush, className, children }: {
  title?: ReactNode
  description?: ReactNode
  actions?: ReactNode
  compact?: boolean
  flush?: boolean
  className?: string
  children?: ReactNode
}) {
  return (
    <section className={`card${compact ? ' compact' : ''}${flush ? ' flush' : ''}${className ? ` ${className}` : ''}`}>
      {title || actions ? (
        <div className="card-head">
          <div className="text">
            {title ? <h3>{title}</h3> : null}
            {description ? <div className="desc">{description}</div> : null}
          </div>
          {actions ? <div className="actions">{actions}</div> : null}
        </div>
      ) : null}
      {children}
    </section>
  )
}

/** Horizontal + vertical scroll box with a sticky header row. */
export function TableWrap({ children, label, className }: { children: ReactNode; label?: string; className?: string }) {
  return <div className={`table-wrap${className ? ` ${className}` : ''}`} role="region" aria-label={label} tabIndex={0}>{children}</div>
}

/* --- badges --------------------------------------------------------------- */

export type BadgeVariant = 'neutral' | 'info' | 'success' | 'warning' | 'danger' | 'accent'

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  passed: 'success', completed: 'success', ready: 'success', ok: 'success', active: 'success', recorded: 'success',
  planned: 'warning', pending: 'warning', waiting_for_approval: 'warning', waiting_for_input: 'warning', unrecorded: 'warning',
  in_progress: 'accent',
  blocked: 'danger', failed: 'danger', stale: 'danger', invalidated: 'danger', error: 'danger',
  not_started: 'neutral', inactive: 'neutral', archived: 'neutral', neutral: 'neutral',
  default: 'info', info: 'info',
}

export function variantFor(status: string): BadgeVariant {
  return STATUS_VARIANT[status] ?? 'neutral'
}

/** The one badge. `variant` wins; `status` maps run/stage statuses to one. */
export function Badge({ variant, status, label, title, mono, soft, icon }: {
  variant?: BadgeVariant
  status?: string
  label?: ReactNode
  title?: string
  mono?: boolean
  soft?: boolean
  icon?: ReactNode
}) {
  const v = variant ?? variantFor(status ?? 'neutral')
  return (
    <span className={`badge ${v}${mono ? ' mono' : ''}${soft ? ' soft' : ''}`} title={title}>
      {icon}{label ?? (status ?? '').replaceAll('_', ' ')}
    </span>
  )
}

/* --- buttons ---------------------------------------------------------------*/

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'danger-solid' | 'link'

export function Button({ variant = 'secondary', size, busy, icon, className, children, disabled, type = 'button', ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant
  size?: 'sm'
  busy?: boolean
  icon?: ReactNode
}) {
  const cls = variant === 'danger-solid' ? 'btn-danger solid' : `btn-${variant}`
  return (
    <button
      type={type}
      className={`btn ${cls}${size ? ` ${size}` : ''}${busy ? ' busy' : ''}${className ? ` ${className}` : ''}`}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      {...rest}
    >
      {busy ? <span className="spinner" aria-hidden="true" /> : icon}
      {children}
    </button>
  )
}

export function IconButton({ label, icon, size, plain, className, ...rest }: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string
  icon: ReactNode
  size?: 'sm'
  plain?: boolean
}) {
  return (
    <button type="button" className={`icon-btn${size ? ` ${size}` : ''}${plain ? ' plain' : ''}${className ? ` ${className}` : ''}`} aria-label={label} title={label} {...rest}>
      {icon}
    </button>
  )
}

/** Kebab menu of row actions: one control per record, keyboard operable. */
export function ActionMenu({ label, items }: {
  label: string
  items: { label: string; icon?: ReactNode; danger?: boolean; disabled?: boolean; title?: string; onSelect: () => void }[]
}) {
  const [open, setOpen] = useState(false)
  const wrap = useRef<HTMLDivElement>(null)
  const list = useRef<HTMLUListElement>(null)
  const id = useId()
  useClickOutside(wrap, () => setOpen(false), open)
  useEffect(() => {
    if (!open) return
    const first = list.current?.querySelector<HTMLButtonElement>('button:not([disabled])')
    first?.focus()
  }, [open])
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.stopPropagation(); setOpen(false); wrap.current?.querySelector<HTMLButtonElement>('button')?.focus(); return }
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    e.preventDefault()
    const btns = [...(list.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])') ?? [])]
    if (!btns.length) return
    const i = btns.indexOf(document.activeElement as HTMLButtonElement)
    const next = e.key === 'ArrowDown' ? (i + 1) % btns.length : (i - 1 + btns.length) % btns.length
    btns[next].focus()
  }
  return (
    <div className="menu-wrap" ref={wrap} onKeyDown={onKey}>
      <IconButton label={label} icon={<MoreHorizontal />} size="sm" aria-haspopup="menu" aria-expanded={open} aria-controls={id} onClick={() => setOpen((o) => !o)} />
      {open ? (
        <ul className="menu" role="menu" id={id} ref={list} aria-label={label}>
          {items.map((it) => (
            <li key={it.label} role="none">
              <button type="button" role="menuitem" className={it.danger ? 'danger' : ''} disabled={it.disabled} title={it.title}
                onClick={() => { setOpen(false); it.onSelect() }}>
                {it.icon}{it.label}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/* --- forms ------------------------------------------------------------------*/

/** Label above, control, helper text or error (with icon) below. */
export function Field({ label, htmlFor, required, optional, help, error, children, className }: {
  label: ReactNode
  htmlFor?: string
  required?: boolean
  optional?: boolean
  help?: ReactNode
  error?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div className={`fld-group${className ? ` ${className}` : ''}`}>
      <label className="fld" htmlFor={htmlFor}>
        {label}
        {required ? <span className="req" aria-hidden="true">*</span> : null}
        {optional ? <span className="opt">(optional)</span> : null}
      </label>
      {children}
      {error ? <div className="err" role="alert"><CircleAlert aria-hidden="true" />{error}</div> : help ? <div className="help">{help}</div> : null}
    </div>
  )
}

/* --- feedback -----------------------------------------------------------------*/

export function Notice({ tone, title, children, actions }: {
  tone: 'info' | 'success' | 'warning' | 'danger'
  title?: ReactNode
  children?: ReactNode
  actions?: ReactNode
}) {
  const Icon = tone === 'success' ? CheckCircle2 : tone === 'warning' ? AlertTriangle : tone === 'danger' ? XCircle : Info
  return (
    <div className={`notice ${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon aria-hidden="true" />
      <div className="body">
        {title ? <b>{title}</b> : null}{title && children ? ' ' : null}{children}
        {actions ? <div className="btn-row">{actions}</div> : null}
      </div>
    </div>
  )
}

export function StatCard({ icon, value, label, sub, accent }: {
  icon: ReactNode
  value: string
  label: string
  sub?: string
  accent: 'green' | 'blue' | 'orange' | 'purple' | 'red' | 'teal'
}) {
  return (
    <div className={`stat-card sc-${accent}`}>
      <div className="ic" aria-hidden="true">{icon}</div>
      <div>
        <div className="v">{value}</div>
        <div className="l">{label}</div>
        {sub ? <div className="s">{sub}</div> : null}
      </div>
    </div>
  )
}

export function Loading({ what = 'Loading' }: { what?: string }) {
  return <div className="loading" role="status"><span className="spinner sm" aria-hidden="true" />{what}…</div>
}

export function Empty({ title, hint, action, bare }: { title: string; hint?: ReactNode; action?: ReactNode; bare?: boolean }) {
  const body = (
    <div className="empty">
      <b>{title}</b>
      {hint ? <span>{hint}</span> : null}
      {action ? <div className="btn-row">{action}</div> : null}
    </div>
  )
  return bare ? body : <div className="card flush">{body}</div>
}

/** In-page confirmation panel. The app never calls window.confirm: a
 * destructive action shows this inline, next to the thing it acts on. */
export function ConfirmPanel({ message, confirmLabel = 'Confirm', danger, onConfirm, onCancel, busy, children }: {
  message: ReactNode
  confirmLabel?: string
  danger?: boolean
  onConfirm: () => void
  onCancel: () => void
  busy?: boolean
  children?: ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)
  useFocusTrap(ref, onCancel)
  return (
    <div ref={ref} className={`confirm-panel${danger ? ' danger' : ''}`} role="alertdialog" aria-label="Confirm">
      <p>{message}</p>
      {children}
      <div className="btn-row">
        <Button data-autofocus variant={danger ? 'danger-solid' : 'primary'} size="sm" onClick={onConfirm} busy={busy}>{confirmLabel}</Button>
        <Button variant="secondary" size="sm" onClick={onCancel} disabled={busy}>Cancel</Button>
      </div>
    </div>
  )
}

export function Modal({ title, description, onClose, children, wide }: { title: string; description?: ReactNode; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const boxRef = useRef<HTMLDivElement>(null)
  useFocusTrap(boxRef, onClose)
  const id = useId()
  return (
    <div className="modal-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose() }}>
      <div ref={boxRef} className={`modal card${wide ? ' modal-wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={id} tabIndex={-1}>
        <div className="card-head">
          <div className="text">
            <h3 id={id}>{title}</h3>
            {description ? <div className="desc">{description}</div> : null}
          </div>
          <div className="actions"><IconButton label="Close dialog" icon={<X />} plain size="sm" onClick={onClose} /></div>
        </div>
        {children}
      </div>
    </div>
  )
}

export function DetailDrawer({ title, subtitle, ariaLabel, onClose, children }: {
  title: ReactNode
  subtitle?: ReactNode
  ariaLabel: string
  onClose: () => void
  children: ReactNode
}) {
  const [closing, setClosing] = useState(false)
  const requestClose = useCallback(() => setClosing(true), [])
  const ref = useRef<HTMLElement>(null)
  useFocusTrap(ref, requestClose)
  useEffect(() => {
    if (!closing) return
    const t = setTimeout(onClose, 190)
    return () => clearTimeout(t)
  }, [closing, onClose])
  return (
    <div className={`drawer-overlay${closing ? ' closing' : ''}`} onMouseDown={(e) => { if (e.target === e.currentTarget) requestClose() }}>
      <aside ref={ref} className="drawer" role="dialog" aria-modal="true" aria-label={ariaLabel} tabIndex={-1}>
        <div className="card-head">
          <div className="text">
            <h3>{title}</h3>
            {subtitle ? <div className="desc">{subtitle}</div> : null}
          </div>
          <div className="actions"><IconButton label="Close" icon={<X />} plain size="sm" onClick={requestClose} /></div>
        </div>
        {children}
      </aside>
    </div>
  )
}

export function Toast() {
  const { toast } = useAdmin()
  return (
    <div className={`toast${toast ? ' show' : ''}${toast?.isError ? ' error' : ''}`} role="status" aria-live="polite">
      {toast ? (toast.isError ? <XCircle aria-hidden="true" /> : <CheckCircle2 aria-hidden="true" />) : null}
      <span>{toast?.message ?? ''}</span>
    </div>
  )
}

export function BusyOverlay() {
  const { busy } = useAdmin()
  return (
    <div className={`busy-overlay${busy ? ' show' : ''}`} aria-hidden={!busy}>
      <div className="spinner" />
      <div className="busy-label">Working…</div>
    </div>
  )
}

/** Blocking popup for every error: action failures, load failures and
 * client-side validation all land here so a `{detail}` is never missed. */
export function ErrorPopup() {
  const { errorPopup, dismissError } = useAdmin()
  const ref = useRef<HTMLDivElement>(null)
  useFocusTrap(ref, dismissError, Boolean(errorPopup))
  if (!errorPopup) return null
  return (
    <div className="modal-overlay error-popup-overlay" onMouseDown={(e) => { if (e.target === e.currentTarget) dismissError() }}>
      <div ref={ref} className="modal card error-popup" role="alertdialog" aria-modal="true" aria-label={errorPopup.title} tabIndex={-1}>
        <div className="card-head">
          <h3><AlertTriangle aria-hidden="true" />{errorPopup.title}</h3>
          <div className="actions"><IconButton label="Close" icon={<X />} plain size="sm" onClick={dismissError} /></div>
        </div>
        <p className="error-popup-message">{errorPopup.message}</p>
        <div className="error-popup-actions">
          <Button data-autofocus variant="primary" onClick={dismissError}>OK</Button>
        </div>
      </div>
    </div>
  )
}

/* --- small formatting helpers --------------------------------------------*/

export function fmtBytes(n: number | null | undefined): string {
  if (n == null) return '—'
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(2)} MB`
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleString(undefined, { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function humanize(s: string): string {
  const w = s.replaceAll('_', ' ').replaceAll('.', ' · ')
  return w.charAt(0).toUpperCase() + w.slice(1)
}
