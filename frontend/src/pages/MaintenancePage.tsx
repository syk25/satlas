import { useTranslation } from 'react-i18next'

// Demo video shown while the backend is paused — same clip linked from the README.
const DEMO_VIDEO_ID = 'F69mwx--Ojc'
const GITHUB_URL = 'https://github.com/syk25/satlas'

export default function MaintenancePage() {
  const { t, i18n } = useTranslation()

  const toggleLanguage = () => {
    i18n.changeLanguage(i18n.language.startsWith('ko') ? 'en' : 'ko')
  }

  return (
    <div className="maintenance">
      <button className="maintenance-lang" onClick={toggleLanguage}>
        {i18n.language.startsWith('ko') ? t('language.en') : t('language.ko')}
      </button>

      <div className="maintenance-card">
        <div className="maintenance-brand">🛰️ SATLAS</div>
        <h1 className="maintenance-title">{t('maintenance.title')}</h1>
        <p className="maintenance-subtitle">{t('maintenance.subtitle')}</p>

        <div className="maintenance-video">
          <iframe
            src={`https://www.youtube-nocookie.com/embed/${DEMO_VIDEO_ID}`}
            title="Satlas demo"
            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
            allowFullScreen
          />
        </div>

        <a
          className="maintenance-github"
          href={GITHUB_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          {t('maintenance.github')}
        </a>
      </div>
    </div>
  )
}
