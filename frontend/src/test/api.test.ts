import { api, ApiError, fileUrl, quantizationBody, request } from '../api';
import { DEFAULT_SETTINGS } from '../components/HarmonyControls';

const signal = () => new AbortController().signal;
function respond(data: unknown, status = 200) { vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify(data), { status })); }
describe('typed API integration', () => {
  it('accepts HTTP 202 separation responses', async () => {
    respond({ audio_id: 'id', status: 'processing' }, 202);
    expect((await api.separate('id', signal())).status).toBe('processing');
  });
  it('uploads multipart data without a manual content-type boundary', async () => {
    respond({ audio_id: 'id', status: 'queued', duration_seconds: 5 }, 201);
    await api.upload(new File(['x'], 'song.wav'), signal());
    expect(fetch).toHaveBeenCalledWith('/api/audio/upload', expect.objectContaining({ body: expect.any(FormData), headers: undefined }));
  });
  it('uses matching scale-aware quantization for diatonic harmony even with a stale mode', () => {
    expect(quantizationBody({ ...DEFAULT_SETTINGS, key: 'A', scale: 'natural_minor', mode: 'chromatic' })).toEqual({ mode: 'scale-aware', key: 'A', scale: 'natural_minor' });
    expect(quantizationBody({ ...DEFAULT_SETTINGS, interval: 'perfect_fifth', mode: 'chromatic' })).toEqual({ mode: 'chromatic' });
  });
  it('handles FastAPI validation detail arrays', async () => {
    respond({ detail: [{ msg: 'Invalid interval' }] }, 422);
    await expect(api.separate('id', signal())).rejects.toThrow('Invalid interval');
  });
  it('preserves the partial MIDI download indication on missing dependencies', async () => {
    respond({ detail: 'Set HARMONYFINDER_SOUNDFONT. MIDI remains available at /api/audio/id/files/harmony.mid' }, 503);
    await expect(api.render('id', signal())).rejects.toMatchObject({ status: 503, midiAvailable: true });
  });
  it('rejects malformed successful JSON and invalid job status', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('<html>wrong server</html>', { status: 200 }));
    await expect(request('/health', signal())).rejects.toBeInstanceOf(ApiError);
    respond({ audio_id: 'id', status: 'unknown' });
    await expect(api.status('id', signal())).rejects.toThrow('invalid job');
  });
  it('reports network and expired-session errors', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    await expect(api.status('id', signal())).rejects.toThrow('Start FastAPI');
    respond({ detail: 'Audio not found' }, 404);
    await expect(api.status('id', signal())).rejects.toThrow('restarting the API');
  });
  it('builds download URLs from IDs rather than server filesystem paths', () => expect(fileUrl('a/b', 'preview_mix.wav')).toBe('/api/audio/a%2Fb/files/preview_mix.wav'));
});
