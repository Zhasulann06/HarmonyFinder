import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import i18n, { detectLanguage, LANGUAGE_STORAGE_KEY } from '../i18n';
import en from '../locales/en.json';
import ru from '../locales/ru.json';
import App from '../App';
import { Preferences, THEME_STORAGE_KEY } from '../components/Preferences';
import { LocalizedMessage } from '../components/LocalizedMessage';
import { ApiError } from '../api';

vi.mock('../upload', async (original) => ({ ...await original<typeof import('../upload')>(), inspectDuration: vi.fn(async () => 5) }));
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status }); }
function studio() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>); }
function flatten(value: object): Record<string, string> {
  return Object.fromEntries(Object.entries(value).flatMap(([group, messages]) => Object.entries(messages as Record<string, string>).map(([key, text]) => [`${group}.${key}`, text])));
}

it.each([['ru', 'ru'], ['ru-RU', 'ru'], ['ru-KZ', 'ru'], ['en-US', 'en'], ['de-DE', 'en']])('detects browser language %s as %s', (browser, expected) => {
  vi.spyOn(navigator, 'language', 'get').mockReturnValue(browser);
  expect(detectLanguage()).toBe(expected);
});

it('prefers a saved language and ignores invalid saved preferences', () => {
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('ru-RU');
  localStorage.setItem(LANGUAGE_STORAGE_KEY, 'en'); expect(detectLanguage()).toBe('en');
  localStorage.setItem(LANGUAGE_STORAGE_KEY, 'fr'); expect(detectLanguage()).toBe('ru');
});

it('has matching catalogs and interpolation placeholders for every stable key', () => {
  const english = flatten(en), russian = flatten(ru);
  expect(Object.keys(russian).sort()).toEqual(Object.keys(english).sort());
  for (const [key, value] of Object.entries(english)) {
    expect(russian[key].trim()).not.toBe('');
    expect(russian[key].match(/\{\{.*?\}\}/g)?.sort()).toEqual(value.match(/\{\{.*?\}\}/g)?.sort());
    expect(i18n.t(key, { lng: 'ru' })).not.toBe(key);
  }
});

it('falls back to English for a missing Russian translation', () => {
  i18n.addResource('en', 'translation', 'test.onlyEnglish', 'English fallback');
  expect(i18n.t('test.onlyEnglish', { lng: 'ru' })).toBe('English fallback');
});

it('switches instantly with accessible keyboard buttons and persists the preference', async () => {
  vi.mocked(fetch).mockResolvedValue(response({ status: 'ok' }));
  studio(); await screen.findByText('Local engine connected');
  const calls = vi.mocked(fetch).mock.calls.length;
  screen.getByRole('button', { name: 'Русский' }).focus();
  await userEvent.keyboard('{Enter}');
  expect(screen.getByRole('button', { name: 'Создать гармонию' })).toBeVisible();
  expect(screen.getByLabelText('Квантование нот')).toBeVisible();
  expect(screen.getByRole('option', { name: 'Диатоническая терция' })).toBeInTheDocument();
  expect(document.documentElement.lang).toBe('ru');
  expect(localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe('ru');
  expect(detectLanguage()).toBe('ru');
  await userEvent.click(screen.getByRole('button', { name: 'English' }));
  expect(screen.getByRole('button', { name: 'Generate harmony' })).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(calls);
});

it('keeps theme and language independent and restores the saved theme on mount', async () => {
  localStorage.setItem(THEME_STORAGE_KEY, 'light');
  const view = render(<Preferences />);
  expect(document.documentElement.dataset.theme).toBe('light');
  await userEvent.click(screen.getByRole('button', { name: 'Русский' }));
  expect(document.documentElement.dataset.theme).toBe('light');
  await userEvent.click(screen.getByRole('button', { name: 'Включить тёмную тему' }));
  expect(i18n.resolvedLanguage).toBe('ru');
  expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  view.unmount(); render(<Preferences />);
  expect(document.documentElement.dataset.theme).toBe('dark');
  expect(screen.getByRole('button', { name: 'Русский' })).toHaveAttribute('aria-pressed', 'true');
});

it('works when localStorage is unavailable', async () => {
  vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('Blocked'); });
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('Blocked'); });
  vi.spyOn(navigator, 'language', 'get').mockReturnValue('ru-RU');
  expect(detectLanguage()).toBe('ru');
  render(<Preferences />);
  await userEvent.click(screen.getByRole('button', { name: 'Русский' }));
  expect(i18n.resolvedLanguage).toBe('ru');
});

