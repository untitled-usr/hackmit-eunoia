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

function asRecord(v: unknown): JsonRecord | null {
  return v && typeof v === 'object' ? (v as JsonRecord) : null
}

function normalizeMidAuthUrl(raw: unknown): string | undefined {
  if (raw == null) return undefined
  const v = String(raw).trim()
  if (!v) return undefined
  if (/^https?:\/\//i.test(v)) return v
  if (v.startsWith('/')) return `${midAuthOrigin}${v}`
  return `${midAuthOrigin}/${v}`
}

export type SocialContactItem = {
  targetPublicId: string
  conversationId: string
  displayName: string
  avatarUrl?: string
  remark: string
  status: string
}

export type ConversationItem = {
  id: string
  peerDisplayName: string
  peerPublicId: string | null
}

export type ConversationMessageItem = {
  id: string
  body: string
  senderId: string
  createdAt: string
  kind: 'text' | 'file'
  attachment?: {
    filename?: string
    contentType?: string
    size?: number
    filePath?: string
  }
}

export type FriendRequestItem = {
  id: string
  message: string
  status: string
  createdAt: string
  requesterVoceUid?: string
  receiverVoceUid?: string
  requester?: SocialUserIdentity
  receiver?: SocialUserIdentity
}

export type FriendRequestRecordItem = FriendRequestItem & {
  respondedAt: string
  canDelete: boolean
}

export type SocialUserIdentity = {
  publicId: string
  username: string
  email: string
  displayName: string
}

export type DirectoryUserItem = SocialUserIdentity

export type BlacklistUserItem = {
  voceUid: string
  name: string
  targetPublicId?: string
  displayName?: string
  avatarUrl?: string
}

function normalizeContacts(payload: unknown): SocialContactItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const contactInfo = asRecord(o.contact_info)
      const targetPublicId = String(o.target_public_id ?? '').trim()
      if (!targetPublicId) return null
      return {
        targetPublicId,
        conversationId: String(o.conversation_id ?? ''),
        displayName: String(o.display_name ?? targetPublicId),
        avatarUrl: normalizeMidAuthUrl(o.avatar_url),
        remark: String(contactInfo?.remark ?? ''),
        status: String(contactInfo?.status ?? ''),
      } as SocialContactItem
    })
    .filter((x): x is SocialContactItem => x !== null)
}

function normalizeConversations(payload: unknown): ConversationItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const id = String(o.id ?? '').trim()
      if (!id) return null
      return {
        id,
        peerDisplayName: String(o.peer_display_name ?? id),
        peerPublicId: o.peer_public_id == null ? null : String(o.peer_public_id),
      } as ConversationItem
    })
    .filter((x): x is ConversationItem => x !== null)
}

function normalizeMessages(payload: unknown): ConversationMessageItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const id = String(o.id ?? '').trim()
      if (!id) return null
      return {
        id,
        body: String(o.body ?? ''),
        senderId: String(o.sender_id ?? ''),
        createdAt: String(o.created_at ?? ''),
        kind: String(o.kind ?? 'text') === 'file' ? 'file' : 'text',
        attachment: (() => {
          const att = asRecord(o.attachment)
          if (!att) return undefined
          return {
            filename: att.filename == null ? undefined : String(att.filename),
            contentType: att.content_type == null ? undefined : String(att.content_type),
            size: att.size == null ? undefined : Number(att.size),
            filePath: att.file_path == null ? undefined : String(att.file_path),
          }
        })(),
      } as ConversationMessageItem
    })
    .filter((x): x is ConversationMessageItem => x !== null)
}

function normalizeFriendRequests(payload: unknown): FriendRequestItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const id = String(o.id ?? '').trim()
      if (!id) return null
      return {
        id,
        message: String(o.message ?? ''),
        status: String(o.status ?? ''),
        createdAt: String(o.created_at ?? ''),
        requesterVoceUid: o.requester_voce_uid == null ? undefined : String(o.requester_voce_uid),
        receiverVoceUid: o.receiver_voce_uid == null ? undefined : String(o.receiver_voce_uid),
        requester: normalizeIdentity(o.requester),
        receiver: normalizeIdentity(o.receiver),
      } as FriendRequestItem
    })
    .filter((x): x is FriendRequestItem => x !== null)
}

