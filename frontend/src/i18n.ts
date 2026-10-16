import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import en from './locales/en.json';
import ru from './locales/ru.json';

export type Language = 'en' | 'ru';
export const LANGUAGE_STORAGE_KEY = 'harmonyfinder.language';
export function detectLanguage(): Language {
  try {
    const saved = localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (saved === 'ru' || saved === 'en') return saved;
  } catch { /* Preferences are optional when storage is blocked. */ }
  return typeof navigator !== 'undefined' && navigator.language.toLowerCase().startsWith('ru') ? 'ru' : 'en';
}

// Resources are bundled: changing language performs no network requests.
void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ru: { translation: ru } },
  lng: detectLanguage(), fallbackLng: 'en', supportedLngs: ['en', 'ru'],
  interpolation: { escapeValue: false }, initAsync: false,
});
function updateDocument(language: string) {
  if (typeof document === 'undefined') return;
  document.documentElement.lang = language;
  document.title = i18n.t('header.brand');
}
i18n.on('languageChanged', updateDocument);
updateDocument(i18n.language);
export function selectLanguage(language: Language): void {
  try { localStorage.setItem(LANGUAGE_STORAGE_KEY, language); } catch { /* Continue in memory. */ }
  void i18n.changeLanguage(language);
}
export default i18n;