it('translates an existing backend error and retains original technical details', async () => {
  render(<><Preferences /><LocalizedMessage message={new ApiError('Install Rubber Band 3+', 503, false, 'HTTP 503: DLL missing')} /></>);
  await userEvent.click(screen.getByRole('button', { name: 'Русский' }));
  expect(screen.getByText(/Установите Rubber Band/)).toBeVisible();
  await userEvent.click(screen.getByText('Технические подробности'));
  expect(screen.getByText('HTTP 503: DLL missing')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'English' }));
  expect(screen.getByText(/Install Rubber Band 3\+ and configure/)).toBeVisible();
});

it('translates validation already on screen', async () => {
  vi.mocked(fetch).mockResolvedValue(response({ status: 'ok' })); studio();
  fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['x'], 'bad.txt')] } });
  expect(await screen.findByRole('alert')).toHaveTextContent('Choose a WAV or MP3 file.');
  await userEvent.click(screen.getByRole('button', { name: 'Русский' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Выберите файл WAV или MP3.');
});

it('preserves upload, settings, gains, processing, results and the playing media element', async () => {
  let finishPitch!: (value: Response) => void;
  const pitch = new Promise<Response>((resolve) => { finishPitch = resolve; });
  vi.mocked(fetch).mockImplementation(async (url) => {
    const path = String(url);
    if (path.endsWith('health')) return response({ status: 'ok' });
    if (path.endsWith('upload')) return response({ audio_id: 'persistent-id', status: 'queued' });
    if (path.endsWith('separate')) return response({ audio_id: 'persistent-id', status: 'processing' });
    if (path.endsWith('status')) return response({ audio_id: 'persistent-id', status: 'completed' });
    if (path.endsWith('analyze-pitch')) return pitch;
    if (path.endsWith('render')) return response({ status: 'completed', output_mode: 'vocal', sample_rate: 44100, files: { 'harmony_vocals.wav': 'v', 'preview_mix.wav': 'm' } });
    return response({ notes: [] });
  });
  const view = studio();
  fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['x'], 'my voice.wav')] } });
  await screen.findByText('my voice.wav');
  await userEvent.selectOptions(screen.getByLabelText('Musical key'), 'F#');
  await userEvent.selectOptions(screen.getByLabelText(/Harmony output/), 'vocal');
  await userEvent.click(screen.getByRole('button', { name: 'Below melody' }));
  fireEvent.change(screen.getByLabelText('Lead vocal volume'), { target: { value: '0.35' } });
  const original = view.container.querySelector('audio');
  const objectUrls = vi.mocked(URL.createObjectURL).mock.calls.length;
  await userEvent.click(screen.getByRole('button', { name: 'Generate harmony' }));
  await waitFor(() => expect(vi.mocked(fetch).mock.calls.some(([u]) => String(u).endsWith('analyze-pitch'))).toBe(true));
  const calls = vi.mocked(fetch).mock.calls.length;
  await userEvent.click(screen.getByRole('button', { name: 'Русский' }));
  expect(screen.getByRole('button', { name: 'Создаём гармонию…' })).toBeDisabled();
  expect(screen.getByLabelText('Тоника')).toHaveValue('F#');
  expect(screen.getByLabelText('Громкость основного вокала')).toHaveValue('0.35');
  expect(screen.getByText(/При прослушивании оба направления/)).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(calls);
  expect(view.container.querySelector('audio')).toBe(original);
  expect(URL.createObjectURL).toHaveBeenCalledTimes(objectUrls);
  await act(async () => { finishPitch(response({ notes: [] })); });
  await screen.findByText('Готово к прослушиванию');
  const audio = view.container.querySelectorAll('audio')[2];
  Object.defineProperty(audio, 'duration', { value: 5 }); fireEvent.loadedMetadata(audio);
  audio.currentTime = 2; audio.volume = 0.3; fireEvent.play(audio);
  const finishedCalls = vi.mocked(fetch).mock.calls.length;
  await userEvent.click(screen.getByRole('button', { name: 'English' }));
  expect(view.container.querySelectorAll('audio')[2]).toBe(audio);
  expect(audio.currentTime).toBe(2); expect(audio.volume).toBe(0.3);
  expect(screen.getByRole('button', { name: 'Pause Vocal harmony' })).toBeVisible();
  expect(screen.getByRole('link', { name: 'Vocal WAV' })).toHaveAttribute('href', '/api/audio/persistent-id/files/harmony_vocals.wav');
  expect(fetch).toHaveBeenCalledTimes(finishedCalls);
  expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('upload'))).toHaveLength(1);
});
