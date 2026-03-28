import { Component, lazy, Suspense, type ErrorInfo, type ReactNode } from 'react'
import { BrowserRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom'
import { Layout } from './components/Layout'
import { AuthProvider } from './context/AuthProvider'
import { useAuth } from './context/useAuth'
import { AgentPage } from './pages/AgentPage'
import { BottlePage } from './pages/BottlePage'
import { HomeLegacyPage } from './pages/HomeLegacyPage'
import { HomeNavPage } from './pages/HomeNavPage'
import { DiaryPage } from './pages/DiaryPage'
import { MessageGuestbookPanel } from './pages/MessageGuestbookPanel'
import { MessageLayout } from './pages/MessageLayout'
import { MessageNotificationsPanel } from './pages/MessageNotificationsPanel'
import { RegisterPage } from './pages/RegisterPage'

const LazyAgentVirtmatePage = lazy(() =>
  import('./pages/AgentVirtmatePage').then((m) => ({ default: m.AgentVirtmatePage })),
)

class RouteErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[RouteErrorBoundary]', error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex h-[60vh] flex-col items-center justify-center gap-3 px-6 text-center">
          <p className="text-sm font-medium text-red-600">页面加载失败</p>
          <pre className="max-w-xl overflow-auto rounded-lg bg-slate-100 p-3 text-left text-xs text-slate-700">
            {this.state.error.message}
          </pre>
          <button
            type="button"
            className="mt-2 rounded-full border border-slate-300 px-4 py-1.5 text-xs hover:bg-slate-50"
            onClick={() => this.setState({ error: null })}
          >
            重试
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

function RequireAuth({
  children,
  title = 'Protected',
  description = '登录后可继续访问该页面。',
}: {
  children: ReactNode
  title?: string
  description?: string
}) {
  const { user, loading, openLoginModal } = useAuth()

  if (loading) {
    return <div className="flex h-[60vh] items-center justify-center text-slate-400">加载中…</div>
  }
  if (!user) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center px-6 py-8">
        <div className="glass w-full max-w-lg rounded-xl p-6 text-center">
          <h3 className="text-base font-semibold text-slate-800">{title}</h3>
          <p className="mt-2 text-sm text-slate-600">{description}</p>
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
  return <>{children}</>
}

function hasAnyCookie() {
  if (typeof document === 'undefined') return true
  return document.cookie.trim().length > 0
}

function RequireIntroPass({ children }: { children: ReactNode }) {
  const location = useLocation()
  if (!hasAnyCookie() && location.pathname !== '/') {
    return <Navigate to="/" replace state={{ from: location }} />
  }
  return <>{children}</>
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route
            element={
              <RequireIntroPass>
                <Layout />
              </RequireIntroPass>
            }
          >
            <Route path="/" element={<HomeLegacyPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/agent" element={<AgentPage />} />
            <Route
              path="/agent/virtmate"
              element={
                <RouteErrorBoundary>
                  <Suspense fallback={<div className="flex h-[60vh] items-center justify-center text-slate-400">加载中…</div>}>
                    <LazyAgentVirtmatePage />
                  </Suspense>
                </RouteErrorBoundary>
              }
            />
            <Route path="/message" element={<MessageLayout />}>
              <Route index element={<MessageGuestbookPanel />} />
              <Route path="notifications" element={<MessageNotificationsPanel />} />
            </Route>
            <Route
              path="/diary"
              element={
                <RequireAuth title="Diary" description="登录后可查看并编辑你的日记。">
                  <DiaryPage />
                </RequireAuth>
              }
            />
            <Route
              path="/bottle"
              element={
                <RequireAuth title="Bottle" description="登录后可查看并使用漂流瓶功能。">
                  <BottlePage />
                </RequireAuth>
              }
            />
            <Route path="/bottle/home" element={<Navigate to="/home" replace />} />
            <Route path="/home" element={<HomeNavPage />} />
            <Route path="/board" element={<Navigate to="/message" replace />} />
            <Route path="/notify" element={<Navigate to="/message/notifications" replace />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
