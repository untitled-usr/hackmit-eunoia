function inferDefaultMidAuthOrigin(): string {
  if (typeof window !== 'undefined' && window.location?.hostname) {
    // Use current page host to avoid localhost/127.0.0.1 cross-site cookie issues.
    return `${window.location.protocol}//${window.location.hostname}:19000`
  }
  return 'http://127.0.0.1:19000'
}

/** mid-auth 根地址，需与 CORS 白名单一致（默认沿用当前页面主机 + 19000） */
export const midAuthOrigin = (
  import.meta.env.VITE_MID_AUTH_ORIGIN ?? inferDefaultMidAuthOrigin()
).replace(/\/$/, '')

export type AuthUser = {
  id: string
  public_id: string
  username: string
  email: string
  display_name: string | null
  is_active: boolean
  avatar_url?: string | null
  last_login_at?: string | null
  created_at?: string
  updated_at?: string
}

export type MidAuthProfile = {
  id: string
  public_id: string
  username: string
  email: string
  display_name: string
  avatar_source: string | null
  avatar_url: string | null
  gender?: string | null
  description?: string | null
}

export type MemosProfileExtras = {
  gender: string | null
  description: string | null
}

export class MidAuthHttpError extends Error {
  readonly status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'MidAuthHttpError'
    this.status = status
  }
}

export async function parseMidAuthErrorMessage(res: Response): Promise<string> {
  try {
    const j: unknown = await res.json()
    if (j && typeof j === 'object' && 'detail' in j) {
      const d = (j as { detail: unknown }).detail
      if (typeof d === 'string') return d
      if (Array.isArray(d)) {
        return d
          .map((x) => {
            if (!x || typeof x !== 'object') return String(x)
            const msg = 'msg' in x ? String((x as { msg: unknown }).msg) : String(x)
            const loc = 'loc' in x && Array.isArray((x as { loc?: unknown }).loc)
              ? (x as { loc: unknown[] }).loc.map((p) => String(p)).join('.')
              : ''
            return loc ? `${loc}: ${msg}` : msg
          })
          .join('；')
      }
    }
  } catch {
    /* ignore */
  }
  return res.statusText || `HTTP ${res.status}`
}

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  throw new MidAuthHttpError(await parseMidAuthErrorMessage(res), res.status)
}

function pickAuthUser(payload: unknown): AuthUser {
  if (payload && typeof payload === 'object' && 'user' in payload) {
    return (payload as { user: AuthUser }).user
  }
  return payload as AuthUser
}

export async function fetchMe(): Promise<AuthUser | null> {
  const res = await fetch(`${midAuthOrigin}/auth/me`, {
    credentials: 'include',
  })
  if (res.status === 401 || res.status === 403) return null
  await throwIfNotOk(res)
  return (await res.json()) as AuthUser
}

export async function loginRequest(identifier: string, password: string): Promise<AuthUser> {
  const res = await fetch(`${midAuthOrigin}/auth/login`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ identifier: identifier.trim(), password }),
  })
  await throwIfNotOk(res)
  return pickAuthUser(await res.json())
}

export async function logoutRequest(): Promise<void> {
  const res = await fetch(`${midAuthOrigin}/auth/logout`, {
    method: 'POST',
    credentials: 'include',
  })
  await throwIfNotOk(res)
}

export async function registerRequest(body: {
  username: string
  email: string
  password: string
  display_name?: string | null
}): Promise<AuthUser> {
  const res = await fetch(`${midAuthOrigin}/auth/register`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username: body.username.trim(),
      email: body.email.trim(),
      password: body.password,
      display_name: body.display_name?.trim() || null,
    }),
  })
  await throwIfNotOk(res)
  return pickAuthUser(await res.json())
}

export async function fetchMyProfile(): Promise<MidAuthProfile | null> {
  const res = await fetch(`${midAuthOrigin}/me/profile`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401 || res.status === 403) return null
  await throwIfNotOk(res)
  return (await res.json()) as MidAuthProfile
}

export function makeMyAvatarFallbackUrl(): string {
  const ts = Date.now()
  return `${midAuthOrigin}/me/avatar?t=${ts}`
}

export type UpdateMyProfilePayload = {
  username?: string
  email?: string
  display_name?: string
  gender?: string | null
  description?: string | null
}

export async function updateMyProfile(
  payload: UpdateMyProfilePayload,
): Promise<MidAuthProfile> {
  const res = await fetch(`${midAuthOrigin}/me/profile`, {
    method: 'PATCH',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(payload),
  })
  await throwIfNotOk(res)
  return (await res.json()) as MidAuthProfile
}

export async function changeMyPassword(
  oldPassword: string,
  newPassword: string,
): Promise<void> {
  const res = await fetch(`${midAuthOrigin}/auth/change-password`, {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      old_password: oldPassword,
      new_password: newPassword,
    }),
  })
  await throwIfNotOk(res)
}

export async function uploadMyAvatar(file: File): Promise<void> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${midAuthOrigin}/me/avatar`, {
    method: 'POST',
    credentials: 'include',
    body: form,
  })
  await throwIfNotOk(res)
}

export async function deleteMyAvatar(): Promise<void> {
  const res = await fetch(`${midAuthOrigin}/me/avatar`, {
    method: 'DELETE',
    credentials: 'include',
  })
  await throwIfNotOk(res)
}

type JsonRecord = Record<string, unknown>

function readStringField(obj: JsonRecord, keys: string[]): string | null {
  for (const key of keys) {
    const value = obj[key]
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function collectCandidateObjects(root: unknown): JsonRecord[] {
  const out: JsonRecord[] = []
  const queue: unknown[] = [root]
  while (queue.length > 0) {
    const item = queue.shift()
    if (!item || typeof item !== 'object') continue
    if (Array.isArray(item)) {
      for (const child of item) queue.push(child)
      continue
    }
    const record = item as JsonRecord
    out.push(record)
    for (const value of Object.values(record)) queue.push(value)
  }
  return out
}

function extractMemosProfileExtras(payload: unknown): MemosProfileExtras {
  const objects = collectCandidateObjects(payload)
  let gender: string | null = null
  let description: string | null = null

  for (const obj of objects) {
    if (!gender) {
      gender = readStringField(obj, ['gender', 'sex', 'Gender', 'Sex'])
    }
    if (!description) {
      description = readStringField(obj, [
        'description',
        'bio',
        'about',
        'signature',
        'intro',
        'summary',
        'Description',
      ])
    }
    if (gender && description) break
  }

  return { gender, description }
}

export async function fetchMyMemosProfileExtras(): Promise<MemosProfileExtras | null> {
  const res = await fetch(`${midAuthOrigin}/me/library/settings?pageSize=100`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401 || res.status === 403 || res.status === 404) return null
  await throwIfNotOk(res)
  return extractMemosProfileExtras((await res.json()) as unknown)
}
