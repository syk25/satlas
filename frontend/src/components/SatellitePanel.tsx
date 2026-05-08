import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  degreesLat,
  degreesLong,
  eciToGeodetic,
  gstime,
  propagate,
  twoline2satrec,
} from 'satellite.js'
import { useCountryAt } from '../hooks/useCountryAt'
import { CATEGORY_COLOR } from '../types'
import type { SatelliteCategory, SatelliteOverhead } from '../types'

interface SatPosition {
  lat: number
  lon: number
  alt: number
  speed: number
}

function useSatPosition(sat: SatelliteOverhead | null): SatPosition | null {
  const [pos, setPos] = useState<SatPosition | null>(null)
  useEffect(() => {
    if (!sat) {
      setPos(null)
      return
    }
    const compute = () => {
      try {
        const satrec = twoline2satrec(sat.line1.trim(), sat.line2.trim())
        const now = new Date()
        const pv = propagate(satrec, now)
        if (!pv.position || typeof pv.position === 'boolean') return
        if (!pv.velocity || typeof pv.velocity === 'boolean') return
        const geo = eciToGeodetic(pv.position as any, gstime(now))
        const v = pv.velocity as { x: number; y: number; z: number }
        setPos({
          lat: degreesLat(geo.latitude),
          lon: degreesLong(geo.longitude),
          alt: geo.height,
          speed: Math.sqrt(v.x ** 2 + v.y ** 2 + v.z ** 2),
        })
      } catch {}
    }
    compute()
    const id = setInterval(compute, 2000)
    return () => clearInterval(id)
  }, [sat])
  return pos
}

interface Props {
  countryName: string | null
  data: SatelliteOverhead[] | null
  loading: boolean
  error: boolean
  trackedSatellite: SatelliteOverhead | null
  selectedSat: SatelliteOverhead | null
  activeCategory: SatelliteCategory | null
  satOffMapDir: 'north' | 'south' | null
  includeInactive: boolean
  onTrack: (sat: SatelliteOverhead) => void
  onStopTracking: () => void
  onSelectSat: (sat: SatelliteOverhead | null) => void
  onCategoryChange: (cat: SatelliteCategory | null) => void
  onIncludeInactiveChange: (next: boolean) => void
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
  const pos = useSatPosition(sat)
  const countryAt = useCountryAt(pos?.lat ?? null, pos?.lon ?? null)

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
        {sat.operator && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.operator')}</span>
            <span className="sat-detail-value">{sat.operator}</span>
          </div>
        )}
        {sat.operator_name && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.operatorName')}</span>
            <span className="sat-detail-value">{sat.operator_name}</span>
          </div>
        )}
        {sat.launch_date && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.launchDate')}</span>
            <span className="sat-detail-value">{sat.launch_date}</span>
          </div>
        )}
        {sat.decay_date && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.decayDate')}</span>
            <span className="sat-detail-value">{sat.decay_date}</span>
          </div>
        )}
        {sat.international_designator && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.designator')}</span>
            <span className="sat-detail-value">{sat.international_designator}</span>
          </div>
        )}
        {sat.object_type && sat.object_type !== 'PAYLOAD' && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.objectType')}</span>
            <span className="sat-detail-value">
              {t(`satellite.objectTypes.${sat.object_type}`)}
            </span>
          </div>
        )}
        {sat.rcs_size && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.rcsSize')}</span>
            <span className="sat-detail-value">
              {t(`satellite.rcsSizes.${sat.rcs_size}`)}
            </span>
          </div>
        )}
      </div>
      {pos && (
        <div className="sat-detail-body">
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.territory')}</span>
            <span className="sat-detail-value">
              {countryAt ? countryAt.name : t('satellite.openSea')}
            </span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.latitude')}</span>
            <span className="sat-detail-value">{pos.lat.toFixed(2)}°</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.longitude')}</span>
            <span className="sat-detail-value">{pos.lon.toFixed(2)}°</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.altitude')}</span>
            <span className="sat-detail-value">{pos.alt.toFixed(0)} km</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.speed')}</span>
            <span className="sat-detail-value">{pos.speed.toFixed(2)} km/s</span>
          </div>
        </div>
      )}
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

