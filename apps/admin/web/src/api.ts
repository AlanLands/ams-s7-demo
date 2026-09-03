import type {
  AuditRow, CacheStats, FileDetail, LlmDescribe, LlmSettings, Overview, Recordings,
  RolesOverrides, RolesPayload, RunRow, SaveResult, SetDetail, SetSummary, User,
  WorkflowPreview, LedgerLine, Observability, PlaybookActions, PlaybookDetail,
  PlaybookSaveResult, PlaybookStep, PlaybookValidation,
  Correction, LearningOverview, Proposal, ProposalDetail, ProposeBody, SelfHealView,
} from './types'

/** Every error the backend raises is `{detail}`; the status code says what
 * kind: 400 refused by validation, 401 bad token, 404 unknown thing, 409
 * refused because of state. Callers branch on `status` where the copy
 * should differ (a 409 on delete says "in use", not "went wrong"). */
export class ApiError extends Error {
  status: number
  /** Extra fields beside `detail` when the server sends them — a playbook
   * 400 lists every `problems` entry so the editor can show them all. */
  problems?: string[]
  constructor(message: string, status: number, problems?: string[]) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.problems = problems
  }
}

const ACTOR_KEY = 's7admin.actor'
const TOKEN_KEY = 's7admin.token'

export function getActor(): string {
  try { return localStorage.getItem(ACTOR_KEY) ?? '' } catch { return '' }
}
export function setActor(v: string) {
  try { localStorage.setItem(ACTOR_KEY, v) } catch { /* storage unavailable */ }
}
export function getToken(): string {
  try { return localStorage.getItem(TOKEN_KEY) ?? '' } catch { return '' }
}
export function setToken(v: string) {
  try {
    if (v) localStorage.setItem(TOKEN_KEY, v)
    else localStorage.removeItem(TOKEN_KEY)
  } catch { /* storage unavailable */ }
}

