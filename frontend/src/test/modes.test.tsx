import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';
import { generate } from '../pipeline';
import { DEFAULT_SETTINGS } from '../components/HarmonyControls';

vi.mock('../upload', async (original) => ({ ...await original<typeof import('../upload')>(), inspectDuration: vi.fn(async () => 2) }));
function response(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status }); }
function studio() { return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><App /></QueryClientProvider>); }
function setup(failure = false) {
  vi.mocked(fetch).mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('health')) return response({ status: 'ok' });
    if (path.endsWith('upload')) return response({ audio_id: 'vocal-id', status: 'queued' }, 201);
    if (path.endsWith('separate')) return response({ audio_id: 'vocal-id', status: 'processing' }, 202);
    if (path.endsWith('status')) return response({ audio_id: 'vocal-id', status: 'completed' });
    if (path.endsWith('render')) return failure ? response({ detail: 'Install Rubber Band 3+' }, 503) : response({ output_mode: 'vocal', status: 'completed', sample_rate: 44100, files: { 'harmony_vocals.wav': 'v', 'preview_mix.wav': 'm' } });
    return response({ notes: [] });
  });
}
async function select() {
  fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['x'], 'voice.wav')] } });
  await screen.findByText('voice.wav');
  await userEvent.selectOptions(screen.getByLabelText('Musical key'), 'A');
  await userEvent.selectOptions(screen.getByLabelText('Scale'), 'natural_minor');
  await userEvent.selectOptions(screen.getByLabelText(/Audio input/), 'vocals_only');
  await userEvent.selectOptions(screen.getByLabelText(/Harmony output/), 'vocal');
}

it('defaults to piano/full song, requires a selected key, and labels experimental output', async () => {
  setup(); studio();
  expect(screen.getByLabelText(/Audio input/)).toHaveValue('full_song');
  expect(screen.getByLabelText(/Harmony output/)).toHaveValue('piano');
  expect(screen.getByLabelText('Musical key')).toHaveValue('');
  expect(screen.queryByText(/Above and Below have sounded robotic/)).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['x'], 'voice.wav')] } });
  await screen.findByText('voice.wav');
  expect(screen.getByRole('button', { name: 'Generate harmony' })).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText(/Harmony output/), 'vocal');
  expect(screen.getByText(/Above and Below have sounded robotic/)).toBeVisible();
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('0.6');
  await userEvent.selectOptions(screen.getByLabelText(/Harmony output/), 'piano');
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('8');
});

it('runs vocals-only vocal output with real payload fields and only the returned downloads', async () => {
  setup(); studio(); await select();
  expect(screen.getByText(/Separation bypassed/)).toBeVisible();
  expect(screen.getByText('Prepare vocals')).toBeVisible();
  expect(screen.getByText('Vocal rendering')).toBeVisible();
  await userEvent.click(screen.getByRole('button', { name: 'Below melody' }));
  await userEvent.click(screen.getByRole('button', { name: 'Generate harmony' }));
  await screen.findByText('Ready to play');
  const calls = vi.mocked(fetch).mock.calls;
  const upload = calls.find(([url]) => String(url).endsWith('upload'))![1]!.body as FormData;
  expect(upload.get('input_mode')).toBe('vocals_only');
  const body = (suffix: string) => JSON.parse(calls.find(([url]) => String(url).endsWith(suffix))![1]!.body as string);
  expect(body('quantize')).toEqual({ mode: 'scale-aware', key: 'A', scale: 'natural_minor' });
  expect(body('harmony')).toMatchObject({ direction: 'below', key: 'A', scale: 'natural_minor' });
  expect(body('render')).toMatchObject({ output_mode: 'vocal', harmony_gain: 0.6, lead_vocal_gain: 0.7 });
  expect(screen.getByRole('link', { name: 'Vocal WAV' })).toHaveAttribute('download', 'harmony_vocals.wav');
  expect(screen.queryByRole('link', { name: 'MIDI' })).not.toBeInTheDocument();
  expect(screen.queryByRole('link', { name: 'Piano WAV' })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Play Vocal harmony' })).toBeVisible();
  expect(screen.getByRole('button', { name: 'Play Preview mix' })).toBeVisible();
  await userEvent.selectOptions(screen.getByLabelText(/Audio input/), 'full_song');
  expect(screen.queryByText('Ready to play')).not.toBeInTheDocument();
});

it('reports missing vocal dependencies without advertising MIDI', async () => {
  setup(true); studio(); await select();
  await userEvent.click(screen.getByRole('button', { name: 'Generate harmony' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Install Rubber Band');
  expect(screen.queryByRole('link', { name: /MIDI/ })).not.toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Generate harmony' })).toBeEnabled();
});

it('rejects a mismatched output response and does not report completion', async () => {
  setup();
  await expect(generate(new File(['x'], 'voice.wav'), { ...DEFAULT_SETTINGS, key: 'C' }, new AbortController().signal, vi.fn(), vi.fn())).rejects.toThrow('all rendered files');
});