function TrackingView({
  sat,
  offMapDir,
  onStop,
}: {
  sat: SatelliteOverhead
  offMapDir: 'north' | 'south' | null
  onStop: () => void
}) {
  const { t } = useTranslation()
  const color = sat.category ? CATEGORY_COLOR[sat.category] : '#facc15'
  const pos = useSatPosition(sat)
  const countryAt = useCountryAt(pos?.lat ?? null, pos?.lon ?? null)

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
        {sat.operator && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.operator')}</span>
            <span className="sat-detail-value">{sat.operator}</span>
          </div>
        )}
        {sat.operator_name && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.operatorName')}</span>
            <span className="sat-detail-value">{sat.operator_name}</span>
          </div>
        )}
        {sat.launch_date && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.launchDate')}</span>
            <span className="sat-detail-value">{sat.launch_date}</span>
          </div>
        )}
        {sat.decay_date && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.decayDate')}</span>
            <span className="sat-detail-value">{sat.decay_date}</span>
          </div>
        )}
        {sat.international_designator && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.designator')}</span>
            <span className="sat-detail-value">{sat.international_designator}</span>
          </div>
        )}
        {sat.object_type && sat.object_type !== 'PAYLOAD' && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.objectType')}</span>
            <span className="sat-detail-value">
              {t(`satellite.objectTypes.${sat.object_type}`)}
            </span>
          </div>
        )}
        {sat.rcs_size && (
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.rcsSize')}</span>
            <span className="sat-detail-value">
              {t(`satellite.rcsSizes.${sat.rcs_size}`)}
            </span>
          </div>
        )}
        {offMapDir ? (
          <p className="sat-offmap-warning">{t(`satellite.offMap.${offMapDir}`)}</p>
        ) : (
          <p className="sat-detail-hint">{t('satellite.trackingHint')}</p>
        )}
      </div>
      {pos && (
        <div className="sat-detail-body">
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.territory')}</span>
            <span className="sat-detail-value">
              {countryAt ? countryAt.name : t('satellite.openSea')}
            </span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.latitude')}</span>
            <span className="sat-detail-value">{pos.lat.toFixed(2)}°</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.longitude')}</span>
            <span className="sat-detail-value">{pos.lon.toFixed(2)}°</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.altitude')}</span>
            <span className="sat-detail-value">{pos.alt.toFixed(0)} km</span>
          </div>
          <div className="sat-detail-row">
            <span className="sat-detail-label">{t('satellite.speed')}</span>
            <span className="sat-detail-value">{pos.speed.toFixed(2)} km/s</span>
          </div>
        </div>
      )}
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
        {sat.operator && <span className="sat-country">{sat.operator}</span>}
      </div>
      <CategoryBadge category={sat.category} />
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
  selectedSat,
  activeCategory,
  satOffMapDir,
  includeInactive,
  onTrack,
  onStopTracking,
  onSelectSat,
  onCategoryChange,
  onIncludeInactiveChange,
}: Props) {
  const { t } = useTranslation()
  const [sheetOpen, setSheetOpen] = useState(false)
  const dragStartY = useRef(0)

  // Auto-expand when content becomes available
  useEffect(() => {
    if (countryName || selectedSat || trackedSatellite) setSheetOpen(true)
  }, [countryName, selectedSat, trackedSatellite])

  function onHandleTouchStart(e: React.TouchEvent) {
    dragStartY.current = e.touches[0].clientY
  }

  function onHandleTouchEnd(e: React.TouchEvent) {
    const dy = dragStartY.current - e.changedTouches[0].clientY
    if (Math.abs(dy) < 10) setSheetOpen((prev) => !prev)
    else if (dy > 40) setSheetOpen(true)
    else if (dy < -40) setSheetOpen(false)
  }

  const categoryOrder = Object.fromEntries(ALL_CATEGORIES.map((c, i) => [c, i]))

  const filtered = (
    activeCategory
      ? (data ?? []).filter((s) => s.category === activeCategory)
      : (data ?? [])
  )
    .slice()
    .sort((a, b) => {
      const catA = a.category ? (categoryOrder[a.category] ?? 999) : 999
      const catB = b.category ? (categoryOrder[b.category] ?? 999) : 999
      if (catA !== catB) return catA - catB
      return a.name.localeCompare(b.name)
    })

  const presentCategories = ALL_CATEGORIES.filter((c) =>
    (data ?? []).some((s) => s.category === c)
  )

  const handleTrack = (sat: SatelliteOverhead) => {
    onSelectSat(null)
    onTrack(sat)
  }

  const renderBody = () => {
    if (trackedSatellite) {
      return (
        <TrackingView
          sat={trackedSatellite}
          offMapDir={satOffMapDir}
          onStop={onStopTracking}
        />
      )
    }
    if (selectedSat) {
      return (
        <SatelliteDetail
          sat={selectedSat}
          onTrack={handleTrack}
          onBack={() => onSelectSat(null)}
        />
      )
    }
    if (!countryName) {
      return <p className="panel-placeholder">{t('panel.placeholder')}</p>
    }
    if (loading) return <p className="panel-status">{t('panel.loading')}</p>
    if (error) return <p className="panel-status panel-error">{t('panel.error')}</p>

    const includeToggle = (
      <label className="include-inactive-toggle">
        <input
          type="checkbox"
          checked={includeInactive}
          onChange={(e) => onIncludeInactiveChange(e.target.checked)}
        />
        <span>{t('panel.includeInactive')}</span>
      </label>
    )

    if (!data || data.length === 0)
      return (
        <>
          {includeToggle}
          <p className="panel-status">{t('panel.noSatellites')}</p>
        </>
      )

    return (
      <>
        {includeToggle}
        {presentCategories.length > 1 && (
          <div className="category-tabs">
            <button
              className={`category-tab${activeCategory === null ? ' active' : ''}`}
              onClick={() => onCategoryChange(null)}
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
                  onClick={() => onCategoryChange(activeCategory === c ? null : c)}
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
            <SatelliteItem key={sat.norad_id} sat={sat} onSelect={onSelectSat} />
          ))}
        </div>
      </>
    )
  }

  return (
    <aside className={`panel${sheetOpen ? ' sheet-open' : ''}`}>
      <div
        className="panel-handle"
        onTouchStart={onHandleTouchStart}
        onTouchEnd={onHandleTouchEnd}
        onClick={() => setSheetOpen((prev) => !prev)}
      >
        <div className="panel-handle-bar" />
      </div>
      <div className="panel-header">
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
