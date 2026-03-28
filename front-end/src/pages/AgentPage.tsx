import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ChangeEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from 'react'
import ReactMarkdown from 'react-markdown'
import remarkBreaks from 'remark-breaks'
import remarkGfm from 'remark-gfm'
import { useLocation, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth'
import { MidAuthHttpError } from '../lib/midAuth'
import {
  addChatTag,
  createWorkbenchMemory,
  deletePersistedAiChat,
  getWorkbenchToolValves,
  getDefaultWorkbenchModelId,
  listChatTags,
  listWorkbenchChats,
  listWorkbenchFolders,
  listWorkbenchFunctions,
  listPersistedAiChatMessages,
  listWorkbenchMemories,
  listWorkbenchModels,
  listWorkbenchNotes,
  listWorkbenchPrompts,
  listWorkbenchSkills,
  listWorkbenchTools,
  postChatCompletionStream,
  postChatCompletionNonStreamDetailed,
  queryWorkbenchMemories,
  renamePersistedAiChat,
  runPersistedAiChatTurn,
  runPersistedAiChatTurnStream,
  searchWorkbenchChats,
  toggleChatArchive,
  toggleChatPin,
  type ChatMessagePayload,
  type WorkbenchChatItem,
  type WorkbenchFolderItem,
  type WorkbenchMemoryItem,
  type WorkbenchModelItem,
  type WorkbenchPromptItem,
  type WorkbenchTagItem,
  type WorkbenchToolItem,
} from '../lib/midAuthWorkbench'

type Role = 'user' | 'assistant'

type ChatMessage = { role: Role; text: string; reasoning?: string }

const QUICK_REPLIES: Record<string, string> = {
  'School Work':
    'Break tasks into small pieces and start with the easiest one.',
  Relationship:
    "Begin with listening; try paraphrasing the other person's viewpoint.",
  Confusion: 'Write problems down and add one next actionable step to each.',
  Emotional: 'Focus on breathing; give yourself a two‑minute gentle pause.',
}

const CAPSULES = [
  { tip: 'Study planning', quick: 'School Work', label: 'School Work' },
  { tip: 'Relationships & communication', quick: 'Relationship', label: 'Relationship' },
  { tip: 'Clarify confusion', quick: 'Confusion', label: 'Confusion' },
  { tip: 'Emotional support', quick: 'Emotional', label: 'Emotional' },
] as const

const agentSquareActionClass =
  'flex size-7 shrink-0 items-center justify-center rounded-md border border-sky-200/90 bg-white/95 text-sm leading-none shadow-sm transition hover:scale-105 hover:bg-sky-50 hover:shadow-md active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400 md:size-8 md:text-base'

/** History drawer width */
const HISTORY_DRAWER_WIDTH_CLASS = 'w-[min(20rem,86vw,320px)]'

/** Align with the right floating rail (`fixed ... top`) for drawer track alignment */
const AGENT_FLOAT_RAIL_TOP_CLASS =
  'top-[calc(1.25rem-3px)] md:top-[calc(1.5rem-3px)]'

function AssistantMarkdown({ content }: { content: string }) {
  return (
    <div className="agent-markdown">
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkBreaks]}>{content}</ReactMarkdown>
    </div>
  )
}

