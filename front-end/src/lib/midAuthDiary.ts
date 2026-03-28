import { MidAuthHttpError, midAuthOrigin, parseMidAuthErrorMessage } from './midAuth'

const DIARY_API_BASE = `${midAuthOrigin}/me/diary/entries`
const META_MARKER = '[EUNOIA_META:'
const META_SUFFIX = ']'
const LEGACY_META_MARKER = '<!--EUNOIA_META:'
const LEGACY_META_SUFFIX = '-->'
const DIARY_SYSTEM_TAG = 'eunoia-diary'
const MAX_SYNC_CONTENT_BYTES = 9000
const MAX_IMAGE_STICKER_DATA_URL_CHARS = 3500

type DiaryStatus = 'normal' | 'archived' | 'digested'

export type DiaryEntrySyncShape = {
  id: number
  title: string
  text: string
  mood: string
  moodIntensity: number
  keywords: string[]
  timestamp: string
  locked: boolean
  unlockTime: string | null
  unlockedAt?: string | null
  status?: 'digested' | 'archived'
  stickers?: Array<{
    id: number
    kind: 'emoji' | 'text' | 'image'
    content: string
    xPercent: number
    yPercent: number
    scale: number
    rotation: number
  }>
}

type DiaryApiEntry = {
  id: string
  title: string
  content: string
  keywords: string[]
  status: DiaryStatus
  locked: boolean
  unlock_time: string | null
  order: number
  created_at: string
  updated_at: string
}

type DiaryMetaPayload = {
  mood?: string
  moodIntensity?: number
  timestamp?: string
  unlockedAt?: string | null
  stickers?: DiaryEntrySyncShape['stickers']
  localId?: number
}

type CompactSticker = [number, 'emoji' | 'text' | 'image', string, number, number, number, number]
type CompactDiaryMetaPayload = {
  v: 2
  m?: string
  mi?: number
  t?: string
  u?: string | null
  l?: number
  s?: CompactSticker[]
}

const remoteIdByLocalId = new Map<number, string>()

function encodeBase64Utf8(input: string): string {
  const bytes = new TextEncoder().encode(input)
  let binary = ''
  for (const b of bytes) binary += String.fromCharCode(b)
  return btoa(binary)
}

function decodeBase64Utf8(input: string): string {
  const binary = atob(input)
  const bytes = Uint8Array.from(binary, (ch) => ch.charCodeAt(0))
  return new TextDecoder().decode(bytes)
}

function toDiaryStatus(value: DiaryEntrySyncShape['status']): DiaryStatus {
  if (value === 'archived') return 'archived'
  if (value === 'digested') return 'digested'
  return 'normal'
}

