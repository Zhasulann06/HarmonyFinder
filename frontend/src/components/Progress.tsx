import { useTranslation } from "react-i18next";
import "../i18n";
import { Check, Circle, LoaderCircle, TriangleAlert } from 'lucide-react';


export function Progress({ stage, busy, failed, completed, inputMode = 'full_song', outputMode = 'piano' }: { stage: number; busy: boolean; failed: boolean; completed: boolean; inputMode?: import('../types').InputMode; outputMode?: import('../types').OutputMode }) {
  const { t } = useTranslation();
  const stages = ['progress.upload', 'progress.separation', 'progress.pitch', 'progress.quantize', 'progress.harmony', 'progress.piano'].map((key) => t(key));
  if (inputMode === 'vocals_only') stages[1] = t("progress.prepare");
  if (outputMode === 'vocal') stages[5] = t("progress.vocal");
  return <section className="pipeline" aria-label={t("progress.label")}><ol>{stages.map((name, index) => {
    const done = completed || index < stage;
    const active = index === stage;
    return <li key={index} className={`${done ? 'done' : ''} ${active ? 'active' : ''}`} aria-current={active && busy ? 'step' : undefined}>
      <span className="pipeline-dot">{done ? <Check size={13} /> : active && failed ? <TriangleAlert size={13} /> : active && busy ? <LoaderCircle size={13} className="animate-spin" /> : <Circle size={7} fill="currentColor" />}</span><span>{name}</span>
    </li>;
  })}</ol><p aria-live="polite" className="pipeline-caption">{busy ? t('progress.running', { stage: stages[stage], hint: stage === 1 && inputMode === 'full_song' ? t('progress.cpu') : t('progress.keepOpen') }) : failed ? t("progress.failed") : completed ? t("progress.complete") : t("progress.idle")}</p></section>;
}