export function AgentPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user, loading: authLoading, openLoginModal } = useAuth()
  const [historyOpen, setHistoryOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [composerDocked, setComposerDocked] = useState(false)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [composerText, setComposerText] = useState('')
  const [workbenchModels, setWorkbenchModels] = useState<WorkbenchModelItem[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [selectedModelId, setSelectedModelId] = useState('')
  const [historyRows, setHistoryRows] = useState<WorkbenchChatItem[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyQuery, setHistoryQuery] = useState('')
  const [selectedChatId, setSelectedChatId] = useState<string | null>(null)
  const [selectedChatTags, setSelectedChatTags] = useState<WorkbenchTagItem[]>([])
  const [newTagName, setNewTagName] = useState('')
  const [prompts, setPrompts] = useState<WorkbenchPromptItem[]>([])
  const [selectedPromptId, setSelectedPromptId] = useState('')
  const [tools, setTools] = useState<WorkbenchToolItem[]>([])
  const [selectedToolId, setSelectedToolId] = useState('')
  const [folders, setFolders] = useState<WorkbenchFolderItem[]>([])
  const [selectedFolderId, setSelectedFolderId] = useState('')
  const [memories, setMemories] = useState<WorkbenchMemoryItem[]>([])
  const [memoryInput, setMemoryInput] = useState('')
  const [memoryStatus, setMemoryStatus] = useState<string | null>(null)
  const [capabilityNote, setCapabilityNote] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [submitHint, setSubmitHint] = useState<string | null>(null)
  const restoredRouteChatIdRef = useRef<string | null>(null)
  const threadScrollRef = useRef<HTMLDivElement>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const [stickToBottom, setStickToBottom] = useState(true)

  const routeChatId = (() => {
    const value = new URLSearchParams(location.search).get('chat_id')
    return (value || '').trim()
  })()
  const routeModelId = (() => {
    const value = new URLSearchParams(location.search).get('model')
    return (value || '').trim()
  })()

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  const onThreadScroll = useCallback(() => {
    const el = threadScrollRef.current
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    setStickToBottom(distance <= 80)
  }, [])

  useEffect(() => {
    if (stickToBottom) scrollToBottom()
  }, [messages, composerDocked, scrollToBottom, stickToBottom])

  const pushBubble = useCallback((role: Role, text: string) => {
    setMessages((m) => [...m, { role, text }])
  }, [])

  const toAiErrorMessage = useCallback((err: unknown, fallback = 'Request failed'): string => {
    if (err instanceof MidAuthHttpError) {
      if (err.status === 401 || err.status === 403) return 'Your session has expired. Please sign in again.'
      if (err.status === 404) return 'This AI capability is not enabled on the backend, or your account is not mapped.'
      if (err.status === 422) return 'Request parameters are invalid (422).'
      if (err.status === 503) return 'AI service is temporarily unavailable (503). Please try again later.'
      return err.message
    }
    return err instanceof Error ? err.message : fallback
  }, [])

  useEffect(() => {
    if (authLoading || !user) {
      setWorkbenchModels([])
      setModelsError(null)
      setSelectedModelId('')
      setHistoryRows([])
      setHistoryError(null)
      setSelectedChatId(null)
      setSelectedChatTags([])
      setPrompts([])
      setTools([])
      setFolders([])
      setMemories([])
      setCapabilityNote(null)
      return
    }
    let cancelled = false
    setModelsLoading(true)
    setModelsError(null)
    ;(async () => {
      try {
        const [items, defaultId] = await Promise.all([
          listWorkbenchModels(),
          getDefaultWorkbenchModelId(),
        ])
        if (cancelled) return
        setWorkbenchModels(items)
        setSubmitHint(null)
        const fromDefault =
          defaultId && items.some((m) => m.id === defaultId) ? defaultId : ''
        setSelectedModelId(fromDefault || items[0]?.id || '')
      } catch (e) {
        if (cancelled) return
        setWorkbenchModels([])
        setSelectedModelId('')
        if (e instanceof MidAuthHttpError && e.status === 503) {
          setModelsError('AI service is temporarily unavailable (503). Please try again later.')
        } else if (e instanceof MidAuthHttpError && (e.status === 401 || e.status === 403)) {
          setModelsError('Please sign in to load models.')
        } else {
          setModelsError(toAiErrorMessage(e, 'Failed to load models.'))
        }
      } finally {
        if (!cancelled) setModelsLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user, authLoading, toAiErrorMessage])

  const loadHistory = useCallback(
    async (query?: string) => {
      if (!user) return
      setHistoryLoading(true)
      setHistoryError(null)
      try {
        const q = (query ?? historyQuery).trim()
        const rows = q ? await searchWorkbenchChats(q, 1) : await listWorkbenchChats({ page: 1 })
        setHistoryRows(rows)
      } catch (e) {
        if (e instanceof MidAuthHttpError && e.status === 404) {
          setHistoryRows([])
          setHistoryError('Chat history API is not enabled in this environment.')
          return
        }
        setHistoryError(toAiErrorMessage(e, 'Failed to load chat history.'))
      } finally {
        setHistoryLoading(false)
      }
    },
    [historyQuery, toAiErrorMessage, user],
  )

  useEffect(() => {
    if (!user || authLoading) return
    void loadHistory('')
  }, [user, authLoading, loadHistory])

  useEffect(() => {
    if (!routeChatId || authLoading || !user) return
    if (restoredRouteChatIdRef.current === routeChatId) return
    let cancelled = false
    ;(async () => {
      setSelectedChatId(routeChatId)
      setComposerDocked(true)
      if (routeModelId && workbenchModels.some((m) => m.id === routeModelId)) {
        setSelectedModelId(routeModelId)
      }
      try {
        const [tags, persistedMessages] = await Promise.all([
          listChatTags(routeChatId).catch(() => [] as WorkbenchTagItem[]),
          listPersistedAiChatMessages(routeChatId),
        ])
        if (cancelled) return
        setSelectedChatTags(tags)
        setMessages(
          persistedMessages.map((item) => ({
            role: item.role === 'assistant' ? 'assistant' : 'user',
            text: item.body,
            reasoning: item.role === 'assistant' ? item.reasoning : undefined,
          })),
        )
        setSubmitHint(null)
      } catch {
        if (cancelled) return
        setSelectedChatTags([])
        setMessages([])
        setSubmitHint('Unable to load messages for this chat.')
      } finally {
        restoredRouteChatIdRef.current = routeChatId
      }
    })()
    return () => {
      cancelled = true
    }
  }, [authLoading, routeChatId, routeModelId, user, workbenchModels])

  useEffect(() => {
    if (!user || authLoading) return
    let cancelled = false
    ;(async () => {
      try {
        const [promptRows, toolRows, folderRows, memoryRows] = await Promise.all([
          listWorkbenchPrompts().catch(() => [] as WorkbenchPromptItem[]),
          listWorkbenchTools().catch(() => [] as WorkbenchToolItem[]),
          listWorkbenchFolders().catch(() => [] as WorkbenchFolderItem[]),
          listWorkbenchMemories().catch(() => [] as WorkbenchMemoryItem[]),
        ])
        if (cancelled) return
        setPrompts(promptRows)
        setTools(toolRows)
        setFolders(folderRows)
        setMemories(memoryRows)
        setSelectedPromptId((prev) => prev || promptRows[0]?.id || '')
        setSelectedToolId((prev) => prev || toolRows[0]?.id || '')
        setSelectedFolderId((prev) => prev || folderRows[0]?.id || '')

        // These capabilities may not exist in some Open WebUI versions; silently degrade on 404.
        await Promise.all([listWorkbenchNotes(), listWorkbenchSkills(), listWorkbenchFunctions()])
        if (!cancelled) setCapabilityNote(null)
      } catch (e) {
        if (cancelled) return
        if (e instanceof MidAuthHttpError && e.status === 404) {
          setCapabilityNote('Some AI extensions are not enabled on this backend version and have been hidden.')
        } else {
          setCapabilityNote(toAiErrorMessage(e, 'Failed to load AI extensions.'))
        }
      }
    })()
    return () => {
      cancelled = true
    }
  }, [user, authLoading, toAiErrorMessage])

  const onSelectHistory = useCallback(async (chat: WorkbenchChatItem) => {
    setSelectedChatId(chat.id)
    setSubmitHint(`Switched to chat: ${chat.title}`)
    setComposerDocked(true)
    if (chat.modelId) {
      const matched = workbenchModels.find((m) => m.id === chat.modelId)
      setSelectedModelId(matched?.id ?? workbenchModels[0]?.id ?? '')
    }
    try {
      const [tags, persistedMessages] = await Promise.all([
        listChatTags(chat.id).catch(() => [] as WorkbenchTagItem[]),
        listPersistedAiChatMessages(chat.id),
      ])
      setSelectedChatTags(tags)
      setMessages(
        persistedMessages.map((item) => ({
          role: item.role === 'assistant' ? 'assistant' : 'user',
          text: item.body,
          reasoning: item.role === 'assistant' ? item.reasoning : undefined,
        })),
      )
      setSubmitHint(null)
    } catch {
      setSelectedChatTags([])
      setMessages([])
      setSubmitHint('Unable to load messages for this chat.')
    }
  }, [workbenchModels])

  const onTogglePin = useCallback(async (chatId: string) => {
    try {
      await toggleChatPin(chatId)
      await loadHistory()
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to pin/unpin chat.'))
    }
  }, [loadHistory, toAiErrorMessage])

  const onToggleArchive = useCallback(async (chatId: string) => {
    try {
      await toggleChatArchive(chatId)
      await loadHistory()
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to archive/unarchive chat.'))
    }
  }, [loadHistory, toAiErrorMessage])

  const onRenameHistory = useCallback(async (chat: WorkbenchChatItem) => {
    const nextTitle = window.prompt('Enter a new chat title', chat.title)?.trim()
    if (!nextTitle || nextTitle === chat.title) return
    try {
      await renamePersistedAiChat(chat.id, nextTitle)
      setSubmitHint('Chat title updated.')
      await loadHistory()
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to rename chat.'))
    }
  }, [loadHistory, toAiErrorMessage])

  const onDeleteHistory = useCallback(async (chat: WorkbenchChatItem) => {
    const confirmed = window.confirm(`Delete chat "${chat.title}"? This cannot be undone.`)
    if (!confirmed) return
    try {
      await deletePersistedAiChat(chat.id)
      if (selectedChatId === chat.id) {
        setSelectedChatId(null)
        setSelectedChatTags([])
        setMessages([])
        setComposerDocked(false)
      }
      setSubmitHint('Chat deleted.')
      await loadHistory()
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to delete chat.'))
    }
  }, [loadHistory, selectedChatId, toAiErrorMessage])

  const onAddTag = useCallback(async () => {
    const chatId = selectedChatId
    const tag = newTagName.trim()
    if (!chatId || !tag) return
    try {
      const tags = await addChatTag(chatId, tag)
      setSelectedChatTags(tags)
      setNewTagName('')
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to add tag.'))
    }
  }, [newTagName, selectedChatId, toAiErrorMessage])

  const onApplyPrompt = useCallback(() => {
    if (!selectedPromptId) return
    const p = prompts.find((x) => x.id === selectedPromptId)
    if (!p) return
    setComposerText((prev) => (prev.trim() ? `${prev}\n${p.content}` : p.content))
  }, [prompts, selectedPromptId])

  const onReadToolValves = useCallback(async () => {
    if (!selectedToolId) return
    try {
      const valves = await getWorkbenchToolValves(selectedToolId)
      setSubmitHint(`Tool config loaded: ${JSON.stringify(valves).slice(0, 120)}...`)
    } catch (e) {
      setSubmitHint(toAiErrorMessage(e, 'Failed to load tool config.'))
    }
  }, [selectedToolId, toAiErrorMessage])

  const onQueryMemory = useCallback(async () => {
    const q = memoryInput.trim()
    if (!q) return
    try {
      const rows = await queryWorkbenchMemories(q, 5)
      setMemories(rows)
      setMemoryStatus(`Query complete: ${rows.length} items`)
    } catch (e) {
      setMemoryStatus(toAiErrorMessage(e, 'Memory query failed.'))
    }
  }, [memoryInput, toAiErrorMessage])

  const onCreateMemory = useCallback(async () => {
    const body = memoryInput.trim()
    if (!body) return
    try {
      const created = await createWorkbenchMemory(body)
      if (created) {
        setMemories((prev) => [created, ...prev])
        setMemoryStatus('Memory created.')
        setMemoryInput('')
      }
    } catch (e) {
      setMemoryStatus(toAiErrorMessage(e, 'Failed to create memory.'))
    }
  }, [memoryInput, toAiErrorMessage])

  const onFormSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (sending) return
    const v = composerText.trim()
    if (!v) return
    if (!user) {
      openLoginModal()
      return
    }
    if (!selectedModelId || workbenchModels.length === 0) {
      if (!modelsLoading) {
        setSubmitHint(
          workbenchModels.length === 0 ? 'No models available. Unable to send.' : 'Please select a model.',
        )
      }
      return
    }
    setSubmitHint(null)
    const apiMessages: ChatMessagePayload[] = [
      ...messages.map((m) => ({ role: m.role, content: m.text })),
      { role: 'user', content: v },
    ]
    setMessages((m) => [...m, { role: 'user', text: v }, { role: 'assistant', text: 'Thinking...' }])
    setComposerText('')
    setComposerDocked(true)
    setSending(true)
    try {
      let persistedSucceeded = false
      try {
        const persisted = await runPersistedAiChatTurnStream(v, selectedModelId, selectedChatId, {
          onChatId: (chatId) => {
            setSelectedChatId((prev) => prev || chatId)
          },
          onReasoningToken: (_token, aggregateReasoning) => {
            setMessages((m) => {
              const next = [...m]
              const last = next.length - 1
              if (last >= 0 && next[last].role === 'assistant') {
                next[last] = {
                  role: 'assistant',
                  text: next[last].text,
                  reasoning: aggregateReasoning,
                }
              }
              return next
            })
          },
          onToken: (_token, aggregate) => {
            setMessages((m) => {
              const next = [...m]
              const last = next.length - 1
              if (last >= 0 && next[last].role === 'assistant') {
                next[last] = {
                  role: 'assistant',
                  text: aggregate.trim() ? aggregate : 'Thinking...',
                  reasoning: next[last].reasoning,
                }
              }
              return next
            })
          },
        })
        setSelectedChatId((prev) => prev || persisted.chatId)
        setMessages((m) => {
          const next = [...m]
          const last = next.length - 1
          if (last >= 0 && next[last].role === 'assistant') {
            next[last] = {
              role: 'assistant',
              text: persisted.assistantText || '(No content)',
              reasoning: next[last].reasoning,
            }
          }
          return next
        })
        persistedSucceeded = true
      } catch (persistErr) {
        // Backward compatibility: if persisted streaming is unavailable, fall back to persisted non-streaming.
        if (
          persistErr instanceof MidAuthHttpError &&
          [404, 405, 422, 501].includes(persistErr.status)
        ) {
          try {
            const persisted = await runPersistedAiChatTurn(v, selectedModelId, selectedChatId)
            setSelectedChatId((prev) => prev || persisted.chatId)
            setMessages((m) => {
              const next = [...m]
              const last = next.length - 1
              if (last >= 0 && next[last].role === 'assistant') {
                next[last] = {
                  role: 'assistant',
                  text: persisted.assistantText || '(No content)',
                }
              }
              return next
            })
            persistedSucceeded = true
          } catch (persistNonStreamErr) {
            if (
              !(persistNonStreamErr instanceof MidAuthHttpError) ||
              ![404, 405, 422, 501].includes(persistNonStreamErr.status)
            ) {
              throw persistNonStreamErr
            }
          }
        } else {
          // Backward compatibility: if persisted endpoints are unavailable, fall back to completion endpoints.
          if (
            !(persistErr instanceof MidAuthHttpError) ||
            ![404, 405, 422, 501].includes(persistErr.status)
          ) {
            throw persistErr
          }
        }
      }

      if (!persistedSucceeded) {
        let streamSucceeded = false
      try {
        const streamed = await postChatCompletionStream(selectedModelId, apiMessages, {
          onReasoningToken: (_token, aggregateReasoning) => {
            setMessages((m) => {
              const next = [...m]
              const last = next.length - 1
              if (last >= 0 && next[last].role === 'assistant') {
                next[last] = {
                  role: 'assistant',
                  text: next[last].text,
                  reasoning: aggregateReasoning,
                }
              }
              return next
            })
          },
          onToken: (_token, aggregate) => {
            setMessages((m) => {
              const next = [...m]
              const last = next.length - 1
              if (last >= 0 && next[last].role === 'assistant') {
                next[last] = {
                  role: 'assistant',
                  text: aggregate.trim() ? aggregate : 'Thinking...',
                  reasoning: next[last].reasoning,
                }
              }
              return next
            })
          },
        })
        if (!streamed.trim()) {
          setMessages((m) => {
            const next = [...m]
            const last = next.length - 1
            if (last >= 0 && next[last].role === 'assistant') {
              next[last] = { role: 'assistant', text: '(No content)' }
            }
            return next
          })
        }
        streamSucceeded = true
      } catch (streamErr) {
        if (!(streamErr instanceof MidAuthHttpError) || streamErr.status !== 422) {
          throw streamErr
        }
      }

        if (!streamSucceeded) {
          const { content, reasoning } = await postChatCompletionNonStreamDetailed(
            selectedModelId,
            apiMessages,
          )
          setMessages((m) => {
            const next = [...m]
            const last = next.length - 1
            if (last >= 0 && next[last].role === 'assistant') {
              next[last] = {
                role: 'assistant',
                text: content.trim() ? content : '(No content)',
                reasoning: reasoning || undefined,
              }
            }
            return next
          })
        }
      }
      void loadHistory()
    } catch (err) {
      const fallback = (msg: string) => {
        setMessages((m) => {
          const next = [...m]
          const last = next.length - 1
          if (last >= 0 && next[last].role === 'assistant') {
            next[last] = { role: 'assistant', text: `[Error] ${msg}` }
          }
          return next
        })
      }
      if (err instanceof MidAuthHttpError) {
        if (err.status === 401 || err.status === 403) openLoginModal()
        fallback(toAiErrorMessage(err))
      } else {
        fallback(toAiErrorMessage(err))
      }
    } finally {
      setSending(false)
    }
  }

  const onCapsule = (quick: string) => {
    pushBubble('user', quick)
    setComposerDocked(true)
    window.setTimeout(
      () =>
        pushBubble(
          'assistant',
          QUICK_REPLIES[quick] ?? "I'm here and happy to think it through with you.",
        ),
      380,
    )
  }

  useEffect(() => {
    if (!historyOpen && !settingsOpen) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setHistoryOpen(false)
        setSettingsOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [historyOpen, settingsOpen])

  const startNewChat = useCallback(() => {
    setHistoryOpen(false)
    setSelectedChatId(null)
    setSelectedChatTags([])
    setMessages([])
    setComposerDocked(false)
    setComposerText('')
    setSending(false)
  }, [])

  const canSend =
    !sending &&
    !!user &&
    !!selectedModelId &&
    workbenchModels.length > 0 &&
    composerText.trim().length > 0

  const openVirtmateVoicePage = useCallback(() => {
    const params = new URLSearchParams()
    if (selectedModelId.trim()) {
      params.set('model', selectedModelId.trim())
    }
    if (selectedChatId?.trim() && messages.length > 0) {
      params.set('chat_id', selectedChatId.trim())
    }
    navigate(`/agent/virtmate?${params.toString()}`)
  }, [messages.length, navigate, selectedChatId, selectedModelId])

  return (
    <section
      id="agent"
      className="view page-container active relative flex h-[100dvh] min-h-0 flex-col overflow-hidden"
    >
      <div
        className={`fixed right-4 z-[34] flex flex-col items-center gap-2 md:right-6 ${AGENT_FLOAT_RAIL_TOP_CLASS}`}
      >
        <button
          type="button"
          id="agent-history-toggle"
          className={`${agentSquareActionClass} -translate-y-1`}
          aria-label="Chat history"
          aria-expanded={historyOpen}
          aria-controls="agent-history-drawer"
          onClick={() => {
            setSettingsOpen(false)
            setHistoryOpen((o) => !o)
          }}
        >
          <span aria-hidden>📜</span>
        </button>
        <div
          className={`shrink-0 rounded-full bg-slate-300/90 transition-[height,width,opacity] duration-300 ease-out ${
            historyOpen ? 'pointer-events-none h-0 w-0 opacity-0' : 'h-px w-6 opacity-100'
          }`}
          aria-hidden
          role="presentation"
        />
        <button
          type="button"
          id="agent-new-chat"
          className={`${agentSquareActionClass} translate-y-1`}
          aria-label="New chat"
          onClick={startNewChat}
        >
          <span aria-hidden>➕</span>
        </button>
      </div>
      <div
        className={`fixed left-[calc(96px+0.75rem)] z-[34] flex items-center gap-2 transition-[bottom] duration-300 ease-out md:left-[calc(96px+1.25rem)] ${
          composerDocked ? 'bottom-[1.375rem] md:bottom-6' : 'bottom-4 md:bottom-6'
        }`}
      >
        <button
          type="button"
          id="agent-settings-toggle"
          className={agentSquareActionClass}
          aria-label="Open settings"
          aria-expanded={settingsOpen}
          aria-controls="agent-settings-panel"
          onClick={() => {
            setHistoryOpen(false)
            setSettingsOpen((o) => !o)
          }}
        >
          <span aria-hidden>⚙️</span>
        </button>
        <div className="w-28 md:w-32">
          <select
            id="agent-model"
            value={selectedModelId}
            onChange={(e) => setSelectedModelId(e.target.value)}
            disabled={
              !user || authLoading || modelsLoading || workbenchModels.length === 0 || sending
            }
            className="h-7 w-full rounded-md border border-slate-200 bg-white/95 px-1.5 text-xs text-slate-800 shadow-sm focus:outline-none focus:ring-2 focus:ring-sky-300 disabled:opacity-60 md:h-8"
          >
            {!user ? (
              <option value="">Please sign in</option>
            ) : modelsLoading ? (
              <option value="">Loading models...</option>
            ) : workbenchModels.length === 0 ? (
              <option value="">No models available</option>
            ) : (
              workbenchModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name}
                </option>
              ))
            )}
          </select>
        </div>
      </div>
      <div
        id="agent-history-backdrop"
        role="presentation"
        className={`fixed inset-0 left-[96px] z-[31] bg-slate-900/25 backdrop-blur-[1px] transition-opacity duration-300 ${
          historyOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={() => setHistoryOpen(false)}
        aria-hidden={!historyOpen}
      />
      <div
        id="agent-settings-backdrop"
        role="presentation"
        className={`fixed inset-0 z-[32] bg-slate-900/20 backdrop-blur-[1px] transition-opacity duration-300 ${
          settingsOpen ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'
        }`}
        onClick={() => setSettingsOpen(false)}
        aria-hidden={!settingsOpen}
      />

      <aside
        id="agent-history-drawer"
        aria-hidden={!historyOpen}
        className={`fixed bottom-0 right-0 top-0 z-[32] flex ${HISTORY_DRAWER_WIDTH_CLASS} flex-col border-l border-slate-200/80 bg-[#FAFAFA]/98 shadow-xl backdrop-blur-md transition-transform duration-300 ease-out ${
          historyOpen ? 'translate-x-0' : 'pointer-events-none translate-x-full'
        }`}
      >
        <div className="px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Chat history</h2>
        </div>
        <div
          className={`pointer-events-none absolute left-0 right-0 z-10 flex flex-col px-4 ${AGENT_FLOAT_RAIL_TOP_CLASS}`}
        >
          <div className="h-7 shrink-0 md:h-8" aria-hidden role="presentation" />
          <div
            className="flex h-4 shrink-0 flex-col justify-center"
            role="presentation"
          >
            <div className="h-px w-full rounded-full bg-slate-300/90" />
          </div>
          <div className="pointer-events-auto flex h-7 items-center justify-start text-sm font-medium leading-none text-slate-600 md:h-8">
            New chat
          </div>
        </div>
        <div
          className="h-[calc(1.25rem-3px+1.75rem+1rem+1.75rem-2.75rem)] shrink-0 md:h-[calc(1.5rem-3px+2rem+1rem+2rem-2.75rem)]"
          aria-hidden
        />
        <div className="px-3 pb-2">
          <div className="flex gap-2">
            <input
              value={historyQuery}
              onChange={(e) => setHistoryQuery(e.target.value)}
              placeholder="Search chats"
              className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
            />
            <button
              type="button"
              onClick={() => void loadHistory()}
              className="rounded-md border border-slate-200 px-2 text-xs text-slate-700 hover:bg-white"
            >
              Search
            </button>
          </div>
          {historyError ? (
            <p className="mt-1 text-[11px] text-red-600">{historyError}</p>
          ) : historyLoading ? (
            <p className="mt-1 text-[11px] text-slate-500">Loading...</p>
          ) : null}
        </div>
        <nav className="min-h-0 flex-1 overflow-y-auto px-2 pb-2 pt-1" aria-label="Chat history list">
          <ul className="flex flex-col gap-1">
            {historyRows.map((row) => (
              <li key={row.id}>
                <div
                  className={`rounded-xl px-3 py-2 text-left text-sm transition-colors ${
                    selectedChatId === row.id ? 'bg-white shadow-sm' : 'hover:bg-white/80'
                  }`}
                >
                  <button type="button" className="w-full text-left" onClick={() => void onSelectHistory(row)}>
                    <span className="block font-medium text-slate-700">{row.title}</span>
                    <span className="mt-0.5 block text-xs text-slate-500">
                      {row.updatedAt || 'No timestamp'}
                    </span>
                  </button>
                  <div className="mt-1 flex gap-1 text-[11px]">
                    <button type="button" className="text-sky-700 hover:underline" onClick={() => void onTogglePin(row.id)}>
                      {row.pinned ? 'Unpin' : 'Pin'}
                    </button>
                    <button type="button" className="text-sky-700 hover:underline" onClick={() => void onToggleArchive(row.id)}>
                      {row.archived ? 'Unarchive' : 'Archive'}
                    </button>
                    <button type="button" className="text-sky-700 hover:underline" onClick={() => void onRenameHistory(row)}>
                      Rename
                    </button>
                    <button type="button" className="text-rose-700 hover:underline" onClick={() => void onDeleteHistory(row)}>
                      Delete
                    </button>
                  </div>
                </div>
              </li>
            ))}
            {!historyLoading && historyRows.length === 0 ? (
              <li className="px-3 py-2 text-xs text-slate-500">No chats yet</li>
            ) : null}
          </ul>
        </nav>
        {selectedChatId ? (
          <div className="border-t border-slate-200/80 px-3 py-2">
            <div className="flex flex-wrap gap-1">
              {selectedChatTags.map((t) => (
                <span key={t.name} className="rounded-full bg-sky-50 px-2 py-0.5 text-[11px] text-sky-700">
                  #{t.name}
                </span>
              ))}
            </div>
            <div className="mt-1 flex gap-1">
              <input
                value={newTagName}
                onChange={(e) => setNewTagName(e.target.value)}
                placeholder="Add tag"
                className="h-7 min-w-0 flex-1 rounded-md border border-slate-200 px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
              />
              <button type="button" onClick={() => void onAddTag()} className="rounded-md border border-slate-200 px-2 text-xs hover:bg-white">
                Add
              </button>
            </div>
          </div>
        ) : null}
      </aside>
      <aside
        id="agent-settings-panel"
        aria-hidden={!settingsOpen}
        className={`fixed bottom-[4.5rem] left-[calc(96px+1rem)] z-[33] w-[min(24rem,calc(100vw-96px-2rem))] rounded-2xl border border-slate-200/90 bg-white/95 p-3 shadow-xl backdrop-blur-md transition-all duration-300 md:bottom-[5rem] md:left-[calc(96px+1.5rem)] md:w-[min(24rem,calc(100vw-96px-3rem))] ${
          settingsOpen
            ? 'pointer-events-auto translate-y-0 opacity-100'
            : 'pointer-events-none translate-y-2 opacity-0'
        }`}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-800">Agent settings</h2>
          <button
            type="button"
            className="rounded-md border border-slate-200 px-2 py-1 text-xs text-slate-600 hover:bg-slate-50"
            onClick={() => setSettingsOpen(false)}
          >
            Close
          </button>
        </div>
        <div className="max-h-[min(62vh,32rem)] overflow-y-auto rounded-xl border border-slate-200/70 bg-slate-50/50 p-3">
          <div className="flex flex-col gap-2 rounded-2xl border border-slate-200/80 bg-white/55 px-4 py-3">
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="agent-prompt" className="text-xs font-medium text-slate-600">
                Prompt
              </label>
              <select
                id="agent-prompt"
                value={selectedPromptId}
                onChange={(e) => setSelectedPromptId(e.target.value)}
                className="min-w-[10rem] flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
              >
                <option value="">None</option>
                {prompts.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={onApplyPrompt}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
              >
                Apply
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="agent-tool" className="text-xs font-medium text-slate-600">
                Tool
              </label>
              <select
                id="agent-tool"
                value={selectedToolId}
                onChange={(e) => setSelectedToolId(e.target.value)}
                className="min-w-[10rem] flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
              >
                <option value="">No tool selected</option>
                {tools.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void onReadToolValves()}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
              >
                Load config
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor="agent-folder" className="text-xs font-medium text-slate-600">
                Folder
              </label>
              <select
                id="agent-folder"
                value={selectedFolderId}
                onChange={(e) => setSelectedFolderId(e.target.value)}
                className="min-w-[10rem] flex-1 rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-xs"
              >
                <option value="">Default folder</option>
                {folders.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex items-center gap-2">
              <input
                value={memoryInput}
                onChange={(e) => setMemoryInput(e.target.value)}
                placeholder="Query or add memory"
                className="h-8 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-2 text-xs outline-none focus:ring-2 focus:ring-sky-300"
              />
              <button
                type="button"
                onClick={() => void onQueryMemory()}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
              >
                Query
              </button>
              <button
                type="button"
                onClick={() => void onCreateMemory()}
                className="rounded-md border border-slate-200 px-2 py-1 text-xs hover:bg-white"
              >
                Add
              </button>
            </div>
            {memoryStatus ? <p className="text-xs text-slate-600">{memoryStatus}</p> : null}
            {capabilityNote ? <p className="text-xs text-amber-700">{capabilityNote}</p> : null}
            {memories.length > 0 ? (
              <p className="text-[11px] text-slate-500">Memories: {memories.length} items</p>
            ) : null}
          </div>
        </div>
      </aside>
      <div
        id="agent-thread-scroll"
        ref={threadScrollRef}
        onScroll={onThreadScroll}
        className={`min-h-0 flex-1 overflow-y-auto px-6 md:px-8 ${
          composerDocked ? 'pb-40 pt-6' : 'pb-[min(46vh,20rem)] pt-8 md:pt-10'
        }`}
      >
        <div id="chat-messages">
          {messages.map((msg, i) => (
            <div
              key={`${i}-${msg.text.slice(0, 20)}`}
              className={
                msg.role === 'user'
                  ? 'bubble me mr-[2.75rem] md:mr-[2.75rem]'
                  : 'bubble ai glass'
              }
              data-role={msg.role === 'user' ? 'user' : 'assistant'}
            >
              {msg.role === 'assistant' && msg.reasoning ? (
                <details className="mb-2 rounded-lg border border-slate-200/80 bg-slate-50/60 p-2 text-xs text-slate-700">
                  <summary className="cursor-pointer select-none text-[11px] font-medium text-slate-500">
                    Reasoning
                  </summary>
                  <pre className="mt-1 whitespace-pre-wrap break-words font-sans">{msg.reasoning}</pre>
                </details>
              ) : null}
              {msg.role === 'assistant' ? (
                <AssistantMarkdown content={msg.text} />
              ) : (
                <div className="whitespace-pre-wrap break-words">{msg.text}</div>
              )}
            </div>
          ))}
          <div ref={messagesEndRef} />
        </div>
      </div>

      <div
        id="agent-composer-shell"
        className={`agent-composer-shell${composerDocked ? ' is-docked' : ' is-intro'}`}
      >
        <div className="w-full px-6 md:px-8">
          <form
            id="agent-form"
            className="flex w-full flex-col gap-3"
            onSubmit={onFormSubmit}
          >
            {!composerDocked && (
              <div
                id="agent-header"
                className="agent-intro-title text-center text-lg text-slate-700 md:text-xl"
              >
                Hello I&apos;m Baymax, your personal healthcare companion
              </div>
            )}
            {submitHint ? (
              <p className="text-xs text-amber-700" role="status">
                {submitHint}
              </p>
            ) : null}
            {!modelsError && !authLoading && user && !modelsLoading && workbenchModels.length === 0 ? (
              <p className="text-xs text-slate-500">
                No models found. Make sure Open WebUI is running and mid-auth downstream is configured.
              </p>
            ) : null}
            <div className="ml-[8.75rem] flex w-[calc(100%-8.75rem)] min-w-0 items-center gap-2 md:ml-[10.5rem] md:w-[calc(100%-10.5rem)]">
              <div className="agent-liquid-input-wrap h-12 min-w-0 flex-1 md:h-14">
                <input
                  id="agent-input"
                  type="text"
                  value={composerText}
                  onChange={(e: ChangeEvent<HTMLInputElement>) =>
                    setComposerText(e.target.value)
                  }
                  disabled={sending}
                  className="agent-liquid-input"
                  placeholder={
                    composerDocked ? 'Type a message' : 'Type and press Enter or choose a capsule'
                  }
                  onKeyDown={(e: ReactKeyboardEvent<HTMLInputElement>) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      e.currentTarget.form?.requestSubmit()
                    }
                  }}
                />
              </div>
              <button
                type="button"
                id="agent-chat-mic"
                className="btn flex h-10 w-10 shrink-0 items-center justify-center !px-0 text-base"
                aria-label="Voice input"
                disabled={sending}
                onClick={openVirtmateVoicePage}
              >
                <span aria-hidden>🎤</span>
              </button>
              <button
                type="submit"
                id="agent-chat-send"
                className="btn h-10 shrink-0 px-4 text-sm disabled:cursor-not-allowed disabled:border-slate-300 disabled:bg-slate-200 disabled:text-slate-400"
                disabled={!canSend}
              >
                {sending ? '…' : 'Send'}
              </button>
            </div>
            {modelsError ? (
              <p className="text-[10px] leading-tight text-red-600" role="alert">
                {modelsError}
              </p>
            ) : null}
            {!composerDocked && (
              <div className="mt-3 flex flex-wrap items-center justify-center gap-3 md:mt-4">
                {CAPSULES.map(({ tip, quick, label }) => (
                  <button
                    key={quick}
                    type="button"
                    className="capsule glass agent-capsule"
                    data-tip={tip}
                    onClick={() => onCapsule(quick)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </form>
        </div>
      </div>
    </section>
  )
}
