import { useEffect, useRef, type ReactNode } from 'react'

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  const boxRef = useRef<HTMLDivElement>(null)
  // Callers pass `onClose` as an inline arrow, so it is a new function on
  // every render. Keep the latest one in a ref and run the focus/Escape
  // effect once per mount — re-running it on each parent re-render (i.e. on
  // every keystroke in a controlled input inside the dialog) moved focus back
  // to the dialog box after the first character and made typing impossible.
  const onCloseRef = useRef(onClose)
  onCloseRef.current = onClose

  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null
    boxRef.current?.focus()
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current()
    }
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('keydown', onKey)
      previouslyFocused?.focus?.()
    }
  }, [])

  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div
        ref={boxRef}
        className={`modal card${wide ? ' modal-wide' : ''}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
      >
        <div className="card-head">
          <h3>{title}</h3>
          <button type="button" className="kebab" aria-label="Close dialog" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
