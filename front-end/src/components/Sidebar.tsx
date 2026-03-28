import { useState } from 'react'
import { NavLink } from 'react-router-dom'
import { useAuth } from '../context/useAuth'

import navRobot from '../assets/emojis/robot.png'
import navNotebook from '../assets/emojis/notebook-with-decorative-cover_1f4d4.png'
import navSpeechBalloon from '../assets/emojis/speech-balloon.png'
import navBottle from '../assets/emojis/bottle.png'
import navHouse from '../assets/emojis/house.png'

const TOP_ITEM = { to: '/agent', icon: navRobot, fallback: '🤖', label: 'Agent' } as const
const MID_ITEMS = [
  { to: '/diary', icon: navNotebook, fallback: '📔', label: 'Diary' },
  { to: '/message', icon: navSpeechBalloon, fallback: '💬', label: 'Message' },
  { to: '/bottle', icon: navBottle, fallback: '🍾', label: 'Bottle' },
] as const
const BOTTOM_ITEM = { to: '/home', icon: navHouse, fallback: '🏠', label: 'Home' } as const
const NAV_ITEMS = [TOP_ITEM, ...MID_ITEMS, BOTTOM_ITEM] as const

export function Sidebar() {
  const { user, loading, openLoginModal, logout } = useAuth()
  const [imageBrokenMap, setImageBrokenMap] = useState<Record<string, boolean>>({})

  const renderNavItem = (item: { to: string; icon: string; fallback: string; label: string }) => {
    const { to, icon, fallback, label } = item
    return (
      <NavLink
        key={to}
        to={to}
        end={to === '/agent' || to === '/home'}
        title={label}
        aria-label={label}
        className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
      >
        <span className="nav-icon-shell" aria-hidden>
          {imageBrokenMap[to] ? (
            <span className="nav-icon-fallback">{fallback}</span>
          ) : (
            <img
              src={icon}
              alt=""
              className="nav-icon-img"
              onError={() => setImageBrokenMap((prev) => ({ ...prev, [to]: true }))}
            />
          )}
        </span>
      </NavLink>
    )
  }

  return (
    <aside className="app-sidebar">
      <nav className="sidebar-nav" aria-label="Primary navigation">
        {NAV_ITEMS.map(renderNavItem)}
      </nav>
      <div className="sidebar-bottom">
        {loading ? (
          <span className="sidebar-meta">…</span>
        ) : user ? (
          <>
            <span
              className="sidebar-meta sidebar-user"
              title={user.display_name || user.username}
            >
              {user.display_name || user.username}
            </span>
            <button
              type="button"
              onClick={() => void logout()}
              className="sidebar-auth-btn"
            >
              Sign out
            </button>
          </>
        ) : (
          <button
            type="button"
            onClick={openLoginModal}
            className="sidebar-auth-btn"
          >
            Sign in
          </button>
        )}
        <div className="sidebar-meta">Eunoia</div>
      </div>
    </aside>
  )
}
