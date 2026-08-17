import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { apiGet, apiPatch, apiPost, apiUpload } from '../api'
import type { RunState, RoleInfo } from '../types'

interface RunContextValue {
  data: RunState | null
  runId: string | null
  role: string
  setRole: (role: string) => void
  runs: string[]
  roles: RoleInfo[]
  section: string
  goTo: (section: string) => void
  /** Whether the acting role holds a server permission (from /api/roles).
   * Pre-disables buttons the server would 403; the 403 stays the rule —
   * this is a hint, and it fails open until the roles list loads. */
  can: (action: string) => boolean
  refresh: () => Promise<void>
  act: (path: string, body?: Record<string, unknown>, okMessage?: string) => Promise<boolean>
  patchAct: (path: string, patch: Record<string, unknown>, okMessage?: string) => Promise<boolean>
  uploadAct: (path: string, form: FormData, okMessage?: string) => Promise<boolean>
  toast: { message: string; isError: boolean } | null
  /** Show a toast without a server round-trip — for client-only feedback
   * (e.g. a JSON export/import outcome) that vanilla surfaced via a bare
   * `toast(...)` call rather than through `act`. Errors route to the
   * blocking error popup instead of the toast. */
  notify: (message: string, isError?: boolean) => void
  /** True while any server action is in flight — drives the global
   * loading overlay, which also blocks double-clicks. */
  busy: boolean
  /** Error awaiting acknowledgement in the popup, or null. */
  errorPopup: string | null
  dismissError: () => void
}

const RunContext = createContext<RunContextValue | null>(null)

export function RunProvider({ children }: { children: ReactNode }) {
  const [runId, setRunId] = useState<string | null>(localStorage.getItem('s7cc.runId'))
  const [role, setRoleState] = useState(localStorage.getItem('s7cc.role') || 'delivery_lead')
  const [section, setSection] = useState(localStorage.getItem('s7cc.section') || 'overview')
  const [data, setData] = useState<RunState | null>(null)
  const [runs, setRuns] = useState<string[]>([])
  const [roles, setRoles] = useState<RoleInfo[]>([])
  const [toast, setToast] = useState<{ message: string; isError: boolean } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [pending, setPending] = useState(0)
  const [errorPopup, setErrorPopup] = useState<string | null>(null)

  const showToast = useCallback((message: string, isError = false) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ message, isError })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const showError = useCallback((message: string) => {
    setErrorPopup(message)
  }, [])

  const notify = useCallback((message: string, isError = false) => {
    if (isError) setErrorPopup(message)
    else showToast(message)
  }, [showToast])

  const setRole = useCallback((next: string) => {
    setRoleState(next)
    localStorage.setItem('s7cc.role', next)
  }, [])

  const goTo = useCallback((next: string) => {
    setSection(next)
    localStorage.setItem('s7cc.section', next)
  }, [])

  const can = useCallback((action: string) => {
    const info = roles.find((r) => r.role === role)
    return info ? info.actions.includes(action) : true
  }, [roles, role])

  const ensureRun = useCallback(async (): Promise<string> => {
    const list = await apiGet<string[]>('/api/runs')
    setRuns(list)
    if (runId && list.includes(runId)) return runId
    if (list.length) {
      const last = list[list.length - 1]
      setRunId(last)
      localStorage.setItem('s7cc.runId', last)
      return last
    }
    const created = await apiPost<{ run: { run_id: string } } & RunState>('/api/runs', { mode: 'simulation' })
    setRunId(created.run.run_id)
    localStorage.setItem('s7cc.runId', created.run.run_id)
    return created.run.run_id
  }, [runId])

  const refresh = useCallback(async () => {
    try {
      const id = await ensureRun()
      const [freshRuns, freshData] = await Promise.all([
        apiGet<string[]>('/api/runs'),
        apiGet<RunState>(`/api/runs/${id}`),
      ])
      setRuns(freshRuns)
      setData(freshData)
    } catch (err) {
      showError(`Could not load run state: ${(err as Error).message}`)
    }
  }, [ensureRun, showError])

  const act = useCallback(async (path: string, body: Record<string, unknown> = {}, okMessage = 'Done') => {
    setPending((n) => n + 1)
    try {
      const next = await apiPost<RunState>(`/api/runs/${runId}${path}`, { role, ...body })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showError((err as Error).message)
      return false
    } finally {
      setPending((n) => n - 1)
    }
  }, [runId, role, showToast, showError])

  const patchAct = useCallback(async (path: string, patch: Record<string, unknown>, okMessage = 'Saved') => {
    setPending((n) => n + 1)
    try {
      const next = await apiPatch<RunState>(`/api/runs/${runId}${path}`, { role, patch })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showError((err as Error).message)
      return false
    } finally {
      setPending((n) => n - 1)
    }
  }, [runId, role, showToast, showError])

  const uploadAct = useCallback(async (path: string, form: FormData, okMessage = 'Done') => {
    form.append('role', role)
    setPending((n) => n + 1)
    try {
      const next = await apiUpload<RunState>(`/api/runs/${runId}${path}`, form)
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showError((err as Error).message)
      return false
    } finally {
      setPending((n) => n - 1)
    }
  }, [runId, role, showToast, showError])

  useEffect(() => {
    apiGet<RoleInfo[]>('/api/roles').then(setRoles).catch(() => setRoles([]))
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // One stable object per state change: without the memo, every provider
  // render hands consumers a fresh object and re-renders the whole tree.
  const value = useMemo<RunContextValue>(() => ({
    data, runId, role, setRole, runs, roles, section, goTo, can, refresh,
    act, patchAct, uploadAct, toast, notify,
    busy: pending > 0,
    errorPopup,
    dismissError: () => setErrorPopup(null),
  }), [data, runId, role, setRole, runs, roles, section, goTo, can, refresh,
    act, patchAct, uploadAct, toast, notify, pending, errorPopup])

  return (
    <RunContext.Provider value={value}>
      {children}
    </RunContext.Provider>
  )
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext)
  if (!ctx) throw new Error('useRun must be used within a RunProvider')
  return ctx
}
