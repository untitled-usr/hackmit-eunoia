import { midAuthOrigin } from './midAuth'

type ApiMode = 'midauth' | 'direct'

export type VirtmateChatRole = 'user' | 'assistant' | string

export type VirtmateChatMessage = {
  role: VirtmateChatRole
  content: string
  created_at?: string
  tts?: { audio_url?: string } | null
}

export type VirtmateSessionSettings = {
  tts_engine?: string
  cam_permission?: string
  username?: string
  mate_name?: string
  prompt?: string
}

export type VirtmateGlobalConfig = {
  asr?: {
    sensitivity?: string
  }
  tts?: {
    local_host?: string
    gpt_sovits_port?: string
    cosyvoice_port?: string
    indextts_port?: string
    voxcpm_port?: string
    local_timeout_sec?: string
    fallback_engine?: string
    default_engine?: string
    gpt_sovits_profiles?: VirtmateGptSovitsProfile[]
    gpt_sovits_default_profile_id?: string
    gpt_sovits_active_profile_id?: string
  }
}

export type VirtmateGptSovitsProfile = {
  id: string
  name: string
  base_url: string
  endpoint?: string | null
  text_lang?: string | null
  prompt_lang?: string | null
  ref_audio?: string | null
  prompt_text?: string | null
  top_k?: number | null
  top_p?: number | null
  temperature?: number | null
  speed?: number | null
  extra_json?: Record<string, unknown> | null
}

export type VirtmateDigitalProfile = {
  id: string
  title: string
  gpt_sovits_prompt?: string
  gpt_sovits_lang?: string
  llm_prompt?: string
  ref_audio_path?: string
  live2d_model_path?: string
  created_at?: number
}

const DEFAULT_MIDAUTH_PREFIX = '/me/virtmate'
const DEFAULT_DIRECT_PREFIX = '/api'

function normalizePrefix(v: string): string {
  const raw = (v || '').trim()
  if (!raw) return DEFAULT_DIRECT_PREFIX
  const withSlash = raw.startsWith('/') ? raw : `/${raw}`
  return withSlash.replace(/\/+$/, '') || DEFAULT_DIRECT_PREFIX
}

function resolveApiMode(): ApiMode {
  const p = new URLSearchParams(window.location.search)
  const fromQuery = (p.get('api_mode') || '').trim().toLowerCase()
  if (fromQuery === 'midauth' || fromQuery === 'direct') return fromQuery

  const fromEnv = (import.meta.env.VITE_VIRTMATE_API_MODE || '').trim().toLowerCase()
  if (fromEnv === 'midauth' || fromEnv === 'direct') return fromEnv

  return 'midauth'
}

function resolveApiPrefix(mode: ApiMode): string {
  const p = new URLSearchParams(window.location.search)
  const fromQuery = (p.get('api_prefix') || '').trim()
  if (fromQuery) return normalizePrefix(fromQuery)

  const fromEnv = (import.meta.env.VITE_VIRTMATE_API_PREFIX || '').trim()
  if (fromEnv) return normalizePrefix(fromEnv)

  return mode === 'midauth' ? DEFAULT_MIDAUTH_PREFIX : DEFAULT_DIRECT_PREFIX
}

function resolveApiOrigin(mode: ApiMode): string {
  const fromEnv = (import.meta.env.VITE_VIRTMATE_API_ORIGIN || '').trim()
  if (fromEnv) return fromEnv.replace(/\/+$/, '')

  if (mode === 'midauth') {
    const midAuthOrigin = (import.meta.env.VITE_MID_AUTH_ORIGIN || '').trim()
    if (midAuthOrigin) return midAuthOrigin.replace(/\/+$/, '')
    return midAuthOriginFromApp()
  }

  return window.location.origin
}

function midAuthOriginFromApp(): string {
  return midAuthOrigin.replace(/\/+$/, '')
}

function resolveAssetOrigin(): string {
  const explicit = (import.meta.env.VITE_VIRTMATE_ASSET_ORIGIN || '').trim()
  if (explicit) return explicit.replace(/\/+$/, '')
  const appUrl = (import.meta.env.VITE_VIRTMATE_APP_URL || '').trim()
  if (appUrl) {
    try {
      return new URL(appUrl, window.location.origin).origin
    } catch {
      return window.location.origin
    }
  }
  return window.location.origin
}

class VirtmateClient {
  readonly mode: ApiMode
  readonly apiPrefix: string
  readonly apiOrigin: string
  readonly assetOrigin: string

  constructor() {
    this.mode = resolveApiMode()
    this.apiPrefix = resolveApiPrefix(this.mode)
    this.apiOrigin = resolveApiOrigin(this.mode)
    this.assetOrigin = resolveAssetOrigin()
  }

  private endpoint(path: string): string {
    const clean = path.replace(/^\/+/, '')
    return `${this.apiOrigin}${this.apiPrefix}/${clean}`
  }

