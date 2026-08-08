import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react'
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
  refresh: () => Promise<void>
  act: (path: string, body?: Record<string, unknown>, okMessage?: string) => Promise<boolean>
  patchAct: (path: string, patch: Record<string, unknown>, okMessage?: string) => Promise<boolean>
  uploadAct: (path: string, form: FormData, okMessage?: string) => Promise<boolean>
  toast: { message: string; isError: boolean } | null
  /** Show a toast without a server round-trip — for client-only feedback
   * (e.g. a JSON export/import outcome) that vanilla surfaced via a bare
   * `toast(...)` call rather than through `act`. */
  notify: (message: string, isError?: boolean) => void
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

  const showToast = useCallback((message: string, isError = false) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ message, isError })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const setRole = useCallback((next: string) => {
    setRoleState(next)
    localStorage.setItem('s7cc.role', next)
  }, [])

  const goTo = useCallback((next: string) => {
    setSection(next)
    localStorage.setItem('s7cc.section', next)
  }, [])

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
      showToast(`Could not load run state: ${(err as Error).message}`, true)
    }
  }, [ensureRun, showToast])

  const act = useCallback(async (path: string, body: Record<string, unknown> = {}, okMessage = 'Done') => {
    try {
      const next = await apiPost<RunState>(`/api/runs/${runId}${path}`, { role, ...body })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

  const patchAct = useCallback(async (path: string, patch: Record<string, unknown>, okMessage = 'Saved') => {
    try {
      const next = await apiPatch<RunState>(`/api/runs/${runId}${path}`, { role, patch })
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

  const uploadAct = useCallback(async (path: string, form: FormData, okMessage = 'Done') => {
    form.append('role', role)
    try {
      const next = await apiUpload<RunState>(`/api/runs/${runId}${path}`, form)
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      showToast((err as Error).message, true)
      return false
    }
  }, [runId, role, showToast])

  useEffect(() => {
    apiGet<RoleInfo[]>('/api/roles').then(setRoles).catch(() => setRoles([]))
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <RunContext.Provider value={{ data, runId, role, setRole, runs, roles, section, goTo, refresh, act, patchAct, uploadAct, toast, notify: showToast }}>
      {children}
    </RunContext.Provider>
  )
}

export function useRun(): RunContextValue {
  const ctx = useContext(RunContext)
  if (!ctx) throw new Error('useRun must be used within a RunProvider')
  return ctx
}
