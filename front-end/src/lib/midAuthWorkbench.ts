import { MidAuthHttpError, midAuthOrigin, parseMidAuthErrorMessage } from './midAuth'

export const midAuthWorkbenchBase = `${midAuthOrigin}/me/ai/workbench`

async function throwIfNotOk(res: Response): Promise<void> {
  if (res.ok) return
  throw new MidAuthHttpError(await parseMidAuthErrorMessage(res), res.status)
}

export type WorkbenchModelItem = { id: string; name: string }

export type ChatMessagePayload = { role: 'user' | 'assistant' | 'system'; content: string }
export type ChatCompletionOutput = { content: string; reasoning: string }
export type AiChatTurnResult = {
  chatId: string
  assistantText: string
}
export type AiChatMessageItem = {
  id: string
  role: 'user' | 'assistant' | 'system'
  body: string
  reasoning?: string
}

export type WorkbenchChatItem = {
  id: string
  title: string
  modelId: string | null
  updatedAt: string | null
  pinned: boolean
  archived: boolean
  folderId: string | null
  shareId: string | null
  raw: Record<string, unknown>
}

export type WorkbenchPromptItem = {
  id: string
  command: string | null
  name: string
  content: string
}

export type WorkbenchToolItem = {
  id: string
  name: string
  description: string
  writeAccess: boolean
  raw: Record<string, unknown>
}

export type WorkbenchMemoryItem = {
  id: string
  content: string
  createdAt: string | null
}

export type WorkbenchFolderItem = {
  id: string
  name: string
  parentId: string | null
}

export type WorkbenchTagItem = {
  name: string
}

type JsonRecord = Record<string, unknown>

function buildQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v == null) continue
    search.set(k, String(v))
  }
  const qs = search.toString()
  return qs ? `?${qs}` : ''
}

async function fetchJson(path: string, init?: RequestInit): Promise<unknown> {
  const headers = init?.headers
  const res = await fetch(`${midAuthWorkbenchBase}${path}`, {
    credentials: 'include',
    ...init,
    headers: { Accept: 'application/json', ...(headers ?? {}) },
  })
  await throwIfNotOk(res)
  if (res.status === 204) return null
  return (await res.json()) as unknown
}

function asRecord(v: unknown): JsonRecord | null {
  return v && typeof v === 'object' ? (v as JsonRecord) : null
}

function normalizeOneTag(v: unknown): WorkbenchTagItem | null {
  if (typeof v === 'string' && v.trim()) return { name: v.trim() }
  const o = asRecord(v)
  if (!o) return null
  const name = String(o.name ?? '').trim()
  if (!name) return null
  return { name }
}

function normalizeOne(m: unknown): WorkbenchModelItem | null {
  if (!m || typeof m !== 'object') return null
  const o = m as Record<string, unknown>
  const id = String(o.id ?? '')
  if (!id) return null
  const name = String(o.name ?? id)
  return { id, name }
}

/** 归一化 OW / mid-auth 返回的模型列表（数组或带 items / data） */
export function normalizeWorkbenchModels(payload: unknown): WorkbenchModelItem[] {
  if (payload == null) return []
  if (Array.isArray(payload)) {
    return payload.map(normalizeOne).filter((x): x is WorkbenchModelItem => x !== null)
  }
  if (typeof payload !== 'object') return []
  const o = payload as Record<string, unknown>
  let source: unknown[] = []
  if (Array.isArray(o.items)) source = o.items
  else if (Array.isArray(o.data)) source = o.data
  else if (o.data && typeof o.data === 'object' && Array.isArray((o.data as { items?: unknown[] }).items)) {
    source = (o.data as { items: unknown[] }).items
  }
  return source.map(normalizeOne).filter((x): x is WorkbenchModelItem => x !== null)
}