function normalizeKeywords(value: string[]): string[] {
  return Array.from(
    new Set(
      (value ?? [])
        .map((v) => String(v ?? '').trim().replace(/^#/, ''))
        .filter(Boolean),
    ),
  )
}

function isDiarySystemTag(tag: string): boolean {
  return tag.trim().toLowerCase() === DIARY_SYSTEM_TAG
}

function withDiarySystemTag(keywords: string[]): string[] {
  const normalized = normalizeKeywords(keywords)
  if (normalized.some((tag) => isDiarySystemTag(tag))) return normalized
  return [...normalized, DIARY_SYSTEM_TAG]
}

function parseMetaFromContent(content: string): { text: string; meta: DiaryMetaPayload | null } {
  const raw = String(content ?? '')
  const tryParseByMarker = (marker: string, suffix: string): { text: string; meta: DiaryMetaPayload | null } | null => {
    const markerIndex = raw.lastIndexOf(marker)
    if (markerIndex < 0) return null
    const suffixIndex = raw.indexOf(suffix, markerIndex)
    if (suffixIndex < 0) return null

    const encoded = raw.slice(markerIndex + marker.length, suffixIndex).trim()
    const text = raw.slice(0, markerIndex).replace(/\s+$/, '')
    if (!encoded) return { text, meta: null }

    try {
      const json = decodeBase64Utf8(encoded)
      const parsed = JSON.parse(json) as unknown
      return { text, meta: parseDiaryMeta(parsed) }
    } catch {
      return { text: raw, meta: null }
    }
  }

  const next = tryParseByMarker(META_MARKER, META_SUFFIX)
  if (next) return next
  const legacy = tryParseByMarker(LEGACY_META_MARKER, LEGACY_META_SUFFIX)
  if (legacy) return legacy
  return { text: raw, meta: null }
}

function encodeMetaToContent(text: string, entry: DiaryEntrySyncShape): string {
  const cleanText = String(text ?? '').trim()
  const compactMeta: CompactDiaryMetaPayload = {
    v: 2,
    m: entry.mood,
    mi: entry.moodIntensity,
    t: entry.timestamp,
    u: entry.unlockedAt ?? null,
    l: entry.id,
    s: toCompactStickers(sanitizeStickersForSync(entry.stickers ?? [])),
  }
  const encoded = encodeBase64Utf8(JSON.stringify(compactMeta))
  const candidate = !cleanText
    ? `${META_MARKER}${encoded}${META_SUFFIX}`
    : `${cleanText}\n\n${META_MARKER}${encoded}${META_SUFFIX}`

  // Avoid silently dropping transform data.
  if (utf8ByteLength(candidate) > MAX_SYNC_CONTENT_BYTES) {
    throw new MidAuthHttpError(
      'Diary content is too large to sync. Please reduce text length or number of image stickers.',
      400,
    )
  }
  return candidate
}

function utf8ByteLength(input: string): number {
  return new TextEncoder().encode(input).length
}

function sanitizeStickersForSync(
  stickers: NonNullable<DiaryEntrySyncShape['stickers']>,
): NonNullable<DiaryEntrySyncShape['stickers']> {
  return stickers.map((sticker) => {
    if (sticker.kind !== 'image') return sticker
    const content = String(sticker.content ?? '')
    if (!content.startsWith('data:image/')) return { ...sticker, kind: 'emoji', content: '🖼️' }
    if (content.length <= MAX_IMAGE_STICKER_DATA_URL_CHARS) return sticker
    // Oversized image sticker will blow up memo.content length; keep a visual placeholder.
    return { ...sticker, kind: 'emoji', content: '🖼️' }
  })
}

function toCompactStickers(
  stickers: NonNullable<DiaryEntrySyncShape['stickers']>,
): CompactSticker[] {
  return stickers.map((sticker) => [
    Number(sticker.id) || Date.now(),
    sticker.kind,
    String(sticker.content ?? ''),
    round2(sticker.xPercent),
    round2(sticker.yPercent),
    round3(sticker.scale),
    round2(sticker.rotation),
  ])
}

function fromCompactStickers(compact: unknown): NonNullable<DiaryEntrySyncShape['stickers']> {
  if (!Array.isArray(compact)) return []
  const out: NonNullable<DiaryEntrySyncShape['stickers']> = []
  for (const item of compact) {
    if (!Array.isArray(item) || item.length < 7) continue
    const [id, kind, content, x, y, scale, rotation] = item
    if (kind !== 'emoji' && kind !== 'text' && kind !== 'image') continue
    out.push({
      id: Number(id) || Date.now(),
      kind,
      content: String(content ?? ''),
      xPercent: clampNum(Number(x), 0, 100, 50),
      yPercent: clampNum(Number(y), 0, 100, 50),
      scale: clampNum(Number(scale), 0.5, 2.5, 1),
      rotation: Number.isFinite(Number(rotation)) ? Number(rotation) : 0,
    })
  }
  return out
}

function parseDiaryMeta(raw: unknown): DiaryMetaPayload | null {
  if (!raw || typeof raw !== 'object') return null
  const rec = raw as Record<string, unknown>

  // v2 compact payload
  if (Number(rec.v) === 2) {
    return {
      mood: typeof rec.m === 'string' ? rec.m : undefined,
      moodIntensity: typeof rec.mi === 'number' ? rec.mi : undefined,
      timestamp: typeof rec.t === 'string' ? rec.t : undefined,
      unlockedAt: rec.u == null ? null : String(rec.u),
      localId: typeof rec.l === 'number' ? rec.l : undefined,
      stickers: fromCompactStickers(rec.s),
    }
  }

  // backward compatibility payload
  return {
    mood: typeof rec.mood === 'string' ? rec.mood : undefined,
    moodIntensity: typeof rec.moodIntensity === 'number' ? rec.moodIntensity : undefined,
    timestamp: typeof rec.timestamp === 'string' ? rec.timestamp : undefined,
    unlockedAt: rec.unlockedAt == null ? null : String(rec.unlockedAt),
    localId: typeof rec.localId === 'number' ? rec.localId : undefined,
    stickers: Array.isArray(rec.stickers) ? (rec.stickers as DiaryEntrySyncShape['stickers']) : [],
  }
}

function round2(v: number): number {
  return Math.round((Number(v) || 0) * 100) / 100
}

function round3(v: number): number {
  return Math.round((Number(v) || 0) * 1000) / 1000
}

function clampNum(value: number, min: number, max: number, fallback: number): number {
  if (!Number.isFinite(value)) return fallback
  return Math.min(max, Math.max(min, value))
}

function coerceNumericId(remoteId: string, fallbackFromMeta?: number): number {
  if (typeof fallbackFromMeta === 'number' && Number.isFinite(fallbackFromMeta)) return fallbackFromMeta
  const n = Number(remoteId)
  if (Number.isFinite(n)) return n
  let hash = 0
  for (let i = 0; i < remoteId.length; i += 1) hash = (hash * 31 + remoteId.charCodeAt(i)) | 0
  return Math.abs(hash) + 1
}

function toLocalEntry(remote: DiaryApiEntry): DiaryEntrySyncShape {
  const { text, meta } = parseMetaFromContent(remote.content)
  const localId = coerceNumericId(remote.id, meta?.localId)
  return {
    id: localId,
    title: remote.title || '',
    text,
    mood: meta?.mood || '😊',
    moodIntensity: typeof meta?.moodIntensity === 'number' ? meta.moodIntensity : 3,
    keywords: normalizeKeywords(remote.keywords ?? []).filter((tag) => !isDiarySystemTag(tag)),
    timestamp: meta?.timestamp || remote.created_at || new Date().toISOString(),
    locked: Boolean(remote.locked),
    unlockTime: remote.unlock_time ?? null,
    unlockedAt: meta?.unlockedAt ?? null,
    status: remote.status === 'normal' ? undefined : remote.status,
    stickers: Array.isArray(meta?.stickers) ? meta!.stickers : [],
  }
}

function isDiaryRemoteEntry(remote: DiaryApiEntry): boolean {
  if (normalizeKeywords(remote.keywords ?? []).some((tag) => isDiarySystemTag(tag))) return true
  const parsed = parseMetaFromContent(remote.content)
  return parsed.meta !== null
}

function toCreatePayload(entry: DiaryEntrySyncShape, order: number): Record<string, unknown> {
  return {
    title: String(entry.title ?? '').trim(),
    content: encodeMetaToContent(entry.text, entry),
    keywords: withDiarySystemTag(entry.keywords ?? []),
    status: toDiaryStatus(entry.status),
    unlock_time: entry.locked && entry.unlockTime ? entry.unlockTime : null,
    order,
  }
}

function toPatchPayload(entry: DiaryEntrySyncShape, order: number): Record<string, unknown> {
  return {
    title: String(entry.title ?? '').trim(),
    content: encodeMetaToContent(entry.text, entry),
    keywords: withDiarySystemTag(entry.keywords ?? []),
    status: toDiaryStatus(entry.status),
    unlock_time: entry.locked && entry.unlockTime ? entry.unlockTime : null,
    order,
  }
}

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  throw new MidAuthHttpError(await parseMidAuthErrorMessage(res), res.status)
}

async function requestJson(path: string, init?: RequestInit): Promise<unknown> {
  const res = await fetch(`${midAuthOrigin}${path}`, {
    credentials: 'include',
    headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    ...init,
  })
  await throwIfNotOk(res)
  if (res.status === 204) return null
  return (await res.json()) as unknown
}

function asDiaryApiEntry(payload: unknown): DiaryApiEntry {
  const record = (payload ?? {}) as Record<string, unknown>
  return {
    id: String(record.id ?? ''),
    title: String(record.title ?? ''),
    content: String(record.content ?? ''),
    keywords: Array.isArray(record.keywords) ? record.keywords.map((x) => String(x)) : [],
    status: (record.status === 'archived' || record.status === 'digested' ? record.status : 'normal') as DiaryStatus,
    locked: Boolean(record.locked),
    unlock_time: record.unlock_time == null ? null : String(record.unlock_time),
    order: typeof record.order === 'number' ? record.order : Number(record.order ?? 0) || 0,
    created_at: String(record.created_at ?? ''),
    updated_at: String(record.updated_at ?? ''),
  }
}

async function createRemoteEntry(entry: DiaryEntrySyncShape, order: number): Promise<DiaryApiEntry> {
  const payload = await requestJson('/me/diary/entries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(toCreatePayload(entry, order)),
  })
  return asDiaryApiEntry(payload)
}

