import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState } from 'react';
import App from '../App';
import { api } from '../api';
import { BALANCED, HARMONY_FORWARD, MixControls } from '../components/MixControls';

vi.mock('../upload', async (original) => ({ ...await original<typeof import('../upload')>(), inspectDuration: vi.fn(async () => 5) }));
function response(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status }); }
function Controls({ disabled = false }) { const [value, setValue] = useState(HARMONY_FORWARD); return <MixControls value={value} disabled={disabled} onChange={setValue} />; }

it('provides independent controls and real preset values', async () => {
  render(<Controls />);
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('8');
  fireEvent.change(screen.getByLabelText('Lead vocal volume'), { target: { value: '0.25' } });
  expect(screen.getByLabelText('Lead vocal volume')).toHaveValue('0.25');
  expect(screen.getByLabelText('Instrumental volume')).toHaveValue('0.85');
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('8');
  await userEvent.click(screen.getByRole('button', { name: 'Balanced' }));
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('4');
  expect(screen.getByLabelText('Lead vocal volume')).toHaveValue('0.7');
  await userEvent.click(screen.getByRole('button', { name: 'Harmony Forward' }));
  expect(screen.getByLabelText('Harmony volume')).toHaveValue('8');
});

it('locks controls while processing', () => {
  render(<Controls disabled />);
  expect(screen.getByLabelText('Lead vocal volume')).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Balanced' })).toBeDisabled();
});

it('sends independent gains to the render API without legacy fields', async () => {
  vi.mocked(fetch).mockResolvedValue(response({ status: 'completed' }));
  await api.render('id', new AbortController().signal, BALANCED);
  const init = vi.mocked(fetch).mock.calls[0][1];
  expect(JSON.parse(init!.body as string)).toEqual({ velocity: 90, ...BALANCED });
});

it('carries changed slider values through the complete studio workflow', async () => {
  let requestBody: unknown;
  vi.mocked(fetch).mockImplementation(async (input, init) => {
    const path = String(input);
    if (path.endsWith('health')) return response({ status: 'ok' });
    if (path.endsWith('upload')) return response({ audio_id: 'mix-id', status: 'queued' }, 201);
    if (path.endsWith('separate')) return response({ audio_id: 'mix-id', status: 'processing' }, 202);
    if (path.endsWith('status')) return response({ audio_id: 'mix-id', status: 'completed' });
    if (path.endsWith('render')) {
      requestBody = JSON.parse(init!.body as string);
      return response({ status: 'completed', sample_rate: 44100, files: { 'harmony.mid': 'm', 'harmony_piano.wav': 'p', 'preview_mix.wav': 'x' }, mix_diagnostics: { mode: 'stems', headroom_gain: 0.5 } });
    }
    return response({ notes: [] });
  });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><App /></QueryClientProvider>);
  fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['x'], 'song.wav')] } });
  await screen.findByText('song.wav');
  await userEvent.selectOptions(screen.getByLabelText('Musical key'), 'C');
  await userEvent.click(screen.getByRole('button', { name: 'Balanced' }));
  fireEvent.change(screen.getByLabelText('Lead vocal volume'), { target: { value: '0.35' } });
  await userEvent.click(screen.getByRole('button', { name: 'Generate harmony' }));
  await screen.findByText('Ready to play');
  expect(requestBody).toEqual({ velocity: 90, instrumental_gain: 0.85, lead_vocal_gain: 0.35, harmony_gain: 4 });
  expect(screen.getByText(/Peak protection reduced/)).toHaveTextContent('6.0 dB');
  expect(screen.getByText('Instruments + lead + harmony')).toBeVisible();
});
