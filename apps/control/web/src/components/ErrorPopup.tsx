import { useRun } from '../state/RunContext'

function humanizeAction(action: string): string {
  const words = action.replaceAll('_', ' ')
  return words.charAt(0).toUpperCase() + words.slice(1)
}

/** Blocking popup for every error the app raises — action failures, load
 * failures and client-side validation all land here instead of the corner
 * toast, so an error can never slip by unread.
 *
 * A permission refusal gets its own shape: it names the action, the role
 * that was acting and the role(s) that hold the permission, and offers to
 * switch to one of them and retry. The retry is recorded under the switched
 * role — the same thing the header picker would have done, one click sooner. */
export function ErrorPopup() {
  const { errorPopup, dismissError, roleLabel } = useRun()
  if (!errorPopup) return null
  const perm = errorPopup.permission

  if (perm) {
    const holders = perm.permitted.map(roleLabel)
    return (
      <div
        className="modal-overlay error-popup-overlay"
        onClick={(e) => { if (e.target === e.currentTarget) dismissError() }}
      >
        <div className="modal card error-popup perm-popup" role="alertdialog" aria-modal="true" aria-label="Needs a different role">
          <div className="card-head">
            <h3>Needs a different role</h3>
            <button type="button" className="kebab" onClick={dismissError} aria-label="Close">✕</button>
          </div>
          <p className="error-popup-message">
            <b>{humanizeAction(perm.action)}</b> is held by <b>{holders.join(' or ')}</b>.
            You are acting as <b>{roleLabel(perm.role)}</b>.
          </p>
          <p className="perm-popup-note">
            Switching records the action under that role — the gate's own separation rules still apply.
          </p>
          <div className="error-popup-actions">
            <button type="button" className="ghost" onClick={dismissError}>Cancel</button>
            {perm.permitted.map((r) => (
              <button
                key={r}
                type="button"
                className="primary"
                onClick={() => { dismissError(); void perm.retry(r) }}
              >
                Switch to {roleLabel(r)} and retry
              </button>
            ))}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div
      className="modal-overlay error-popup-overlay"
      onClick={(e) => { if (e.target === e.currentTarget) dismissError() }}
    >
      <div className="modal card error-popup" role="alertdialog" aria-modal="true" aria-label="Error">
        <div className="card-head">
          <h3>⚠ Something went wrong</h3>
          <button type="button" className="kebab" onClick={dismissError} aria-label="Close">✕</button>
        </div>
        <p className="error-popup-message">{errorPopup.message}</p>
        <div className="error-popup-actions">
          <button type="button" onClick={dismissError}>OK</button>
        </div>
      </div>
    </div>
  )
}
