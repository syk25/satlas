import { useTranslation } from 'react-i18next'

export function Navbar() {
  const { t, i18n } = useTranslation()
  const toggleLang = () => i18n.changeLanguage(i18n.language === 'ko' ? 'en' : 'ko')

  return (
    <nav className="navbar">
      <span className="navbar-brand">{t('app.title')}</span>
      <div className="navbar-spacer" />
      <button className="lang-toggle" onClick={toggleLang}>
        {i18n.language === 'ko' ? 'EN' : 'KO'}
      </button>
    </nav>
  )
}
