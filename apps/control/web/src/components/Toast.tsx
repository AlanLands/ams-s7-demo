import { useRun } from '../state/RunContext'

export function Toast() {
  const { toast } = useRun()
  return (
    <div className={`toast${toast ? ' show' : ''}${toast?.isError ? ' error' : ''}`} role="status" aria-live="polite">
      {toast?.message ?? ''}
    </div>
  )
}
