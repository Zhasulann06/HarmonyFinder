import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import App from '../App';
import { HarmonyControls, DEFAULT_SETTINGS } from '../components/HarmonyControls';
import { AudioPlayer } from '../components/AudioPlayer';

vi.mock('../upload', async (importOriginal) => ({ ...await importOriginal<typeof import('../upload')>(), inspectDuration: vi.fn(async () => 5) }));
function response(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status }); }
function setupApi(failRender = false) {
  vi.mocked(fetch).mockImplementation(async (input) => {
    const path = String(input);
    if (path.endsWith('health')) return response({ status: 'ok', service: 'HarmonyFinder API' });
    if (path.endsWith('upload')) return response({ audio_id: 'actual-upload-id', status: 'queued', duration_seconds: 5 }, 201);
    if (path.endsWith('separate')) return response({ audio_id: 'actual-upload-id', status: 'processing' }, 202);
    if (path.endsWith('status')) return response({ audio_id: 'actual-upload-id', status: 'completed' });
    if (path.endsWith('render')) return failRender ? response({ detail: 'Set HARMONYFINDER_SOUNDFONT. MIDI remains available at /api/audio/actual-upload-id/files/harmony.mid' }, 503) : response({ status: 'completed', sample_rate: 44100, channels: 2, files: { 'harmony.mid': 'midi', 'harmony_piano.wav': 'piano', 'preview_mix.wav': 'mix' } });
    return response({ notes: [] });
  });
}
function studio() { const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }); return render(<QueryClientProvider client={client}><App /></QueryClientProvider>); }
async function choose() { fireEvent.change(screen.getByLabelText('Choose audio file'), { target: { files: [new File(['audio'], 'song.wav', { type: 'audio/wav' })] } }); await screen.findByText('song.wav'); await userEvent.selectOptions(screen.getByLabelText('Musical key'), 'C'); }
describe('studio controls', () => {
  it('requires a file before generation and enables the action after validation', async () => {
    setupApi(); studio(); expect(screen.getByRole('button', { name: /Generate harmony/ })).toBeDisabled();
    await choose(); expect(screen.getByRole('button', { name: /Generate harmony/ })).toBeEnabled();
    await userEvent.click(screen.getByRole('button', { name: 'Remove audio file' }));
    expect(screen.getByRole('button', { name: /Generate harmony/ })).toBeDisabled(); expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
  it('forces diatonic scale-aware mode and supports fixed intervals', async () => {
    const onChange = vi.fn(); const view = render(<HarmonyControls value={DEFAULT_SETTINGS} disabled={false} onChange={onChange} />);
    expect(screen.getByLabelText('Pitch quantization')).toBeDisabled();
    await userEvent.selectOptions(screen.getByLabelText('Harmony interval'), 'perfect_fifth');
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ interval: 'perfect_fifth' }));
    view.rerender(<HarmonyControls value={{ ...DEFAULT_SETTINGS, interval: 'perfect_fifth', mode: 'chromatic' }} disabled={false} onChange={onChange} />);
    expect(screen.getByLabelText('Pitch quantization')).toBeEnabled();
    await userEvent.selectOptions(screen.getByLabelText('Harmony interval'), 'diatonic_sixth');
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ interval: 'diatonic_sixth', mode: 'scale-aware' }));
  });
  it('prevents duplicate requests and exposes actual download links', async () => {
    setupApi(); studio(); await choose();
    const button = screen.getByRole('button', { name: /Generate harmony/ }); fireEvent.click(button); fireEvent.click(button);
    await screen.findByText('Ready to play');
    expect(vi.mocked(fetch).mock.calls.filter(([url]) => String(url).endsWith('/upload'))).toHaveLength(1);
    expect(screen.getByRole('link', { name: 'MIDI' })).toHaveAttribute('href', '/api/audio/actual-upload-id/files/harmony.mid');
    expect(screen.getByRole('link', { name: 'Piano WAV' })).toHaveAttribute('download', 'harmony_piano.wav');
    expect(screen.getByRole('link', { name: 'Preview WAV' })).toHaveAttribute('href', '/api/audio/actual-upload-id/files/preview_mix.wav');
    expect(screen.getByText(/No voiced notes/)).toBeVisible();
  });
  it('shows actionable rendering errors and retains available MIDI', async () => {
    setupApi(true); studio(); await choose(); await userEvent.click(screen.getByRole('button', { name: /Generate harmony/ }));
    expect(await screen.findByRole('alert')).toHaveTextContent('HARMONYFINDER_SOUNDFONT');
    expect(screen.getByRole('link', { name: 'Download available MIDI' })).toHaveAttribute('href', '/api/audio/actual-upload-id/files/harmony.mid');
    expect(screen.queryByRole('link', { name: 'Piano WAV' })).not.toBeInTheDocument();
  });
  it('aborts in-flight generation and revokes preview URLs on unmount', async () => {
    setupApi(); const view = studio(); await choose();
    let requestSignal: AbortSignal | null | undefined;
    vi.mocked(fetch).mockImplementation((_input, init) => { requestSignal = init?.signal; return new Promise((_resolve, reject) => requestSignal?.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')))); });
    fireEvent.click(screen.getByRole('button', { name: /Generate harmony/ }));
    await waitFor(() => expect(requestSignal).toBeDefined()); view.unmount();
    expect(requestSignal?.aborted).toBe(true); expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
});
describe('audio player', () => {
  it('controls real media playback, seek, volume, and replay', async () => {
    const view = render(<AudioPlayer src="/song.wav" title="Track" subtitle="Test" />);
    const element = view.container.querySelector('audio')!;
    Object.defineProperty(element, 'duration', { value: 10 });
    fireEvent.loadedMetadata(element);
    await userEvent.click(screen.getByRole('button', { name: 'Play Track' })); expect(element.play).toHaveBeenCalled();
    fireEvent.play(element); expect(screen.getByRole('button', { name: 'Pause Track' })).toBeVisible();
    fireEvent.change(screen.getByLabelText('Seek Track'), { target: { value: '4' } }); expect(element.currentTime).toBe(4);
    fireEvent.change(screen.getByLabelText('Volume Track'), { target: { value: '0.3' } }); expect(element.volume).toBe(0.3);
    await userEvent.click(screen.getByRole('button', { name: 'Replay Track' })); expect(element.currentTime).toBe(0);
    fireEvent.error(element); expect(screen.getByRole('alert')).toHaveTextContent('Audio unavailable');
  });
});
