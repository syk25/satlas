import { useTranslation } from 'react-i18next'
import { NavLink } from 'react-router-dom'

export function Navbar() {
  const { t, i18n } = useTranslation()
  const toggleLang = () => i18n.changeLanguage(i18n.language === 'ko' ? 'en' : 'ko')

  return (
    <nav className="navbar">
      <span className="navbar-brand">{t('app.title')}</span>
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
      </div>
      <div className="navbar-spacer" />
      <button className="lang-toggle" onClick={toggleLang}>
        {i18n.language === 'ko' ? 'EN' : 'KO'}
      </button>
    </nav>
  )
}
