import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  virtmateClient,
  type VirtmateDigitalProfile,
  type VirtmateSessionSettings,
} from '../lib/virtmateClient'

const GPT_SOVITS_LANG_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'auto', label: 'auto（多语种混合）' },
  { value: 'auto_yue', label: 'auto_yue（多语种混合-粤语）' },
  { value: 'en', label: 'en（英文）' },
  { value: 'zh', label: 'zh（中英混合）' },
  { value: 'ja', label: 'ja（日英混合）' },
  { value: 'yue', label: 'yue（粤英混合）' },
  { value: 'ko', label: 'ko（韩英混合）' },
  { value: 'all_zh', label: 'all_zh（全中文）' },
  { value: 'all_ja', label: 'all_ja（全日文）' },
  { value: 'all_yue', label: 'all_yue（全粤语）' },
  { value: 'all_ko', label: 'all_ko（全韩文）' },
]

// 顶部「WS状态 + 设置」控件组位置（按当前微调结果固定）
const LIVE2D_TOP_CONTROLS_OFFSET_X_CLASS = '-translate-x-[18px]'
const LIVE2D_TOP_CONTROLS_OFFSET_Y_CLASS = 'translate-y-2'
const LIVE2D_TOP_CONTROLS_ROW_CLASS = `${LIVE2D_TOP_CONTROLS_OFFSET_X_CLASS} ${LIVE2D_TOP_CONTROLS_OFFSET_Y_CLASS} flex items-center justify-end gap-2.5`
const LIVE2D_SETTINGS_BUTTON_CLASS =
  'inline-flex size-8 items-center justify-center rounded-md border border-slate-300 bg-white text-sm shadow-sm hover:bg-slate-50'
const LIVE2D_STATUS_ICON_BUTTON_CLASS =
  'inline-flex size-8 items-center justify-center rounded-md border border-slate-300 bg-white text-sm shadow-sm hover:bg-slate-50'

function normalizeAudioUrl(url: string): string {
  if (!url) return url
  if (/^https?:\/\//i.test(url)) return url
  if (url.startsWith('/')) return `${virtmateClient.apiOrigin}${url}`
  return `${virtmateClient.apiOrigin}/${url}`
}

function resolveInitialModelId(): string {
  const search = new URLSearchParams(window.location.search)
  const fromQuery = (search.get('model') || '').trim()
  if (fromQuery) return fromQuery
  return localStorage.getItem('virtmate_model_id') || ''
}

function createAutoSessionId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return `sess-${crypto.randomUUID()}`
    }
  } catch {
    // ignore and fallback
  }
  const rand = Math.random().toString(36).slice(2, 10)
  return `sess-${Date.now().toString(36)}-${rand}`
}

function resolveInitialSessionId(): string {
  const search = new URLSearchParams(window.location.search)
  const fromQuery = (search.get('session_id') || '').trim()
  if (fromQuery) {
    sessionStorage.setItem('virtmate_session_id_tab', fromQuery)
    return fromQuery
  }
  const fromTab = (sessionStorage.getItem('virtmate_session_id_tab') || '').trim()
  if (fromTab) return fromTab
  const generated = createAutoSessionId()
  sessionStorage.setItem('virtmate_session_id_tab', generated)
  return generated
}

function resolveInitialConversationId(): string {
  const search = new URLSearchParams(window.location.search)
  const fromChatId = (search.get('chat_id') || '').trim()
  if (fromChatId) return fromChatId
  const fromConversationId = (search.get('conversation_id') || '').trim()
  if (fromConversationId) return fromConversationId
  return ''
}

type ProfileEditorDraft = {
  title: string
  gptSovitsPrompt: string
  refTranscript: string
  gptSovitsLang: string
  llmPrompt: string
  refAudioPath: string
  live2dModelPath: string
}

function createEmptyProfileDraft(): ProfileEditorDraft {
  return {
    title: '',
    gptSovitsPrompt: '',
    refTranscript: '',
    gptSovitsLang: 'zh',
    llmPrompt: '',
    refAudioPath: '',
    live2dModelPath: '',
  }
}

async function loadCubismScript(src: string): Promise<void> {
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script')
    script.src = src
    script.async = true
    script.dataset.live2dCubismCore = 'true'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('Cubism Core 脚本加载失败'))
    document.head.appendChild(script)
  })
}

async function ensureCubismCoreLoaded(src: string): Promise<void> {
  const win = window as unknown as { Live2DCubismCore?: unknown }
  if (win.Live2DCubismCore) return

  const existing = document.querySelector(
    'script[data-live2d-cubism-core="true"]',
  ) as HTMLScriptElement | null
  if (existing) {
    await new Promise<void>((resolve, reject) => {
      if (win.Live2DCubismCore) {
        resolve()
        return
      }
      const onLoad = () => resolve()
      const onError = () => reject(new Error('Cubism Core 脚本加载失败'))
      existing.addEventListener('load', onLoad, { once: true })
      existing.addEventListener('error', onError, { once: true })
    })
    if (!win.Live2DCubismCore) {
      throw new Error('Cubism Core 未初始化')
    }
    return
  }

  try {
    await loadCubismScript(src)
  } catch {
    // Fallback to current frontend origin when assetOrigin points elsewhere.
    const fallback = (() => {
      try {
        const parsed = new URL(src, window.location.origin)
        return `${window.location.origin}${parsed.pathname}`
      } catch {
        return src
      }
    })()
    if (fallback !== src) {
      await loadCubismScript(fallback)
    } else {
      throw new Error('Cubism Core 脚本加载失败')
    }
  }
  if (!win.Live2DCubismCore) {
    throw new Error('Cubism Core 未初始化')
  }
}