function normalizeOneChat(v: unknown): WorkbenchChatItem | null {
  const o = asRecord(v)
  if (!o) return null
  const id = String(o.id ?? o.chat_id ?? '').trim()
  if (!id) return null
  const chatObj = asRecord(o.chat)
  const rowModels = Array.isArray(o.models) ? o.models : []
  const chatModels = Array.isArray(chatObj?.models) ? chatObj.models : []
  const inferredModelId = String(
    o.model_id ??
      o.model ??
      chatObj?.model_id ??
      chatObj?.model ??
      rowModels[0] ??
      chatModels[0] ??
      '',
  ).trim()
  const title = String(o.title ?? o.name ?? chatObj?.title ?? '未命名对话').trim() || '未命名对话'
  const updatedAtRaw = o.updated_at ?? o.updatedAt ?? o.update_time ?? o.timestamp ?? null
  const updatedAt = updatedAtRaw == null ? null : String(updatedAtRaw)
  return {
    id,
    title,
    modelId: inferredModelId || null,
    updatedAt,
    pinned: Boolean(o.pinned ?? o.is_pinned ?? false),
    archived: Boolean(o.archived ?? o.is_archived ?? false),
    folderId: o.folder_id == null ? null : String(o.folder_id),
    shareId: o.share_id == null ? null : String(o.share_id),
    raw: o,
  }
}

function normalizePrompts(payload: unknown): WorkbenchPromptItem[] {
  if (!Array.isArray(payload)) return []
  const out: WorkbenchPromptItem[] = []
  for (const item of payload) {
    const o = asRecord(item)
    if (!o) continue
    const id = String(o.id ?? '').trim()
    if (!id) continue
    out.push({
      id,
      command: o.command == null ? null : String(o.command),
      name: String(o.name ?? o.title ?? id),
      content: String(o.content ?? ''),
    })
  }
  return out
}

function normalizeTools(payload: unknown): WorkbenchToolItem[] {
  if (!Array.isArray(payload)) return []
  const out: WorkbenchToolItem[] = []
  for (const item of payload) {
    const o = asRecord(item)
    if (!o) continue
    const id = String(o.id ?? '').trim()
    if (!id) continue
    out.push({
      id,
      name: String(o.name ?? id),
      description: String(o.description ?? ''),
      writeAccess: Boolean(o.write_access ?? o.writeAccess ?? false),
      raw: o,
    })
  }
  return out
}

function normalizeMemories(payload: unknown): WorkbenchMemoryItem[] {
  let source: unknown[] = []
  if (Array.isArray(payload)) source = payload
  else {
    const o = asRecord(payload)
    if (o && Array.isArray(o.items)) source = o.items
    else if (o && Array.isArray(o.data)) source = o.data
  }
  const out: WorkbenchMemoryItem[] = []
  for (const item of source) {
    const o = asRecord(item)
    if (!o) continue
    const id = String(o.id ?? '').trim()
    if (!id) continue
    out.push({
      id,
      content: String(o.content ?? o.body ?? ''),
      createdAt: o.created_at == null ? null : String(o.created_at),
    })
  }
  return out
}

function normalizeFolders(payload: unknown): WorkbenchFolderItem[] {
  if (!Array.isArray(payload)) return []
  const out: WorkbenchFolderItem[] = []
  for (const item of payload) {
    const o = asRecord(item)
    if (!o) continue
    const id = String(o.id ?? '').trim()
    if (!id) continue
    out.push({
      id,
      name: String(o.name ?? id),
      parentId: o.parent_id == null ? null : String(o.parent_id),
    })
  }
  return out
}

function uniqueById(models: WorkbenchModelItem[]): WorkbenchModelItem[] {
  const seen = new Set<string>()
  const out: WorkbenchModelItem[] = []
  for (const m of models) {
    if (seen.has(m.id)) continue
    seen.add(m.id)
    out.push(m)
  }
  return out
}