async function patchRemoteEntry(remoteId: string, entry: DiaryEntrySyncShape, order: number): Promise<DiaryApiEntry> {
  const payload = await requestJson(`/me/diary/entries/${encodeURIComponent(remoteId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(toPatchPayload(entry, order)),
  })
  return asDiaryApiEntry(payload)
}

async function upsertRemoteEntry(
  entry: DiaryEntrySyncShape,
  order: number,
  existingRemoteId: string | undefined,
): Promise<DiaryApiEntry> {
  if (!existingRemoteId) {
    return createRemoteEntry(entry, order)
  }

  try {
    return await patchRemoteEntry(existingRemoteId, entry, order)
  } catch (error) {
    if (error instanceof MidAuthHttpError && error.status === 404) {
      // Reconcile stale mapping before creating to avoid duplicate diary rows.
      const reconciledRemoteId = await findRemoteIdByLocalId(entry.id)
      if (reconciledRemoteId) {
        remoteIdByLocalId.set(entry.id, reconciledRemoteId)
        return patchRemoteEntry(reconciledRemoteId, entry, order)
      }
      return createRemoteEntry(entry, order)
    }
    throw error
  }
}

async function findRemoteIdByLocalId(localId: number): Promise<string | null> {
  const payload = await requestJson('/me/diary/entries')
  const items = Array.isArray((payload as { items?: unknown[] })?.items)
    ? ((payload as { items: unknown[] }).items ?? [])
    : []
  for (const raw of items) {
    const remote = asDiaryApiEntry(raw)
    if (!remote.id || !isDiaryRemoteEntry(remote)) continue
    const { meta } = parseMetaFromContent(remote.content)
    if (typeof meta?.localId === 'number' && Number.isFinite(meta.localId) && meta.localId === localId) {
      return remote.id
    }
  }
  return null
}

async function reorderRemoteEntries(orderPairs: Array<{ id: string; order: number }>): Promise<void> {
  try {
    await requestJson('/me/diary/entries/reorder', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify({ entries: orderPairs }),
    })
  } catch (error) {
    // Reorder is a best-effort step; each entry already carries `order` in create/patch payload.
    // Ignore per-entry not found to avoid surfacing false save failures on lock/unlock updates.
    if (error instanceof MidAuthHttpError && error.status === 404) return
    throw error
  }
}

export async function fetchDiaryEntriesFromMemos<T>(): Promise<T[] | null> {
  const res = await fetch(DIARY_API_BASE, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (res.status === 401 || res.status === 403 || res.status === 404) return null
  await throwIfNotOk(res)
  const payload = (await res.json()) as { items?: unknown[] }
  const items = Array.isArray(payload?.items) ? payload.items : []
  // Reset mapping at hydrate boundary to avoid cross-page/cross-user leakage.
  remoteIdByLocalId.clear()
  const remotes = items.map(asDiaryApiEntry).filter((x) => x.id).filter(isDiaryRemoteEntry)
  const dedupedByLocalId = new Map<number, { local: DiaryEntrySyncShape; remote: DiaryApiEntry; updatedMs: number }>()
  for (const remote of remotes) {
    const local = toLocalEntry(remote)
    const updatedMs = Number.isFinite(Date.parse(remote.updated_at)) ? Date.parse(remote.updated_at) : 0
    const existing = dedupedByLocalId.get(local.id)
    if (!existing || updatedMs >= existing.updatedMs) {
      dedupedByLocalId.set(local.id, { local, remote, updatedMs })
    }
  }
  const locals: DiaryEntrySyncShape[] = []
  for (const { local, remote } of dedupedByLocalId.values()) {
    remoteIdByLocalId.set(local.id, remote.id)
    locals.push(local)
  }
  return locals as unknown as T[]
}

export async function saveDiaryEntriesToMemos<T>(entries: T[]): Promise<void> {
  const localEntries = (entries as unknown as DiaryEntrySyncShape[]).map((e) => ({ ...e }))

  // Only rely on diary mapping hydrated from diary API.
  const orderPairs: Array<{ id: string; order: number }> = []
  for (let i = 0; i < localEntries.length; i += 1) {
    const entry = localEntries[i]
    const order = i + 1
    const existingRemoteId = remoteIdByLocalId.get(entry.id)
    const saved = await upsertRemoteEntry(entry, order, existingRemoteId)
    remoteIdByLocalId.set(entry.id, saved.id)
    orderPairs.push({ id: saved.id, order })
  }

  // Persist order in one shot.
  if (orderPairs.length > 0) {
    await reorderRemoteEntries(orderPairs)
  }
}