function normalizeFriendRequestRecords(payload: unknown): FriendRequestRecordItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const id = String(o.id ?? '').trim()
      if (!id) return null
      return {
        id,
        message: String(o.message ?? ''),
        status: String(o.status ?? ''),
        createdAt: String(o.created_at ?? ''),
        requesterVoceUid: o.requester_voce_uid == null ? undefined : String(o.requester_voce_uid),
        receiverVoceUid: o.receiver_voce_uid == null ? undefined : String(o.receiver_voce_uid),
        requester: normalizeIdentity(o.requester),
        receiver: normalizeIdentity(o.receiver),
        respondedAt: String(o.responded_at ?? ''),
        canDelete: Boolean(o.can_delete ?? false),
      } as FriendRequestRecordItem
    })
    .filter((x): x is FriendRequestRecordItem => x !== null)
}

function normalizeIdentity(payload: unknown): SocialUserIdentity | undefined {
  const o = asRecord(payload)
  if (!o) return undefined
  const publicId = String(o.public_id ?? '').trim()
  const username = String(o.username ?? '').trim()
  const email = String(o.email ?? '').trim()
  if (!publicId && !username && !email) return undefined
  const displayName = String(o.display_name ?? username ?? publicId)
  return { publicId, username, email, displayName }
}

function normalizeDirectoryUsers(payload: unknown): DirectoryUserItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => normalizeIdentity(item))
    .filter((x): x is DirectoryUserItem => x !== undefined)
}

function normalizeBlacklistUsers(payload: unknown): BlacklistUserItem[] {
  const root = asRecord(payload)
  const items = Array.isArray(root?.items) ? root.items : []
  return items
    .map((item) => {
      const o = asRecord(item)
      if (!o) return null
      const voceUid = String(o.voce_uid ?? '').trim()
      if (!voceUid) return null
      return {
        voceUid,
        name: String(o.name ?? ''),
        targetPublicId: o.target_public_id == null ? undefined : String(o.target_public_id),
        displayName: o.display_name == null ? undefined : String(o.display_name),
        avatarUrl: normalizeMidAuthUrl(o.avatar_url),
      } as BlacklistUserItem
    })
    .filter((x): x is BlacklistUserItem => x !== null)
}

export async function listSocialContacts(): Promise<SocialContactItem[]> {
  return normalizeContacts(await fetchJson('/me/social/contacts'))
}

export async function listConversations(): Promise<ConversationItem[]> {
  return normalizeConversations(await fetchJson('/me/conversations'))
}

export async function listConversationMessages(
  conversationId: string,
  opts?: { limit?: number; beforeMessageId?: string },
): Promise<ConversationMessageItem[]> {
  const q = new URLSearchParams()
  if (opts?.limit) q.set('limit', String(opts.limit))
  if (opts?.beforeMessageId) q.set('before_message_id', String(opts.beforeMessageId))
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return normalizeMessages(await fetchJson(`/me/conversations/${encodeURIComponent(conversationId)}/messages${suffix}`))
}