  private wsEndpoint(sessionId: string): string {
    const wsProto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const wsPath = this.mode === 'midauth' ? `${this.apiPrefix}/ws/events` : '/ws/events'
    const host = new URL(this.apiOrigin).host
    return `${wsProto}://${host}${wsPath}?session_id=${encodeURIComponent(sessionId)}`
  }

  private withAuth(init?: RequestInit): RequestInit {
    const next = { ...(init || {}) }
    if (this.mode === 'midauth' && !next.credentials) next.credentials = 'include'
    return next
  }

  private async readJsonSafe<T>(res: Response): Promise<T | null> {
    const raw = await res.text()
    if (!raw.trim()) return null
    try {
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  }

  async getSessionSettings(sessionId: string): Promise<VirtmateSessionSettings> {
    const res = await fetch(
      `${this.endpoint('session/settings')}?session_id=${encodeURIComponent(sessionId)}`,
      this.withAuth(),
    )
    if (!res.ok) throw new Error(`加载会话设置失败: ${res.status}`)
    return (await this.readJsonSafe<VirtmateSessionSettings>(res)) || {}
  }

  async saveSessionSettings(payload: {
    session_id: string
    tts_engine?: string
    cam_permission?: string
    username?: string
    mate_name?: string
    prompt?: string
  }): Promise<void> {
    const res = await fetch(
      this.endpoint('session/settings'),
      this.withAuth({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    )
    if (!res.ok) throw new Error(`保存会话设置失败: ${res.status}`)
  }

  async getGlobalConfig(): Promise<VirtmateGlobalConfig> {
    const res = await fetch(this.endpoint('config/global'), this.withAuth())
    if (!res.ok) throw new Error(`加载全局配置失败: ${res.status}`)
    return (await this.readJsonSafe<VirtmateGlobalConfig>(res)) || {}
  }

  async saveGlobalConfig(payload: {
    asr_sensitivity?: string
    tts_gpt_sovits_profiles?: VirtmateGptSovitsProfile[]
    tts_gpt_sovits_default_profile_id?: string
    tts_gpt_sovits_active_profile_id?: string
  }): Promise<void> {
    const res = await fetch(
      this.endpoint('config/global'),
      this.withAuth({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    )
    if (!res.ok) throw new Error(`保存全局配置失败: ${res.status}`)
  }

  async sendChat(payload: {
    session_id: string
    text: string
    with_tts: boolean
    stream: boolean
    model: string
    conversation_id?: string | null
  }, userId: string): Promise<{
    conversation_id?: string
    error?: string
    tts_audio_url?: string
    tts_error?: string
    tts_ref_audio_requested?: string
    tts_ref_audio_used?: string
  }> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (this.mode === 'direct' && userId.trim()) headers['user-id'] = userId.trim()
    const res = await fetch(
      this.endpoint('chat/send'),
      this.withAuth({
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      }),
    )
    const data =
      (await this.readJsonSafe<{
        conversation_id?: string
        conversationId?: string
        chat_id?: string
        error?: string
        tts_audio_url?: string
        tts_error?: string
        assistant?: {
          tts?: {
            audio_url?: string
            error?: string
            ref_audio_requested?: string
            ref_audio_used?: string
          } | null
        } | null
      }>(res)) || {}
    if (!res.ok) throw new Error(data.error || `发送失败: ${res.status}`)
    const conversationId = String(
      data.conversation_id ?? data.conversationId ?? data.chat_id ?? '',
    ).trim()
    return {
      conversation_id: conversationId || undefined,
      error: data.error,
      tts_audio_url:
        String(data.tts_audio_url || data.assistant?.tts?.audio_url || '').trim() || undefined,
      tts_error: String(data.tts_error || data.assistant?.tts?.error || '').trim() || undefined,
      tts_ref_audio_requested:
        String(data.assistant?.tts?.ref_audio_requested || '').trim() || undefined,
      tts_ref_audio_used: String(data.assistant?.tts?.ref_audio_used || '').trim() || undefined,
    }
  }

  async recognizeAsr(audio: Blob, sessionId: string, filename: string): Promise<string> {
    const fd = new FormData()
    fd.append('audio', audio, filename)
    fd.append('session_id', sessionId)
    const res = await fetch(
      this.endpoint('asr/recognize'),
      this.withAuth({ method: 'POST', body: fd }),
    )
    const data = (await this.readJsonSafe<{ text?: string; error?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.error || `识别失败: ${res.status}`)
    return data.text || ''
  }

  async postPlaybackState(payload: {
    session_id: string
    is_playing: boolean
    mouth_y?: number
  }): Promise<void> {
    await fetch(
      this.endpoint('tts/playback'),
      this.withAuth({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    )
  }

  async listProfiles(timeoutMs = 8000): Promise<{ profiles: VirtmateDigitalProfile[]; activeProfileId: string }> {
    const controller = new AbortController()
    const timer = window.setTimeout(() => controller.abort(), Math.max(1000, timeoutMs))
    let res: Response
    try {
      res = await fetch(
        this.endpoint('profiles'),
        this.withAuth({
          signal: controller.signal,
        }),
      )
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') {
        throw new Error('加载 profile 超时，请检查 mid-auth 服务')
      }
      throw e
    } finally {
      window.clearTimeout(timer)
    }
    const data =
      (await this.readJsonSafe<{ profiles?: VirtmateDigitalProfile[]; active_profile_id?: string }>(res)) ||
      {}
    if (!res.ok) throw new Error(`加载 profile 失败: ${res.status}`)
    return {
      profiles: Array.isArray(data.profiles) ? data.profiles : [],
      activeProfileId: String(data.active_profile_id || '').trim(),
    }
  }

  async createProfile(payload: Omit<VirtmateDigitalProfile, 'id' | 'created_at'>): Promise<VirtmateDigitalProfile> {
    const res = await fetch(
      this.endpoint('profiles'),
      this.withAuth({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    )
    const data = (await this.readJsonSafe<{ profile?: VirtmateDigitalProfile; detail?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.detail || `创建 profile 失败: ${res.status}`)
    if (!data.profile) throw new Error('创建 profile 失败: 无返回数据')
    return data.profile
  }

  async updateProfile(profileId: string, payload: Omit<VirtmateDigitalProfile, 'id' | 'created_at'>): Promise<VirtmateDigitalProfile> {
    const res = await fetch(
      this.endpoint(`profiles/${encodeURIComponent(profileId)}`),
      this.withAuth({
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
    )
    const data = (await this.readJsonSafe<{ profile?: VirtmateDigitalProfile; detail?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.detail || `更新 profile 失败: ${res.status}`)
    if (!data.profile) throw new Error('更新 profile 失败: 无返回数据')
    return data.profile
  }

  async deleteProfile(profileId: string): Promise<void> {
    const res = await fetch(
      this.endpoint(`profiles/${encodeURIComponent(profileId)}`),
      this.withAuth({ method: 'DELETE' }),
    )
    if (!res.ok) throw new Error(`删除 profile 失败: ${res.status}`)
  }

  async activateProfile(profileId: string): Promise<void> {
    const res = await fetch(
      this.endpoint(`profiles/${encodeURIComponent(profileId)}/activate`),
      this.withAuth({ method: 'POST' }),
    )
    if (!res.ok) throw new Error(`切换 profile 失败: ${res.status}`)
  }

  async moveProfile(profileId: string, direction: 'forward' | 'backward'): Promise<void> {
    const res = await fetch(
      this.endpoint(`profiles/${encodeURIComponent(profileId)}/move`),
      this.withAuth({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ direction }),
      }),
    )
    if (!res.ok) throw new Error(`移动 profile 失败: ${res.status}`)
  }

  async uploadProfileRefAudio(file: File): Promise<string> {
    const fd = new FormData()
    fd.append('file', file, file.name || 'ref.wav')
    const res = await fetch(
      this.endpoint('profiles/assets/ref-audio'),
      this.withAuth({ method: 'POST', body: fd }),
    )
    const data = (await this.readJsonSafe<{ path?: string; detail?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.detail || `上传参考音频失败: ${res.status}`)
    return String(data.path || '').trim()
  }

  async deleteProfileRefAudio(path: string): Promise<void> {
    const trimmedPath = String(path || '').trim()
    if (!trimmedPath) return
    const res = await fetch(
      this.endpoint('profiles/assets/ref-audio'),
      this.withAuth({
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: trimmedPath }),
      }),
    )
    const data = (await this.readJsonSafe<{ detail?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.detail || `删除参考音频失败: ${res.status}`)
  }

  async uploadProfileLive2D(file: File): Promise<string> {
    const fd = new FormData()
    fd.append('file', file, file.name || 'model.zip')
    const res = await fetch(
      this.endpoint('profiles/assets/live2d'),
      this.withAuth({ method: 'POST', body: fd }),
    )
    const data = (await this.readJsonSafe<{ path?: string; detail?: string }>(res)) || {}
    if (!res.ok) throw new Error(data.detail || `上传 Live2D 资源失败: ${res.status}`)
    return String(data.path || '').trim()
  }

  getSceneMouthYUrl(sessionId: string): string {
    const endpoint =
      this.mode === 'midauth' ? `${this.apiPrefix}/scene/mouth_y` : '/api/scene/mouth_y'
    return `${this.apiOrigin}${endpoint}?session_id=${encodeURIComponent(sessionId)}`
  }

  getLive2DModelUrl(): string {
    return `${this.assetOrigin}/assets/live2d_model/hiyori_free_t08/hiyori_free_t08.model3.json`
  }

  getLive2DCubismCoreUrl(): string {
    return `${this.assetOrigin}/assets/live2d_core/live2dcubismcore.min.js`
  }

  createEventsSocket(sessionId: string): WebSocket {
    return new WebSocket(this.wsEndpoint(sessionId))
  }
}

export const virtmateClient = new VirtmateClient()
