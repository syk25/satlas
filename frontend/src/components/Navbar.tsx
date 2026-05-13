import { useTranslation } from 'react-i18next'
import { NavLink, useNavigate } from 'react-router-dom'

export function Navbar() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const toggleLang = () => i18n.changeLanguage(i18n.language === 'ko' ? 'en' : 'ko')

  // Clicking the brand always goes to the map and re-enters it fresh. The
  // `reset` token in state lets MapPage's effect fire even when the route
  // doesn't change (already on `/`).
  const handleBrandClick = () => {
    navigate('/', { state: { reset: Date.now() } })
  }

  return (
    <nav className="navbar">
      <button type="button" className="navbar-brand" onClick={handleBrandClick}>
        {t('app.title')}
      </button>
      <div className="navbar-links">
        <NavLink
          to="/"
          end
          className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
        >
          {t('nav.map')}
        </NavLink>
        <NavLink
          to="/dashboard"
          className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
        >
          {t('nav.dashboard')}
        </NavLink>
        <NavLink
          to="/about"
          className={({ isActive }) => `navbar-link${isActive ? ' active' : ''}`}
        >
          {t('nav.about')}
        </NavLink>
      </div>
      <div className="navbar-spacer" />
      <button className="lang-toggle" onClick={toggleLang}>
        {i18n.language === 'ko' ? 'EN' : 'KO'}
      </button>
    </nav>
  )
}
