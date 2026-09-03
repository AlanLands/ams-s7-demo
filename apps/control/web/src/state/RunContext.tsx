import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, apiGet, apiPatch, apiPost, apiUpload, getActingUserId, setActingUserId } from '../api'
import type { RunState, RoleInfo, UserInfo } from '../types'

/** A refused action the user can retry as one of the roles that hold it.
 * `retry` switches the acting role first, so the action is recorded under
 * that role exactly as if it had been picked in the header beforehand. */
export interface PermissionBlock {
  action: string
  role: string
  permitted: string[]
  retry: (asRole: string) => Promise<boolean>
}

export interface ErrorInfo {
  message: string
  permission?: PermissionBlock
}

interface RunContextValue {
  data: RunState | null
  runId: string | null
  role: string
  /** Pick a plain role. Clears any "act as user" choice, so no X-S7-User
   * header is sent and the server sees exactly the pre-users behaviour. */
  setRole: (role: string) => void
  /** Active admin-defined users (GET /api/users). Empty when the admin app
   * has none — the header then behaves exactly as before. */
  users: UserInfo[]
  /** The user being acted as, or null when a plain role was chosen. */
  actingUser: UserInfo | null
  /** Act as an admin-defined person: sets the acting role to the user's
   * role and stores the id so every request carries X-S7-User. */
  actAsUser: (user: UserInfo) => void
  runs: string[]
  roles: RoleInfo[]
  section: string
  goTo: (section: string) => void
  /** Whether the acting role holds a server permission (from /api/roles).
   * Pre-disables buttons the server would 403; the 403 stays the rule —
   * this is a hint, and it fails open until the roles list loads. */
  can: (action: string) => boolean
  /** Presenter-facing label for a role id ("business_owner" → "Business
   * Owner"), falling back to a humanised id before the roles list loads. */
  roleLabel: (role: string) => string
  /** Labels of the roles holding `action`, in declaration order. */
  permittedLabels: (action: string) => string[]
  /** Tooltip for a pre-disabled control: names the role(s) that hold the
   * permission and the role currently acting. `undefined` when allowed, so
   * it can be passed straight to `title`. */
  needs: (action: string) => string | undefined
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
  errorPopup: ErrorInfo | null
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
  const [users, setUsers] = useState<UserInfo[]>([])
  const [userId, setUserId] = useState<string | null>(getActingUserId)
  const [toast, setToast] = useState<{ message: string; isError: boolean } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [pending, setPending] = useState(0)
  const [errorPopup, setErrorPopup] = useState<ErrorInfo | null>(null)

