import { MidAuthHttpError, midAuthOrigin, parseMidAuthErrorMessage } from './midAuth'

type JsonRecord = Record<string, unknown>

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  throw new MidAuthHttpError(await parseMidAuthErrorMessage(res), res.status)
}

async function fetchJson(path: string, init?: RequestInit): Promise<unknown> {
  const headers = init?.headers
  const res = await fetch(`${midAuthOrigin}${path}`, {
    credentials: 'include',
    ...init,
    headers: { Accept: 'application/json', ...(headers ?? {}) },
  })
  await throwIfNotOk(res)
  if (res.status === 204) return null
  return (await res.json()) as unknown
}

function asRecord(value: unknown): JsonRecord | null {
  return value && typeof value === 'object' ? (value as JsonRecord) : null
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

export type DriftBottle = {
  name: string
  memo?: string
  creator?: string
  state?: string
  score?: number
  content: string
  tags: string[]
}

export type PickDriftBottleResult = {
  driftBottle: DriftBottle
  remainingPicks: number
}

export type RefreshDriftCandidatesResult = {
  refreshedCount: number
}

export type SearchDriftBottlesResult = {
  driftBottles: DriftBottle[]
  nextPageToken?: string
}

export type CreateDriftBottleInput = {
  content: string
  tags?: string[]
  attachments?: Array<{
    name?: string
    filename?: string
    content?: string
    type?: string
    externalLink?: string
  }>
}

function normalizeBottle(payload: unknown): DriftBottle {
  const root = asRecord(payload) ?? {}
  const memoInfo = asRecord(root.memoInfo)
  const tags = Array.isArray(root.tags)
    ? root.tags
        .map((v) => readString(v).trim())
        .filter((v) => v.length > 0)
    : []
  return {
    name: readString(root.name),
    memo: readString(root.memo) || undefined,
    creator: readString(root.creator) || undefined,
    state: readString(root.state) || undefined,
    score: typeof root.score === 'number' ? root.score : undefined,
    content: readString(memoInfo?.content),
    tags,
  }
}

export async function createDriftBottle(input: CreateDriftBottleInput): Promise<DriftBottle> {
  const payload = await fetchJson('/me/bottles', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      content: input.content,
      tags: input.tags ?? [],
      attachments: input.attachments ?? [],
    }),
  })
  return normalizeBottle(payload)
}

export async function pickDriftBottle(): Promise<PickDriftBottleResult> {
  const payload = await fetchJson('/me/bottles/pick', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  const root = asRecord(payload) ?? {}
  return {
    driftBottle: normalizeBottle(root.driftBottle),
    remainingPicks: typeof root.remainingPicks === 'number' ? root.remainingPicks : 0,
  }
}

export async function getDriftBottle(bottleIdOrName: string): Promise<DriftBottle> {
  const bottleId = bottleIdOrName.replace(/^drift-bottles\//, '')
  const payload = await fetchJson(`/me/bottles/${encodeURIComponent(bottleId)}`)
  return normalizeBottle(payload)
}

export async function replyDriftBottle(bottleIdOrName: string, content: string): Promise<void> {
  const bottleId = bottleIdOrName.replace(/^drift-bottles\//, '')
  await fetchJson(`/me/bottles/${encodeURIComponent(bottleId)}/reply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
  })
}

export async function refreshMyDriftBottleCandidates(): Promise<RefreshDriftCandidatesResult> {
  const payload = await fetchJson('/me/bottles/refresh', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  })
  const root = asRecord(payload) ?? {}
  return { refreshedCount: typeof root.refreshedCount === 'number' ? root.refreshedCount : 0 }
}

export async function searchDriftBottlesByTag(
  tag: string,
  pageSize = 20,
  pageToken?: string,
): Promise<SearchDriftBottlesResult> {
  const params = new URLSearchParams()
  params.set('tag', tag)
  params.set('pageSize', String(pageSize))
  if (pageToken) params.set('pageToken', pageToken)
  const payload = await fetchJson(`/me/bottles/search?${params.toString()}`)
  const root = asRecord(payload) ?? {}
  const driftBottles = Array.isArray(root.driftBottles)
    ? root.driftBottles.map((item) => normalizeBottle(item))
    : []
  const nextPageToken = readString(root.nextPageToken)
  return {
    driftBottles,
    nextPageToken: nextPageToken || undefined,
  }
}
