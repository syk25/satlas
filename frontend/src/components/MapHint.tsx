import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'

const STORAGE_KEY = 'satlas:onboarding:map-hint:seen'
const VISIBLE_MS = 4000
const FADE_MS = 500

interface Props {
  externalDismiss?: boolean
}

export default function MapHint({ externalDismiss }: Props) {
  const { t } = useTranslation()
  const [show, setShow] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) !== '1'
    } catch {
      return false
    }
  })
  const [fading, setFading] = useState(false)

  const dismiss = useCallback(() => {
    setFading((wasFading) => {
      if (wasFading) return wasFading
      try {
        localStorage.setItem(STORAGE_KEY, '1')
      } catch {
        // localStorage unavailable (e.g., privacy mode) — skip persistence.
      }
      window.setTimeout(() => setShow(false), FADE_MS)
      return true
    })
  }, [])

  useEffect(() => {
    if (!show) return
    const id = window.setTimeout(dismiss, VISIBLE_MS)
    return () => window.clearTimeout(id)
  }, [show, dismiss])

  useEffect(() => {
    if (externalDismiss) dismiss()
  }, [externalDismiss, dismiss])

  if (!show) return null

  return (
    <div
      className={`map-hint${fading ? ' map-hint--fading' : ''}`}
      onClick={dismiss}
      role="status"
    >
      {t('onboarding.mapHint')}
    </div>
  )
}