  const showToast = useCallback((message: string, isError = false) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ message, isError })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const showError = useCallback((message: string) => {
    setErrorPopup({ message })
  }, [])

  const notify = useCallback((message: string, isError = false) => {
    if (isError) setErrorPopup({ message })
    else showToast(message)
  }, [showToast])

  const setRole = useCallback((next: string) => {
    setRoleState(next)
    localStorage.setItem('s7cc.role', next)
    // A plain role means no user: drop the header so nothing is attributed
    // to a person who was not chosen.
    setUserId(null)
    setActingUserId(null)
  }, [])

  const actAsUser = useCallback((user: UserInfo) => {
    setRoleState(user.role)
    localStorage.setItem('s7cc.role', user.role)
    setUserId(user.id)
    setActingUserId(user.id)
  }, [])

  const actingUser = useMemo(() => (userId ? users.find((u) => u.id === userId) ?? null : null), [users, userId])

  const goTo = useCallback((next: string) => {
    setSection(next)
    localStorage.setItem('s7cc.section', next)
  }, [])

  const can = useCallback((action: string) => {
    const info = roles.find((r) => r.role === role)
    return info ? info.actions.includes(action) : true
  }, [roles, role])

  const roleLabel = useCallback((id: string) => {
    const info = roles.find((r) => r.role === id)
    return info?.label ?? id.replaceAll('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  }, [roles])

  const permittedLabels = useCallback((action: string) => (
    roles.filter((r) => r.actions.includes(action)).map((r) => r.label)
  ), [roles])

  const needs = useCallback((action: string) => {
    if (can(action)) return undefined
    const holders = permittedLabels(action)
    const who = holders.length ? holders.join(' or ') : 'a different role'
    return `Requires ${who} — you are acting as ${roleLabel(role)}. Switch role in the header.`
  }, [can, permittedLabels, roleLabel, role])

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

  type Kind = 'post' | 'patch' | 'upload'
  type Perform = (kind: Kind, path: string, payload: Record<string, unknown> | FormData,
    okMessage: string, asRole: string) => Promise<boolean>

  // One code path for every server action. A 403 that names the roles
  // holding the permission becomes a retryable block: the popup offers
  // "switch to <role> and retry", and the retry re-enters here under the
  // switched role — nothing is bypassed, the action is simply recorded
  // under the role a person chose, as it would be from the header picker.
  const perform: Perform = useCallback(async (kind, path, payload, okMessage, asRole) => {
    setPending((n) => n + 1)
    try {
      let next: RunState
      if (kind === 'upload') {
        const form = payload as FormData
        form.set('role', asRole)
        next = await apiUpload<RunState>(`/api/runs/${runId}${path}`, form)
      } else if (kind === 'patch') {
        next = await apiPatch<RunState>(`/api/runs/${runId}${path}`, { role: asRole, patch: payload })
      } else {
        next = await apiPost<RunState>(`/api/runs/${runId}${path}`, { role: asRole, ...(payload as Record<string, unknown>) })
      }
      setData(next)
      showToast(okMessage)
      return true
    } catch (err) {
      const e = err as ApiError
      if (e instanceof ApiError && e.permission && e.permission.permitted.length) {
        setErrorPopup({
          message: e.message,
          permission: {
            action: e.permission.action,
            role: asRole,
            permitted: e.permission.permitted,
            retry: (r) => {
              // Retrying as a role is a role choice: a stored user would
              // otherwise override it server-side, so it is cleared first.
              setRole(r)
              setActingUserId(null)
              return perform(kind, path, payload, okMessage, r)
            },
          },
        })
      } else {
        showError(e.message)
      }
      return false
    } finally {
      setPending((n) => n - 1)
    }
  }, [runId, showToast, showError, setRole])

  const act = useCallback((path: string, body: Record<string, unknown> = {}, okMessage = 'Done') =>
    perform('post', path, body, okMessage, role), [perform, role])

  const patchAct = useCallback((path: string, patch: Record<string, unknown>, okMessage = 'Saved') =>
    perform('patch', path, patch, okMessage, role), [perform, role])

  const uploadAct = useCallback((path: string, form: FormData, okMessage = 'Done') =>
    perform('upload', path, form, okMessage, role), [perform, role])

  useEffect(() => {
    apiGet<RoleInfo[]>('/api/roles').then(setRoles).catch(() => setRoles([]))
    // Users are optional: an older server without the route, or an admin
    // app with none defined, both leave the picker exactly as it was.
    apiGet<UserInfo[]>('/api/users')
      .then((list) => {
        const active = Array.isArray(list) ? list.filter((u) => u.active !== false) : []
        setUsers(active)
        // A remembered user that no longer exists (deleted or deactivated in
        // the admin app) must not keep sending its id.
        const stored = getActingUserId()
        if (stored && !active.some((u) => u.id === stored)) {
          setUserId(null)
          setActingUserId(null)
        }
      })
      .catch(() => setUsers([]))
    refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // One stable object per state change: without the memo, every provider
  // render hands consumers a fresh object and re-renders the whole tree.
  const value = useMemo<RunContextValue>(() => ({
    data, runId, role, setRole, users, actingUser, actAsUser, runs, roles, section, goTo, can, roleLabel, permittedLabels, needs, refresh,
    act, patchAct, uploadAct, toast, notify,
    busy: pending > 0,
    errorPopup,
    dismissError: () => setErrorPopup(null),
  }), [data, runId, role, setRole, users, actingUser, actAsUser, runs, roles, section, goTo, can, roleLabel, permittedLabels, needs, refresh,
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
