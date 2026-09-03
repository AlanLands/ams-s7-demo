import { useCallback, useEffect, useState, type ReactNode } from 'react'

/** Slide-in inspector for a table row. Replaces the fixed right-hand rail on
 * the Build & Review tabs: the table gets the full width, and a row's detail
 * opens on click and closes on ✕, Escape or a click on the backdrop.
 *
 * Same overlay/closing pattern as the workspace drawer so the two feel
 * identical; the body is wrapped in `.dp-inspector` so the existing inspector
 * blocks (`dp-ins-block`, `dp-ins-metrics`, `dp-ins-actions`) style unchanged. */
export function DetailDrawer({ title, subtitle, ariaLabel, onClose, children }: {
  title: ReactNode
  subtitle?: ReactNode
  ariaLabel: string
  onClose: () => void
  children: ReactNode
}) {
  const [closing, setClosing] = useState(false)
  const requestClose = useCallback(() => setClosing(true), [])

  useEffect(() => {
    if (!closing) return
    const t = setTimeout(onClose, 230)
    return () => clearTimeout(t)
  }, [closing, onClose])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') requestClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [requestClose])

  return (
    <div
      className={`drawer-overlay${closing ? ' closing' : ''}`}
      onClick={(e) => { if (e.target === e.currentTarget) requestClose() }}
    >
      <aside className="drawer story-drawer detail-drawer" role="dialog" aria-label={ariaLabel}>
        <div className="card-head">
          <h3>{title}</h3>
          <button type="button" className="kebab" onClick={requestClose} aria-label="Close">✕</button>
        </div>
        {subtitle ? <p className="hint" style={{ marginTop: -4 }}>{subtitle}</p> : null}
        <div className="dp-inspector">{children}</div>
      </aside>
    </div>
  )
}
