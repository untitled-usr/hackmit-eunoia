import { useEffect, useId, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth'

export function LoginModal() {
  const { loginOpen, closeLoginModal, login } = useAuth()
  const navigate = useNavigate()
  const titleId = useId()
  const [identifier, setIdentifier] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!loginOpen) return
    setError(null)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') closeLoginModal()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [loginOpen, closeLoginModal])

  if (!loginOpen) return null

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const id = identifier.trim()
    if (!id || !password) {
      setError('Please enter your username/email and password.')
      return
    }
    setSubmitting(true)
    try {
      await login(id, password)
      setIdentifier('')
      setPassword('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed.')
    } finally {
      setSubmitting(false)
    }
  }

  const goRegister = () => {
    closeLoginModal()
    navigate('/register')
  }

  return (
    <div
      className="liquid-auth-shell fixed inset-0 z-[220] flex items-center justify-center p-4"
      role="presentation"
      onMouseDown={(ev) => {
        if (ev.target === ev.currentTarget) closeLoginModal()
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className="relative z-10 w-full max-w-sm liquid-auth-card-wrap"
      >
        <div className="liquid-auth-card-halo" aria-hidden />
        <div className="liquid-glass-card">
        <h2 id={titleId} className="liquid-auth-title">Sign in</h2>
        <p className="liquid-auth-subtitle">Sign in with your platform account</p>

        <form className="liquid-auth-form" onSubmit={onSubmit} noValidate>
          <div className="liquid-field">
            <label htmlFor="login-identifier" className="liquid-label">
              Username or email
            </label>
            <input
              id="login-identifier"
              type="text"
              autoComplete="username"
              value={identifier}
              onChange={(e) => setIdentifier(e.target.value)}
              className="liquid-input"
            />
          </div>
          <div className="liquid-field">
            <label htmlFor="login-password" className="liquid-label">
              Password
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="liquid-input"
            />
          </div>

          {error ? (
            <p className="liquid-auth-error" role="alert">
              {error}
            </p>
          ) : null}

          <button
            type="submit"
            disabled={submitting}
            className="liquid-btn w-full"
          >
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
        </form>

        <button
          type="button"
          onClick={goRegister}
          className="mt-[25px] liquid-link"
        >
          Sign up
        </button>

        <button
          type="button"
          onClick={closeLoginModal}
          className="mt-3 liquid-link"
        >
          Cancel
        </button>
        </div>
      </div>
    </div>
  )
}
