import type {
  AuditRow, CacheStats, FileDetail, LlmDescribe, LlmSettings, Overview, Recordings,
  RolesOverrides, RolesPayload, RunRow, SaveResult, SetDetail, SetSummary, User,
  WorkflowPreview, LedgerLine, Observability, PlaybookActions, PlaybookDetail,
  PlaybookSaveResult, PlaybookStep, PlaybookValidation,
  Correction, LearningOverview, Proposal, ProposalDetail, ProposeBody, SelfHealView,
  AssetBrowseResult, AssetCreateResult, AssetImportResult, AssetSelection,
  Impact, NewAsset, ProfileDetail, ProfileFileDetail, ProfileNewFile, ProfileSaveResult, ProfileSummary,
  GithubIntegration, RepoTestResult, RepositoriesPayload,
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

/** Same auth headers, no JSON content type — for multipart uploads and
 * binary downloads. Errors are read the same way as `request`. */
async function raw(path: string, options: RequestInit = {}): Promise<Response> {
  const h = headers()
  delete h['Content-Type']
  const res = await fetch(`/api/admin${path}`, { ...options, headers: { ...h, ...(options.headers as Record<string, string> | undefined) } })
  if (!res.ok) {
    let detail = res.statusText || `HTTP ${res.status}`
    try {
      const body = await res.json()
      if (typeof body.detail === 'string') detail = body.detail
      else if (body.detail) detail = JSON.stringify(body.detail)
    } catch { /* non-JSON error body */ }
    throw new ApiError(detail, res.status)
  }
  return res
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

  /** Delivery profiles — one bundle of seven layers, an overlay over the
   * committed default set (docs/design-history/plans/2026-09-07-delivery-profiles.md).
   * The file routes share the layer ledger with the prompt-set routes. */
  profiles: {
    list: () => get<{ profiles: ProfileSummary[] }>('/profiles').then((r) => r.profiles),
    create: (body: { name: string; description: string }) => post<ProfileSummary>('/profiles', body),
    detail: (name: string) => get<ProfileDetail>(`/profiles/${enc(name)}`),
    update: (name: string, description: string) => patch<ProfileSummary>(`/profiles/${enc(name)}`, { description }),
    remove: (name: string) => del<void>(`/profiles/${enc(name)}`),
    history: (name: string) => get<{ history: LedgerLine[] }>(`/profiles/${enc(name)}/history`).then((r) => r.history),
    file: (name: string, id: string) => get<ProfileFileDetail>(`/profiles/${enc(name)}/files/${enc(id)}`),
    saveFile: (name: string, id: string, body: string, note: string) =>
      put<ProfileSaveResult>(`/profiles/${enc(name)}/files/${enc(id)}`, { body, note }),
    createFile: (name: string, body: ProfileNewFile) => post<ProfileSaveResult>(`/profiles/${enc(name)}/files`, body),
    createAsset: (name: string, body: NewAsset) =>
      post<AssetCreateResult>(`/profiles/${enc(name)}/assets`, body),
    browseAssets: (name: string, body: { repository: string; ref?: string; subdir?: string }) =>
      post<AssetBrowseResult>(`/profiles/${enc(name)}/assets/browse`, body),
    importAssets: (name: string, body: { repository: string; ref?: string; note?: string; files: AssetSelection[] }) =>
      post<AssetImportResult>(`/profiles/${enc(name)}/assets/import`, body),
    version: (name: string, id: string, n: number) =>
      get<{ id: string; version: number; body: string }>(`/profiles/${enc(name)}/files/${enc(id)}/versions/${n}`),
    diff: (name: string, id: string, from: number, to: number) =>
      get<{ from?: number; to?: number; diff: string }>(`/profiles/${enc(name)}/files/${enc(id)}/diff?from=${from}&to=${to}`)
        .then((r) => ({ from, to, diff: r.diff })),
    rollback: (name: string, id: string, to_version: number, note: string) =>
      post<ProfileSaveResult>(`/profiles/${enc(name)}/files/${enc(id)}/rollback`, { to_version, note }),
    /** Drop the profile's override so the default shows through again. */
    revert: (name: string, id: string, note: string) =>
      post<ProfileSaveResult>(`/profiles/${enc(name)}/files/${enc(id)}/revert`, { note }),
    impact: (name: string, id: string) => get<Impact>(`/profiles/${enc(name)}/files/${enc(id)}/impact`),
    exportUrl: (name: string) => `/api/admin/profiles/${enc(name)}/export.zip`,
    /** The zip as a Blob, fetched with the auth headers a plain anchor cannot send. */
    exportBlob: (name: string) => raw(`/profiles/${enc(name)}/export.zip`).then((r) => r.blob()),
    importZip: (file: File, opts: { name?: string; replace?: boolean } = {}) => {
      const form = new FormData()
      form.append('file', file, file.name)
      return raw(`/profiles/import${qs({ name: opts.name, replace: opts.replace ? 'true' : undefined })}`, { method: 'POST', body: form })
        .then((r) => r.json() as Promise<ProfileSummary>)
    },
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

  /** Known repositories — the cross-run registry the Control Centre's
   * reconnect chips read, joined with the runs that use each one. Derived
   * on read, RULE_BASED. Connecting stays a per-run action in the Control
   * Centre; `test` is an explicit operator probe (git ls-remote), audited. */
  repositories: {
    list: () => get<RepositoriesPayload>('/repositories'),
    forget: (url: string) => post<void>('/repositories/forget', { url }),
    test: (url: string) => post<RepoTestResult>('/repositories/test', { url }),
  },

  /** The GitHub integration layer as a profile resolves it, plus the gh
   * CLI's own login status. Credentials never live in S7. */
  integrations: {
    github: (profile = 'default') => get<GithubIntegration>(`/integrations/github${qs({ profile })}`),
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