async function listCompatModels(): Promise<WorkbenchModelItem[]> {
  const [legacyRes, baseLegacyRes] = await Promise.all([
    fetch(`${midAuthWorkbenchBase}/openwebui/models/openai-compat?refresh=true`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    }),
    fetch(`${midAuthWorkbenchBase}/openwebui/models/base/openai-compat`, {
      credentials: 'include',
      headers: { Accept: 'application/json' },
    }),
  ])

  // If both fail, surface one of the errors.
  if (!legacyRes.ok && !baseLegacyRes.ok) {
    await throwIfNotOk(legacyRes)
  }

  const listA = legacyRes.ok
    ? normalizeWorkbenchModels(await legacyRes.json())
    : ([] as WorkbenchModelItem[])
  const listB = baseLegacyRes.ok
    ? normalizeWorkbenchModels(await baseLegacyRes.json())
    : ([] as WorkbenchModelItem[])
  return uniqueById([...listA, ...listB])
}

export async function listWorkbenchModels(): Promise<WorkbenchModelItem[]> {
  const res = await fetch(`${midAuthWorkbenchBase}/models?refresh=true`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) {
    // Some Open WebUI builds do not support /models/list for this acting user.
    // Fall back to legacy openai-compat model catalogs.
    if (res.status === 404 || res.status === 422) return listCompatModels()
    await throwIfNotOk(res)
  }
  const json: unknown = await res.json()
  const models = normalizeWorkbenchModels(json)
  if (models.length > 0) return models
  return listCompatModels()
}

/** 未配置默认模型时返回 null（不抛错） */
export async function getDefaultWorkbenchModelId(): Promise<string | null> {
  const res = await fetch(`${midAuthWorkbenchBase}/models/default`, {
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) return null
  try {
    const j: unknown = await res.json()
    if (j && typeof j === 'object' && 'id' in j) {
      const id = String((j as { id: unknown }).id)
      return id || null
    }
  } catch {
    /* ignore */
  }
  return null
}

export async function getWorkbenchSession(): Promise<unknown> {
  return fetchJson('/session')
}

export async function getWorkbenchConfig(configKey: string): Promise<unknown> {
  return fetchJson(`/config/${encodeURIComponent(configKey)}`)
}

export async function listWorkbenchChats(params?: {
  page?: number
  includePinned?: boolean
  includeFolders?: boolean
}): Promise<WorkbenchChatItem[]> {
  const qs = buildQuery({
    page: params?.page,
    include_pinned: params?.includePinned,
    include_folders: params?.includeFolders,
  })
  const payload = await fetchJson(`/chats/list${qs}`)
  if (!Array.isArray(payload)) return []
  return payload.map(normalizeOneChat).filter((x): x is WorkbenchChatItem => x !== null)
}

export async function searchWorkbenchChats(text: string, page?: number): Promise<WorkbenchChatItem[]> {
  const q = text.trim()
  if (!q) return []
  const qs = buildQuery({ text: q, page })
  const payload = await fetchJson(`/chats/search${qs}`)
  if (!Array.isArray(payload)) return []
  return payload.map(normalizeOneChat).filter((x): x is WorkbenchChatItem => x !== null)
}

export async function toggleChatPin(chatId: string): Promise<void> {
  await fetchJson(`/chats/${encodeURIComponent(chatId)}/pin`, { method: 'POST' })
}

export async function toggleChatArchive(chatId: string): Promise<void> {
  await fetchJson(`/chats/${encodeURIComponent(chatId)}/archive`, { method: 'POST' })
}

export async function renamePersistedAiChat(chatId: string, title: string): Promise<void> {
  const normalizedChatId = String(chatId).trim()
  const nextTitle = title.trim()
  if (!normalizedChatId || !nextTitle) {
    throw new Error('会话标题不能为空')
  }
  const res = await fetch(`${midAuthOrigin}/me/ai/chats/${encodeURIComponent(normalizedChatId)}`, {
    method: 'PATCH',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ title: nextTitle }),
  })
  await throwIfNotOk(res)
}

