import type { ReactNode } from 'react'

export function Modal({ title, onClose, children, wide }: { title: string; onClose: () => void; children: ReactNode; wide?: boolean }) {
  return (
    <div
      className="modal-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className={`modal card${wide ? ' modal-wide' : ''}`}>
        <div className="card-head">
          <h3>{title}</h3>
          <button type="button" className="kebab" onClick={onClose}>✕</button>
        </div>
        {children}
      </div>
    </div>
  )
}
