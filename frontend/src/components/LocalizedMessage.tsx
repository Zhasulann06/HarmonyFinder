import { useTranslation } from 'react-i18next';
import en from '../locales/en.json';
import { ApiError } from '../api';

const exact = new Map<string, string>(Object.entries(en.errors).map(([key, message]) => [message, `errors.${key}`]));
Object.entries(en.warnings).forEach(([key, message]) => exact.set(message, `warnings.${key}`));
export function messageKey(message: string): string {
  const known = exact.get(message);
  if (known) return known;
  if (/rubber.?band|HARMONYFINDER_RUBBERBAND/i.test(message)) return 'errors.rubberband';
  if (/fluidsynth|soundfont|HARMONYFINDER_SOUNDFONT/i.test(message)) return 'errors.fluidsynth';
  if (/ffmpeg|ffprobe/i.test(message)) return 'errors.ffmpeg';
  if (/preparation failed/i.test(message)) return 'errors.preparation';
  if (/separation failed|demucs/i.test(message)) return 'errors.separation';
  if (/already|is processing/i.test(message)) return 'errors.busy';
  if (/scale|key|diatonic/i.test(message)) return 'errors.scale';
  if (/not available|not completed|requires completed|requires prepared/i.test(message)) return 'errors.prerequisite';
  if (/20 Mi?B|exceeds 20/i.test(message)) return 'errors.size';
  if (/30 seconds|at most 30/i.test(message)) return 'errors.long';
  if (/Only WAV|unsupported.*format/i.test(message)) return 'errors.format';
  if (/corrupt|invalid.*audio|invalid.*WAV|truncated|not MP3|no playable audio/i.test(message)) return 'errors.invalidAudio';
  if (/pitch analysis failed/i.test(message)) return 'errors.pitch';
  if (/export failed/i.test(message)) return 'errors.export';
  if (/stem mixing requires/i.test(message)) return 'errors.prerequisite';
  if (/rendering failed/i.test(message)) return 'errors.render';
  if (/Input should|Value error|invalid.*(input|interval|direction|gain)|greater than|less than|Field required|Extra inputs/i.test(message)) return 'errors.input';
  return 'errors.unknown';
}

export function LocalizedMessage({ message }: { message: string | Error }) {
  const { t } = useTranslation();
  const raw = typeof message === 'string' ? message : message.message;
  const key = messageKey(raw);
  const details = message instanceof ApiError ? message.technicalDetails : raw;
  return <><span>{t(key)}</span>{(!exact.has(raw) || message instanceof ApiError) && <details className="technical-details"><summary>{t('errors.details')}</summary><pre>{details}</pre></details>}</>;
}
