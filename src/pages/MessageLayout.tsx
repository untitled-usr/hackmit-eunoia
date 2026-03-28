import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '../context/useAuth'

export function MessageLayout() {
  const { user, loading } = useAuth()
  const showTabs = Boolean(user) || loading

  return (
    <section
      id="message"
      className="view page-container active flex h-[100dvh] min-h-0 flex-col overflow-hidden"
    >
      {showTabs ? (
        <div className="shrink-0 border-b border-slate-200/50 px-6 pb-4 pt-6 md:px-8 md:pt-8">
          <div className="flex flex-wrap gap-2">
            <NavLink
              to="/message"
              end
              className={({ isActive }) => `message-tab${isActive ? ' active' : ''}`}
            >
              Chat
            </NavLink>
            <NavLink
              to="/message/notifications"
              className={({ isActive }) => `message-tab${isActive ? ' active' : ''}`}
            >
              Notifications
            </NavLink>
          </div>
        </div>
      ) : null}
      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <Outlet />
      </div>
    </section>
  )
}
