/** Structured half of a 403 — the server names the action, the refused
 * role and the roles that hold the permission, so the UI can offer the fix. */
export interface PermissionDetail {
  action: string
  role: string | null
  permitted: string[]
}

export class ApiError extends Error {
  status: number
  permission: PermissionDetail | null
  constructor(message: string, status: number, permission: PermissionDetail | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.permission = permission
  }
}

/** The admin-defined user the presenter is acting as, if any. Sent as
 * `X-S7-User: <id>` on every request: the server derives the acting role
 * from it and records the person's name where an actor is recorded.
 * Absent when a plain role was picked — role bodies then work unchanged. */
const USER_KEY = 's7cc.userId'
export function getActingUserId(): string | null {
  try { return localStorage.getItem(USER_KEY) } catch { return null }
}
export function setActingUserId(id: string | null) {
  try {
    if (id) localStorage.setItem(USER_KEY, id)
    else localStorage.removeItem(USER_KEY)
  } catch { /* storage unavailable */ }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }
  const userId = getActingUserId()
  if (userId) headers['X-S7-User'] = userId
  const res = await fetch(path, {
    ...options,
    headers: { ...headers, ...(options.headers as Record<string, string> | undefined) },
  })
  if (!res.ok) {
    let detail = res.statusText
    let permission: PermissionDetail | null = null
    try {
      const body = await res.json()
      detail = body.detail ?? detail
      if (res.status === 403 && Array.isArray(body.permitted) && typeof body.action === 'string') {
        permission = { action: body.action, role: body.role ?? null, permitted: body.permitted }
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(detail, res.status, permission)
  }
  return res.json() as Promise<T>
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path)
}

export function apiPost<T>(path: string, body: Record<string, unknown> = {}): Promise<T> {
  return request<T>(path, { method: 'POST', body: JSON.stringify(body) })
}

export function apiPatch<T>(path: string, body: Record<string, unknown>): Promise<T> {
  return request<T>(path, { method: 'PATCH', body: JSON.stringify(body) })
}

export function apiUpload<T>(path: string, form: FormData): Promise<T> {
  return request<T>(path, { method: 'POST', body: form })
}
