import { useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth'

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    const u = username.trim()
    const em = email.trim()
    if (!u || !em || !password) {
      setError('Please enter your username, email, and password.')
      return
    }
    if (!isValidEmail(em)) {
      setError('Please enter a valid email address.')
      return
    }
    if (password.length < 8) {
      setError('Password must be at least 8 characters.')
      return
    }
    setSubmitting(true)
    try {
      await register({
        username: u,
        email: em,
        password,
        displayName: displayName.trim(),
      })
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-up failed.')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <section className="liquid-auth-shell">
      <div className="w-full max-w-md liquid-auth-card-wrap">
        <div className="liquid-auth-card-halo" aria-hidden />
        <div className="liquid-glass-card">
        <h1 className="liquid-auth-title">Sign up</h1>
        <p className="liquid-auth-subtitle">Create a platform account (password at least 8 characters)</p>

        <form className="liquid-auth-form" onSubmit={onSubmit} noValidate>
          <div className="liquid-field">
            <label htmlFor="reg-username" className="liquid-label">
              Username
            </label>
            <input
              id="reg-username"
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="liquid-input"
            />
          </div>
          <div className="liquid-field">
            <label htmlFor="reg-email" className="liquid-label">
              Email
            </label>
            <input
              id="reg-email"
              type="email"
              inputMode="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="liquid-input"
            />
          </div>
          <div className="liquid-field">
            <label htmlFor="reg-display" className="liquid-label">
              Display name
            </label>
            <input
              id="reg-display"
              type="text"
              autoComplete="nickname"
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Optional; defaults to username"
              className="liquid-input"
            />
          </div>
          <div className="liquid-field">
            <label htmlFor="reg-password" className="liquid-label">
              Password
            </label>
            <input
              id="reg-password"
              type="password"
              autoComplete="new-password"
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
            {submitting ? 'Submitting…' : 'Sign up'}
          </button>
        </form>

        <button
          type="button"
          onClick={() => navigate(-1)}
          className="mt-[25px] liquid-link"
        >
          Back
        </button>
        </div>
      </div>
    </section>
  )
}