export async function deletePersistedAiChat(chatId: string): Promise<void> {
  const normalizedChatId = String(chatId).trim()
  if (!normalizedChatId) return
  const res = await fetch(`${midAuthOrigin}/me/ai/chats/${encodeURIComponent(normalizedChatId)}`, {
    method: 'DELETE',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  await throwIfNotOk(res)
}

export async function listChatTags(chatId: string): Promise<WorkbenchTagItem[]> {
  const payload = await fetchJson(`/chats/${encodeURIComponent(chatId)}/tags`)
  if (!Array.isArray(payload)) return []
  return payload.map(normalizeOneTag).filter((x): x is WorkbenchTagItem => x !== null)
}

export async function addChatTag(chatId: string, name: string): Promise<WorkbenchTagItem[]> {
  const payload = await fetchJson(`/chats/${encodeURIComponent(chatId)}/tags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  })
  if (!Array.isArray(payload)) return []
  return payload.map(normalizeOneTag).filter((x): x is WorkbenchTagItem => x !== null)
}

export async function clearChatTags(chatId: string): Promise<void> {
  await fetchJson(`/chats/${encodeURIComponent(chatId)}/tags/all`, { method: 'DELETE' })
}

export async function listWorkbenchPrompts(): Promise<WorkbenchPromptItem[]> {
  const payload = await fetchJson('/prompts')
  return normalizePrompts(payload)
}

export async function listWorkbenchTools(): Promise<WorkbenchToolItem[]> {
  const payload = await fetchJson('/tools')
  return normalizeTools(payload)
}

export async function getWorkbenchToolValves(toolId: string): Promise<unknown> {
  return fetchJson(`/tools/${encodeURIComponent(toolId)}/valves`)
}

export async function updateWorkbenchToolValves(toolId: string, valves: Record<string, unknown>): Promise<unknown> {
  return fetchJson(`/tools/${encodeURIComponent(toolId)}/valves`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(valves),
  })
}

export async function listWorkbenchMemories(): Promise<WorkbenchMemoryItem[]> {
  const payload = await fetchJson('/memories')
  return normalizeMemories(payload)
}

export async function createWorkbenchMemory(body: string): Promise<WorkbenchMemoryItem | null> {
  const payload = await fetchJson('/memories', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  return normalizeMemories([payload])[0] ?? null
}

export async function queryWorkbenchMemories(body: string, limit?: number): Promise<WorkbenchMemoryItem[]> {
  const payload = await fetchJson('/memories/query', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body, ...(limit ? { limit } : {}) }),
  })
  return normalizeMemories(payload)
}

export async function listWorkbenchFolders(): Promise<WorkbenchFolderItem[]> {
  const payload = await fetchJson('/folders')
  return normalizeFolders(payload)
}

export async function createWorkbenchFolder(name: string, parentId?: string | null): Promise<WorkbenchFolderItem | null> {
  const payload = await fetchJson('/folders', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, ...(parentId ? { parent_id: parentId } : {}) }),
  })
  return normalizeFolders([payload])[0] ?? null
}

export async function listWorkbenchNotes(page?: number): Promise<unknown[]> {
  const qs = buildQuery({ page })
  const payload = await fetchJson(`/notes${qs}`)
  return Array.isArray(payload) ? payload : []
}

export async function listWorkbenchSkills(): Promise<unknown[]> {
  const payload = await fetchJson('/skills')
  return Array.isArray(payload) ? payload : []
}

export async function listWorkbenchFunctions(): Promise<unknown[]> {
  const payload = await fetchJson('/functions')
  return Array.isArray(payload) ? payload : []
}

function extractChatCompletionText(json: unknown): string {
  if (!json || typeof json !== 'object') return ''
  const choices = (json as { choices?: unknown }).choices
  if (!Array.isArray(choices) || choices.length === 0) return ''
  const first = choices[0] as { message?: { content?: unknown } }
  const content = first?.message?.content
  if (typeof content === 'string') return content
  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (part && typeof part === 'object') {
          const p = part as Record<string, unknown>
          if (typeof p.text === 'string') return p.text
          if (typeof p.content === 'string') return p.content
        }
        return ''
      })
      .join('')
  }
  if (content != null) return String(content)
  return ''
}

function extractTextLike(value: unknown): string {
  if (typeof value === 'string') return value
  if (Array.isArray(value)) {
    return value
      .map((part) => {
        const p = asRecord(part)
        if (!p) return ''
        if (typeof p.text === 'string') return p.text
        if (typeof p.content === 'string') return p.content
        if (typeof p.reasoning === 'string') return p.reasoning
        if (typeof p.reasoning_content === 'string') return p.reasoning_content
        return ''
      })
      .join('')
  }
  if (value != null) return String(value)
  return ''
}

function extractChatCompletionReasoning(json: unknown): string {
  if (!json || typeof json !== 'object') return ''
  const choices = (json as { choices?: unknown }).choices
  if (!Array.isArray(choices) || choices.length === 0) return ''
  const first = choices[0] as {
    delta?: {
      reasoning?: unknown
      reasoning_content?: unknown
      reasoning_content_text?: unknown
      thinking?: unknown
    }
    message?: {
      reasoning?: unknown
      reasoning_content?: unknown
      reasoning_content_text?: unknown
      thinking?: unknown
    }
  }
  return (
    extractTextLike(first.delta?.reasoning_content) ||
    extractTextLike(first.delta?.reasoning) ||
    extractTextLike(first.delta?.reasoning_content_text) ||
    extractTextLike(first.delta?.thinking) ||
    extractTextLike(first.message?.reasoning_content) ||
    extractTextLike(first.message?.reasoning) ||
    extractTextLike(first.message?.reasoning_content_text) ||
    extractTextLike(first.message?.thinking) ||
    ''
  )
}

function extractChatCompletionDelta(json: unknown): ChatCompletionOutput {
  if (!json || typeof json !== 'object') return { content: '', reasoning: '' }
  const choices = (json as { choices?: unknown }).choices
  if (!Array.isArray(choices) || choices.length === 0) return { content: '', reasoning: '' }
  const first = choices[0] as {
    delta?: { content?: unknown }
    message?: { content?: unknown }
  }
  const deltaContent = first.delta?.content
  const content = extractTextLike(deltaContent) || extractTextLike(first.message?.content)
  const reasoning = extractChatCompletionReasoning(json)
  return { content, reasoning }
}

export async function postChatCompletionNonStreamDetailed(
  model: string,
  messages: ChatMessagePayload[],
): Promise<ChatCompletionOutput> {
  const res = await fetch(`${midAuthWorkbenchBase}/chat/completions`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ model, messages, stream: false }),
  })
  await throwIfNotOk(res)
  const json: unknown = await res.json()
  return {
    content: extractChatCompletionText(json),
    reasoning: extractChatCompletionReasoning(json),
  }
}

export async function postChatCompletionNonStream(
  model: string,
  messages: ChatMessagePayload[],
): Promise<string> {
  const out = await postChatCompletionNonStreamDetailed(model, messages)
  return out.content
}

export async function postChatCompletionStream(
  model: string,
  messages: ChatMessagePayload[],
  handlers?: {
    onToken?: (token: string, aggregate: string) => void
    onReasoningToken?: (token: string, aggregate: string) => void
    signal?: AbortSignal
  },
): Promise<string> {
  const res = await fetch(`${midAuthWorkbenchBase}/chat/completions`, {
    method: 'POST',
    credentials: 'include',
    signal: handlers?.signal,
    headers: {
      Accept: 'text/event-stream, application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ model, messages, stream: true }),
  })
  await throwIfNotOk(res)

  const contentType = res.headers.get('content-type') ?? ''
  if (!contentType.includes('text/event-stream') || !res.body) {
    const json: unknown = await res.json()
    const full = extractChatCompletionText(json)
    const fullReasoning = extractChatCompletionReasoning(json)
    if (fullReasoning) handlers?.onReasoningToken?.(fullReasoning, fullReasoning)
    if (full) handlers?.onToken?.(full, full)
    return full
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let aggregate = ''
  let aggregateReasoning = ''
  let buf = ''

  const emitData = (data: string): boolean => {
    const trimmed = data.trim()
    if (!trimmed) return false
    if (trimmed === '[DONE]') return true
    try {
      const parsed = JSON.parse(trimmed) as unknown
      const { content, reasoning } = extractChatCompletionDelta(parsed)
      if (reasoning) {
        aggregateReasoning += reasoning
        handlers?.onReasoningToken?.(reasoning, aggregateReasoning)
      }
      if (content) {
        aggregate += content
        handlers?.onToken?.(content, aggregate)
      }
    } catch {
      // Ignore malformed SSE chunk and continue stream reading.
    }
    return false
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const shouldStop = emitData(line.slice(5))
      if (shouldStop) return aggregate
    }
  }

  if (buf.startsWith('data:')) {
    emitData(buf.slice(5))
  }
  return aggregate
}

/**
 * 持久化聊天回合（写入 OpenWebUI chat tree）
 * - chatId 为空时：创建新会话并发送首条消息
 * - chatId 存在时：向现有会话追加用户消息
 */
export async function runPersistedAiChatTurn(
  body: string,
  model: string,
  chatId?: string | null,
): Promise<AiChatTurnResult> {
  const content = body.trim()
  if (!content) {
    throw new Error('消息不能为空')
  }

  if (!chatId) {
    const res = await fetch(`${midAuthOrigin}/me/ai/chats`, {
      method: 'POST',
      credentials: 'include',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ body: content, model: model.trim() || undefined }),
    })
    await throwIfNotOk(res)
    const data = (await res.json()) as {
      chat?: { id?: unknown }
      assistant_message?: { body?: unknown }
    }
    const createdId = String(data?.chat?.id ?? '').trim()
    if (!createdId) throw new Error('创建会话失败：未返回 chat id')
    return {
      chatId: createdId,
      assistantText: String(data?.assistant_message?.body ?? '').trim(),
    }
  }

  const normalizedChatId = String(chatId).trim()
  const res = await fetch(`${midAuthOrigin}/me/ai/chats/${encodeURIComponent(normalizedChatId)}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ body: content, model: model.trim() || undefined }),
  })
  await throwIfNotOk(res)
  const data = (await res.json()) as { body?: unknown }
  return {
    chatId: normalizedChatId,
    assistantText: String(data?.body ?? '').trim(),
  }
}

