import { useAuth } from '../context/useAuth'

export function HomeSignInPrompt({ title, description }: { title: string; description: string }) {
  const { openLoginModal } = useAuth()

  return (
    <div className="home-dashboard">
      <div className="home-dashboard-container">
        <div className="home-dashboard-card home-dashboard-card--center">
          <div className="home-signin-prompt">
            <div className="home-dashboard-title">{title}</div>
            <div className="home-loading-text home-signin-text">{description}</div>
            <button type="button" className="home-action-btn home-signin-btn" onClick={openLoginModal}>
              Sign in
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
