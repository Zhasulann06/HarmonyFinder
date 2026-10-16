import { api } from '../api';
import { generate, pollSeparation, wait } from '../pipeline';
import { DEFAULT_SETTINGS } from '../components/HarmonyControls';

function response(data: unknown, status = 200) { return new Response(JSON.stringify(data), { status }); }
describe('separation polling', () => {
  it('stops as soon as completion arrives', async () => {
    vi.mocked(fetch).mockResolvedValueOnce(response({ audio_id: 'id', status: 'processing' })).mockResolvedValueOnce(response({ audio_id: 'id', status: 'completed' }));
    await pollSeparation('id', new AbortController().signal, 0, 5);
    expect(fetch).toHaveBeenCalledTimes(2);
  });
  it('stops on failure and shows the server error', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ audio_id: 'id', status: 'failed', error: 'Demucs failed' }));
    await expect(pollSeparation('id', new AbortController().signal, 0, 5)).rejects.toThrow('Demucs failed');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
  it('has a finite polling limit', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ audio_id: 'id', status: 'queued' }));
    // Each response body must be independently readable.
    vi.mocked(fetch).mockImplementation(async () => response({ audio_id: 'id', status: 'queued' }));
    await expect(pollSeparation('id', new AbortController().signal, 0, 3)).rejects.toThrow('Stopped polling');
    expect(fetch).toHaveBeenCalledTimes(3);
  });
  it('aborts a pending delay without another request', async () => {
    const controller = new AbortController(); const pending = wait(60_000, controller.signal); controller.abort();
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' });
    await expect(pollSeparation('id', controller.signal)).rejects.toMatchObject({ name: 'AbortError' });
    expect(fetch).not.toHaveBeenCalled();
  });
});
describe('end-to-end request orchestration', () => {
  it('runs each real API step in order with matching settings', async () => {
    const urls: string[] = []; const stages: number[] = [];
    vi.mocked(fetch).mockImplementation(async (input) => {
      const path = String(input); urls.push(path);
      if (path.endsWith('upload')) return response({ audio_id: 'new-id', status: 'queued', duration_seconds: 5 }, 201);
      if (path.endsWith('separate')) return response({ audio_id: 'new-id', status: 'processing' }, 202);
      if (path.endsWith('status')) return response({ audio_id: 'new-id', status: 'completed' });
      if (path.endsWith('render')) return response({ status: 'completed', files: { 'harmony.mid': 'url', 'harmony_piano.wav': 'url', 'preview_mix.wav': 'url' } });
      return response({ notes: [] });
    });
    const quantize = vi.spyOn(api, 'quantize'); const harmony = vi.spyOn(api, 'harmony');
    const result = await generate(new File(['x'], 'song.wav'), DEFAULT_SETTINGS, new AbortController().signal, (stage) => stages.push(stage), vi.fn());
    expect(result.audioId).toBe('new-id');
    expect(stages).toEqual([0, 1, 2, 3, 4, 5]);
    expect(urls.map((url) => url.split('/').at(-1))).toEqual(['upload', 'separate', 'status', 'analyze-pitch', 'quantize', 'harmony', 'render']);
    expect(quantize.mock.calls[0][1]).toEqual(harmony.mock.calls[0][1]);
  });
  it('never proceeds to later stages after upload fails', async () => {
    vi.mocked(fetch).mockResolvedValue(response({ detail: 'Corrupt WAV' }, 422));
    await expect(generate(new File(['x'], 'bad.wav'), DEFAULT_SETTINGS, new AbortController().signal, vi.fn(), vi.fn())).rejects.toThrow('Corrupt WAV');
    expect(fetch).toHaveBeenCalledTimes(1);
  });
});
