import en from "./locales/en.json";
export function validateFile(file: File): string | null {
  if (!/\.(wav|mp3)$/i.test(file.name)) return en.errors.format;
  if (file.size === 0) return en.errors.empty;
  if (file.size > 20 * 1024 * 1024) return en.errors.size;
  return null;
}
export function validateDuration(duration: number): string | null {
  if (!Number.isFinite(duration) || duration <= 0) return en.errors.invalidAudio;
  return duration > 30 ? en.errors.long : null;
}
export function inspectDuration(file: File, signal: AbortSignal): Promise<number> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const audio = new Audio();
    const url = URL.createObjectURL(file);
    const cleanup = () => { clearTimeout(timer); signal.removeEventListener('abort', abort); audio.onloadedmetadata = null; audio.onerror = null; audio.removeAttribute('src'); audio.load(); URL.revokeObjectURL(url); };
    const abort = () => { cleanup(); reject(signal.reason); };
    const timer = setTimeout(() => { cleanup(); reject(new Error(en.errors.metadata)); }, 10_000);
    audio.onloadedmetadata = () => { const duration = audio.duration; cleanup(); const error = validateDuration(duration); if (error) reject(new Error(error)); else resolve(duration); };
    audio.onerror = () => { cleanup(); reject(new Error(en.errors.browser)); };
    signal.addEventListener('abort', abort, { once: true });
    audio.preload = 'metadata'; audio.src = url;
  });
}
