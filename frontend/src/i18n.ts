import i18n from 'i18next'
import LanguageDetector from 'i18next-browser-languagedetector'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import ko from './locales/ko.json'

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: { en: { translation: en }, ko: { translation: ko } },
    fallbackLng: 'en',
    supportedLngs: ['en', 'ko'],
    interpolation: { escapeValue: false },
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
    },
  })

// First-visit IP-based language pick. Once the user has toggled (or geo has
// resolved), localStorage carries the choice forward and we skip this fetch.
if (typeof window !== 'undefined' && !localStorage.getItem('i18nextLng')) {
  fetch('/api/geo')
    .then((r) => r.json())
    .then((data: { country: string | null }) => {
      const lng = data.country === 'KR' ? 'ko' : 'en'
      if (lng !== i18n.language) i18n.changeLanguage(lng)
    })
    .catch(() => {
      /* dev or offline: navigator-based guess from detection.order stays. */
    })
}

export default i18n
