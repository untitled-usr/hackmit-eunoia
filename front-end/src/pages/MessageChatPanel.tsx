import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from '../context/useAuth'
import { MidAuthHttpError } from '../lib/midAuth'
import {
  addBlacklistByPublicId,
  type ConversationItem,
  createFriendRequestByIdentifier,
  deleteConversationMessage,
  type DirectoryUserItem,
  buildChatResourceFileUrl,
  listBlacklistUsers,
  listConversations,
  listConversationMessages,
  listSocialContacts,
  openChatEventsStream,
  pinConversationByPeer,
  removeBlacklistByPublicId,
  removeFriendByPublicId,
  sendConversationMessage,
  sendConversationFile,
  startDirectConversation,
  unpinConversationByPeer,
  searchDirectoryUsers,
  type BlacklistUserItem,
  type ConversationMessageItem,
  type SocialContactItem,
} from '../lib/midAuthSocialChat'

function inferDisplayName(contact: SocialContactItem): string {
  return contact.remark.trim() || contact.displayName.trim() || contact.targetPublicId
}

type ChatMessageViewItem = ConversationMessageItem & {
  localObjectUrl?: string
  localFileName?: string
  localMimeType?: string
}

type CachedFileMeta = {
  filePath: string
  filename?: string
  contentType?: string
}

type CachedImagePreviewMap = Record<string, string>

function looksLikeStoragePath(value: string): boolean {
  return /^\d{4}\/\d{1,2}\/\d{1,2}\/[0-9a-f-]{16,}$/i.test(value.trim())
}

function inferAttachmentFromBody(body: string): {
  filePath?: string
  filename?: string
  contentType?: string
} {
  const raw = body.trim()
  if (!raw) return {}
  if (looksLikeStoragePath(raw)) return { filePath: raw }
  try {
    const parsed = JSON.parse(raw) as unknown
    if (!parsed || typeof parsed !== 'object') return {}
    const row = parsed as Record<string, unknown>
    const content =
      row.content && typeof row.content === 'object'
        ? (row.content as Record<string, unknown>)
        : null
    const properties =
      row.properties && typeof row.properties === 'object'
        ? (row.properties as Record<string, unknown>)
        : null
    const fp =
      String(
        row.path ??
          row.file_path ??
          content?.path ??
          content?.file_path ??
          properties?.path ??
          properties?.file_path ??
          '',
      ).trim() || undefined
    if (!fp || !looksLikeStoragePath(fp)) return {}
    const filename = String(
      row.name ?? row.filename ?? content?.name ?? content?.filename ?? properties?.name ?? '',
    ).trim()
    const contentType = String(
      row.content_type ??
        row.mime_type ??
        content?.content_type ??
        content?.mime_type ??
        properties?.content_type ??
        '',
    ).trim()
    return {
      filePath: fp,
      filename: filename || undefined,
      contentType: contentType || undefined,
    }
  } catch {
    return {}
  }
}

