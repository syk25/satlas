import { useTranslation } from 'react-i18next'
import { useOverheadSatellites } from '../hooks/useOverheadSatellites'
import type { SatelliteOverhead } from '../types'

interface Props {
  countryCode: string | null
  countryName: string | null
}

function SatelliteItem({ sat }: { sat: SatelliteOverhead }) {
  const { t } = useTranslation()
  return (
    <div className="satellite-item">
      <div className="sat-name">{sat.name}</div>
      <div className="sat-meta">
        <span>{t('satellite.norad', { id: sat.norad_id })}</span>
        {sat.operator_country && (
          <span className="sat-country">{sat.operator_country}</span>
        )}
      </div>
      {sat.orbit_class && <div className="sat-orbit">{sat.orbit_class}</div>}
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

export function SatellitePanel({ countryCode, countryName }: Props) {
  const { t } = useTranslation()
  const { data, loading, error } = useOverheadSatellites(countryCode)

  const renderBody = () => {
    if (!countryCode) {
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
        <p className="panel-count">{t('panel.count_other', { count: data.length })}</p>
        <div className="satellite-list">
          {data.map((sat) => (
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