export async function sendConversationMessage(
  conversationId: string,
  body: string,
): Promise<ConversationMessageItem | null> {
  const payload = await fetchJson(`/me/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ body }),
  })
  const list = normalizeMessages({ items: [payload] })
  return list[0] ?? null
}

export async function sendConversationFile(
  conversationId: string,
  file: File,
): Promise<ConversationMessageItem | null> {
  const body = new FormData()
  body.append('file', file)
  const res = await fetch(`${midAuthOrigin}/me/conversations/${encodeURIComponent(conversationId)}/messages`, {
    method: 'POST',
    credentials: 'include',
    headers: { Accept: 'application/json' },
    body,
  })
  await throwIfNotOk(res)
  const payload = (await res.json()) as unknown
  const list = normalizeMessages({ items: [payload] })
  return list[0] ?? null
}

export async function startDirectConversation(
  targetPublicId: string,
  body: string,
): Promise<{ conversation: ConversationItem; message: ConversationMessageItem | null }> {
  const payload = await fetchJson('/me/conversations', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_public_id: targetPublicId, body }),
  })
  const root = asRecord(payload)
  const conversation = normalizeConversations({ items: [root?.conversation] })[0]
  if (!conversation) throw new MidAuthHttpError('创建会话失败：后端返回异常', 500)
  const message = normalizeMessages({ items: [root?.message] })[0] ?? null
  return { conversation, message }
}

export async function pinConversationByPeer(targetPublicId: string): Promise<void> {
  await fetchJson('/me/conversations/pin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_public_id: targetPublicId }),
  })
}

export async function unpinConversationByPeer(targetPublicId: string): Promise<void> {
  await fetchJson('/me/conversations/unpin', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_public_id: targetPublicId }),
  })
}

export async function deleteConversationMessage(
  conversationId: string,
  messageId: string,
): Promise<void> {
  await fetchJson(
    `/me/conversations/${encodeURIComponent(conversationId)}/messages/${encodeURIComponent(messageId)}`,
    { method: 'DELETE' },
  )
}

export async function listIncomingFriendRequests(): Promise<FriendRequestItem[]> {
  return normalizeFriendRequests(await fetchJson('/me/social/friend-requests/incoming'))
}

export async function listOutgoingFriendRequests(): Promise<FriendRequestItem[]> {
  return normalizeFriendRequests(await fetchJson('/me/social/friend-requests/outgoing'))
}

export async function listFriendRequestRecords(): Promise<FriendRequestRecordItem[]> {
  return normalizeFriendRequestRecords(await fetchJson('/me/social/friend-requests/records'))
}

export async function acceptFriendRequest(requestId: string): Promise<void> {
  await fetchJson(`/me/social/friend-requests/${encodeURIComponent(requestId)}/accept`, {
    method: 'POST',
  })
}

export async function rejectFriendRequest(requestId: string): Promise<void> {
  await fetchJson(`/me/social/friend-requests/${encodeURIComponent(requestId)}/reject`, {
    method: 'POST',
  })
}

export async function cancelFriendRequest(requestId: string): Promise<void> {
  await fetchJson(`/me/social/friend-requests/${encodeURIComponent(requestId)}/cancel`, {
    method: 'POST',
  })
}

export async function searchDirectoryUsers(
  keyword: string,
  limit = 20,
): Promise<DirectoryUserItem[]> {
  const q = keyword.trim()
  if (!q) return []
  return normalizeDirectoryUsers(
    await fetchJson('/me/directory/users/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: q, limit }),
    }),
  )
}

export async function createFriendRequestByIdentifier(
  targetIdentifier: string,
  message = '',
): Promise<void> {
  const v = targetIdentifier.trim()
  if (!v) throw new MidAuthHttpError('目标用户不能为空', 422)
  await fetchJson('/me/social/friend-requests', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_identifier: v, message }),
  })
}

export async function removeFriendByPublicId(targetPublicId: string): Promise<void> {
  await fetchJson(`/me/social/friends/${encodeURIComponent(targetPublicId)}`, {
    method: 'DELETE',
  })
}

export async function listBlacklistUsers(): Promise<BlacklistUserItem[]> {
  return normalizeBlacklistUsers(await fetchJson('/me/social/blacklist'))
}

export async function addBlacklistByPublicId(targetPublicId: string): Promise<void> {
  await fetchJson('/me/social/blacklist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_public_id: targetPublicId }),
  })
}

export async function removeBlacklistByPublicId(targetPublicId: string): Promise<void> {
  await fetchJson(`/me/social/blacklist/${encodeURIComponent(targetPublicId)}`, {
    method: 'DELETE',
  })
}

export function openChatEventsStream(opts?: {
  afterMid?: number
  usersVersion?: number
}): EventSource {
  const q = new URLSearchParams()
  if (typeof opts?.afterMid === 'number') q.set('after_mid', String(opts.afterMid))
  if (typeof opts?.usersVersion === 'number') q.set('users_version', String(opts.usersVersion))
  const suffix = q.toString() ? `?${q.toString()}` : ''
  return new EventSource(`${midAuthOrigin}/me/im/events${suffix}`, { withCredentials: true })
}

export function buildChatResourceFileUrl(filePath: string, opts?: { download?: boolean; thumbnail?: boolean }): string {
  const q = new URLSearchParams()
  q.set('file_path', filePath)
  if (opts?.download) q.set('download', 'true')
  if (opts?.thumbnail) q.set('thumbnail', 'true')
  return `${midAuthOrigin}/me/im/resources/file?${q.toString()}`
}

