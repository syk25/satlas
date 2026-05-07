import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteCategory, SatelliteOverhead } from '../types'

interface Props {
  countryName: string | null
  data: SatelliteOverhead[] | null
  loading: boolean
  error: boolean
}

function CategoryBadge({ category }: { category: SatelliteCategory | null }) {
  if (!category || category === 'OTHER') return null
  const color = CATEGORY_COLOR[category]
  return (
    <span className="sat-category-badge" style={{ color, borderColor: `${color}55` }}>
      {category.replace('_', ' ')}
    </span>
  )
}

function SatelliteItem({ sat }: { sat: SatelliteOverhead }) {
  const { t } = useTranslation()
  return (
    <div className="satellite-item">
      <div className="sat-name">{sat.name}</div>
      <div className="sat-meta">
        <span>{t('satellite.norad', { id: sat.norad_id })}</span>
        {sat.orbit_class && <span className="sat-orbit-inline">{sat.orbit_class}</span>}
        {sat.operator_country && (
          <span className="sat-country">{sat.operator_country}</span>
        )}
      </div>
      <CategoryBadge category={sat.category} />
    </div>
  )
}

function LangToggle() {
  const { i18n } = useTranslation()
  const toggle = () => i18n.changeLanguage(i18n.language === 'ko' ? 'en' : 'ko')
  return (
    <button className="lang-toggle" onClick={toggle}>
      {i18n.language === 'ko' ? 'EN' : 'KO'}
    </button>
  )
}

const ALL_CATEGORIES: SatelliteCategory[] = [
  'STATION',
  'WEATHER',
  'GNSS',
  'MILITARY',
  'AMATEUR',
  'COMMERCIAL',
  'EARTH_OBS',
  'SCIENTIFIC',
  'OTHER',
]

export function SatellitePanel({ countryName, data, loading, error }: Props) {
  const { t } = useTranslation()
  const [activeCategory, setActiveCategory] = useState<SatelliteCategory | null>(null)

  const filtered = activeCategory
    ? (data ?? []).filter((s) => s.category === activeCategory)
    : (data ?? [])

  // Only show category tabs that actually have satellites
  const presentCategories = ALL_CATEGORIES.filter((c) =>
    (data ?? []).some((s) => s.category === c)
  )

  const renderBody = () => {
    if (!countryName) {
      return <p className="panel-placeholder">{t('panel.placeholder')}</p>
    }
    if (loading) {
      return <p className="panel-status">{t('panel.loading')}</p>
    }
    if (error) {
      return <p className="panel-status panel-error">{t('panel.error')}</p>
    }
    if (!data || data.length === 0) {
      return <p className="panel-status">{t('panel.noSatellites')}</p>
    }

    return (
      <>
        {/* Category filter tabs */}
        {presentCategories.length > 1 && (
          <div className="category-tabs">
            <button
              className={`category-tab${activeCategory === null ? ' active' : ''}`}
              onClick={() => setActiveCategory(null)}
            >
              {t('panel.all')} ({data.length})
            </button>
            {presentCategories.map((c) => {
              const count = data.filter((s) => s.category === c).length
              return (
                <button
                  key={c}
                  className={`category-tab${activeCategory === c ? ' active' : ''}`}
                  style={
                    activeCategory === c
                      ? { color: CATEGORY_COLOR[c], borderColor: CATEGORY_COLOR[c] }
                      : {}
                  }
                  onClick={() => setActiveCategory((prev) => (prev === c ? null : c))}
                >
                  {c.replace('_', ' ')} {count}
                </button>
              )
            })}
          </div>
        )}

        <p className="panel-count">
          {t('panel.count_other', { count: filtered.length })}
        </p>
        <div className="satellite-list">
          {filtered.map((sat) => (
            <SatelliteItem key={sat.norad_id} sat={sat} />
          ))}
        </div>
      </>
    )
  }

  return (
    <aside className="panel">
      <div className="panel-header">
        <div className="panel-title-row">
          <span className="panel-app-name">{t('app.title')}</span>
          <LangToggle />
        </div>
        {countryName && <h2 className="panel-country">{countryName}</h2>}
        {!countryName && <p className="panel-tagline">{t('app.tagline')}</p>}
      </div>
      <div className="panel-body">{renderBody()}</div>
    </aside>
  )
}
