import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';
import i18n from '../i18n';

beforeEach(async () => {
  localStorage.clear();
  await i18n.changeLanguage('en');
  document.documentElement.dataset.theme = 'dark';
  vi.stubGlobal('fetch', vi.fn());
  URL.createObjectURL = vi.fn(() => 'blob:test-recording');
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {});
  vi.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue();
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