function headers(): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  const actor = getActor().trim()
  if (actor) h['X-Admin-User'] = actor
  const token = getToken().trim()
  if (token) h['X-Admin-Token'] = token
  return h
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api/admin${path}`, { ...options, headers: { ...headers(), ...(options.headers as Record<string, string> | undefined) } })
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    let problems: string[] | undefined
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail) detail = JSON.stringify(body.detail)
      if (Array.isArray(body.problems)) problems = body.problems.map(String)
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, problems)
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  return (text ? JSON.parse(text) : undefined) as T
}

const get = <T,>(path: string) => request<T>(path)
const post = <T,>(path: string, body: unknown = {}) => request<T>(path, { method: 'POST', body: JSON.stringify(body) })
const put = <T,>(path: string, body: unknown) => request<T>(path, { method: 'PUT', body: JSON.stringify(body) })
const patch = <T,>(path: string, body: unknown) => request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
const del = <T,>(path: string) => request<T>(path, { method: 'DELETE' })

const enc = encodeURIComponent

/** Typed client mirroring docs/admin-api.md, one function per route. */
export const api = {
  health: () => get<{ ok: boolean; config_root: string }>('/health'),
  overview: () => get<Overview>('/overview'),

  promptSets: {
    list: () => get<SetSummary[]>('/prompt-sets'),
    create: (body: { name: string; cloned_from?: string; description?: string; note?: string }) =>
      post<SetSummary>('/prompt-sets', body),
    detail: (set: string) => get<SetDetail>(`/prompt-sets/${enc(set)}`),
    update: (set: string, description: string) => patch<SetSummary>(`/prompt-sets/${enc(set)}`, { description }),
    remove: (set: string) => del<void>(`/prompt-sets/${enc(set)}`),
    history: (set: string) => get<LedgerLine[]>(`/prompt-sets/${enc(set)}/history`),
    file: (set: string, id: string) => get<FileDetail>(`/prompt-sets/${enc(set)}/files/${enc(id)}`),
    saveFile: (set: string, id: string, body: string, note: string) =>
      put<SaveResult>(`/prompt-sets/${enc(set)}/files/${enc(id)}`, { body, note }),
    createFile: (set: string, body: {
      layer: string; id: string; title: string; stage: string; summary: string; body: string; variables?: string[]; note: string
    }) => post<FileDetail>(`/prompt-sets/${enc(set)}/files`, body),
    version: (set: string, id: string, n: number) =>
      get<{ version: number; body: string }>(`/prompt-sets/${enc(set)}/files/${enc(id)}/versions/${n}`),
    diff: (set: string, id: string, from: number, to: number) =>
      get<{ from: number; to: number; diff: string }>(`/prompt-sets/${enc(set)}/files/${enc(id)}/diff?from=${from}&to=${to}`),
    rollback: (set: string, id: string, to_version: number, note: string) =>
      post<SaveResult>(`/prompt-sets/${enc(set)}/files/${enc(id)}/rollback`, { to_version, note }),
    workflows: (set: string) => get<WorkflowPreview[]>(`/prompt-sets/${enc(set)}/workflows`),
    workflow: (set: string, wf: string) => get<WorkflowPreview>(`/prompt-sets/${enc(set)}/workflows/${enc(wf)}`),
  },

  llm: {
    describe: () => get<LlmDescribe>('/llm'),
    save: (body: LlmSettings) => put<LlmSettings>('/llm', body),
  },
  recordings: () => get<Recordings>('/recordings'),
  cache: {
    stats: () => get<CacheStats>('/cache'),
    clear: () => del<{ removed: number }>('/cache'),
  },

  roles: {
    get: () => get<RolesPayload>('/roles'),
    save: (body: RolesOverrides) => put<RolesPayload>('/roles', body),
    reset: () => post<RolesPayload>('/roles/reset'),
  },

  users: {
    list: () => get<User[]>('/users'),
    create: (body: { name: string; role: string; email?: string }) => post<User>('/users', body),
    update: (id: string, body: Partial<Pick<User, 'name' | 'email' | 'role' | 'active'>>) =>
      patch<User>(`/users/${enc(id)}`, body),
    remove: (id: string) => del<void>(`/users/${enc(id)}`),
  },

  runs: {
    list: () => get<RunRow[]>('/runs'),
    archived: () => get<RunRow[]>('/runs/archived'),
    reset: (id: string) => post<RunRow>(`/runs/${enc(id)}/reset`),
    archive: (id: string) => post<{ archived_to: string }>(`/runs/${enc(id)}/archive`),
    remove: (id: string) => del<void>(`/runs/${enc(id)}`),
    /** The run's self-healing change records and playbook progress â€”
     * derived on read, RULE_BASED. Fetched only when the drawer opens. */
    selfHealing: (id: string) => get<SelfHealView>(`/runs/${enc(id)}/self-healing`),
  },

  audit: (limit = 200, action = '') =>
    get<AuditRow[]>(`/audit?limit=${limit}${action ? `&action=${enc(action)}` : ''}`),

  /** Structured playbook editing — steps validated against the engine's own
   * catalogue (factory/self_heal.py). Rollback is the file route with the
   * playbook id: a playbook is a layer file, so the ledger is shared. */
  playbooks: {
    actions: () => get<PlaybookActions>('/playbook-actions'),
    list: (set: string) => get<PlaybookDetail[]>(`/prompt-sets/${enc(set)}/playbooks`),
    detail: (set: string, id: string) => get<PlaybookDetail>(`/prompt-sets/${enc(set)}/playbooks/${enc(id)}`),
    save: (set: string, id: string, body: { trigger?: string; stage?: string; steps: PlaybookStep[]; note: string }) =>
      put<PlaybookSaveResult>(`/prompt-sets/${enc(set)}/playbooks/${enc(id)}`, body),
    validate: (set: string, id: string, steps: PlaybookStep[]) =>
      post<PlaybookValidation>(`/prompt-sets/${enc(set)}/playbooks/${enc(id)}/validate`, { steps }),
  },

  /** Cross-run figures counted from files; null means unmeasured. */
  observability: (days = 30, promptSet = '') =>
    get<Observability>(`/observability?days=${days}${promptSet ? `&prompt_set=${enc(promptSet)}` : ''}`),

  /** Correction learning — admin only, never read by the Control Centre.
   * Corrections are engine-recorded; a proposal is one real model call
   * (502 when it fails or a replay recording is missing); nothing is
   * applied until accept records the new version through the ledger. */
  learning: {
    overview: (promptSet = '', days?: number) =>
      get<LearningOverview>(`/learning/overview${qs({ prompt_set: promptSet, days })}`),
    corrections: (opts: { promptSet?: string; stage?: string; targetId?: string; days?: number; learnableOnly?: boolean } = {}) =>
      get<Correction[]>(`/learning/corrections${qs({
        prompt_set: opts.promptSet, stage: opts.stage, target_id: opts.targetId, days: opts.days,
        learnable_only: opts.learnableOnly === undefined ? undefined : String(opts.learnableOnly),
      })}`),
    correction: (id: string) => get<Correction>(`/learning/corrections/${enc(id)}`),
    proposals: (promptSet = '', status = '') =>
      get<Proposal[]>(`/learning/proposals${qs({ prompt_set: promptSet, status })}`),
    propose: (body: ProposeBody) => post<Proposal>('/learning/proposals', body),
    proposal: (set: string, id: string) => get<ProposalDetail>(`/learning/proposals/${enc(set)}/${enc(id)}`),
    accept: (set: string, id: string, note: string) => post<Proposal>(`/learning/proposals/${enc(set)}/${enc(id)}/accept`, { note }),
    reject: (set: string, id: string, note: string) => post<Proposal>(`/learning/proposals/${enc(set)}/${enc(id)}/reject`, { note }),
  },
}

/** `?a=1&b=2` from a record, skipping blanks and undefined; '' when empty. */
function qs(params: Record<string, string | number | undefined | null>): string {
  const parts = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${enc(k)}=${enc(String(v))}`)
  return parts.length ? `?${parts.join('&')}` : ''
}
