import { useTranslation } from 'react-i18next'

type SourceLink = {
  labelKey:
    | 'about.source.code'
    | 'about.source.tle'
    | 'about.source.catalog'
    | 'about.source.boundaries'
  name: string
  href: string
}

const SOURCE_LINKS: SourceLink[] = [
  {
    labelKey: 'about.source.code',
    name: 'github.com/syk25/satlas',
    href: 'https://github.com/syk25/satlas',
  },
  { labelKey: 'about.source.tle', name: 'CelesTrak', href: 'https://celestrak.org' },
  {
    labelKey: 'about.source.catalog',
    name: 'SATCAT (Space-Track)',
    href: 'https://www.space-track.org',
  },
  {
    labelKey: 'about.source.boundaries',
    name: 'Natural Earth',
    href: 'https://www.naturalearthdata.com',
  },
]

const FEEDBACK_URLS: Record<string, string> = {
  en: 'https://forms.gle/Mfms2Bu1W9agNHKYA',
  ko: 'https://forms.gle/p6t6MNGMVE9TrPtp6',
}

export default function AboutPage() {
  const { t, i18n } = useTranslation()
  const lang = (i18n.resolvedLanguage ?? i18n.language).split('-')[0]
  const feedbackUrl = FEEDBACK_URLS[lang] ?? FEEDBACK_URLS.en

  return (
    <div className="about">
      <header className="about-header">
        <h1 className="about-title">{t('about.title')}</h1>
        <p className="about-intro">{t('about.intro')}</p>
      </header>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.why.title')}</h2>
        <p>{t('about.why.body')}</p>
        <p className="about-paragraph-next">{t('about.why.story')}</p>
      </section>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.how.title')}</h2>
        <p>{t('about.how.body')}</p>
        <p className="about-paragraph-next">{t('about.how.refresh')}</p>
      </section>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.limits.title')}</h2>
        <p>{t('about.limits.body')}</p>
      </section>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.source.title')}</h2>
        <p>{t('about.source.intro')}</p>
        <ul className="about-sources">
          {SOURCE_LINKS.map((link) => (
            <li key={link.href}>
              <span className="about-source-label">{t(link.labelKey)}</span>
              <a href={link.href} target="_blank" rel="noopener noreferrer">
                {link.name}
              </a>
            </li>
          ))}
        </ul>
      </section>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.feedback.title')}</h2>
        <p>{t('about.feedback.body')}</p>
        <p className="about-paragraph-next">
          <a
            href={feedbackUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="about-feedback-link"
          >
            {t('about.feedback.cta')} ↗
          </a>
        </p>
      </section>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.privacy.title')}</h2>
        <p>{t('about.privacy.body')}</p>
      </section>
    </div>
  )
}
