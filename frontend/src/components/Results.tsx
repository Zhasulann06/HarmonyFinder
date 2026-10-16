import { LocalizedMessage } from './LocalizedMessage';
import { useTranslation } from "react-i18next";
import "../i18n";
import { Download, Headphones, Music2, RotateCcw } from 'lucide-react';
import { fileUrl } from '../api';
import type { GenerationResult, RenderFile } from '../types';
import { AudioPlayer } from './AudioPlayer';

const downloads: { file: RenderFile; label: string }[] = [{ file: 'harmony.mid', label: "downloads.midi" }, { file: 'harmony_piano.wav', label: "downloads.piano" }, { file: 'harmony_vocals.wav', label: "downloads.vocal" }, { file: 'preview_mix.wav', label: "downloads.preview" }];
export function Results({ result, originalUrl, onRegenerate, busy, outputMode = 'piano' }: { result: GenerationResult | undefined; originalUrl: string; onRegenerate: () => void; busy: boolean; outputMode?: import('../types').OutputMode }) {
  const { t } = useTranslation();
  const vocal = result ? result.render.output_mode === 'vocal' || !!result.render.files['harmony_vocals.wav'] : outputMode === 'vocal';
  const harmonyFile = vocal ? 'harmony_vocals.wav' : 'harmony_piano.wav';
  return <section id="results" className={`results-section ${result ? 'ready' : ''}`} aria-labelledby="results-title">
    <div className="section-heading"><div><span className="step-number">03</span><h2 id="results-title">{t("results.title")}</h2></div>{result && <span className="ready-label">{t("results.ready")}</span>}</div>
    {!result ? <div className="results-empty"><span className="empty-icon"><Headphones size={27} strokeWidth={1.5} /></span><h3>{t("results.emptyTitle")}</h3><p>{t("results.emptyHint")}</p><div className="flex gap-2 mt-5"><span className="tag">{vocal ? t("results.experimental") : t("results.piano")}</span><span className="tag">{t("results.preview")}</span>{!vocal && <span className="tag">{t("results.midi")}</span>}</div></div> : <>
      <div className="result-summary"><Music2 size={16} /><span>{t('results.summary', { count: result.harmony.notes.length, rate: result.render.sample_rate / 1000, quality: vocal ? t('results.experimentalShort') : t('results.timing') })}</span></div>
      {result.harmony.notes.length === 0 && <p className="notice">{t("results.noNotes")}</p>}
      {result.render.warning && <div className="notice"><LocalizedMessage message={result.render.warning} /></div>}
      {result.render.mix_diagnostics?.warning && <div className="notice"><LocalizedMessage message={result.render.mix_diagnostics.warning} /></div>}
      {result.render.mix_diagnostics && result.render.mix_diagnostics.headroom_gain < 1 && <p className="notice">{t('results.protection', { db: (-20 * Math.log10(result.render.mix_diagnostics.headroom_gain)).toFixed(1) })}</p>}
      <div className="players-grid"><AudioPlayer key={`original-${result.audioId}`} src={originalUrl} title={t("results.original")} subtitle={t("results.uploaded")} />{result.render.files[harmonyFile] && <AudioPlayer key={`${harmonyFile}-${result.audioId}`} src={fileUrl(result.audioId, harmonyFile)} title={vocal ? t("results.vocal") : t("results.piano")} subtitle={vocal ? t("results.shifted") : t("results.secondVoice")} />}{result.render.files['preview_mix.wav'] && <AudioPlayer key={`mix-${result.audioId}`} src={fileUrl(result.audioId, 'preview_mix.wav')} title={t("results.preview")} subtitle={result.render.mix_diagnostics?.mode === 'stems' ? t("results.stems") : t("results.legacy")} accent />}</div>
      <div className="downloads"><span className="text-sm text-muted">{t("results.take")}</span><div className="flex flex-wrap gap-2">{downloads.filter(({ file }) => result.render.files[file]).map(({ file, label }) => <a className="download-link" key={file} href={fileUrl(result.audioId, file)} download={file}><Download size={14} />{t(label)}</a>)}</div></div>
      <button className="text-button" disabled={busy} onClick={onRegenerate}><RotateCcw size={14} />  {t("results.regenerate")}</button>
    </>}
  </section>;
}