export async function runPersistedAiChatTurnStream(
  body: string,
  model: string,
  chatId?: string | null,
  handlers?: {
    onToken?: (token: string, aggregate: string) => void
    onReasoningToken?: (token: string, aggregate: string) => void
    onChatId?: (chatId: string) => void
    signal?: AbortSignal
  },
): Promise<AiChatTurnResult> {
  const content = body.trim()
  if (!content) {
    throw new Error('消息不能为空')
  }
  const normalizedChatId = String(chatId ?? '').trim()
  const isCreate = !normalizedChatId
  const endpoint = isCreate
    ? `${midAuthOrigin}/me/ai/chats`
    : `${midAuthOrigin}/me/ai/chats/${encodeURIComponent(normalizedChatId)}/messages`
  const res = await fetch(endpoint, {
    method: 'POST',
    credentials: 'include',
    signal: handlers?.signal,
    headers: {
      Accept: 'text/event-stream, application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      body: content,
      model: model.trim() || undefined,
      stream: true,
    }),
  })
  await throwIfNotOk(res)

  let resolvedChatId = normalizedChatId
  const contentType = res.headers.get('content-type') ?? ''
  if (!contentType.includes('text/event-stream') || !res.body) {
    const json = (await res.json()) as {
      chat?: { id?: unknown }
      assistant_message?: { body?: unknown }
      body?: unknown
    }
    const cid = String(json?.chat?.id ?? '').trim()
    if (cid) {
      resolvedChatId = cid
      handlers?.onChatId?.(cid)
    }
    const full = String(json?.assistant_message?.body ?? json?.body ?? '').trim()
    if (full) handlers?.onToken?.(full, full)
    if (!resolvedChatId) throw new Error('创建会话失败：未返回 chat id')
    return { chatId: resolvedChatId, assistantText: full }
  }

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let aggregate = ''
  let aggregateReasoning = ''
  let buf = ''

  const emitData = (data: string): boolean => {
    const trimmed = data.trim()
    if (!trimmed) return false
    if (trimmed === '[DONE]') return true
    try {
      const parsed = JSON.parse(trimmed) as Record<string, unknown>
      const eventType = String(parsed.type ?? '').trim()
      if (eventType === 'chat.meta') {
        const cid = String(parsed.chat_id ?? '').trim()
        if (cid) {
          resolvedChatId = cid
          handlers?.onChatId?.(cid)
        }
        return false
      }
      const err = String(parsed.error ?? '').trim()
      if (err) throw new Error(err)
      const { content: delta, reasoning } = extractChatCompletionDelta(parsed)
      if (reasoning) {
        aggregateReasoning += reasoning
        handlers?.onReasoningToken?.(reasoning, aggregateReasoning)
      }
      if (delta) {
        aggregate += delta
        handlers?.onToken?.(delta, aggregate)
      }
    } catch (e) {
      if (e instanceof Error && e.message) throw e
      // Ignore malformed chunk and continue reading.
    }
    return false
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    const lines = buf.split('\n')
    buf = lines.pop() ?? ''
    for (const line of lines) {
      if (!line.startsWith('data:')) continue
      const shouldStop = emitData(line.slice(5))
      if (shouldStop) {
        if (!resolvedChatId) throw new Error('创建会话失败：未返回 chat id')
        return { chatId: resolvedChatId, assistantText: aggregate }
      }
    }
  }

  if (buf.startsWith('data:')) {
    emitData(buf.slice(5))
  }
  if (!resolvedChatId) throw new Error('创建会话失败：未返回 chat id')
  return { chatId: resolvedChatId, assistantText: aggregate }
}

/** 从持久化会话读取完整消息列表（用于历史会话回显） */
export async function listPersistedAiChatMessages(chatId: string): Promise<AiChatMessageItem[]> {
  const normalizedChatId = String(chatId).trim()
  if (!normalizedChatId) return []
  const res = await fetch(`${midAuthOrigin}/me/ai/chats/${encodeURIComponent(normalizedChatId)}/messages`, {
    method: 'GET',
    credentials: 'include',
    headers: { Accept: 'application/json' },
  })
  await throwIfNotOk(res)
  const data = (await res.json()) as { items?: Array<Record<string, unknown>> }
  const rows = Array.isArray(data?.items) ? data.items : []
  return rows
    .map((row) => {
      const id = String(row.id ?? '').trim()
      const roleRaw = String(row.role ?? '').trim()
      const role: 'user' | 'assistant' | 'system' =
        roleRaw === 'assistant' || roleRaw === 'system' ? roleRaw : 'user'
      const body = String(row.body ?? '').trim()
      const reasoning = String(row.reasoning ?? '').trim()
      if (!id) return null
      const item: AiChatMessageItem = { id, role, body }
      if (reasoning) item.reasoning = reasoning
      return item
    })
    .filter((x): x is AiChatMessageItem => x !== null)
}
