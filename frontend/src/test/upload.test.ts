import { inspectDuration, validateDuration, validateFile } from '../upload';

describe('upload validation', () => {
  it.each(['song.wav', 'song.MP3'])('accepts supported filename %s', (name) => expect(validateFile(new File(['audio'], name))).toBeNull());
  it('rejects unsupported, empty, and oversized files', () => {
    expect(validateFile(new File(['x'], 'song.flac'))).toMatch(/WAV or MP3/);
    expect(validateFile(new File([], 'song.wav'))).toMatch(/empty/);
    const file = new File(['x'], 'song.wav'); Object.defineProperty(file, 'size', { value: 20 * 1024 * 1024 + 1 });
    expect(validateFile(file)).toMatch(/20 MiB/);
  });
  it('accepts the exact size and duration limits', () => {
    const file = new File(['x'], 'song.wav'); Object.defineProperty(file, 'size', { value: 20 * 1024 * 1024 });
    expect(validateFile(file)).toBeNull(); expect(validateDuration(30)).toBeNull();
  });
  it.each([0, NaN, Infinity, -1, 30.01])('rejects duration %s', (duration) => expect(validateDuration(duration)).not.toBeNull());
  it('releases the temporary URL when metadata succeeds', async () => {
    const element = document.createElement('audio');
    vi.stubGlobal('Audio', function () { return element; });
    Object.defineProperty(element, 'duration', { value: 12 });
    const result = inspectDuration(new File(['x'], 'song.wav'), new AbortController().signal);
    element.dispatchEvent(new Event('loadedmetadata'));
    await expect(result).resolves.toBe(12);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test-recording');
  });
  it('aborts metadata checks and releases the URL', async () => {
    const controller = new AbortController();
    const result = inspectDuration(new File(['x'], 'song.wav'), controller.signal);
    controller.abort();
    await expect(result).rejects.toMatchObject({ name: 'AbortError' });
    expect(URL.revokeObjectURL).toHaveBeenCalled();
  });
});
