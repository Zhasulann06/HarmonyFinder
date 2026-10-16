import en from "./locales/en.json";
import type { HarmonyMelody, HarmonySettings, JobStatus, MixSettings, PitchAnalysis, QuantizedMelody, RenderFile, RenderResponse, UploadResponse } from './types';
import type { InputMode, OutputMode } from './types';

export const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api').replace(/\/$/, '');
export class ApiError extends Error {
  constructor(message: string, public status: number, public midiAvailable = false, public technicalDetails = message) { super(message); }
}
export function fileUrl(id: string, name: RenderFile): string {
  return `${API_BASE}/audio/${encodeURIComponent(id)}/files/${name}`;
}

function errorMessage(detail: unknown, status: number): string {
  if (status === 404) return en.errors.session;
  if (Array.isArray(detail)) return detail.map((entry: { msg?: string }) => entry.msg || en.errors.input).join('. ');
  if (typeof detail === 'string') return detail;
  return `The API returned HTTP ${status}. Check that the backend is running and try again.`;
}

export async function request<T>(path: string, signal: AbortSignal, body?: unknown, method = 'POST'): Promise<T> {
  const timeout = AbortSignal.timeout(20 * 60_000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method, signal: AbortSignal.any([signal, timeout]),
      headers: body && !(body instanceof FormData) ? { 'Content-Type': 'application/json' } : undefined,
      body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
    });
    const data: unknown = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : null;
      throw new ApiError(errorMessage(detail, response.status), response.status, typeof detail === 'string' && detail.includes('MIDI remains available at'), `HTTP ${response.status}\n${JSON.stringify(detail, null, 2)}`);
    }
    if (data === null || typeof data !== 'object') throw new ApiError(en.errors.json, response.status);
    return data as T;
  } catch (error) {
    if (signal.aborted || error instanceof ApiError) throw error;
    if (timeout.aborted) throw new Error(en.errors.requestTimeout);
    throw new Error(en.errors.network);
  }
}
function assertJob(job: JobStatus): void {
  if (typeof job.audio_id !== 'string' || !['queued', 'processing', 'completed', 'failed'].includes(job.status)) throw new Error(en.errors.job);
}
export const api = {
  async upload(file: File, signal: AbortSignal, inputMode: InputMode = 'full_song') {
    const form = new FormData(); form.append('file', file);
    form.append('input_mode', inputMode);
    const result = await request<UploadResponse>('/audio/upload', signal, form);
    assertJob(result); return result;
  },
  async separate(id: string, signal: AbortSignal) {
    const result = await request<JobStatus>(`/audio/${encodeURIComponent(id)}/separate`, signal);
    assertJob(result); return result;
  },
  async status(id: string, signal: AbortSignal) {
    const result = await request<JobStatus>(`/audio/${encodeURIComponent(id)}/status`, signal, undefined, 'GET');
    assertJob(result); return result;
  },
  pitch: (id: string, signal: AbortSignal) => request<PitchAnalysis>(`/audio/${encodeURIComponent(id)}/analyze-pitch`, signal),
  quantize: (id: string, settings: HarmonySettings, signal: AbortSignal) => request<QuantizedMelody>(`/audio/${encodeURIComponent(id)}/quantize`, signal, quantizationBody(settings)),
  harmony: (id: string, settings: HarmonySettings, signal: AbortSignal) => request<HarmonyMelody>(`/audio/${encodeURIComponent(id)}/harmony`, signal, { interval: settings.interval, direction: settings.direction, key: settings.key || null, scale: settings.scale }),
  render: (id: string, signal: AbortSignal, mix?: MixSettings, outputMode: OutputMode = 'piano') => request<RenderResponse>(`/audio/${encodeURIComponent(id)}/render`, signal, { velocity: 90, ...(mix ?? { instrumental_gain: 0.85, lead_vocal_gain: 0.40, harmony_gain: outputMode === 'vocal' ? 0.6 : 8.0 }), ...(outputMode === 'vocal' ? { output_mode: outputMode } : {}) }),
};
export function isDiatonic(settings: HarmonySettings): boolean { return settings.interval.startsWith('diatonic_'); }
export function quantizationBody(settings: HarmonySettings) {
  return isDiatonic(settings) || settings.mode === 'scale-aware'
    ? { mode: 'scale-aware', key: settings.key, scale: settings.scale }
    : { mode: 'chromatic' };
}
