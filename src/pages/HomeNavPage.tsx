import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { EunoiaDisclaimer } from '../components/EunoiaDisclaimer'
import { useAuth } from '../context/useAuth'
import {
  changeMyPassword,
  deleteMyAvatar,
  fetchMyProfile,
  makeMyAvatarFallbackUrl,
  midAuthOrigin,
  type MidAuthProfile,
  updateMyProfile,
  uploadMyAvatar,
} from '../lib/midAuth'
import './home-nav.css'

const STATUS_PRESETS = ['Isolated', 'Angry', 'Anxious', 'Fatigue', 'Peaceful', 'Reflective']

function resolveAvatarUrl(raw: string | null): string | null {
  if (!raw) return null
  const value = raw.trim()
  if (!value) return null
  if (/^https?:\/\//i.test(value)) return value
  if (value.startsWith('/')) return `${midAuthOrigin}${value}`
  return `${midAuthOrigin}/${value}`
}

export function HomeNavPage() {
  const { user, loading: authLoading, openLoginModal, refreshUser } = useAuth()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [profileLoading, setProfileLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [passwordSaving, setPasswordSaving] = useState(false)
  const [avatarSaving, setAvatarSaving] = useState(false)
  const [profileError, setProfileError] = useState<string | null>(null)
  const [profileMsg, setProfileMsg] = useState<string | null>(null)
  const [profile, setProfile] = useState<MidAuthProfile | null>(null)

  const [activeModal, setActiveModal] = useState<'profile' | 'privacy' | null>(null)

  const [form, setForm] = useState({
    username: '',
    email: '',
    display_name: '',
    gender: '',
    description: '',
  })
  const [passwordForm, setPasswordForm] = useState({
    oldPassword: '',
    newPassword: '',
    confirmPassword: '',
  })
  const [passwordHint, setPasswordHint] = useState('')

  const [status, setStatus] = useState('Peaceful')
  const [statusEditing, setStatusEditing] = useState(false)
  const [statusDraft, setStatusDraft] = useState('')
  const statusInputRef = useRef<HTMLInputElement>(null)

  const [avatarCandidates, setAvatarCandidates] = useState<string[]>([])
  const [avatarIndex, setAvatarIndex] = useState(0)
  const avatarSrc = useMemo(() => avatarCandidates[avatarIndex] ?? null, [avatarCandidates, avatarIndex])

  useEffect(() => {
    if (authLoading || !user) {
      setProfileLoading(false)
      setProfile(null)
      setProfileError(null)
      setProfileMsg(null)
      setAvatarCandidates([])
      setAvatarIndex(0)
      setForm({ username: '', email: '', display_name: '', gender: '', description: '' })
      return
    }
    let cancelled = false
    setProfileLoading(true)
    setProfileError(null)
    ;(async () => {
      try {
        const p = await fetchMyProfile()
        if (cancelled) return
        if (!p) {
          setProfile(null)
          setProfileError('请先登录后查看主页资料')
          setAvatarCandidates([])
          setAvatarIndex(0)
          return
        }
        setProfile(p)
        setForm({
          username: p.username,
          email: p.email,
          display_name: p.display_name,
          gender: p.gender || '',
          description: p.description || '',
        })
        const candidates = [resolveAvatarUrl(p.avatar_url), makeMyAvatarFallbackUrl()].filter(
          (x): x is string => Boolean(x),
        )
        setAvatarCandidates(Array.from(new Set(candidates)))
        setAvatarIndex(0)
      } catch (e) {
        if (cancelled) return
        setProfile(null)
        setProfileError(e instanceof Error ? e.message : '加载资料失败')
        setAvatarCandidates([])
        setAvatarIndex(0)
      } finally {
        if (!cancelled) setProfileLoading(false)
      }
    })()
    return () => { cancelled = true }
  }, [authLoading, user])

  const reloadProfile = useCallback(async () => {
    const p = await fetchMyProfile()
    if (!p) {
      setProfile(null)
      setProfileError('请先登录后查看主页资料')
      return
    }
    setProfile(p)
    setForm({
      username: p.username,
      email: p.email,
      display_name: p.display_name,
      gender: p.gender || '',
      description: p.description || '',
    })
    const candidates = [resolveAvatarUrl(p.avatar_url), makeMyAvatarFallbackUrl()].filter(
      (x): x is string => Boolean(x),
    )
    setAvatarCandidates(Array.from(new Set(candidates)))
    setAvatarIndex(0)
  }, [])

  const openModal = useCallback((type: 'profile' | 'privacy') => {
    setActiveModal(type)
    setPasswordHint('')
    setProfileError(null)
    setProfileMsg(null)
  }, [])

  const closeModals = useCallback(() => {
    setActiveModal(null)
    setPasswordHint('')
  }, [])

  const onSaveProfile = useCallback(async () => {
    if (!profile) return
    setSaving(true)
    setProfileError(null)
    setProfileMsg(null)
    try {
      const next = await updateMyProfile({
        username: form.username.trim(),
        email: form.email.trim(),
        display_name: form.display_name.trim(),
        gender: form.gender.trim() || null,
        description: form.description.trim() || null,
      })
      setProfile(next)
      await refreshUser()
      setProfileMsg('资料已保存')
      await reloadProfile()
      closeModals()
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : '保存失败')
    } finally {
      setSaving(false)
    }
  }, [closeModals, form, profile, refreshUser, reloadProfile])

  const onSavePassword = useCallback(async () => {
    if (!passwordForm.oldPassword || !passwordForm.newPassword) {
      setPasswordHint('请填写完整的密码信息。')
      return
    }
    if (passwordForm.newPassword !== passwordForm.confirmPassword) {
      setPasswordHint('两次输入的新密码不一致。')
      return
    }
    setPasswordSaving(true)
    setPasswordHint('')
    try {
      await changeMyPassword(passwordForm.oldPassword, passwordForm.newPassword)
      setPasswordForm({ oldPassword: '', newPassword: '', confirmPassword: '' })
      setPasswordHint('已提交。')
      await refreshUser()
      closeModals()
      openLoginModal()
    } catch (e) {
      setPasswordHint(e instanceof Error ? e.message : '修改密码失败')
    } finally {
      setPasswordSaving(false)
    }
  }, [closeModals, openLoginModal, passwordForm, refreshUser])

  const onUploadAvatar = useCallback(async (file: File | null) => {
    if (!file) return
    setAvatarSaving(true)
    setProfileError(null)
    setProfileMsg(null)
    try {
      await uploadMyAvatar(file)
      setProfileMsg('头像已更新')
      await reloadProfile()
      await refreshUser()
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : '上传头像失败')
    } finally {
      setAvatarSaving(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }, [refreshUser, reloadProfile])

  const onDeleteAvatar = useCallback(async () => {
    setAvatarSaving(true)
    setProfileError(null)
    setProfileMsg(null)
    try {
      await deleteMyAvatar()
      setProfileMsg('头像已删除')
      await reloadProfile()
      await refreshUser()
    } catch (e) {
      setProfileError(e instanceof Error ? e.message : '删除头像失败')
    } finally {
      setAvatarSaving(false)
    }
  }, [refreshUser, reloadProfile])

  const enterStatusEdit = useCallback(() => {
    setStatusEditing(true)
    setStatusDraft(status)
    setTimeout(() => statusInputRef.current?.focus(), 0)
  }, [status])

  const exitStatusEdit = useCallback((save: boolean) => {
    if (save && statusDraft.trim()) {
      setStatus(statusDraft.trim().slice(0, 50))
    }
    setStatusEditing(false)
  }, [statusDraft])

  const onOverlayKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Escape') closeModals()
  }, [closeModals])

  const displayName = profile?.display_name || 'Home'
  const username = profile ? `@${profile.username}` : '未登录'
  const email = profile?.email || ''
  const publicId = profile?.public_id || ''
  const gender = profile?.gender || ''
  const description = profile?.description || ''

  if (authLoading || profileLoading) {
    return (
      <div className="home-dashboard">
        <div className="home-loading-text">加载中…</div>
        <EunoiaDisclaimer />
      </div>
    )
  }

  if (!user) {
    return (
      <div className="home-dashboard">
        <div className="home-dashboard-container">
          <div className="home-dashboard-card" style={{ alignItems: 'center', justifyContent: 'center' }}>
            <div className="home-dashboard-title">Personal Identity</div>
            <div className="home-loading-text">请先登录以查看个人资料</div>
            <button type="button" className="home-action-btn" onClick={openLoginModal}>
              登录
            </button>
          </div>
        </div>
        <EunoiaDisclaimer />
      </div>
    )
  }

  return (
    <div className="home-dashboard">
      <div className="home-dashboard-container">
        <div className="home-dashboard-card">
          <div className="home-dashboard-top">
            <div className="home-dashboard-title">Personal Identity</div>
            <div className="home-identity">
              <div
                className="home-avatar"
                aria-label="Public ID"
                onClick={() => fileInputRef.current?.click()}
              >
                {avatarSrc ? (
                  <img
                    className="home-avatar-img"
                    src={avatarSrc}
                    alt=""
                    onError={() => setAvatarIndex((i) => (i + 1 < avatarCandidates.length ? i + 1 : i))}
                  />
                ) : (
                  <span>{publicId || '🍾'}</span>
                )}
                <span className="home-avatar-edit">edit</span>
              </div>
              <div className="home-identity-text">
                <div className="home-display-name">{displayName}</div>
                <div className="home-username">{username}</div>
              </div>
            </div>

            <div className="home-status">
              <div className="home-status-label">Current Status</div>
              <div
                className={`home-status-pill${statusEditing ? ' is-editing' : ''}`}
                role="button"
                tabIndex={0}
                onClick={() => { if (!statusEditing) enterStatusEdit() }}
                onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !statusEditing) { e.preventDefault(); enterStatusEdit() } }}
              >
                {statusEditing ? (
                  <input
                    ref={statusInputRef}
                    className="home-status-input"
                    type="text"
                    maxLength={50}
                    value={statusDraft}
                    onChange={(e) => setStatusDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') { e.preventDefault(); exitStatusEdit(true) }
                      if (e.key === 'Escape') { e.preventDefault(); exitStatusEdit(false) }
                      e.stopPropagation()
                    }}
                    onBlur={() => exitStatusEdit(true)}
                    onClick={(e) => e.stopPropagation()}
                  />
                ) : (
                  <div className="home-status-text">{status}</div>
                )}
              </div>
              <div className="home-status-presets">
                {STATUS_PRESETS.map((preset) => (
                  <button
                    key={preset}
                    className={`home-status-tag${status === preset ? ' is-selected' : ''}`}
                    type="button"
                    onClick={() => setStatus(preset)}
                  >
                    {preset}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="home-dashboard-fields">
            <div className="glass-inset-field">
              <div className="glass-field-label">Display Name</div>
              <div className="glass-field-value">{displayName}</div>
            </div>
            <div className="glass-inset-field">
              <div className="glass-field-label">Email</div>
              <div className="glass-field-value">{email}</div>
            </div>
            <div className="glass-inset-field">
              <div className="glass-field-label">Public ID</div>
              <div className="glass-field-value">{publicId}</div>
            </div>
            <div className="glass-inset-field glass-inset-field--block">
              <div className="glass-field-label">Gender</div>
              <div className="glass-field-value">{gender || '未设置'}</div>
            </div>
            <div className="glass-inset-field glass-inset-field--block">
              <div className="glass-field-label">Description</div>
              <div className="glass-field-value glass-field-value--multiline">{description || '未设置'}</div>
            </div>
          </div>

          {profileError && <div className="home-msg-error">{profileError}</div>}
          {profileMsg && <div className="home-msg-success">{profileMsg}</div>}

          <div className="home-dashboard-bottom">
            <div className="home-meta">
              <div className="home-meta-item">Email: {email}</div>
              <div className="home-meta-item">Public ID: {publicId}</div>
            </div>
            <div className="home-actions">
              <button className="home-action-btn" type="button" onClick={() => openModal('profile')}>
                Update Profile
              </button>
              <button className="home-action-btn" type="button" onClick={() => openModal('privacy')}>
                Privacy Settings
              </button>
            </div>
          </div>
        </div>
      </div>

      {activeModal && (
        <div
          className="home-modal-overlay"
          onClick={(e) => { if (e.target === e.currentTarget) closeModals() }}
          onKeyDown={onOverlayKeyDown}
          role="presentation"
        >
          {activeModal === 'profile' && (
            <div className="home-modal" role="dialog" aria-modal="true">
              <div className="home-modal-title">Update Profile</div>
              <div className="home-modal-content">
                <div className="glass-inset-field">
                  <div className="glass-field-label">Display Name</div>
                  <input
                    className="glass-field-input"
                    type="text"
                    value={form.display_name}
                    onChange={(e) => setForm((s) => ({ ...s, display_name: e.target.value }))}
                  />
                </div>
                <div className="glass-inset-field">
                  <div className="glass-field-label">Email</div>
                  <input
                    className="glass-field-input"
                    type="email"
                    value={form.email}
                    onChange={(e) => setForm((s) => ({ ...s, email: e.target.value }))}
                  />
                </div>
                <div className="glass-inset-field glass-inset-field--block">
                  <div className="glass-field-label">Gender</div>
                  <input
                    className="glass-field-input"
                    type="text"
                    value={form.gender}
                    onChange={(e) => setForm((s) => ({ ...s, gender: e.target.value }))}
                  />
                </div>
                <div className="glass-inset-field glass-inset-field--block">
                  <div className="glass-field-label">Description</div>
                  <textarea
                    className="glass-field-input glass-field-textarea"
                    rows={4}
                    value={form.description}
                    onChange={(e) => setForm((s) => ({ ...s, description: e.target.value }))}
                  />
                </div>
                <div className="home-modal-actions" style={{ gap: '12px' }}>
                  {avatarSrc && (
                    <button
                      className="home-action-btn"
                      type="button"
                      disabled={avatarSaving}
                      onClick={() => void onDeleteAvatar()}
                    >
                      {avatarSaving ? '处理中…' : 'Delete Avatar'}
                    </button>
                  )}
                  <button
                    className="home-action-btn"
                    type="button"
                    disabled={saving}
                    onClick={() => void onSaveProfile()}
                  >
                    {saving ? '保存中…' : 'Submit'}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeModal === 'privacy' && (
            <div className="home-modal" role="dialog" aria-modal="true">
              <div className="home-modal-title">Privacy Settings</div>
              <div className="home-modal-content">
                <div className="glass-inset-field">
                  <div className="glass-field-label">Old Password</div>
                  <input
                    className="glass-field-input"
                    type="password"
                    value={passwordForm.oldPassword}
                    onChange={(e) => setPasswordForm((s) => ({ ...s, oldPassword: e.target.value }))}
                  />
                </div>
                <div className="glass-inset-field">
                  <div className="glass-field-label">New Password</div>
                  <input
                    className="glass-field-input"
                    type="password"
                    value={passwordForm.newPassword}
                    onChange={(e) => setPasswordForm((s) => ({ ...s, newPassword: e.target.value }))}
                  />
                </div>
                <div className="glass-inset-field">
                  <div className="glass-field-label">Confirm New Password</div>
                  <input
                    className="glass-field-input"
                    type="password"
                    value={passwordForm.confirmPassword}
                    onChange={(e) => setPasswordForm((s) => ({ ...s, confirmPassword: e.target.value }))}
                  />
                </div>
                {passwordHint && <div className="home-modal-hint">{passwordHint}</div>}
                <div className="home-modal-actions">
                  <button
                    className="home-action-btn"
                    type="button"
                    disabled={passwordSaving}
                    onClick={() => void onSavePassword()}
                  >
                    {passwordSaving ? '提交中…' : 'Submit'}
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      <input
        ref={fileInputRef}
        className="hidden"
        type="file"
        accept="image/*"
        onChange={(e) => void onUploadAvatar(e.target.files?.[0] ?? null)}
      />
      <EunoiaDisclaimer />
    </div>
  )
}
