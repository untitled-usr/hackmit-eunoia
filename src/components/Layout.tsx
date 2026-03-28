import { Outlet, useLocation } from 'react-router-dom'
import { LoginModal } from './LoginModal'
import { Sidebar } from './Sidebar'
import { useAuth } from '../context/useAuth'

const agentWaterBgUrl = new URL('../assets/backgrounds/water-background.jpg', import.meta.url).href
const bottleSeaBgUrl = new URL('../assets/backgrounds/sea.jpg', import.meta.url).href
const diaryBgUrl = new URL('../assets/backgrounds/diary.jpg', import.meta.url).href
const messageBgUrl = new URL('../assets/backgrounds/message_background.jpg', import.meta.url).href

export function Layout() {
  const location = useLocation()
  const { user } = useAuth()
  const isAgentRoute = location.pathname === '/agent' || location.pathname.startsWith('/agent/')
  const isBottleRoute = location.pathname === '/bottle' || location.pathname.startsWith('/bottle/')
  const isDiaryRoute = location.pathname === '/diary'
  const isMessageRoute = location.pathname === '/message' || location.pathname.startsWith('/message/')
  const showAgentWaterBg = isAgentRoute && Boolean(user)
  const showBottleSeaBg = isBottleRoute && Boolean(user)
  const showDiaryBg = isDiaryRoute && Boolean(user)
  const showMessageBg = isMessageRoute && Boolean(user)

  return (
    <>
      {showAgentWaterBg ? (
        <div className="agent-water-layer agent-water-layer--global" aria-hidden>
          <div className="agent-water-blur" style={{ backgroundImage: `url(${agentWaterBgUrl})` }} />
          <div className="agent-water-bg" style={{ backgroundImage: `url(${agentWaterBgUrl})` }} />
          <div className="agent-water-drops">
            <div className="agent-water-drop" style={{ left: '10%', width: 10, height: 10, animationDelay: '0.5s' }} />
            <div className="agent-water-drop" style={{ left: '30%', width: 8, height: 8, animationDelay: '1.2s' }} />
            <div className="agent-water-drop" style={{ left: '50%', width: 12, height: 12, animationDelay: '0.2s' }} />
            <div className="agent-water-drop" style={{ left: '70%', width: 9, height: 9, animationDelay: '1.8s' }} />
            <div className="agent-water-drop" style={{ left: '90%', width: 11, height: 11, animationDelay: '0.8s' }} />
          </div>
          <svg xmlns="http://www.w3.org/2000/svg" version="1.1" style={{ display: 'none' }}>
            <defs>
              <filter id="agent-water-effect">
                <feTurbulence type="fractalNoise" baseFrequency="0.01 0.04" numOctaves={3} result="noise">
                  <animate
                    attributeName="baseFrequency"
                    values="0.01 0.04;0.02 0.08;0.01 0.04"
                    dur="15s"
                    repeatCount="indefinite"
                  />
                </feTurbulence>
                <feDisplacementMap in="SourceGraphic" in2="noise" scale={50} xChannelSelector="R" yChannelSelector="G" />
              </filter>
            </defs>
          </svg>
        </div>
      ) : null}
      {showBottleSeaBg ? (
        <div className="bottle-sea-layer bottle-sea-layer--global" aria-hidden>
          <div className="bottle-sea-blur" style={{ backgroundImage: `url(${bottleSeaBgUrl})` }} />
          <div className="bottle-sea-bg" style={{ backgroundImage: `url(${bottleSeaBgUrl})` }} />
          <div className="bottle-sea-sparkle" />
          <svg xmlns="http://www.w3.org/2000/svg" version="1.1" style={{ display: 'none' }}>
            <defs>
              <filter id="bottle-sea-effect">
                <feTurbulence type="fractalNoise" baseFrequency="0.02 0.08" numOctaves={3} result="noise">
                  <animate
                    attributeName="baseFrequency"
                    values="0.02 0.08;0.03 0.1;0.02 0.08"
                    dur="10s"
                    repeatCount="indefinite"
                  />
                </feTurbulence>
                <feDisplacementMap in="SourceGraphic" in2="noise" scale={30} xChannelSelector="R" yChannelSelector="G" />
              </filter>
            </defs>
          </svg>
        </div>
      ) : null}
      {showDiaryBg ? (
        <div className="diary-bg-layer diary-bg-layer--global" aria-hidden>
          <div className="diary-bg-photo" style={{ backgroundImage: `url(${diaryBgUrl})` }} />
          <div className="diary-bg-veil" />
        </div>
      ) : null}
      {showMessageBg ? (
        <div className="message-bg-layer message-bg-layer--global" aria-hidden>
          <div className="message-bg-photo" style={{ backgroundImage: `url(${messageBgUrl})` }} />
          <div className="message-bg-veil" />
        </div>
      ) : null}
      <LoginModal />
      <Sidebar />
      <main
        id="stage"
        className="min-h-screen overflow-x-hidden pl-[96px] text-slate-800"
      >
        <div className="page-wrapper">
          <Outlet />
        </div>
      </main>
    </>
  )
}
