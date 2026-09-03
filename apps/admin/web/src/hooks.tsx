import { useCallback, useEffect, useState } from 'react'
import { errorMessage } from './state/AdminContext'
import { Button, Notice } from './components/ui'

/** Load-on-mount with loading / error / reload — every page uses the same
 * three states so an empty page and a broken backend never look alike. */
export function useLoad<T>(loader: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    loader()
      .then((d) => { if (!cancelled) setData(d) })
      .catch((err: unknown) => { if (!cancelled) setError(errorMessage(err)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  return { data, setData, error, loading, reload }
}

export function LoadError({ what, error, onRetry }: { what: string; error: string; onRetry: () => void }) {
  return (
    <Notice tone="danger" title={`Could not load ${what}.`} actions={<Button variant="secondary" size="sm" onClick={onRetry}>Retry</Button>}>
      {error}
    </Notice>
  )
}
