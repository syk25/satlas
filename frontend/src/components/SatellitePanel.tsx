import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteCategory, SatelliteOverhead } from '../types'

interface Props {
  countryName: string | null
  data: SatelliteOverhead[] | null
  loading: boolean
  error: boolean
  trackedSatellite: SatelliteOverhead | null
  onTrack: (sat: SatelliteOverhead) => void
  onStopTracking: () => void
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

function SatelliteDetail({
  sat,
  onTrack,
  onBack,
}: {
  sat: SatelliteOverhead
  onTrack: (s: SatelliteOverhead) => void
  onBack: () => void
}) {
  const { t } = useTranslation()
  const color = sat.category ? CATEGORY_COLOR[sat.category] : '#facc15'

  return (
    <div className="sat-detail">
      <button className="sat-detail-back" onClick={onBack}>
        ← {t('satellite.back')}
      </button>
      <div className="sat-detail-header">
        <div
          className="sat-detail-dot"
          style={{ background: color, boxShadow: `0 0 8px ${color}` }}
        />
        <h3 className="sat-detail-name">{sat.name}</h3>
      </div>
      <div className="sat-detail-body">
        <div className="sat-detail-row">
          <span className="sat-detail-label">NORAD</span>
          <span className="sat-detail-value">{sat.norad_id}</span>
        </div>
        {sat.orbit_class && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.orbit')}</span>
            <span className="sat-detail-value">{sat.orbit_class}</span>
          </div>
        )}
        {sat.category && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.category')}</span>
            <CategoryBadge category={sat.category} />
          </div>
        )}
        {sat.operator_name && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.operator')}</span>
            <span className="sat-detail-value">{sat.operator_name}</span>
          </div>
        )}
        {sat.operator_country && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.country')}</span>
            <span className="sat-detail-value">{sat.operator_country}</span>
          </div>
        )}
      </div>
      <button
        className="track-btn"
        style={{ borderColor: color, color }}
        onClick={() => onTrack(sat)}
      >
        ◎ {t('satellite.track')}
      </button>
    </div>
  )
}

function TrackingView({ sat, onStop }: { sat: SatelliteOverhead; onStop: () => void }) {
  const { t } = useTranslation()
  const color = sat.category ? CATEGORY_COLOR[sat.category] : '#facc15'

  return (
    <div className="sat-detail">
      <div className="tracking-badge">{t('satellite.tracking')}</div>
      <div className="sat-detail-header">
        <div
          className="sat-detail-dot tracking-pulse"
          style={{ background: color, boxShadow: `0 0 10px ${color}` }}
        />
        <h3 className="sat-detail-name">{sat.name}</h3>
      </div>
      <div className="sat-detail-body">
        <div className="sat-detail-row">
          <span className="sat-detail-label">NORAD</span>
          <span className="sat-detail-value">{sat.norad_id}</span>
        </div>
        {sat.orbit_class && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.orbit')}</span>
            <span className="sat-detail-value">{sat.orbit_class}</span>
          </div>
        )}
        {sat.category && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.category')}</span>
            <CategoryBadge category={sat.category} />
          </div>
        )}
        <p className="sat-detail-hint">{t('satellite.trackingHint')}</p>
      </div>
      <button className="track-stop-btn" onClick={onStop}>
        ✕ {t('satellite.stopTracking')}
      </button>
    </div>
  )
}

function SatelliteItem({
  sat,
  onSelect,
}: {
  sat: SatelliteOverhead
  onSelect: (s: SatelliteOverhead) => void
}) {
  const { t } = useTranslation()
  return (
    <button className="satellite-item" onClick={() => onSelect(sat)}>
      <div className="sat-name">{sat.name}</div>
      <div className="sat-meta">
        <span>{t('satellite.norad', { id: sat.norad_id })}</span>
        {sat.orbit_class && <span className="sat-orbit-inline">{sat.orbit_class}</span>}
        {sat.operator_country && (
          <span className="sat-country">{sat.operator_country}</span>
        )}
      </div>
      <CategoryBadge category={sat.category} />
    </button>
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

export function SatellitePanel({
  countryName,
  data,
  loading,
  error,
  trackedSatellite,
  onTrack,
  onStopTracking,
}: Props) {
  const { t } = useTranslation()
  const [activeCategory, setActiveCategory] = useState<SatelliteCategory | null>(null)
  const [selectedSat, setSelectedSat] = useState<SatelliteOverhead | null>(null)

  const filtered = activeCategory
    ? (data ?? []).filter((s) => s.category === activeCategory)
    : (data ?? [])

  const presentCategories = ALL_CATEGORIES.filter((c) =>
    (data ?? []).some((s) => s.category === c)
  )

  const handleTrack = (sat: SatelliteOverhead) => {
    setSelectedSat(null)
    onTrack(sat)
  }

  const renderBody = () => {
    if (trackedSatellite) {
      return <TrackingView sat={trackedSatellite} onStop={onStopTracking} />
    }
    if (selectedSat) {
      return (
        <SatelliteDetail
          sat={selectedSat}
          onTrack={handleTrack}
          onBack={() => setSelectedSat(null)}
        />
      )
    }
    if (!countryName) {
      return <p className="panel-placeholder">{t('panel.placeholder')}</p>
    }
    if (loading) return <p className="panel-status">{t('panel.loading')}</p>
    if (error) return <p className="panel-status panel-error">{t('panel.error')}</p>
    if (!data || data.length === 0)
      return <p className="panel-status">{t('panel.noSatellites')}</p>

    return (
      <>
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
            <SatelliteItem key={sat.norad_id} sat={sat} onSelect={setSelectedSat} />
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
        {!trackedSatellite && countryName && (
          <h2 className="panel-country">{countryName}</h2>
        )}
        {!trackedSatellite && !countryName && (
          <p className="panel-tagline">{t('app.tagline')}</p>
        )}
      </div>
      <div className="panel-body">{renderBody()}</div>
    </aside>
  )
}
