import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { ApiError, api, getActor, getToken, setActor as persistActor, setToken as persistToken } from '../api'

export type Section =
  | 'overview' | 'prompt_sets' | 'prompt_editor' | 'playbooks' | 'learning' | 'llm' | 'recordings'
  | 'roles' | 'users' | 'runs' | 'observability' | 'audit'

interface AdminContextValue {
  section: Section
  /** Prompt set open in the editor (section === 'prompt_editor'). */
  editingSet: string | null
  goTo: (section: Section) => void
  openEditor: (set: string) => void
  /** Playbook the Playbooks page should select on arrival (with its prompt
   * set when known) â€” set by a link elsewhere, cleared once honoured. */
  playbookFocus: { id: string; set?: string | null } | null
  openPlaybook: (id: string, set?: string | null) => void
  clearPlaybookFocus: () => void
  actor: string
  setActor: (v: string) => void
  token: string
  setToken: (v: string) => void
  /** Backend reachability and whether the token gate is on: from /health. */
  health: 'unknown' | 'ok' | 'unauthorized' | 'down'
  configRoot: string | null
  recheckHealth: () => void
  toast: { message: string; isError: boolean } | null
  notify: (message: string) => void
  /** Route an error to the blocking popup. Accepts anything thrown. */
  fail: (err: unknown, prefix?: string) => void
  errorPopup: { title: string; message: string } | null
  dismissError: () => void
  /** Wrap a server action: busy overlay, popup on failure, toast on success. */
  run: <T,>(work: () => Promise<T>, okMessage?: string) => Promise<T | undefined>
  busy: boolean
}

const AdminContext = createContext<AdminContextValue | null>(null)

const SECTION_KEY = 's7admin.section'
const SET_KEY = 's7admin.editingSet'

function readSection(): Section {
  try { return (localStorage.getItem(SECTION_KEY) as Section) || 'overview' } catch { return 'overview' }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message
  if (err instanceof Error) return err.message
  return String(err)
}

export function AdminProvider({ children }: { children: ReactNode }) {
  const [section, setSection] = useState<Section>(readSection)
  const [editingSet, setEditingSet] = useState<string | null>(() => {
    try { return localStorage.getItem(SET_KEY) } catch { return null }
  })
  const [playbookFocus, setPlaybookFocus] = useState<{ id: string; set?: string | null } | null>(null)
  const [actor, setActorState] = useState(getActor)
  const [token, setTokenState] = useState(getToken)
  const [health, setHealth] = useState<AdminContextValue['health']>('unknown')
  const [configRoot, setConfigRoot] = useState<string | null>(null)
  const [toast, setToast] = useState<{ message: string; isError: boolean } | null>(null)
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const [errorPopup, setErrorPopup] = useState<{ title: string; message: string } | null>(null)
  const [pending, setPending] = useState(0)

  const goTo = useCallback((next: Section) => {
    setSection(next)
    try { localStorage.setItem(SECTION_KEY, next) } catch { /* ignore */ }
  }, [])

  const openEditor = useCallback((set: string) => {
    setEditingSet(set)
    try { localStorage.setItem(SET_KEY, set) } catch { /* ignore */ }
    goTo('prompt_editor')
  }, [goTo])

  const openPlaybook = useCallback((id: string, set?: string | null) => {
    setPlaybookFocus({ id, set })
    goTo('playbooks')
  }, [goTo])
  const clearPlaybookFocus = useCallback(() => setPlaybookFocus(null), [])

  const setActor = useCallback((v: string) => { setActorState(v); persistActor(v) }, [])
  const setToken = useCallback((v: string) => { setTokenState(v); persistToken(v) }, [])

  const notify = useCallback((message: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current)
    setToast({ message, isError: false })
    toastTimer.current = setTimeout(() => setToast(null), 3200)
  }, [])

  const fail = useCallback((err: unknown, prefix?: string) => {
    const msg = errorMessage(err)
    const status = err instanceof ApiError ? err.status : 0
    let title = 'Something went wrong'
    if (status === 401) title = 'Not authorised'
    else if (status === 409) title = 'Refused by current state'
    else if (status === 400) title = 'Refused by validation'
    else if (status === 404) title = 'Not found'
    setErrorPopup({ title, message: prefix ? `${prefix}: ${msg}` : msg })
  }, [])

  const recheckHealth = useCallback(() => {
    api.health()
      .then((h) => { setHealth('ok'); setConfigRoot(h.config_root) })
      .catch((err: unknown) => {
        setHealth(err instanceof ApiError && err.status === 401 ? 'unauthorized' : 'down')
      })
  }, [])

  useEffect(() => { recheckHealth() }, [recheckHealth, token])

  const run = useCallback(async <T,>(work: () => Promise<T>, okMessage?: string): Promise<T | undefined> => {
    setPending((n) => n + 1)
    try {
      const out = await work()
      if (okMessage) notify(okMessage)
      return out
    } catch (err) {
      fail(err)
      return undefined
    } finally {
      setPending((n) => n - 1)
    }
  }, [notify, fail])

  const value = useMemo<AdminContextValue>(() => ({
    section, editingSet, goTo, openEditor, playbookFocus, openPlaybook, clearPlaybookFocus,
    actor, setActor, token, setToken,
    health, configRoot, recheckHealth, toast, notify, fail, errorPopup,
    dismissError: () => setErrorPopup(null), run, busy: pending > 0,
  }), [section, editingSet, goTo, openEditor, playbookFocus, openPlaybook, clearPlaybookFocus,
    actor, setActor, token, setToken,
    health, configRoot, recheckHealth, toast, notify, fail, errorPopup, run, pending])

  return <AdminContext.Provider value={value}>{children}</AdminContext.Provider>
}

export function useAdmin(): AdminContextValue {
  const ctx = useContext(AdminContext)
  if (!ctx) throw new Error('useAdmin must be used within an AdminProvider')
  return ctx
}
