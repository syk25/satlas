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

export default function AboutPage() {
  const { t } = useTranslation()

  return (
    <div className="about">
      <header className="about-header">
        <h1 className="about-title">{t('about.title')}</h1>
        <p className="about-intro">{t('about.intro')}</p>
      </header>

      <section className="about-section">
        <h2 className="about-section-title">{t('about.why.title')}</h2>
        <p>{t('about.why.body')}</p>
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
        <h2 className="about-section-title">{t('about.privacy.title')}</h2>
        <p>{t('about.privacy.body')}</p>
      </section>
    </div>
  )
}
