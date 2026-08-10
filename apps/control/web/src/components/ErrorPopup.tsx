import { useRun } from '../state/RunContext'

/** Blocking popup for every error the app raises — action failures, load
 * failures and client-side validation all land here instead of the corner
 * toast, so an error can never slip by unread. */
export function ErrorPopup() {
  const { errorPopup, dismissError } = useRun()
  if (!errorPopup) return null
  return (
    <div
      className="modal-overlay error-popup-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) dismissError() }}
    >
      <div className="modal card error-popup" role="alertdialog" aria-modal="true" aria-label="Error">
        <div className="card-head">
          <h3>⚠ Something went wrong</h3>
          <button type="button" className="kebab" onClick={dismissError}>✕</button>
        </div>
        <p className="error-popup-message">{errorPopup}</p>
        <div className="error-popup-actions">
          <button type="button" onClick={dismissError}>OK</button>
        </div>
      </div>
    </div>
  )
}