export function MessageChatPanel() {
  const isImageLike = useCallback((mime?: string, name?: string): boolean => {
    const m = (mime || '').toLowerCase()
    if (m.startsWith('image/')) return true
    const n = (name || '').toLowerCase()
    return /\.(png|jpe?g|gif|webp|bmp|svg|heic|heif)$/.test(n)
  }, [])

  const { user, loading, openLoginModal } = useAuth()
  const [friends, setFriends] = useState<SocialContactItem[]>([])
  const [conversations, setConversations] = useState<ConversationItem[]>([])
  const [friendsLoading, setFriendsLoading] = useState(false)
  const [friendsError, setFriendsError] = useState<string | null>(null)
  const [friendQuery, setFriendQuery] = useState('')
  const [listView, setListView] = useState<'chats' | 'friends' | null>('chats')
  const [selectedFriendId, setSelectedFriendId] = useState<string | null>(null)
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessageViewItem[]>([])
  const [messagesLoading, setMessagesLoading] = useState(false)
  const [messagesError, setMessagesError] = useState<string | null>(null)
  const [composerText, setComposerText] = useState('')
  const [sending, setSending] = useState(false)
  const [pinnedPeers, setPinnedPeers] = useState<Record<string, boolean>>({})
  const [blacklistMap, setBlacklistMap] = useState<Record<string, boolean>>({})
  const [hint, setHint] = useState<string | null>(null)
  const [friendInfo, setFriendInfo] = useState<SocialContactItem | null>(null)
  const [contextMenu, setContextMenu] = useState<{
    x: number
    y: number
    friend: SocialContactItem
  } | null>(null)
  const [addFriendOpen, setAddFriendOpen] = useState(false)
  const [addQuery, setAddQuery] = useState('')
  const [addMessage, setAddMessage] = useState('')
  const [addTarget, setAddTarget] = useState<DirectoryUserItem | null>(null)
  const [addResults, setAddResults] = useState<DirectoryUserItem[]>([])
  const [addLoading, setAddLoading] = useState(false)
  const [fileMetaMap, setFileMetaMap] = useState<Record<string, CachedFileMeta>>({})
  const [imagePreviewMap, setImagePreviewMap] = useState<CachedImagePreviewMap>({})
  const selectedConversationIdRef = useRef<string | null>(null)
  const streamRefreshTimerRef = useRef<number | null>(null)
  const lastSidebarRefreshAtRef = useRef<number>(0)
  const lastMessageRefreshAtRef = useRef<number>(0)
  const composerFocusedRef = useRef(false)
  const composerHeightRef = useRef<number>(40)
  const composerRef = useRef<HTMLTextAreaElement | null>(null)
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const createdObjectUrlsRef = useRef<string[]>([])
  const previewLoadingRef = useRef<Set<string>>(new Set())
  const [sendingFile, setSendingFile] = useState(false)
  const [lightboxSrc, setLightboxSrc] = useState<string | null>(null)
  const [lightboxLoading, setLightboxLoading] = useState(false)
  const lightboxObjectUrlRef = useRef<string | null>(null)

  const fileMetaStorageKey = useMemo(
    () => `eunoia.chat.filemeta.${user?.id ?? 'anon'}`,
    [user?.id],
  )
  const imagePreviewStorageKey = useMemo(
    () => `eunoia.chat.imagepreview.${user?.id ?? 'anon'}`,
    [user?.id],
  )

  const sameContacts = useCallback((a: SocialContactItem[], b: SocialContactItem[]) => {
    if (a.length !== b.length) return false
    for (let i = 0; i < a.length; i += 1) {
      const x = a[i]
      const y = b[i]
      if (
        !x ||
        !y ||
        x.targetPublicId !== y.targetPublicId ||
        x.conversationId !== y.conversationId ||
        x.displayName !== y.displayName ||
        x.avatarUrl !== y.avatarUrl ||
        x.remark !== y.remark ||
        x.status !== y.status
      ) {
        return false
      }
    }
    return true
  }, [])

  const sameConversations = useCallback((a: ConversationItem[], b: ConversationItem[]) => {
    if (a.length !== b.length) return false
    for (let i = 0; i < a.length; i += 1) {
      const x = a[i]
      const y = b[i]
      if (
        !x ||
        !y ||
        x.id !== y.id ||
        x.peerDisplayName !== y.peerDisplayName ||
        x.peerPublicId !== y.peerPublicId
      ) {
        return false
      }
    }
    return true
  }, [])

  const syncComposerHeight = useCallback(() => {
    const el = composerRef.current
    if (!el) return
    const maxHeight = 168
    el.style.height = 'auto'
    const next = Math.min(el.scrollHeight, maxHeight)
    const nextHeight = Math.max(next, 40)
    if (composerHeightRef.current !== nextHeight) {
      composerHeightRef.current = nextHeight
      el.style.height = `${nextHeight}px`
    } else {
      el.style.height = `${nextHeight}px`
    }
    el.style.overflowY = el.scrollHeight > maxHeight ? 'auto' : 'hidden'
  }, [])

  const onToggleListView = useCallback((next: 'chats' | 'friends') => {
    setListView((prev) => (prev === next ? null : next))
  }, [])

  const closeLightbox = useCallback(() => {
    setLightboxLoading(false)
    setLightboxSrc(null)
    if (lightboxObjectUrlRef.current) {
      URL.revokeObjectURL(lightboxObjectUrlRef.current)
      lightboxObjectUrlRef.current = null
    }
  }, [])

  const toChatErrorMessage = useCallback((err: unknown, fallback = '请求失败'): string => {
    if (err instanceof MidAuthHttpError) {
      if (err.status === 401 || err.status === 403) return '登录状态失效，请重新登录'
      if (err.status === 404) return '当前后端未启用聊天能力'
      if (err.status === 503) return '聊天服务暂不可用（503），请稍后重试'
      return err.message
    }
    return err instanceof Error ? err.message : fallback
  }, [])

  const loadFriendsAndConversations = useCallback(async (opts?: { silent?: boolean }) => {
    if (!user) return
    const silent = Boolean(opts?.silent)
    if (!silent) setFriendsLoading(true)
    setFriendsError(null)
    const [contactsRes, conversationsRes] = await Promise.allSettled([
      listSocialContacts(),
      listConversations(),
    ])
    if (contactsRes.status === 'fulfilled') {
      setFriends((prev) => (sameContacts(prev, contactsRes.value) ? prev : contactsRes.value))
    } else {
      setFriends([])
    }
    if (conversationsRes.status === 'fulfilled') {
      setConversations((prev) =>
        sameConversations(prev, conversationsRes.value) ? prev : conversationsRes.value,
      )
    } else {
      setConversations([])
    }
    if (contactsRes.status === 'rejected' && conversationsRes.status === 'rejected') {
      setFriendsError('加载聊天数据失败，请稍后重试')
    } else if (contactsRes.status === 'rejected') {
      setFriendsError(toChatErrorMessage(contactsRes.reason, '加载好友列表失败'))
    } else if (conversationsRes.status === 'rejected') {
      setFriendsError(toChatErrorMessage(conversationsRes.reason, '加载聊天列表失败'))
    }
    if (!silent) setFriendsLoading(false)
  }, [sameContacts, sameConversations, toChatErrorMessage, user])

  const loadBlacklist = useCallback(async () => {
    if (!user) return
    try {
      const rows = await listBlacklistUsers()
      const next: Record<string, boolean> = {}
      rows.forEach((x: BlacklistUserItem) => {
        if (x.targetPublicId) next[x.targetPublicId] = true
      })
      setBlacklistMap(next)
    } catch {
      // non-fatal for chat main flow
    }
  }, [user])

  useEffect(() => {
    if (!user || loading) {
      setFriends([])
      setConversations([])
      setSelectedFriendId(null)
      setSelectedConversationId(null)
      setMessages([])
      setFriendsError(null)
      setMessagesError(null)
      return
    }
    void loadFriendsAndConversations()
    void loadBlacklist()
  }, [user, loading, loadFriendsAndConversations, loadBlacklist])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(fileMetaStorageKey)
      if (!raw) {
        setFileMetaMap({})
        return
      }
      const parsed = JSON.parse(raw) as unknown
      if (!parsed || typeof parsed !== 'object') {
        setFileMetaMap({})
        return
      }
      const next: Record<string, CachedFileMeta> = {}
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (!v || typeof v !== 'object') continue
        const o = v as Record<string, unknown>
        const fp = String(o.filePath ?? '').trim()
        if (!fp) continue
        next[k] = {
          filePath: fp,
          filename: o.filename == null ? undefined : String(o.filename),
          contentType: o.contentType == null ? undefined : String(o.contentType),
        }
      }
      setFileMetaMap(next)
    } catch {
      setFileMetaMap({})
    }
  }, [fileMetaStorageKey])

  useEffect(() => {
    try {
      window.localStorage.setItem(fileMetaStorageKey, JSON.stringify(fileMetaMap))
    } catch {
      // ignore quota / private mode issues
    }
  }, [fileMetaMap, fileMetaStorageKey])

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(imagePreviewStorageKey)
      if (!raw) {
        setImagePreviewMap({})
        return
      }
      const parsed = JSON.parse(raw) as unknown
      if (!parsed || typeof parsed !== 'object') {
        setImagePreviewMap({})
        return
      }
      const next: CachedImagePreviewMap = {}
      for (const [k, v] of Object.entries(parsed as Record<string, unknown>)) {
        if (typeof v !== 'string') continue
        if (!v.startsWith('data:image/')) continue
        next[k] = v
      }
      setImagePreviewMap(next)
    } catch {
      setImagePreviewMap({})
    }
  }, [imagePreviewStorageKey])

  useEffect(() => {
    try {
      window.localStorage.setItem(imagePreviewStorageKey, JSON.stringify(imagePreviewMap))
    } catch {
      // ignore quota / private mode issues
    }
  }, [imagePreviewMap, imagePreviewStorageKey])

  useEffect(() => {
    return () => {
      for (const url of createdObjectUrlsRef.current) {
        URL.revokeObjectURL(url)
      }
      createdObjectUrlsRef.current = []
      previewLoadingRef.current.clear()
      if (lightboxObjectUrlRef.current) {
        URL.revokeObjectURL(lightboxObjectUrlRef.current)
        lightboxObjectUrlRef.current = null
      }
    }
  }, [])

  useEffect(() => {
    for (const msg of messages) {
      if (msg.kind !== 'file') continue
      if (msg.localObjectUrl) continue
      const bodyPath = msg.body && looksLikeStoragePath(msg.body) ? msg.body.trim() : ''
      const filePath = (msg.attachment?.filePath || fileMetaMap[msg.id]?.filePath || bodyPath || '').trim()
      if (!filePath) continue
      const key = `${msg.id}:${filePath}`
      if (previewLoadingRef.current.has(key)) continue
      previewLoadingRef.current.add(key)
      void (async () => {
        try {
          const res = await fetch(buildChatResourceFileUrl(filePath, { thumbnail: true }), {
            credentials: 'include',
          })
          if (!res.ok) return
          const blob = await res.blob()
          const inferredName = msg.attachment?.filename || fileMetaMap[msg.id]?.filename || msg.body || filePath
          const inferredMime = msg.localMimeType || msg.attachment?.contentType || fileMetaMap[msg.id]?.contentType
          const isImageBlob = blob.type.startsWith('image/') || isImageLike(inferredMime, inferredName)
          if (!isImageBlob) return
          const url = URL.createObjectURL(blob)
          createdObjectUrlsRef.current.push(url)
          setMessages((prev) =>
            prev.map((m) =>
              m.id === msg.id
                ? {
                    ...m,
                    localObjectUrl: url,
                    localMimeType: m.localMimeType || blob.type || undefined,
                  }
                : m,
            ),
          )
        } catch {
          // ignore preview prefetch errors, fallback to file tile
        } finally {
          previewLoadingRef.current.delete(key)
        }
      })()
    }
  }, [fileMetaMap, isImageLike, messages])

  useEffect(() => {
    const onClose = () => setContextMenu(null)
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setContextMenu(null)
        closeLightbox()
      }
    }
    window.addEventListener('click', onClose)
    window.addEventListener('keydown', onEsc)
    return () => {
      window.removeEventListener('click', onClose)
      window.removeEventListener('keydown', onEsc)
    }
  }, [closeLightbox])

  const filteredFriends = useMemo(() => {
    const q = friendQuery.trim().toLowerCase()
    if (!q) return friends
    return friends.filter((f) => {
      const name = inferDisplayName(f).toLowerCase()
      return name.includes(q) || f.targetPublicId.toLowerCase().includes(q)
    })
  }, [friends, friendQuery])

  const friendsMap = useMemo(() => {
    const out: Record<string, SocialContactItem> = {}
    for (const x of friends) out[x.targetPublicId] = x
    return out
  }, [friends])

  const filteredConversations = useMemo(() => {
    const q = friendQuery.trim().toLowerCase()
    const rows = conversations.map((c) => {
      const peerPublicId = c.peerPublicId?.trim() || null
      const friend = peerPublicId ? friendsMap[peerPublicId] : undefined
      const displayName =
        friend ? inferDisplayName(friend) : c.peerDisplayName.trim() || peerPublicId || c.id
      return {
        conversation: c,
        peerPublicId,
        displayName,
        avatarUrl: friend?.avatarUrl,
      }
    })
    if (!q) return rows
    return rows.filter((row) => {
      return (
        row.displayName.toLowerCase().includes(q) ||
        row.conversation.id.toLowerCase().includes(q) ||
        (row.peerPublicId ? row.peerPublicId.toLowerCase().includes(q) : false)
      )
    })
  }, [conversations, friendQuery, friendsMap])

  const resolveConversationIdByFriend = useCallback(
    (targetPublicId: string): string | null => {
      const friend = friends.find((x) => x.targetPublicId === targetPublicId)
      if (!friend) return null
      return friend.conversationId || null
    },
    [friends],
  )

  const loadConversationMessages = useCallback(
    async (conversationId: string, opts?: { silent?: boolean }) => {
      if (!user) return
      const silent = Boolean(opts?.silent)
      if (!silent) {
        setMessagesLoading(true)
        setMessagesError(null)
      }
      try {
        const rows = await listConversationMessages(conversationId, { limit: 100 })
        setMessages((prev) => {
          const prevById = new Map(prev.map((m) => [m.id, m]))
          const mergedRows: ChatMessageViewItem[] = rows.map((row) => {
            const cached = fileMetaMap[row.id]
            const prevMsg = prevById.get(row.id)
            const inferred = row.kind === 'file' ? inferAttachmentFromBody(row.body || '') : {}
            const filePath = row.attachment?.filePath || cached?.filePath || inferred.filePath
            const filename = row.attachment?.filename || cached?.filename || inferred.filename
            const contentType =
              row.attachment?.contentType || cached?.contentType || inferred.contentType
            const cachedPreview = imagePreviewMap[row.id]
            const hasValidPath = Boolean(filePath) && looksLikeStoragePath(filePath || '')
            const normalizedKind: 'text' | 'file' = row.kind === 'file' || hasValidPath ? 'file' : 'text'
            return {
              ...row,
              kind: normalizedKind,
              attachment:
                normalizedKind === 'file'
                  ? {
                      ...row.attachment,
                      filePath: filePath || undefined,
                      filename: filename || undefined,
                      contentType: contentType || undefined,
                    }
                  : row.attachment,
              localObjectUrl: prevMsg?.localObjectUrl || cachedPreview,
              localFileName: prevMsg?.localFileName || filename,
              localMimeType: prevMsg?.localMimeType || contentType,
            }
          })
          if (prev.length !== mergedRows.length) return mergedRows
          for (let i = 0; i < mergedRows.length; i += 1) {
            const a = prev[i]
            const b = mergedRows[i]
            if (
              !a ||
              !b ||
              a.id !== b.id ||
              a.body !== b.body ||
              a.senderId !== b.senderId ||
              a.createdAt !== b.createdAt ||
              a.kind !== b.kind ||
              a.attachment?.filePath !== b.attachment?.filePath ||
              a.localObjectUrl !== b.localObjectUrl
            ) {
              return mergedRows
            }
          }
          return prev
        })
      } catch (e) {
        if (!silent) {
          setMessages([])
          setMessagesError(toChatErrorMessage(e, '加载会话消息失败'))
        }
      } finally {
        if (!silent) setMessagesLoading(false)
      }
    },
    [fileMetaMap, imagePreviewMap, toChatErrorMessage, user],
  )

  const onSelectFriend = useCallback(
    async (friend: SocialContactItem) => {
      setSelectedFriendId(friend.targetPublicId)
      const existingConversationId = resolveConversationIdByFriend(friend.targetPublicId)
      setSelectedConversationId(existingConversationId)
      if (existingConversationId) {
        setHint(`已切换到会话：${inferDisplayName(friend)}`)
        await loadConversationMessages(existingConversationId)
      } else {
        setMessages([])
        setMessagesError(null)
        setHint(`已选择好友：${inferDisplayName(friend)}（首次发送将自动创建会话）`)
      }
    },
    [loadConversationMessages, resolveConversationIdByFriend],
  )

  const onSelectConversation = useCallback(
    async (item: ConversationItem) => {
      setSelectedConversationId(item.id)
      setSelectedFriendId(item.peerPublicId ?? null)
      setHint(`已切换到会话：${item.peerDisplayName || item.id}`)
      await loadConversationMessages(item.id)
    },
    [loadConversationMessages],
  )

  const onTogglePinFriend = useCallback(
    async (targetPublicId: string) => {
      try {
        const nextPinned = !Boolean(pinnedPeers[targetPublicId])
        if (nextPinned) await pinConversationByPeer(targetPublicId)
        else await unpinConversationByPeer(targetPublicId)
        setPinnedPeers((prev) => ({ ...prev, [targetPublicId]: nextPinned }))
      } catch (e) {
        setHint(toChatErrorMessage(e, '置顶操作失败'))
      }
    },
    [pinnedPeers, toChatErrorMessage],
  )

  const onToggleBlockFriend = useCallback(
    async (targetPublicId: string) => {
      const blocked = Boolean(blacklistMap[targetPublicId])
      try {
        if (blocked) {
          await removeBlacklistByPublicId(targetPublicId)
          setBlacklistMap((prev) => {
            const next = { ...prev }
            delete next[targetPublicId]
            return next
          })
          setHint('已取消屏蔽')
        } else {
          await addBlacklistByPublicId(targetPublicId)
          setBlacklistMap((prev) => ({ ...prev, [targetPublicId]: true }))
          setHint('已屏蔽该好友')
        }
      } catch (e) {
        setHint(toChatErrorMessage(e, '屏蔽操作失败'))
      }
    },
    [blacklistMap, toChatErrorMessage],
  )

  const onRemoveFriend = useCallback(
    async (targetPublicId: string) => {
      try {
        await removeFriendByPublicId(targetPublicId)
        setHint('已删除好友')
        if (selectedFriendId === targetPublicId) {
          setSelectedFriendId(null)
          setSelectedConversationId(null)
          setMessages([])
        }
        await loadFriendsAndConversations()
      } catch (e) {
        setHint(toChatErrorMessage(e, '删除好友失败'))
      }
    },
    [loadFriendsAndConversations, selectedFriendId, toChatErrorMessage],
  )

  const onClearChatHistory = useCallback(
    async (friend: SocialContactItem) => {
      const conversationId = resolveConversationIdByFriend(friend.targetPublicId)
      if (!conversationId) {
        setHint('该好友暂无聊天记录')
        return
      }
      try {
        let before: string | undefined
        for (let i = 0; i < 50; i += 1) {
          const rows = await listConversationMessages(conversationId, {
            limit: 200,
            beforeMessageId: before,
          })
          if (!rows.length) break
          for (const m of rows) {
            await deleteConversationMessage(conversationId, m.id)
          }
          before = rows[rows.length - 1]?.id
          if (rows.length < 200) break
        }
        if (selectedConversationId === conversationId) {
          await loadConversationMessages(conversationId)
        }
        setHint('聊天记录已清除')
      } catch (e) {
        setHint(toChatErrorMessage(e, '清除聊天记录失败'))
      }
    },
    [
      loadConversationMessages,
      resolveConversationIdByFriend,
      selectedConversationId,
      toChatErrorMessage,
    ],
  )

  const avatarLetter = useCallback((friend: SocialContactItem): string => {
    const label = inferDisplayName(friend).trim()
    if (!label) return '?'
    return label[0]!.toUpperCase()
  }, [])

  const onSend = useCallback(async () => {
    const text = composerText.trim()
    if (!text || sending) return
    if (!selectedConversationId && !selectedFriendId) {
      setHint('请先从左侧选择一个会话或好友')
      return
    }
    setSending(true)
    setHint(null)
    try {
      let conversationId = selectedConversationId
      if (!conversationId) {
        if (!selectedFriendId) {
          setHint('当前会话缺少可用的用户标识，无法发送')
          return
        }
        const created = await startDirectConversation(selectedFriendId, text)
        conversationId = created.conversation.id
        setSelectedConversationId(conversationId)
        if (created.message) {
          setMessages((prev) => [...prev, created.message!])
        } else {
          await loadConversationMessages(conversationId)
        }
      } else {
        const sent = await sendConversationMessage(conversationId, text)
        if (sent) setMessages((prev) => [...prev, sent])
      }
      setComposerText('')
      await loadFriendsAndConversations({ silent: true })
    } catch (e) {
      setHint(toChatErrorMessage(e, '发送消息失败'))
    } finally {
      setSending(false)
    }
  }, [
    composerText,
    loadConversationMessages,
    selectedConversationId,
    selectedFriendId,
    sending,
    loadFriendsAndConversations,
    toChatErrorMessage,
  ])

  const onPickFile = useCallback(() => {
    fileInputRef.current?.click()
  }, [])

  const onSelectFile = useCallback(
    async (file: File | null) => {
      if (!file || sendingFile) return
      if (!selectedConversationId) {
        setHint('请先发送一条文字消息建立会话，再发送文件')
        return
      }
      const localUrl = URL.createObjectURL(file)
      createdObjectUrlsRef.current.push(localUrl)
      const tempId = `local-file-${Date.now()}-${Math.random().toString(16).slice(2)}`
      const tempMessage: ChatMessageViewItem = {
        id: tempId,
        body: file.name,
        senderId: '',
        createdAt: new Date().toISOString(),
        kind: 'file',
        attachment: {
          filename: file.name,
          contentType: file.type || 'application/octet-stream',
          size: file.size,
        },
        localObjectUrl: localUrl,
        localFileName: file.name,
        localMimeType: file.type || 'application/octet-stream',
      }
      setMessages((prev) => [...prev, tempMessage])
      setSendingFile(true)
      let imageDataUrl: string | null = null
      if (isImageLike(file.type, file.name)) {
        try {
          imageDataUrl = await new Promise<string>((resolve, reject) => {
            const reader = new FileReader()
            reader.onload = () => resolve(String(reader.result ?? ''))
            reader.onerror = () => reject(new Error('read-failed'))
            reader.readAsDataURL(file)
          })
        } catch {
          imageDataUrl = null
        }
      }
      try {
        const sent = await sendConversationFile(selectedConversationId, file)
        if (sent) {
          if (imageDataUrl && imageDataUrl.startsWith('data:image/')) {
            setImagePreviewMap((prev) => ({ ...prev, [sent.id]: imageDataUrl! }))
          }
          const sentFilePath = sent.attachment?.filePath?.trim()
          if (sentFilePath) {
            setFileMetaMap((prev) => ({
              ...prev,
              [sent.id]: {
                filePath: sentFilePath,
                filename: sent.attachment?.filename || file.name,
                contentType: sent.attachment?.contentType || file.type || undefined,
              },
            }))
          }
          setMessages((prev) => {
            let replaced = false
            const next = prev.map((m) => {
              if (m.id !== tempId) return m
              replaced = true
              return {
                ...sent,
                localObjectUrl: localUrl,
                localFileName: file.name,
                localMimeType: file.type || 'application/octet-stream',
              }
            })
            if (replaced) return next
            // If a silent refresh removed temp message before upload returns,
            // still append final sent message with local preview data.
            return [
              ...next,
              {
                ...sent,
                localObjectUrl: localUrl,
                localFileName: file.name,
                localMimeType: file.type || 'application/octet-stream',
              },
            ]
          })
        } else {
          setMessages((prev) => prev.filter((m) => m.id !== tempId))
          await loadConversationMessages(selectedConversationId)
        }
        await loadFriendsAndConversations({ silent: true })
      } catch (e) {
        setMessages((prev) => prev.filter((m) => m.id !== tempId))
        setHint(toChatErrorMessage(e, '发送文件失败'))
      } finally {
        setSendingFile(false)
        if (fileInputRef.current) fileInputRef.current.value = ''
      }
    },
    [
      loadConversationMessages,
      loadFriendsAndConversations,
      selectedConversationId,
      sendingFile,
      isImageLike,
      toChatErrorMessage,
    ],
  )

  const onDownloadFile = useCallback(
    async (msg: ChatMessageViewItem) => {
      const fileName = msg.attachment?.filename || msg.localFileName || msg.body || 'file'
      const ok = window.confirm(`下载文件「${fileName}」吗？`)
      if (!ok) return
      if (msg.localObjectUrl) {
        const a = document.createElement('a')
        a.href = msg.localObjectUrl
        a.download = fileName
        a.click()
        return
      }
      const bodyPath = msg.body && looksLikeStoragePath(msg.body) ? msg.body.trim() : ''
      const filePath = (msg.attachment?.filePath || fileMetaMap[msg.id]?.filePath || bodyPath || '').trim()
      if (!filePath) {
        setHint('当前后端未返回可下载链接，暂无法直接下载该历史文件')
        return
      }
      try {
        const res = await fetch(buildChatResourceFileUrl(filePath, { download: true }), {
          credentials: 'include',
        })
        if (!res.ok) {
          setHint('下载失败，请稍后重试')
          return
        }
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        createdObjectUrlsRef.current.push(url)
        const a = document.createElement('a')
        a.href = url
        a.download = fileName
        a.click()
      } catch {
        setHint('下载失败，请检查登录状态或网络')
      }
    },
    [fileMetaMap],
  )

  const onOpenImageLightbox = useCallback(
    async (msg: ChatMessageViewItem) => {
      setLightboxLoading(true)
      setLightboxSrc(null)
      const bodyPath = msg.body && looksLikeStoragePath(msg.body) ? msg.body.trim() : ''
      const filePath = (msg.attachment?.filePath || fileMetaMap[msg.id]?.filePath || bodyPath || '').trim()
      if (!filePath) {
        setLightboxLoading(false)
        setHint('图片原图链接缺失，暂无法全屏预览')
        return
      }
      try {
        const res = await fetch(buildChatResourceFileUrl(filePath), {
          credentials: 'include',
        })
        if (!res.ok) {
          setLightboxLoading(false)
          setHint('加载原图失败，请稍后重试')
          return
        }
        const blob = await res.blob()
        if (!blob.type.startsWith('image/')) {
          setLightboxLoading(false)
          setHint('该文件不是图片，无法全屏预览')
          return
        }
        const url = URL.createObjectURL(blob)
        if (lightboxObjectUrlRef.current) {
          URL.revokeObjectURL(lightboxObjectUrlRef.current)
        }
        lightboxObjectUrlRef.current = url
        setLightboxSrc(url)
      } catch {
        setHint('加载原图失败，请检查登录状态或网络')
      } finally {
        setLightboxLoading(false)
      }
    },
    [fileMetaMap],
  )

  const onSearchAddFriend = useCallback(async () => {
    const q = addQuery.trim()
    if (!q) {
      setAddResults([])
      setAddTarget(null)
      return
    }
    setAddTarget(null)
    setAddLoading(true)
    try {
      const rows = await searchDirectoryUsers(q, 20)
      setAddResults(rows.filter((x) => x.publicId !== user?.public_id))
    } catch (e) {
      setHint(toChatErrorMessage(e, '搜索用户失败'))
    } finally {
      setAddLoading(false)
    }
  }, [addQuery, toChatErrorMessage, user?.public_id])

  const onAddFriend = useCallback(
    async (identifier: string) => {
      try {
        await createFriendRequestByIdentifier(identifier, addMessage.trim())
        setHint('好友申请已发送')
        setAddTarget(null)
        setAddMessage('')
        await loadFriendsAndConversations()
      } catch (e) {
        setHint(toChatErrorMessage(e, '发送好友申请失败'))
      }
    },
    [addMessage, loadFriendsAndConversations, toChatErrorMessage],
  )

  const onAddSelectedPeerAsFriend = useCallback(
    async (peerPublicId: string) => {
      try {
        await createFriendRequestByIdentifier(peerPublicId)
        setHint('好友申请已发送')
        await loadFriendsAndConversations()
      } catch (e) {
        setHint(toChatErrorMessage(e, '发送好友申请失败'))
      }
    },
    [loadFriendsAndConversations, toChatErrorMessage],
  )

  const selectedConversation = useMemo(
    () => conversations.find((x) => x.id === selectedConversationId) ?? null,
    [conversations, selectedConversationId],
  )

  const selectedPeerPublicId = selectedConversation?.peerPublicId ?? selectedFriendId
  const selectedPeerIsFriend = Boolean(selectedPeerPublicId && friendsMap[selectedPeerPublicId])

  useEffect(() => {
    selectedConversationIdRef.current = selectedConversationId
  }, [selectedConversationId])

  useEffect(() => {
    syncComposerHeight()
  }, [composerText, syncComposerHeight])

  useEffect(() => {
    if (!user || loading) return
    const stream = openChatEventsStream()
    const scheduleRefresh = () => {
      if (streamRefreshTimerRef.current != null) return
      streamRefreshTimerRef.current = window.setTimeout(async () => {
        streamRefreshTimerRef.current = null
        const now = Date.now()
        if (now - lastSidebarRefreshAtRef.current >= 2500) {
          lastSidebarRefreshAtRef.current = now
          await loadFriendsAndConversations({ silent: true })
        }
        const cid = selectedConversationIdRef.current
        const minMessageRefreshInterval = composerFocusedRef.current ? 1500 : 500
        if (cid && now - lastMessageRefreshAtRef.current >= minMessageRefreshInterval) {
          lastMessageRefreshAtRef.current = now
          await loadConversationMessages(cid, { silent: true })
        }
      }, 250)
    }
    stream.onmessage = () => {
      scheduleRefresh()
    }
    stream.onerror = () => {
      // EventSource will auto-reconnect; keep UI silent to avoid noise.
    }
    return () => {
      stream.close()
      if (streamRefreshTimerRef.current != null) {
        window.clearTimeout(streamRefreshTimerRef.current)
        streamRefreshTimerRef.current = null
      }
    }
  }, [loadConversationMessages, loadFriendsAndConversations, loading, user])

  if (!loading && !user) {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center px-6 py-8">
        <div className="glass w-full max-w-lg rounded-xl p-6 text-center">
          <h3 className="text-base font-semibold text-slate-800">消息中心</h3>
          <p className="mt-2 text-sm text-slate-600">登录后可查看好友列表并进行聊天。</p>
          <button
            type="button"
            onClick={openLoginModal}
            className="mt-4 rounded-md border border-slate-200 px-3 py-1.5 text-sm text-sky-700 hover:bg-white"
          >
            立即登录
          </button>
        </div>
      </div>
    )
  }

  return (
    <div id="message-history" className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-6 pb-6 pt-2 md:px-8 md:pb-8">
        <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
          <div className="mb-2 flex shrink-0 items-center justify-start gap-1">
            <button
              type="button"
              onClick={() => onToggleListView('chats')}
              className={`rounded-md border px-2 py-0.5 text-xs ${
                listView === 'chats'
                  ? 'border-sky-200 bg-sky-50 text-sky-700'
                  : 'border-slate-200 text-slate-700 hover:bg-white'
              }`}
            >
              消息
            </button>
            <button
              type="button"
              onClick={() => onToggleListView('friends')}
              className={`rounded-md border px-2 py-0.5 text-xs ${
                listView === 'friends'
                  ? 'border-sky-200 bg-sky-50 text-sky-700'
                  : 'border-slate-200 text-slate-700 hover:bg-white'
              }`}
            >
              好友
            </button>
          </div>
          <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-4 overflow-hidden md:flex-row md:items-stretch">
          {listView ? (
            <div className="glass flex min-h-0 w-full shrink-0 flex-col rounded-xl p-3 md:w-[min(100%,340px)] md:min-w-[260px]">
              <div className="mb-2 shrink-0 text-sm font-semibold text-slate-700">
                {listView === 'chats' ? '聊天列表' : '好友列表'}
              </div>
              <div className="mb-2 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setAddFriendOpen((v) => !v)}
                  className={`rounded-md border px-2 py-0.5 text-xs ${
                    listView !== 'friends'
                      ? 'invisible border-slate-200 text-sky-700'
                      : addFriendOpen
                        ? 'border-sky-700 bg-sky-700 text-white hover:bg-sky-800'
                        : 'border-slate-200 text-sky-700 hover:bg-white'
                  }`}
                >
                  + 添加好友
                </button>
              </div>
            {listView === 'friends' && addFriendOpen ? (
              <div className="mb-2 rounded-lg border border-slate-200 bg-white/80 p-2">
                <div className="flex gap-2">
                  <input
                    value={addQuery}
                    onChange={(e) => setAddQuery(e.target.value)}
                    placeholder="搜索 username / email / public id"
                    className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
                  />
                  <button
                    type="button"
                    onClick={() => void onSearchAddFriend()}
                    className="rounded-md border border-slate-200 px-2 text-xs text-slate-700 hover:bg-white"
                  >
                    搜索
                  </button>
                </div>
                {addLoading ? <p className="mt-2 text-xs text-slate-500">搜索中…</p> : null}
                <div className="mt-2 max-h-40 space-y-1 overflow-y-auto">
                  {addResults.map((u) => {
                    const alreadyFriend = Boolean(friendsMap[u.publicId])
                    return (
                    <div key={`${u.publicId}-${u.username}`} className="rounded-md border border-slate-100 px-2 py-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="min-w-0 truncate text-xs font-medium text-slate-700">
                          {u.displayName || u.username}
                        </div>
                        {alreadyFriend ? (
                          <span className="shrink-0 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] text-emerald-700">
                            已添加
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[11px] text-slate-500">
                        {u.username} · {u.email} · {u.publicId}
                      </div>
                      <div className="mt-1 flex gap-1">
                        <button
                          type="button"
                          disabled={alreadyFriend}
                          onClick={() => {
                            setAddTarget(u)
                            setAddMessage('')
                          }}
                          className="rounded border border-slate-200 px-1.5 py-0.5 text-[11px] text-sky-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {alreadyFriend ? '已添加' : '添加好友'}
                        </button>
                      </div>
                      {addTarget?.publicId === u.publicId ? (
                        <div className="mt-2 rounded border border-slate-200 bg-white p-2">
                          <input
                            value={addMessage}
                            onChange={(e) => setAddMessage(e.target.value)}
                            placeholder="附言（可选）"
                            className="h-8 w-full rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
                          />
                          <div className="mt-2 flex justify-end gap-2">
                            <button
                              type="button"
                              onClick={() => {
                                setAddTarget(null)
                                setAddMessage('')
                              }}
                              className="rounded border border-slate-200 px-2 py-0.5 text-[11px] text-slate-600 hover:bg-slate-50"
                            >
                              取消
                            </button>
                            <button
                              type="button"
                              onClick={() => void onAddFriend(u.publicId)}
                              className="rounded border border-sky-200 px-2 py-0.5 text-[11px] text-sky-700 hover:bg-sky-50"
                            >
                              发送申请
                            </button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  )})}
                  {!addLoading && addQuery.trim() && addResults.length === 0 ? (
                    <p className="text-xs text-slate-500">未找到匹配用户</p>
                  ) : null}
                </div>
              </div>
            ) : null}
            {!(listView === 'friends' && addFriendOpen) ? (
              <div className="mb-2 flex shrink-0 gap-2">
                <input
                  value={friendQuery}
                  onChange={(e) => setFriendQuery(e.target.value)}
                  placeholder={listView === 'chats' ? '搜索聊天对象' : '搜索好友'}
                  className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
                />
                <button
                  type="button"
                  onClick={() => void loadFriendsAndConversations()}
                  className="rounded-md border border-slate-200 px-2 text-xs text-slate-700 hover:bg-white"
                >
                  刷新
                </button>
              </div>
            ) : null}
            {friendsError ? <p className="mb-2 text-xs text-red-600">{friendsError}</p> : null}
            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain">
              {listView === 'chats'
                ? filteredConversations.map((row) => (
                    <div
                      key={row.conversation.id}
                      className={`rounded-xl px-3 py-2 text-left transition-colors ${
                        selectedConversationId === row.conversation.id
                          ? 'bg-white shadow-sm'
                          : 'hover:bg-white/80'
                      }`}
                    >
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => void onSelectConversation(row.conversation)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void onSelectConversation(row.conversation)
                        }}
                        className="cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-full border border-slate-200 bg-slate-100">
                            {row.avatarUrl ? (
                              <img src={row.avatarUrl} alt={row.displayName} className="h-full w-full object-cover" />
                            ) : (
                              <span className="flex h-full w-full items-center justify-center text-xs text-slate-600">
                                {(row.displayName[0] || '?').toUpperCase()}
                              </span>
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-800">{row.displayName}</div>
                            {!row.peerPublicId ? <div className="text-[11px] text-amber-700">未关联 public_id</div> : null}
                          </div>
                          {!row.peerPublicId || !friendsMap[row.peerPublicId] ? (
                            <span className="ml-auto rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                              非好友
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))
                : filteredFriends.map((friend) => (
                    <div
                      key={friend.targetPublicId}
                      className={`rounded-xl px-3 py-2 text-left transition-colors ${
                        selectedFriendId === friend.targetPublicId ? 'bg-white shadow-sm' : 'hover:bg-white/80'
                      }`}
                      onContextMenu={(e) => {
                        e.preventDefault()
                        setContextMenu({
                          x: e.clientX,
                          y: e.clientY,
                          friend,
                        })
                      }}
                    >
                      <div
                        role="button"
                        tabIndex={0}
                        onClick={() => void onSelectFriend(friend)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') void onSelectFriend(friend)
                        }}
                        className="cursor-pointer"
                      >
                        <div className="flex items-center gap-2">
                          <div className="relative h-8 w-8 shrink-0 overflow-hidden rounded-full border border-slate-200 bg-slate-100">
                            {friend.avatarUrl ? (
                              <img
                                src={friend.avatarUrl}
                                alt={inferDisplayName(friend)}
                                className="h-full w-full object-cover"
                              />
                            ) : (
                              <span className="flex h-full w-full items-center justify-center text-xs text-slate-600">
                                {avatarLetter(friend)}
                              </span>
                            )}
                          </div>
                          <div className="min-w-0">
                            <div className="truncate text-sm font-medium text-slate-800">
                              {inferDisplayName(friend)}
                            </div>
                          </div>
                          {blacklistMap[friend.targetPublicId] ? (
                            <span className="ml-auto rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                              已屏蔽
                            </span>
                          ) : null}
                          {pinnedPeers[friend.targetPublicId] ? (
                            <span className="ml-1 rounded border border-sky-200 bg-sky-50 px-1.5 py-0.5 text-[10px] text-sky-700">
                              已置顶
                            </span>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  ))}
              {!friendsLoading &&
              (listView === 'chats' ? filteredConversations.length === 0 : filteredFriends.length === 0) ? (
                <div className="px-2 py-2 text-xs text-slate-500">
                  {listView === 'chats' ? '暂无聊天记录' : '暂无好友'}
                </div>
              ) : null}
              {friendsLoading ? <div className="px-2 py-2 text-xs text-slate-500">加载中…</div> : null}
            </div>
          </div>
          ) : null}
          <div className="glass flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-xl p-4">
            <div className="min-h-0 flex-1 overflow-hidden">
              {!selectedFriendId && !selectedConversationId ? (
                <div className="rounded-lg border border-dashed border-slate-200 p-4 text-sm text-slate-500">
                  从左侧选择一个会话或好友开始聊天。
                </div>
              ) : (
                <div className="flex h-full min-h-0 flex-col gap-3">
                  {selectedConversationId && !selectedPeerIsFriend ? (
                    <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">
                      <div>当前聊天对象还不是你的好友。</div>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button
                          type="button"
                          disabled={!selectedPeerPublicId}
                          onClick={() =>
                            selectedPeerPublicId ? void onToggleBlockFriend(selectedPeerPublicId) : undefined
                          }
                          className="rounded border border-amber-300 bg-white px-2 py-1 text-[11px] hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          {selectedPeerPublicId && blacklistMap[selectedPeerPublicId] ? '取消屏蔽' : '屏蔽'}
                        </button>
                        <button
                          type="button"
                          disabled={!selectedPeerPublicId}
                          onClick={() =>
                            selectedPeerPublicId ? void onAddSelectedPeerAsFriend(selectedPeerPublicId) : undefined
                          }
                          className="rounded border border-amber-300 bg-white px-2 py-1 text-[11px] hover:bg-amber-100 disabled:cursor-not-allowed disabled:opacity-60"
                        >
                          添加好友
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {messagesError ? <p className="text-xs text-red-600">{messagesError}</p> : null}
                  {messagesLoading ? <p className="text-xs text-slate-500">加载消息中…</p> : null}
                  <div className="min-h-0 flex-1 space-y-2 overflow-y-auto rounded-lg border border-slate-200/80 bg-white/50 p-3">
                    {messages.map((msg) => (
                      <div
                        key={msg.id}
                        className={`flex ${selectedConversationId && msg.senderId !== selectedConversationId ? 'justify-end' : 'justify-start'}`}
                      >
                        <div
                          className={
                            selectedConversationId && msg.senderId !== selectedConversationId
                              ? 'bubble me max-w-[80%]'
                              : 'bubble ai glass max-w-[80%]'
                          }
                        >
                          <div className="text-[11px] text-slate-500">{msg.createdAt}</div>
                          {msg.kind === 'file' ? (
                            (() => {
                              const filePath =
                                msg.attachment?.filePath || (msg.body && looksLikeStoragePath(msg.body) ? msg.body : '') || ''
                              const cached = fileMetaMap[msg.id]
                              const resolvedPath = filePath || cached?.filePath || ''
                              const fileName =
                                msg.attachment?.filename ||
                                msg.localFileName ||
                                cached?.filename ||
                                msg.body ||
                                (resolvedPath ? resolvedPath.split('/').pop() || '(无文件名)' : '(无文件名)')
                              const mime =
                                msg.localMimeType || msg.attachment?.contentType || cached?.contentType || ''
                              const isImage = Boolean(msg.localObjectUrl) && isImageLike(mime, fileName || resolvedPath)
                              const imageSrc = msg.localObjectUrl
                              if (isImage && imageSrc) {
                                return (
                                  <div className="mt-1">
                                    <img
                                      src={imageSrc}
                                      alt={fileName}
                                      className="max-h-56 max-w-full cursor-pointer rounded-lg border border-slate-200 object-contain transition-opacity hover:opacity-90"
                                      onClick={() => void onOpenImageLightbox(msg)}
                                    />
                                    <div className="mt-1 text-[11px] text-slate-600">{fileName}</div>
                                  </div>
                                )
                              }
                              return (
                                <button
                                  type="button"
                                  onClick={() => void onDownloadFile(msg)}
                                  className="mt-1 w-full rounded-lg border border-slate-200 bg-white/80 px-2 py-1 text-left text-xs text-slate-700 hover:bg-white"
                                >
                                  [文件] {fileName}
                                </button>
                              )
                            })()
                          ) : (
                            <div className="mt-1 whitespace-pre-wrap break-words">{msg.body}</div>
                          )}
                        </div>
                      </div>
                    ))}
                    {messages.length === 0 && !messagesLoading ? (
                      <p className="text-xs text-slate-500">暂无消息，发送第一条消息开始会话。</p>
                    ) : null}
                  </div>
                  <div className="flex items-end gap-2">
                    <input
                      ref={fileInputRef}
                      type="file"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.currentTarget.files?.[0] ?? null
                        void onSelectFile(file)
                      }}
                    />
                    <textarea
                      ref={composerRef}
                      value={composerText}
                      onChange={(e) => setComposerText(e.target.value)}
                      onFocus={() => {
                        composerFocusedRef.current = true
                      }}
                      onBlur={() => {
                        composerFocusedRef.current = false
                      }}
                      onInput={() => {
                        syncComposerHeight()
                      }}
                      disabled={sending}
                      rows={1}
                      className="min-h-10 max-h-40 min-w-0 flex-1 resize-none overflow-y-auto rounded-2xl border border-slate-200 bg-white/80 px-4 py-2 text-sm leading-6 focus:border-sky-300 focus:outline-none focus:shadow-[inset_0_0_0_1px_rgba(56,189,248,0.65)] disabled:opacity-60"
                      placeholder="输入消息，Enter 发送，Shift+Enter 换行"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          void onSend()
                        }
                      }}
                    />
                    <button
                      type="button"
                      onClick={onPickFile}
                      disabled={sendingFile}
                      className="inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white/90 text-lg leading-none text-slate-700 hover:bg-white disabled:cursor-not-allowed disabled:opacity-60"
                      title={sendingFile ? '上传中' : '发送文件'}
                    >
                      {sendingFile ? '…' : '+'}
                    </button>
                    <button type="button" onClick={() => void onSend()} disabled={sending || sendingFile} className="btn">
                      {sending ? '发送中…' : '发送'}
                    </button>
                  </div>
                </div>
              )}
            </div>
            {hint ? <p className="mt-3 text-xs text-slate-600">{hint}</p> : null}
          </div>
          </div>
        </div>
      </div>
      {contextMenu ? (
        <div
          className="fixed z-50 min-w-44 rounded-lg border border-slate-200 bg-white p-1 shadow-lg"
          style={{ left: contextMenu.x, top: contextMenu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            className="block w-full rounded px-3 py-1.5 text-left text-xs hover:bg-slate-100"
            onClick={() => {
              setFriendInfo(contextMenu.friend)
              setContextMenu(null)
            }}
          >
            显示信息
          </button>
          <button
            type="button"
            className="block w-full rounded px-3 py-1.5 text-left text-xs hover:bg-slate-100"
            onClick={() => {
              void onRemoveFriend(contextMenu.friend.targetPublicId)
              setContextMenu(null)
            }}
          >
            删除好友
          </button>
          <button
            type="button"
            className="block w-full rounded px-3 py-1.5 text-left text-xs hover:bg-slate-100"
            onClick={() => {
              void onToggleBlockFriend(contextMenu.friend.targetPublicId)
              setContextMenu(null)
            }}
          >
            {blacklistMap[contextMenu.friend.targetPublicId] ? '取消屏蔽' : '屏蔽好友'}
          </button>
          <button
            type="button"
            className="block w-full rounded px-3 py-1.5 text-left text-xs hover:bg-slate-100"
            onClick={() => {
              void onTogglePinFriend(contextMenu.friend.targetPublicId)
              setContextMenu(null)
            }}
          >
            {pinnedPeers[contextMenu.friend.targetPublicId] ? '取消置顶' : '置顶'}
          </button>
          <button
            type="button"
            className="block w-full rounded px-3 py-1.5 text-left text-xs text-red-600 hover:bg-red-50"
            onClick={() => {
              void onClearChatHistory(contextMenu.friend)
              setContextMenu(null)
            }}
          >
            清除聊天记录
          </button>
        </div>
      ) : null}
      {friendInfo ? (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-black/30 p-4">
          <div className="w-full max-w-sm rounded-xl bg-white p-4 shadow-xl">
            <div className="text-sm font-semibold text-slate-800">好友信息</div>
            <div className="mt-2 text-xs text-slate-600">
              <div>名称：{inferDisplayName(friendInfo)}</div>
              <div>public_id：{friendInfo.targetPublicId}</div>
              <div>状态：{friendInfo.status || 'normal'}</div>
              <div>备注：{friendInfo.remark || '无'}</div>
              <div>会话ID：{friendInfo.conversationId || '无'}</div>
            </div>
            <div className="mt-3 flex justify-end">
              <button
                type="button"
                className="rounded-md border border-slate-200 px-3 py-1 text-xs hover:bg-slate-50"
                onClick={() => setFriendInfo(null)}
              >
                关闭
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {lightboxLoading || lightboxSrc ? (
        <div
          className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={closeLightbox}
        >
          <div className="flex h-[75vh] w-[75vw] items-center justify-center" onClick={(e) => e.stopPropagation()}>
            {lightboxSrc ? (
              <img
                src={lightboxSrc}
                alt="preview"
                className="h-full w-full rounded-lg object-contain shadow-2xl"
              />
            ) : (
              <div className="text-sm text-white/90">正在加载原图...</div>
            )}
          </div>
          <button
            type="button"
            className="absolute right-4 top-4 rounded-full bg-white/20 p-2 text-white transition-colors hover:bg-white/40"
            onClick={closeLightbox}
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      ) : null}
    </div>
  )
}