export function AgentVirtmatePage() {
  const navigate = useNavigate()
  const [wsState, setWsState] = useState('未连接')
  const [chatStatus, setChatStatus] = useState('idle')
  const [voiceStatus, setVoiceStatus] = useState('')
  const [sessionId] = useState(resolveInitialSessionId)
  const [userId] = useState(localStorage.getItem('virtmate_user_id') || '')
  const [modelId] = useState(resolveInitialModelId)
  const [conversationId, setConversationId] = useState(resolveInitialConversationId)
  const [textInput, setTextInput] = useState('')
  const [lastTtsAudioUrl, setLastTtsAudioUrl] = useState('')
  const [recording, setRecording] = useState(false)
  const [autoVoiceMode, setAutoVoiceMode] = useState(false)
  const [live2dError, setLive2dError] = useState<string | null>(null)
  const [live2dSettingsEntryOpen, setLive2dSettingsEntryOpen] = useState(false)
  const [profilesLoading, setProfilesLoading] = useState(false)
  const [profiles, setProfiles] = useState<VirtmateDigitalProfile[]>([])
  const [activeProfileId, setActiveProfileId] = useState('')
  const [settingsStatus, setSettingsStatus] = useState<string | null>(null)
  const [settingsView, setSettingsView] = useState<'list' | 'editor'>('list')
  const [editorProfileId, setEditorProfileId] = useState<string | null>(null)
  const [editorDraft, setEditorDraft] = useState<ProfileEditorDraft>(createEmptyProfileDraft)
  const [asrRecognizing, setAsrRecognizing] = useState(false)
  const [controlsExpanded, setControlsExpanded] = useState(false)
  const [statusPopoverOpen, setStatusPopoverOpen] = useState(false)
  const [contextMenu, setContextMenu] = useState<{
    profileId: string
    x: number
    y: number
  } | null>(null)
  const [settings, setSettings] = useState<VirtmateSessionSettings>({
    tts_engine: '云端edge-tts',
    cam_permission: '关闭',
    username: '',
    mate_name: '',
    prompt: '',
  })

  const wsRef = useRef<WebSocket | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const mediaStreamRef = useRef<MediaStream | null>(null)
  const audioContextRef = useRef<AudioContext | null>(null)
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)
  const currentAudioBlobUrlRef = useRef<string | null>(null)
  const lastTtsPlayKeyRef = useRef('')
  const lastTtsPlayAtRef = useRef(0)
  const vadFrameRef = useRef<number | null>(null)
  const autoRestartTimerRef = useRef<number | null>(null)
  const autoVoiceModeRef = useRef(false)
  const audioPlaybackActiveRef = useRef(false)
  const waitingTtsRef = useRef(false)
  const chunksRef = useRef<Blob[]>([])
  const live2dRootRef = useRef<HTMLDivElement>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const live2dAppRef = useRef<any>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const live2dModelRef = useRef<any>(null)
  const mouthPollRef = useRef<number | null>(null)
  const profileRailRef = useRef<HTMLDivElement | null>(null)

  const isMidAuthMode = virtmateClient.mode === 'midauth'

  useEffect(() => {
    autoVoiceModeRef.current = autoVoiceMode
  }, [autoVoiceMode])

  const persistSessionKeys = useCallback(
    (next: { session?: string; user?: string; model?: string; conversation?: string }) => {
      if (next.session !== undefined) sessionStorage.setItem('virtmate_session_id_tab', next.session)
      if (next.user !== undefined) localStorage.setItem('virtmate_user_id', next.user)
      if (next.model !== undefined) localStorage.setItem('virtmate_model_id', next.model)
      if (next.conversation !== undefined) localStorage.setItem('virtmate_conversation_id', next.conversation)
    },
    [],
  )

  const loadSettings = useCallback(async () => {
    const s = await virtmateClient.getSessionSettings(sessionId)
    setSettings((prev) => ({
      ...prev,
      tts_engine: s.tts_engine ?? prev.tts_engine,
      cam_permission: s.cam_permission ?? prev.cam_permission,
      username: s.username ?? '',
      mate_name: s.mate_name ?? '',
      prompt: s.prompt ?? '',
    }))
  }, [sessionId])

  const loadProfiles = useCallback(async () => {
    setProfilesLoading(true)
    try {
      const result = await virtmateClient.listProfiles()
      const allProfiles = Array.isArray(result.profiles) ? result.profiles : []
      // 内置默认 profile 由右侧固定卡片展示，列表只保留可编辑的自定义项。
      setProfiles(allProfiles.filter((p) => String(p.id || '').trim() !== 'default'))
      setActiveProfileId(result.activeProfileId || '')
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '加载 profile 失败')
    } finally {
      setProfilesLoading(false)
    }
  }, [])

  const clearAutoRestartTimer = useCallback(() => {
    if (autoRestartTimerRef.current) {
      window.clearTimeout(autoRestartTimerRef.current)
      autoRestartTimerRef.current = null
    }
  }, [])

  const cleanupVoiceDetection = useCallback(() => {
    if (vadFrameRef.current) {
      window.cancelAnimationFrame(vadFrameRef.current)
      vadFrameRef.current = null
    }
    if (audioContextRef.current) {
      void audioContextRef.current.close().catch(() => {
        // ignore
      })
      audioContextRef.current = null
    }
  }, [])

  const cleanupRecorderResources = useCallback(() => {
    cleanupVoiceDetection()
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop())
      mediaStreamRef.current = null
    }
    recorderRef.current = null
    chunksRef.current = []
  }, [cleanupVoiceDetection])

  const queueAutoListen = useCallback(
    (delayMs = 450) => {
      clearAutoRestartTimer()
      if (!autoVoiceModeRef.current) return
      autoRestartTimerRef.current = window.setTimeout(() => {
        autoRestartTimerRef.current = null
        if (!autoVoiceModeRef.current || recorderRef.current || audioPlaybackActiveRef.current) return
        void onStartRecord({ autoStop: true })
      }, delayMs)
    },
    [clearAutoRestartTimer],
  )

  const playTtsAudio = useCallback(
    (rawUrl: string, options?: { force?: boolean }) => {
      const audioUrl = String(rawUrl || '').trim()
      if (!audioUrl) return
      const dedupeKey = normalizeAudioUrl(audioUrl)
      const now = Date.now()
      // 去重：同一条 TTS 往往会从 chat/send + ws tts.ready 各触发一次。
      if (!options?.force && dedupeKey === lastTtsPlayKeyRef.current && now - lastTtsPlayAtRef.current < 2500) {
        return
      }
      lastTtsPlayKeyRef.current = dedupeKey
      lastTtsPlayAtRef.current = now
      setLastTtsAudioUrl(audioUrl)
      waitingTtsRef.current = false
      clearAutoRestartTimer()
      audioPlaybackActiveRef.current = true
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current.currentTime = 0
      }
      if (currentAudioBlobUrlRef.current) {
        URL.revokeObjectURL(currentAudioBlobUrlRef.current)
        currentAudioBlobUrlRef.current = null
      }
      void (async () => {
        let resolvedUrl = normalizeAudioUrl(audioUrl)
        if (isMidAuthMode) {
          try {
            const res = await fetch(resolvedUrl, { credentials: 'include' })
            if (res.ok) {
              const blob = await res.blob()
              const blobUrl = URL.createObjectURL(blob)
              currentAudioBlobUrlRef.current = blobUrl
              resolvedUrl = blobUrl
            } else {
              setVoiceStatus(`语音资源获取失败（HTTP ${res.status}）`)
            }
          } catch (err) {
            const detail =
              err instanceof Error && err.message ? ` (${err.message.slice(0, 120)})` : ''
            setVoiceStatus(`语音资源获取失败${detail}`)
          }
        }
        const audio = new Audio(resolvedUrl)
        audio.preload = 'auto'
        currentAudioRef.current = audio
        void virtmateClient.postPlaybackState({ session_id: sessionId, is_playing: true })
        audio.onended = () => {
          currentAudioRef.current = null
          if (currentAudioBlobUrlRef.current) {
            URL.revokeObjectURL(currentAudioBlobUrlRef.current)
            currentAudioBlobUrlRef.current = null
          }
          audioPlaybackActiveRef.current = false
          void virtmateClient.postPlaybackState({ session_id: sessionId, is_playing: false, mouth_y: 0 })
          if (autoVoiceModeRef.current) {
            setVoiceStatus('回答结束，继续监听...')
            queueAutoListen(250)
          }
        }
        audio.onerror = () => {
          currentAudioRef.current = null
          if (currentAudioBlobUrlRef.current) {
            URL.revokeObjectURL(currentAudioBlobUrlRef.current)
            currentAudioBlobUrlRef.current = null
          }
          audioPlaybackActiveRef.current = false
          void virtmateClient.postPlaybackState({ session_id: sessionId, is_playing: false, mouth_y: 0 })
          const mediaErrorCode = audio.error?.code ? ` (MediaError ${audio.error.code})` : ''
          setVoiceStatus(`语音播放失败${mediaErrorCode}，可点击“播放上次语音”重试`)
          if (autoVoiceModeRef.current) {
            setVoiceStatus('语音播放失败，继续监听...')
            queueAutoListen(250)
          }
        }
        void audio.play().catch((err: unknown) => {
          currentAudioRef.current = null
          audioPlaybackActiveRef.current = false
          void virtmateClient.postPlaybackState({ session_id: sessionId, is_playing: false, mouth_y: 0 })
          const detail =
            err instanceof Error && err.message ? ` (${err.message.slice(0, 120)})` : ''
          setVoiceStatus(`浏览器阻止自动播报或地址无效${detail}，可点击“播放上次语音”`)
          if (autoVoiceModeRef.current) {
            setVoiceStatus('浏览器阻止自动播报，继续监听...')
            queueAutoListen(250)
          }
        })
      })()
    },
    [clearAutoRestartTimer, isMidAuthMode, queueAutoListen, sessionId],
  )

  const onReplayLastTts = useCallback(() => {
    if (!lastTtsAudioUrl) {
      setVoiceStatus('暂无可播放语音')
      return
    }
    playTtsAudio(lastTtsAudioUrl, { force: true })
  }, [lastTtsAudioUrl, playTtsAudio])

  const sendChatText = useCallback(
    async (rawText: string, options?: { auto?: boolean }) => {
      const text = rawText.trim()
      if (!text) return false
      if (!modelId.trim()) {
        setChatStatus('请填写模型 ID')
        return false
      }
      if (!isMidAuthMode && !userId.trim()) {
        setChatStatus('请填写 user-id（直连模式需要）')
        return false
      }
      if (!options?.auto) setTextInput('')
      try {
        const ttsEnabled = (settings.tts_engine || '').trim() !== '关闭语音合成'
        if (options?.auto) {
          waitingTtsRef.current = ttsEnabled
          if (ttsEnabled) {
            clearAutoRestartTimer()
            autoRestartTimerRef.current = window.setTimeout(() => {
              autoRestartTimerRef.current = null
              if (!autoVoiceModeRef.current || audioPlaybackActiveRef.current || !waitingTtsRef.current) return
              waitingTtsRef.current = false
              setVoiceStatus('未检测到语音播报，继续监听...')
              queueAutoListen(300)
            }, 4000)
          }
        }
        const data = await virtmateClient.sendChat(
          {
            session_id: sessionId,
            text,
            with_tts: true,
            stream: true,
            model: modelId.trim(),
            conversation_id: conversationId.trim() || null,
          },
          userId,
        )
        if (data.tts_audio_url) {
          playTtsAudio(data.tts_audio_url)
          if (data.tts_ref_audio_requested) {
            if (data.tts_ref_audio_used) {
              setVoiceStatus('已使用参考音频')
            } else {
              setVoiceStatus('本次未使用参考音频，请检查配置')
            }
          }
        } else if ((settings.tts_engine || '').trim() !== '关闭语音合成') {
          const reason = data.tts_error ? `：${data.tts_error}` : ''
          setVoiceStatus(`后端未返回可播放语音${reason}`)
        }
        const nextConversationId = String(data.conversation_id || '').trim()
        if (nextConversationId) {
          setConversationId(nextConversationId)
          setChatStatus('done')
        } else if (!conversationId.trim()) {
          setChatStatus('发送成功，但后端未返回 conversation_id')
        } else {
          setChatStatus('done')
        }
        if (options?.auto && !ttsEnabled) {
          setVoiceStatus('回答完成，继续监听...')
          queueAutoListen(350)
        }
        return true
      } catch (e) {
        setChatStatus(e instanceof Error ? e.message : '发送失败')
        if (options?.auto && autoVoiceModeRef.current) {
          setVoiceStatus('发送失败，稍后重试监听')
          queueAutoListen(1000)
        }
        return false
      }
    },
    [
      clearAutoRestartTimer,
      conversationId,
      isMidAuthMode,
      modelId,
      queueAutoListen,
      sessionId,
      settings.tts_engine,
      playTtsAudio,
      userId,
    ],
  )

  const connectWs = useCallback(() => {
    wsRef.current?.close()
    const socket = virtmateClient.createEventsSocket(sessionId)
    wsRef.current = socket
    socket.onopen = () => setWsState('已连接')
    socket.onclose = () => setWsState('已断开')
    socket.onerror = () => setWsState('连接异常')
    socket.onmessage = (evt) => {
      const payload = JSON.parse(evt.data)
      if (payload.type === 'chat.status') setChatStatus(String(payload.data?.status || 'idle'))
      if (payload.type === 'tts.ready' && payload.data?.audio_url) {
        playTtsAudio(String(payload.data.audio_url))
      }
    }
  }, [playTtsAudio, sessionId])

  useEffect(() => {
    persistSessionKeys({
      session: sessionId,
      user: userId,
      model: modelId,
      conversation: conversationId,
    })
  }, [sessionId, userId, modelId, conversationId, persistSessionKeys])

  useEffect(() => {
    void loadSettings().catch(() => {
      // ignore settings load error in current UI
    })
    void loadProfiles().catch(() => {
      // ignore global config load error in current UI
    })
    connectWs()
    return () => {
      wsRef.current?.close()
      clearAutoRestartTimer()
      cleanupRecorderResources()
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current.currentTime = 0
        currentAudioRef.current = null
      }
      if (currentAudioBlobUrlRef.current) {
        URL.revokeObjectURL(currentAudioBlobUrlRef.current)
        currentAudioBlobUrlRef.current = null
      }
    }
  }, [connectWs, loadProfiles, loadSettings])

  const onStartRecord = useCallback(async (options?: { autoStop?: boolean }) => {
    if (recorderRef.current) return
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      mediaStreamRef.current = stream
      const recorder = new MediaRecorder(stream)
      recorderRef.current = recorder
      chunksRef.current = []
      recorder.ondataavailable = (evt) => chunksRef.current.push(evt.data)
      recorder.onstop = async () => {
        const shouldAutoContinue = autoVoiceModeRef.current
        const mimeType = recorder.mimeType || 'audio/webm'
        const recordedChunks = chunksRef.current.slice()
        cleanupRecorderResources()
        setRecording(false)
        try {
          const blob = new Blob(recordedChunks, { type: mimeType })
          const ext = mimeType.includes('ogg') ? 'ogg' : 'webm'
          const text = await virtmateClient.recognizeAsr(blob, sessionId, `voice.${ext}`)
          setTextInput(text)
          if (!shouldAutoContinue) {
            setVoiceStatus(text ? '识别成功' : '未识别到文字')
            return
          }
          if (!text.trim()) {
            setVoiceStatus('未识别到文字，继续监听...')
            queueAutoListen(300)
            return
          }
          setVoiceStatus('识别成功，正在发送...')
          await sendChatText(text, { auto: true })
        } catch (e) {
          setVoiceStatus(e instanceof Error ? e.message : '识别失败')
          if (shouldAutoContinue) queueAutoListen(900)
        }
      }
      recorder.start()
      if (options?.autoStop) {
        const AudioCtx = window.AudioContext
        if (!AudioCtx) {
          throw new Error('当前浏览器不支持自动语音模式')
        }
        const ctx = new AudioCtx()
        const source = ctx.createMediaStreamSource(stream)
        const analyser = ctx.createAnalyser()
        analyser.fftSize = 2048
        analyser.smoothingTimeConstant = 0.85
        source.connect(analyser)
        audioContextRef.current = ctx

        const samples = new Uint8Array(analyser.fftSize)
        const startedAt = performance.now()
        let heardSpeech = false
        let lastVoiceAt = startedAt
        const minRecordMs = 900
        const maxRecordMs = 15000
        const silenceMs = 1200
        const threshold = 0.02
        const detect = () => {
          if (recorder.state === 'inactive') return
          analyser.getByteTimeDomainData(samples)
          let sum = 0
          for (const value of samples) {
            const normalized = (value - 128) / 128
            sum += normalized * normalized
          }
          const rms = Math.sqrt(sum / samples.length)
          const now = performance.now()
          if (rms >= threshold) {
            heardSpeech = true
            lastVoiceAt = now
          }
          if (heardSpeech && now - lastVoiceAt >= silenceMs && now - startedAt >= minRecordMs) {
            recorder.stop()
            return
          }
          if (now - startedAt >= maxRecordMs) {
            recorder.stop()
            return
          }
          vadFrameRef.current = window.requestAnimationFrame(detect)
        }
        vadFrameRef.current = window.requestAnimationFrame(detect)
      }
      setRecording(true)
      setVoiceStatus(options?.autoStop ? '自动监听中，请开始说话...' : '录音中...')
    } catch (e) {
      cleanupRecorderResources()
      setVoiceStatus(e instanceof Error ? e.message : '无法开始录音')
      if (options?.autoStop) setAutoVoiceMode(false)
    }
  }, [cleanupRecorderResources, queueAutoListen, sendChatText, sessionId])

  const onStopRecord = useCallback(() => {
    if (!recorderRef.current || recorderRef.current.state === 'inactive' || !recording) return
    recorderRef.current.stop()
    setVoiceStatus('录音已停止，识别中...')
  }, [recording])

  const onSendChat = useCallback(async () => {
    await sendChatText(textInput)
  }, [sendChatText, textInput])

  const onStartAutoVoiceMode = useCallback(async () => {
    if (autoVoiceMode) return
    setAutoVoiceMode(true)
    setVoiceStatus('自动语音模式已开启，准备监听...')
    await onStartRecord({ autoStop: true })
  }, [autoVoiceMode, onStartRecord])

  const onStopAutoVoiceMode = useCallback(() => {
    setAutoVoiceMode(false)
    waitingTtsRef.current = false
    clearAutoRestartTimer()
    if (recorderRef.current && recorderRef.current.state !== 'inactive') {
      recorderRef.current.stop()
    } else {
      cleanupRecorderResources()
      setRecording(false)
    }
    setVoiceStatus('自动语音模式已关闭')
  }, [cleanupRecorderResources, clearAutoRestartTimer])

  const onCreateProfileEntry = useCallback(() => {
    setEditorProfileId(null)
    setEditorDraft(createEmptyProfileDraft())
    setSettingsView('editor')
    setContextMenu(null)
  }, [])

  const onEditProfileEntry = useCallback((profileId: string) => {
    const hit = profiles.find((p) => p.id === profileId)
    if (!hit) return
    setEditorProfileId(profileId)
    const existingPrompt = hit.gpt_sovits_prompt || ''
    setEditorDraft({
      title: hit.title || '',
      gptSovitsPrompt: '',
      refTranscript: existingPrompt,
      gptSovitsLang: hit.gpt_sovits_lang || 'zh',
      llmPrompt: hit.llm_prompt || '',
      refAudioPath: hit.ref_audio_path || '',
      live2dModelPath: hit.live2d_model_path || '',
    })
    setSettingsView('editor')
    setContextMenu(null)
  }, [profiles])

  const onActivateProfileEntry = useCallback(async (profileId: string) => {
    try {
      await virtmateClient.activateProfile(profileId)
      setActiveProfileId(profileId)
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '切换 profile 失败')
    }
  }, [])

  const onDeleteProfileEntry = useCallback(async (profileId: string) => {
    try {
      await virtmateClient.deleteProfile(profileId)
      await loadProfiles()
      setContextMenu(null)
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '删除 profile 失败')
    }
  }, [loadProfiles])

  const onMoveProfileEntry = useCallback(async (profileId: string, direction: 'forward' | 'backward') => {
    try {
      await virtmateClient.moveProfile(profileId, direction)
      await loadProfiles()
      setContextMenu(null)
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '移动 profile 失败')
    }
  }, [loadProfiles])

  const onSaveProfileEntry = useCallback(async () => {
    const refTranscript = editorDraft.refTranscript.trim()
    const extraPrompt = editorDraft.gptSovitsPrompt.trim()
    const resolvedPrompt = refTranscript && extraPrompt ? `${refTranscript}\n${extraPrompt}` : refTranscript || extraPrompt
    const payload = {
      title: editorDraft.title.trim(),
      gpt_sovits_prompt: resolvedPrompt,
      gpt_sovits_lang: editorDraft.gptSovitsLang.trim() || 'zh',
      llm_prompt: editorDraft.llmPrompt.trim(),
      ref_audio_path: editorDraft.refAudioPath.trim(),
      live2d_model_path: editorDraft.live2dModelPath.trim(),
    }
    try {
      let savedProfileId = editorProfileId || ''
      if (editorProfileId) {
        const updated = await virtmateClient.updateProfile(editorProfileId, payload)
        savedProfileId = String(updated.id || editorProfileId).trim() || editorProfileId
      } else {
        const created = await virtmateClient.createProfile(payload)
        savedProfileId = String(created.id || '').trim()
      }
      if (savedProfileId) {
        await virtmateClient.activateProfile(savedProfileId)
        setActiveProfileId(savedProfileId)
      }
      await loadProfiles()
      setSettingsView('list')
      setEditorProfileId(null)
      setEditorDraft(createEmptyProfileDraft())
      setSettingsStatus('已保存并激活当前 profile（参考文本/参考音频已提交）')
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '保存 profile 失败')
    }
  }, [editorDraft, editorProfileId, loadProfiles])

  const onCancelProfileEdit = useCallback(() => {
    setSettingsView('list')
    setEditorProfileId(null)
    setEditorDraft(createEmptyProfileDraft())
    setSettingsStatus(null)
  }, [])

  const onUploadRefAudio = useCallback(async (file: File) => {
    try {
      const path = await virtmateClient.uploadProfileRefAudio(file)
      setEditorDraft((prev) => ({ ...prev, refAudioPath: path }))
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '上传参考音频失败')
    }
  }, [])

  const onRemoveRefAudio = useCallback(async () => {
    const refPath = editorDraft.refAudioPath.trim()
    if (!refPath) {
      setSettingsStatus('当前没有参考音频可删除')
      return
    }
    if (!window.confirm('确认删除当前参考音频吗？')) return
    try {
      if (refPath.startsWith('/me/virtmate/profile-assets/audio/')) {
        await virtmateClient.deleteProfileRefAudio(refPath)
      }
      setEditorDraft((prev) => ({ ...prev, refAudioPath: '' }))
      setSettingsStatus('已删除参考音频，请点击“完成”保存 profile')
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '删除参考音频失败')
    }
  }, [editorDraft.refAudioPath])

  const onRecognizeRefAudioText = useCallback(async () => {
    const refPath = editorDraft.refAudioPath.trim()
    if (!refPath) {
      setSettingsStatus('请先上传参考音频')
      return
    }
    try {
      setAsrRecognizing(true)
      setSettingsStatus('ASR 识别中...')
      const src = normalizeAudioUrl(refPath)
      const res = await fetch(src, isMidAuthMode ? { credentials: 'include' } : undefined)
      if (!res.ok) throw new Error(`读取参考音频失败: ${res.status}`)
      const blob = await res.blob()
      if (!blob.size) throw new Error('参考音频为空，无法识别')
      const filename = decodeURIComponent(refPath.split('/').pop() || 'reference.wav')
      const text = (await virtmateClient.recognizeAsr(blob, sessionId, filename)).trim()
      setEditorDraft((prev) => ({ ...prev, refTranscript: text }))
      setSettingsStatus(text ? 'ASR识别完成，已填入参考文本，可手动修改' : 'ASR未识别到文本，请手动填写')
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : 'ASR识别失败')
    } finally {
      setAsrRecognizing(false)
    }
  }, [editorDraft.refAudioPath, isMidAuthMode, sessionId])

  const onUploadLive2D = useCallback(async (file: File) => {
    try {
      const path = await virtmateClient.uploadProfileLive2D(file)
      setEditorDraft((prev) => ({ ...prev, live2dModelPath: path }))
      setSettingsStatus(null)
    } catch (e) {
      setSettingsStatus(e instanceof Error ? e.message : '上传 Live2D 模型失败')
    }
  }, [])

  useEffect(() => {
    if (!contextMenu) return
    const close = () => setContextMenu(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [contextMenu])

  useEffect(() => {
    if (!statusPopoverOpen) return
    const close = () => setStatusPopoverOpen(false)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [statusPopoverOpen])

  const scrollProfileRailBy = useCallback((delta: number) => {
    const rail = profileRailRef.current
    if (!rail) return
    rail.scrollBy({ left: delta, behavior: 'smooth' })
  }, [])

  const onProfileRailWheel = useCallback((e: React.WheelEvent<HTMLDivElement>) => {
    const rail = profileRailRef.current
    if (!rail) return
    if (Math.abs(e.deltaY) < Math.abs(e.deltaX)) return
    e.preventDefault()
    rail.scrollBy({ left: e.deltaY, behavior: 'auto' })
  }, [])

  const activeProfile = useMemo(
    () => profiles.find((item) => item.id === activeProfileId) ?? null,
    [activeProfileId, profiles],
  )
  const defaultProfileActive = activeProfileId === 'default'

  const canInitLive2d = true
  const wsIndicatorClass =
    wsState === '已连接'
      ? 'bg-emerald-500'
      : wsState === '连接异常'
        ? 'bg-rose-500'
        : 'bg-slate-400'

  useEffect(() => {
    if (!canInitLive2d || !live2dRootRef.current) return
    let cancelled = false
    ;(async () => {
      try {
        setLive2dError(null)
        await ensureCubismCoreLoaded(virtmateClient.getLive2DCubismCoreUrl())
        if (cancelled) return
        const PIXI = await import('pixi.js')
        ;(window as unknown as Record<string, unknown>).PIXI = PIXI
        const { Live2DModel } = await import('pixi-live2d-display/cubism4')
        if (cancelled) return

        const app = new PIXI.Application({
          resizeTo: live2dRootRef.current as HTMLElement,
          antialias: true,
          backgroundAlpha: 0,
        })
        const safeDestroyApp = (target: typeof app | null) => {
          if (!target) return
          const appWithGuard = target as typeof target & {
            cancelResize?: (() => void) | null
            __virtmateDestroyed?: boolean
          }
          if (appWithGuard.__virtmateDestroyed) return
          try {
            if (typeof appWithGuard.cancelResize !== 'function') {
              appWithGuard.cancelResize = () => {
                // noop fallback for pixi resize plugin teardown
              }
            }
            appWithGuard.__virtmateDestroyed = true
            appWithGuard.destroy(true)
          } catch {
            // ignore repeated/partial destroy errors
          }
        }
        if (cancelled) {
          safeDestroyApp(app)
          return
        }
        live2dRootRef.current?.appendChild(app.view as unknown as HTMLCanvasElement)
        live2dAppRef.current = app

        const modelUrl =
          activeProfile?.live2d_model_path && activeProfile.live2d_model_path.trim()
            ? normalizeAudioUrl(activeProfile.live2d_model_path)
            : virtmateClient.getLive2DModelUrl()
        const model = await Live2DModel.from(modelUrl)
        if (cancelled) {
          model.destroy()
          safeDestroyApp(app)
          return
        }
        const fitModel = () => {
          if (!live2dAppRef.current) return
          const bounds = model.getLocalBounds()
          const baseWidth = Math.max(1, bounds.width)
          const baseHeight = Math.max(1, bounds.height)
          const targetWidth = live2dAppRef.current.screen.width * 0.62
          const targetHeight = live2dAppRef.current.screen.height * 0.88
          const scale = Math.min(targetWidth / baseWidth, targetHeight / baseHeight)
          model.scale.set(scale)
          model.anchor.set(0.5, 1)
          model.position.set(
            live2dAppRef.current.screen.width / 2,
            live2dAppRef.current.screen.height - 4,
          )
        }
        fitModel()
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        app.stage.addChild(model as any)
        live2dModelRef.current = model

        const onResize = () => {
          if (!live2dAppRef.current || !live2dModelRef.current) return
          fitModel()
        }
        window.addEventListener('resize', onResize)

        mouthPollRef.current = window.setInterval(async () => {
          try {
            const res = await fetch(virtmateClient.getSceneMouthYUrl(sessionId), {
              credentials: virtmateClient.mode === 'midauth' ? 'include' : 'same-origin',
            })
            const data = (await res.json()) as { y?: number }
            const y = Math.max(0, Math.min(1, Number(data.y ?? 0)))
            const coreModel = (live2dModelRef.current as unknown as {
              internalModel?: { coreModel?: { setParameterValueById: (id: string, value: number) => void } }
            }).internalModel?.coreModel
            coreModel?.setParameterValueById('ParamMouthOpenY', y)
          } catch {
            // ignore polling failures
          }
        }, 120)

        return () => {
          window.removeEventListener('resize', onResize)
        }
      } catch (e) {
        setLive2dError(e instanceof Error ? e.message : 'Live2D 加载失败')
      }
    })()

    return () => {
      cancelled = true
      if (mouthPollRef.current) {
        window.clearInterval(mouthPollRef.current)
        mouthPollRef.current = null
      }
      const model = live2dModelRef.current
      live2dModelRef.current = null
      if (model) {
        try {
          model.destroy()
        } catch {
          // ignore repeated-destroy errors from live2d runtime
        }
      }
      const app = live2dAppRef.current as
        | ({
            cancelResize?: (() => void) | null
            __virtmateDestroyed?: boolean
            destroy: (removeView?: boolean) => void
          })
        | null
      live2dAppRef.current = null
      if (app && !app.__virtmateDestroyed) {
        try {
          // In some pixi/live2d teardown orders this can be missing or nulled.
          if (typeof app.cancelResize !== 'function') {
            app.cancelResize = () => {
              // noop fallback to keep destroy idempotent
            }
          }
          app.__virtmateDestroyed = true
          app.destroy(true)
        } catch {
          // ignore repeated-destroy errors from pixi runtime
        }
      }
      if (live2dRootRef.current) live2dRootRef.current.innerHTML = ''
    }
  }, [activeProfile?.live2d_model_path, canInitLive2d, sessionId])

  return (
    <section className="view page-container active flex h-[100dvh] min-h-0 flex-col overflow-hidden px-4 pb-4 pt-3 md:px-6">
      <div className="mb-1.5 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold text-slate-800">VirtMate</h1>
        </div>
        <button
          type="button"
          className="h-8 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-700 shadow-sm hover:bg-slate-50"
          onClick={() => {
            const params = new URLSearchParams()
            const normalizedChatId = conversationId.trim()
            const normalizedModelId = modelId.trim()
            if (normalizedChatId) params.set('chat_id', normalizedChatId)
            if (normalizedModelId) params.set('model', normalizedModelId)
            const query = params.toString()
            navigate(query ? `/agent?${query}` : '/agent')
          }}
        >
          返回 Agent
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden rounded-2xl border border-slate-200 bg-white/80 p-2.5 shadow-sm">
        <div className="flex h-full min-h-0 flex-col gap-2.5">
            <div className={LIVE2D_TOP_CONTROLS_ROW_CLASS}>
              <div className="relative">
                <button
                  type="button"
                  className={LIVE2D_STATUS_ICON_BUTTON_CLASS}
                  aria-label="连接状态"
                  title="连接状态"
                  onClick={(e) => {
                    e.stopPropagation()
                    setStatusPopoverOpen((v) => !v)
                  }}
                >
                  <span className={`size-2.5 rounded-full ${wsIndicatorClass}`} />
                </button>
                {statusPopoverOpen ? (
                  <div
                    className="absolute right-0 top-full z-20 mt-2 min-w-[11rem] rounded-md border border-slate-200 bg-white p-2 text-xs text-slate-600 shadow-lg"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <p>WS: {wsState}</p>
                    <p className="mt-0.5">状态: {chatStatus}</p>
                  </div>
                ) : null}
              </div>
              <button
                type="button"
                className={LIVE2D_SETTINGS_BUTTON_CLASS}
                onClick={() => {
                  setLive2dSettingsEntryOpen(true)
                  void loadProfiles()
                }}
                aria-label="打开设置入口"
                title="设置"
              >
                ⚙
              </button>
            </div>
            {live2dSettingsEntryOpen ? (
              <div className="min-h-0 flex-1 rounded-lg border border-slate-200 bg-white">
                <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2">
                  <span className="text-sm text-slate-600">设置入口（占位）</span>
                  <button
                    type="button"
                    className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
                    onClick={() => setLive2dSettingsEntryOpen(false)}
                  >
                    返回
                  </button>
                </div>
                <div className="h-[calc(100%-41px)] bg-gradient-to-b from-slate-100/80 via-slate-50 to-white px-4 py-3">
                  <div className="mb-2 flex items-center justify-end gap-2">
                    <button
                      type="button"
                      className="rounded-md border border-slate-300 bg-white/90 px-2 py-1 text-xs text-slate-700 hover:bg-white"
                      onClick={() => scrollProfileRailBy(-240)}
                      aria-label="向左滚动"
                    >
                      ←
                    </button>
                    <button
                      type="button"
                      className="rounded-md border border-slate-300 bg-white/90 px-2 py-1 text-xs text-slate-700 hover:bg-white"
                      onClick={() => scrollProfileRailBy(240)}
                      aria-label="向右滚动"
                    >
                      →
                    </button>
                  </div>
                  {profilesLoading ? (
                    <p className="text-xs text-slate-500">加载 profile 中...</p>
                  ) : settingsView === 'editor' ? (
                    <div className="h-[calc(100%-1.75rem)] overflow-y-auto rounded-2xl border border-slate-200 bg-white p-3">
                      <h3 className="mb-3 text-sm font-semibold text-slate-700">
                        {editorProfileId ? '编辑 Profile' : '新建 Profile'}
                      </h3>
                      <div className="space-y-2">
                        <label className="block text-xs text-slate-600">标题</label>
                        <input
                          value={editorDraft.title}
                          onChange={(e) => setEditorDraft((p) => ({ ...p, title: e.target.value }))}
                          className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm"
                          placeholder="给 profile 取个名字"
                        />
                        <label className="block text-xs text-slate-600">LLM 提示词</label>
                        <textarea
                          value={editorDraft.llmPrompt}
                          onChange={(e) => setEditorDraft((p) => ({ ...p, llmPrompt: e.target.value }))}
                          className="h-16 w-full rounded-md border border-slate-200 bg-white p-2 text-sm"
                        />
                        <label className="block text-xs text-slate-600">GPT-SoVITS 语种</label>
                        <select
                          value={editorDraft.gptSovitsLang}
                          onChange={(e) => setEditorDraft((p) => ({ ...p, gptSovitsLang: e.target.value }))}
                          className="h-9 w-full rounded-md border border-slate-200 bg-white px-2 text-sm"
                        >
                          {GPT_SOVITS_LANG_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
                          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2">
                            <label className="block text-xs text-slate-600">参考音频（wav/webm/ogg）</label>
                            <input
                              type="file"
                              accept=".wav,.webm,.ogg,audio/*"
                              className="mt-1 w-full text-xs"
                              onChange={(e) => {
                                const f = e.target.files?.[0]
                                if (f) void onUploadRefAudio(f)
                              }}
                            />
                            <p className="mt-1 truncate text-[11px] text-slate-500">
                              {editorDraft.refAudioPath || '未上传'}
                            </p>
                            <button
                              type="button"
                              onClick={() => void onRecognizeRefAudioText()}
                              disabled={asrRecognizing || !editorDraft.refAudioPath.trim()}
                              className="mt-2 h-7 rounded-md border border-slate-300 bg-white px-2 text-[11px] text-slate-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              {asrRecognizing ? 'ASR识别中...' : 'ASR自动识别并填入'}
                            </button>
                            <button
                              type="button"
                              onClick={() => void onRemoveRefAudio()}
                              disabled={!editorDraft.refAudioPath.trim()}
                              className="ml-2 mt-2 h-7 rounded-md border border-rose-300 bg-rose-50 px-2 text-[11px] text-rose-700 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                              删除参考音频
                            </button>
                          </div>
                          <div className="rounded-lg border border-slate-200 bg-slate-50/70 p-2">
                            <label className="block text-xs text-slate-600">Live2D 模型资源</label>
                            <input
                              type="file"
                              className="mt-1 w-full text-xs"
                              onChange={(e) => {
                                const f = e.target.files?.[0]
                                if (f) void onUploadLive2D(f)
                              }}
                            />
                            <p className="mt-1 truncate text-[11px] text-slate-500">
                              {editorDraft.live2dModelPath || '未上传'}
                            </p>
                          </div>
                        </div>
                        <p className="text-xs text-slate-600">
                          建议优先填写“参考音频对应文本”。保存时会优先使用该文本作为 GPT-SoVITS 的提示词；若你需要额外控制风格，可在下方补充说明。
                        </p>
                        <label className="block text-xs text-slate-600">GPT-SoVITS 附加提示词（可选）</label>
                        <textarea
                          value={editorDraft.gptSovitsPrompt}
                          onChange={(e) => setEditorDraft((p) => ({ ...p, gptSovitsPrompt: e.target.value }))}
                          className="h-14 w-full rounded-md border border-slate-200 bg-white p-2 text-sm"
                          placeholder="当参考文本不足以表达风格时，可补充说明"
                        />
                        <label className="block text-xs text-slate-600">参考音频对应文本（推荐）</label>
                        <textarea
                          value={editorDraft.refTranscript}
                          onChange={(e) => setEditorDraft((p) => ({ ...p, refTranscript: e.target.value }))}
                          className="h-16 w-full rounded-md border border-slate-200 bg-white p-2 text-sm"
                          placeholder="建议填写参考音频逐字文本；可用上方 ASR 按钮自动识别后再手动修改"
                        />
                        {settingsStatus ? (
                          <p className="text-xs text-amber-700">{settingsStatus}</p>
                        ) : null}
                        <div className="flex items-center gap-2 pt-2">
                          <button
                            type="button"
                            className="rounded-md border border-sky-300 bg-sky-100 px-3 py-1.5 text-sm hover:bg-sky-200"
                            onClick={() => void onSaveProfileEntry()}
                          >
                            完成
                          </button>
                          <button
                            type="button"
                            className="rounded-md border border-slate-300 bg-white px-3 py-1.5 text-sm hover:bg-slate-50"
                            onClick={onCancelProfileEdit}
                          >
                            取消
                          </button>
                        </div>
                      </div>
                    </div>
                  ) : (
                    <div
                      ref={profileRailRef}
                      onWheel={onProfileRailWheel}
                      className="h-[calc(100%-1.75rem)] overflow-x-auto overflow-y-hidden"
                    >
                      <div className="flex h-full min-w-max flex-row-reverse items-stretch gap-4">
                      <button
                        type="button"
                        onClick={() => void onActivateProfileEntry('default')}
                        className={`group relative h-full w-40 shrink-0 overflow-hidden rounded-[1.75rem] border text-left shadow-[0_18px_34px_-16px_rgba(14,116,144,0.45)] ${
                          defaultProfileActive
                            ? 'border-sky-200/90 ring-2 ring-sky-300/40'
                            : 'border-white/70'
                        }`}
                      >
                        <div className="absolute inset-0 bg-gradient-to-b from-sky-300/80 via-cyan-300/60 to-indigo-300/65" />
                        <div className="absolute inset-0 bg-gradient-to-b from-white/12 via-transparent to-black/10" />
                        {defaultProfileActive ? (
                          <div className="absolute right-2 top-2 rounded-full border border-white/70 bg-sky-500/85 px-2 py-0.5 text-[10px] font-semibold text-white shadow-sm">
                            已选中
                          </div>
                        ) : null}
                        <div className="absolute inset-x-2 bottom-2 rounded-2xl border border-white/55 bg-white/50 px-2 py-1.5 backdrop-blur-md">
                          <p className="text-[10px] text-sky-700">默认 Profile</p>
                          <p className="line-clamp-2 text-xs font-semibold text-slate-900">默认 Profile</p>
                        </div>
                      </button>
                        {profiles.map((profile, idx) => (
                        <button
                          key={profile.id}
                          type="button"
                          onClick={() => void onActivateProfileEntry(profile.id)}
                          onContextMenu={(e) => {
                            e.preventDefault()
                            setContextMenu({ profileId: profile.id, x: e.clientX, y: e.clientY })
                          }}
                          className={`group relative h-full w-40 shrink-0 overflow-hidden rounded-[1.75rem] border bg-white/30 text-left shadow-[0_14px_30px_-18px_rgba(15,23,42,0.55)] backdrop-blur-xl transition hover:-translate-y-0.5 ${
                            activeProfileId === profile.id
                              ? 'border-sky-200/90 ring-2 ring-sky-300/40'
                              : 'border-white/70'
                          }`}
                        >
                          <div
                            className="absolute inset-0"
                            style={{
                              background:
                                idx % 3 === 0
                                  ? 'linear-gradient(165deg, rgba(129,140,248,0.55), rgba(14,165,233,0.42) 55%, rgba(255,255,255,0.18))'
                                  : idx % 3 === 1
                                    ? 'linear-gradient(165deg, rgba(244,114,182,0.52), rgba(251,191,36,0.36) 55%, rgba(255,255,255,0.2))'
                                    : 'linear-gradient(165deg, rgba(16,185,129,0.5), rgba(56,189,248,0.4) 55%, rgba(255,255,255,0.2))',
                            }}
                          />
                          <div className="absolute inset-0 bg-gradient-to-b from-white/8 via-transparent to-black/10" />
                          {activeProfileId === profile.id ? (
                            <div className="absolute right-2 top-2 rounded-full border border-white/70 bg-sky-500/85 px-2 py-0.5 text-[10px] font-semibold text-white shadow-sm">
                              已选中
                            </div>
                          ) : null}
                          <div className="absolute inset-x-2 bottom-2 rounded-2xl border border-white/55 bg-white/45 px-2 py-1.5 backdrop-blur-md">
                            <p className="text-[10px] text-slate-600">自定义 Profile</p>
                            <p className="line-clamp-2 text-xs font-semibold text-slate-800">{profile.title}</p>
                          </div>
                        </button>
                      ))}
                      <button
                        type="button"
                        onClick={onCreateProfileEntry}
                        className="group relative h-full w-40 shrink-0 overflow-hidden rounded-[1.75rem] border border-white/60 bg-white/30 shadow-[0_12px_28px_-18px_rgba(15,23,42,0.55)] backdrop-blur-xl transition hover:-translate-y-0.5"
                        title="新建 profile"
                      >
                        <div className="absolute inset-0 bg-gradient-to-b from-white/45 to-white/10" />
                        <div className="absolute inset-0 grid place-items-center text-5xl font-light text-slate-400/80">+</div>
                        <div className="absolute inset-x-2 bottom-2 rounded-2xl border border-white/50 bg-white/45 px-2 py-1 text-center text-[11px] text-slate-600 backdrop-blur-md">
                          新建 Profile
                        </div>
                      </button>
                      </div>
                    </div>
                  )}
                  {settingsStatus ? (
                    <p className="mt-1 text-xs text-amber-700">{settingsStatus}</p>
                  ) : null}
                  {contextMenu ? (
                    <div
                      className="fixed z-[60] w-36 rounded-md border border-slate-200 bg-white py-1 shadow-lg"
                      style={{ left: contextMenu.x, top: contextMenu.y }}
                    >
                      <button
                        type="button"
                        className="block w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                        onClick={() => onEditProfileEntry(contextMenu.profileId)}
                      >
                        编辑
                      </button>
                      <button
                        type="button"
                        className="block w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                        onClick={() => void onMoveProfileEntry(contextMenu.profileId, 'backward')}
                      >
                        前移
                      </button>
                      <button
                        type="button"
                        className="block w-full px-3 py-1.5 text-left text-xs text-slate-700 hover:bg-slate-50"
                        onClick={() => void onMoveProfileEntry(contextMenu.profileId, 'forward')}
                      >
                        后移
                      </button>
                      <button
                        type="button"
                        className="block w-full px-3 py-1.5 text-left text-xs text-rose-700 hover:bg-rose-50"
                        onClick={() => void onDeleteProfileEntry(contextMenu.profileId)}
                      >
                        删除
                      </button>
                    </div>
                  ) : null}
                </div>
              </div>
            ) : (
              <>
            <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-2 shadow-inner">
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  className={`h-8 rounded-md px-3 text-xs disabled:opacity-60 ${
                    autoVoiceMode
                      ? 'border border-rose-300 bg-rose-100 text-rose-700 hover:bg-rose-200'
                      : 'border border-sky-300 bg-sky-100 text-slate-800 hover:bg-sky-200'
                  }`}
                  onClick={() =>
                    autoVoiceMode ? onStopAutoVoiceMode() : void onStartAutoVoiceMode()
                  }
                >
                  {autoVoiceMode ? '停止语音' : '开启语音'}
                </button>
                <button
                  type="button"
                  className="h-8 rounded-md border border-slate-300 bg-white px-3 text-xs hover:bg-slate-50 disabled:opacity-60"
                  onClick={() => void onStartRecord()}
                  disabled={recording || autoVoiceMode}
                >
                  手动录音
                </button>
                <button
                  type="button"
                  className="h-8 rounded-md border border-slate-300 bg-white px-3 text-xs hover:bg-slate-50 disabled:opacity-60"
                  onClick={onStopRecord}
                  disabled={!recording || autoVoiceMode}
                >
                  停止
                </button>
                <button
                  type="button"
                  className="h-8 rounded-md border border-slate-300 bg-white px-3 text-xs hover:bg-slate-50 disabled:opacity-60"
                  onClick={onReplayLastTts}
                  disabled={!lastTtsAudioUrl}
                >
                  播放上次语音
                </button>
                <button
                  type="button"
                  className="ml-auto h-8 rounded-md border border-slate-300 bg-white px-3 text-xs hover:bg-slate-50"
                  onClick={() => setControlsExpanded((v) => !v)}
                >
                  {controlsExpanded ? '收起控件' : '展开控件'}
                </button>
              </div>
              <p className="mt-2 text-xs text-slate-600">
                {voiceStatus || (autoVoiceMode ? '自动语音模式运行中' : '语音控件已收起，可展开后输入/发送')}
              </p>
              {controlsExpanded ? (
                <div className="mt-2 flex items-center gap-2">
                  <input
                    value={textInput}
                    onChange={(e) => setTextInput(e.target.value)}
                    className="h-9 min-w-0 flex-1 rounded-md border border-slate-200 bg-white px-3 text-sm shadow-sm"
                    placeholder="识别结果或手动输入"
                  />
                  <button
                    type="button"
                    className="h-9 rounded-md border border-sky-300 bg-sky-100 px-4 text-sm hover:bg-sky-200 disabled:opacity-60"
                    onClick={() => void onSendChat()}
                    disabled={autoVoiceMode}
                  >
                    发送
                  </button>
                </div>
              ) : null}
            </div>
            {live2dError ? <p className="mb-2 text-sm text-red-600">{live2dError}</p> : null}
            <div
              ref={live2dRootRef}
              className="min-h-0 flex-1 overflow-hidden rounded-lg border border-slate-200 bg-[#0f172a]/85"
            />
              </>
            )}
        </div>
      </div>
    </section>
  )
}
