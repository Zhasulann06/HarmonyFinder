# Phase 3E: Russian / English localization and theme preferences

## Behavior

The header contains keyboard-accessible RU / EN buttons next to the Light / Dark
toggle. The active language uses `aria-pressed`, and native buttons support Tab,
Enter and Space. Language changes take effect immediately without a reload or
translation-resource request. The document language and browser title update too.

Preference order:

1. Read `harmonyfinder.language` from localStorage; accept only `ru` or `en`.
2. Otherwise use Russian when `navigator.language` starts with `ru`, case-insensitively.
3. Otherwise use English.

Explicit language selections are saved. Invalid saved values are ignored. If
storage access is blocked, switching still works in memory but cannot persist.
The separate `harmonyfinder.theme` key saves `light` or `dark`; default is dark.
The repository had no existing theme toggle when this work began, so Phase 3E
adds that small control and light palette while retaining the Studio layout.
Following visual feedback, the light background was darkened to `#e1dce9` and
near-white panels replaced with muted lavender-gray surfaces.

## Architecture

- `frontend/src/i18n.ts` initializes i18next with bundled resources and English
  fallback, and handles browser detection, storage and document language/title.
- `frontend/src/locales/en.json` and `ru.json` each contain **185 stable keys**,
  grouped by header, hero, upload, modes, harmony, intervals, mixer, generation,
  progress, results, downloads, player, footer, errors and warnings. There are
  370 translated resource entries in total. Identifiers and musical note symbols
  remain unchanged.
- Components use react-i18next's `useTranslation()` and `t(key, values)`.
  Interpolated sentences keep their grammar in each catalog rather than joining
  translated fragments around numbers or player names. Resource parity and
  interpolation placeholders are tested.
- `components/Preferences.tsx` owns theme state independently of Studio state.
  Language updates do not change component keys, audio sources or pipeline inputs.
  There is no language-dependent effect that starts processing or calls the API.
- `components/LocalizedMessage.tsx` maps canonical client messages and known
  backend error families to stable keys at **display time**. Errors already on
  screen therefore update when language changes. Unknown failures get a localized
  general message rather than an untranslated English error as the main UI text.
  Raw server details and status are retained in an expandable debugging disclosure.
- `ApiError.technicalDetails` preserves the raw HTTP error details, including
  validation arrays. Upload/pipeline error strings reuse the English catalog as
  canonical diagnostic values, preserving existing internal tests and avoiding
  duplicated message definitions. Their displayed text is localized at render time.

Catalog coverage includes empty/loaded/processing/completed/failed states, the
experimental vocal warning, preparation/separation stages, player accessibility
labels, validation, presets, peak protection and available-file downloads.
Brand names, MIDI/WAV/MP3 identifiers, note symbols, filenames and user data are
intentionally unchanged. The FastAPI schemas, endpoints, request identifiers,
DSP and rendering algorithms were not modified.

## Changed files

New files:

- `frontend/src/i18n.ts`
- `frontend/src/locales/en.json`, `frontend/src/locales/ru.json`
- `frontend/src/components/Preferences.tsx`, `LocalizedMessage.tsx`
- `frontend/src/test/localization.test.tsx`
- `frontend/scripts/localization-smoke.mjs`
- `docs/localization.md`

Updated files:

- `frontend/src/App.tsx`, `styles.css`, `api.ts`, `upload.ts`, `pipeline.ts`, `types.ts`
- All seven pre-existing `frontend/src/components/*.tsx` components
- `frontend/src/test/setup.ts`
- `frontend/scripts/browser-smoke.mjs` (explicit English locale for its English assertions)
- `frontend/package.json`, `frontend/package-lock.json`
- `README.md`

Dependencies added: i18next 26.4.5 and react-i18next 17.0.17, locked by npm.
Installation reported zero npm audit vulnerabilities. No backend dependency changes.

## Verification (2026-10-15)

- **53 frontend tests passed**, seven files: all 39 previous tests plus 14 new
  localization tests, including the parameterized browser-language cases.
- TypeScript checks passed.
- Production build passed (Vite, 1,668 modules).
- Existing English desktop/mobile browser smoke passed. Its first run correctly
  opened in Russian because the machine's browser language is Russian; the test
  now explicitly requests `en-US` instead of assuming the default locale.
- New real Edge localization smoke passed for RU and EN, light and dark, at
  1440, 390 and 320 pixel widths (12 combinations). No horizontal page overflow.
  Russian light-theme screenshots were visually reviewed at desktop and 320px.
- A real vocals-only/vocal-harmony pipeline used the existing 20.04-second vocal
  stem. Language was changed while pYIN was processing; the job completed once,
  with one upload and one render request. Switching again while the generated
  vocal was playing preserved the same HTMLAudioElement, advancing playback
  position, mix gain and download URL, with no new POST requests.
- Unit tests also assert no additional fetch calls when switching language,
  no regenerated object URL, unchanged source selection, key/direction/gain state,
  retained results, theme independence, keyboard access, storage failures and
  English fallback. The normal background health polling remains unchanged.
- Backend tests were not rerun for this frontend-only phase; no backend files changed.

Run from Windows PowerShell:

```powershell
cd frontend
npm.cmd install
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# With the API and Vite running:
npm.cmd run test:browser
$env:E2E_AUDIO = '..\backend\data\audio\fa570cb6-1482-4dd2-8907-3ec2c0cbdf83\vocals.wav'
npm.cmd run test:localization
```

Use any available valid recording for `E2E_AUDIO`. Without it, the localization
script still tests detection, persistence, keyboard switching and all layout
combinations. `STUDIO_URL` can override localhost:5173 (verification used :5174).
Tests use installed Edge; `BROWSER_CHANNEL` can select another installed channel.
Screenshots are in ignored `frontend/test-results/locale-*.png`.

## Limits

Technical details intentionally retain the original server language and field
identifiers. The raw JSON API and Swagger documentation are not localized.
Future backend error wording may need an additional mapping; otherwise a localized
general message and the original diagnostic are shown. No automatic translation
service is used. Language preferences survive refresh, but the existing temporary
Studio audio session still does not—switching languages itself never refreshes it.
Vocal harmony remains experimental with the previously documented audio artifacts.
