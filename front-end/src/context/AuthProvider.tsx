import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  fetchMe,
  loginRequest,
  logoutRequest,
  MidAuthHttpError,
  registerRequest,
  type AuthUser,
} from '../lib/midAuth'
import { AuthContext } from './authContext'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [loading, setLoading] = useState(true)
  const [loginOpen, setLoginOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      try {
        const u = await fetchMe()
        if (!cancelled) setUser(u)
      } catch {
        if (!cancelled) setUser(null)
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  const openLoginModal = useCallback(() => setLoginOpen(true), [])
  const closeLoginModal = useCallback(() => setLoginOpen(false), [])

  const ensureSessionUser = useCallback(async () => {
    try {
      const me = await fetchMe()
      if (!me) {
        throw new Error(
          '登录成功但会话未生效（cookie 未携带）。请使用与 mid-auth 同主机访问前端，例如都用 127.0.0.1 或都用 localhost。',
        )
      }
      return me
    } catch (err) {
      if (err instanceof MidAuthHttpError && err.status === 503) {
        throw new Error('mid-auth 当前不可用（503），请稍后重试。')
      }
      if (err instanceof Error) throw err
      throw new Error('会话校验失败')
    }
  }, [])

  const login = useCallback(async (identifier: string, password: string) => {
    try {
      await loginRequest(identifier, password)
    } catch (err) {
      if (err instanceof MidAuthHttpError && (err.status === 401 || err.status === 403)) {
        throw new Error('用户名/邮箱或密码错误')
      }
      throw err
    }
    const u = await ensureSessionUser()
    setUser(u)
    setLoginOpen(false)
  }, [ensureSessionUser])

  const logout = useCallback(async () => {
    try {
      await logoutRequest()
    } finally {
      // 即使后端登出失败，也优先清理本地登录态，避免 UI 卡在已登录状态。
      setUser(null)
    }
  }, [])

  const register = useCallback(
    async (p: { username: string; email: string; password: string; displayName: string }) => {
      try {
        await registerRequest({
          username: p.username,
          email: p.email,
          password: p.password,
          display_name: p.displayName.trim() ? p.displayName.trim() : null,
        })
      } catch (err) {
        if (err instanceof MidAuthHttpError && err.status === 409) {
          throw new Error('用户名或邮箱已存在')
        }
        throw err
      }
      await loginRequest(p.email.trim() || p.username.trim(), p.password)
      const u = await ensureSessionUser()
      setUser(u)
      setLoginOpen(false)
    },
    [ensureSessionUser],
  )

  const refreshUser = useCallback(async () => {
    try {
      const u = await fetchMe()
      setUser(u)
    } catch {
      setUser(null)
    }
  }, [])

  const value = useMemo(
    () => ({
      user,
      loading,
      loginOpen,
      openLoginModal,
      closeLoginModal,
      login,
      logout,
      register,
      refreshUser,
    }),
    [
      user,
      loading,
      loginOpen,
      openLoginModal,
      closeLoginModal,
      login,
      logout,
      register,
      refreshUser,
    ],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
