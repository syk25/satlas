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
  })

export default i18n
