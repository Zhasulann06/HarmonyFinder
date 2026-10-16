import { useLayoutEffect, useState } from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { selectLanguage } from '../i18n';

export const THEME_STORAGE_KEY = 'harmonyfinder.theme';
export function initialTheme(): 'light' | 'dark' {
  try { return localStorage.getItem(THEME_STORAGE_KEY) === 'light' ? 'light' : 'dark'; }
  catch { return 'dark'; }
}
export function Preferences() {
  const { t, i18n } = useTranslation();
  const [theme, setTheme] = useState(initialTheme);
  useLayoutEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark';
    setTheme(next); document.documentElement.dataset.theme = next;
    try { localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Continue in memory. */ }
  }
  return <div className="preferences">
    <button type="button" className="theme-button" onClick={toggleTheme} aria-label={t(theme === 'dark' ? 'header.light' : 'header.dark')} title={t(theme === 'dark' ? 'header.light' : 'header.dark')}>
      {theme === 'dark' ? <Sun size={17} aria-hidden="true" /> : <Moon size={17} aria-hidden="true" />}
    </button>
    <div className="language-switch" role="group" aria-label={t('header.language')}>
      {(['ru', 'en'] as const).map((language) => <button key={language} type="button" lang={language} aria-label={language === 'ru' ? 'Русский' : 'English'} aria-pressed={i18n.resolvedLanguage === language} onClick={() => selectLanguage(language)}>{language.toUpperCase()}</button>)}
    </div>
  </div>;
}

// Apply the saved theme before the first React paint; language is independent.
if (typeof document !== 'undefined') document.documentElement.dataset.theme = initialTheme();
