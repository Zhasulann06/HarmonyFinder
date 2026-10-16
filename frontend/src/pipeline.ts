import en from "./locales/en.json";
import { api } from './api';
import type { GenerationResult, HarmonySettings, MixSettings } from './types';

export function wait(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    signal.throwIfAborted();
    const cancel = () => { clearTimeout(timer); reject(signal.reason); };
    const timer = setTimeout(() => { signal.removeEventListener('abort', cancel); resolve(); }, ms);
    signal.addEventListener('abort', cancel, { once: true });
  });
}
export async function pollSeparation(id: string, signal: AbortSignal, interval = 2000, maxAttempts = 450): Promise<void> {
  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    signal.throwIfAborted();
    const job = await api.status(id, signal);
    if (job.status === 'completed') return;
    if (job.status === 'failed') throw new Error(job.error || en.errors.separation);
    if (attempt < maxAttempts - 1) await wait(interval, signal);
  }
  throw new Error(en.errors.pollTimeout);
}
export async function generate(file: File, settings: HarmonySettings, signal: AbortSignal, onStage: (stage: number) => void, onUpload: (id: string) => void, mix?: MixSettings, modes: import('./types').ProcessingModes = { input_mode: 'full_song', output_mode: 'piano' }): Promise<GenerationResult> {
  const stage = (index: number) => { signal.throwIfAborted(); onStage(index); };
  stage(0);
  const upload = await api.upload(file, signal, modes.input_mode);
  signal.throwIfAborted(); onUpload(upload.audio_id);
  const id = upload.audio_id;
  stage(1); await api.separate(id, signal);
  // A wall-clock bound also covers slow individual status requests.
  try { await pollSeparation(id, AbortSignal.any([signal, AbortSignal.timeout(15 * 60_000)])); }
  catch (error) {
    if (error instanceof DOMException && error.name === 'TimeoutError') throw new Error(en.errors.separationTimeout);
    throw error;
  }
  stage(2); await api.pitch(id, signal);
  stage(3); await api.quantize(id, settings, signal);
  stage(4); const harmony = await api.harmony(id, settings, signal);
  if (!Array.isArray(harmony.notes)) throw new Error(en.errors.harmonyResponse);
  stage(5); const render = await api.render(id, signal, mix, modes.output_mode);
  const required = modes.output_mode === 'vocal' ? ['harmony_vocals.wav', 'preview_mix.wav'] as const : ['harmony.mid', 'harmony_piano.wav', 'preview_mix.wav'] as const;
  if (render.status !== 'completed' || required.some((name) => !render.files?.[name]) || (render.output_mode && render.output_mode !== modes.output_mode)) throw new Error(en.errors.renderResponse);
  signal.throwIfAborted();
  return { audioId: id, harmony, render };
}
