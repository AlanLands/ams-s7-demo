import { useEffect, useState } from 'react'
import { useRun } from '../state/RunContext'

/** Full-screen loading overlay shown while any server action is in flight.
 * Appears after a short delay so near-instant simulated actions don't
 * flicker; while visible it also blocks stray double-clicks. */
export function BusyOverlay() {
  const { busy } = useRun()
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!busy) {
      setVisible(false)
      return
    }
    const timer = setTimeout(() => setVisible(true), 150)
    return () => clearTimeout(timer)
  }, [busy])

  if (!busy) return null
  return (
    <div className={`busy-overlay${visible ? ' show' : ''}`} role="status" aria-live="polite" aria-label="Working">
      <div className="spinner" />
      <div className="busy-label">Working…</div>
    </div>
  )
}
