import { useTranslation } from "react-i18next";
import "../i18n";
import { SlidersHorizontal } from 'lucide-react';
import type { MixSettings } from '../types';

export const HARMONY_FORWARD: MixSettings = { instrumental_gain: 0.85, lead_vocal_gain: 0.40, harmony_gain: 8.0 };
export const BALANCED: MixSettings = { instrumental_gain: 0.85, lead_vocal_gain: 0.70, harmony_gain: 4.0 };
export const VOCAL_BALANCED: MixSettings = { instrumental_gain: 0.85, lead_vocal_gain: 0.70, harmony_gain: 0.6 };
const controls = [
  { key: 'instrumental_gain', label: "mixer.instrumental", max: 2, step: 0.05 },
  { key: 'lead_vocal_gain', label: "mixer.lead", max: 2, step: 0.05 },
  { key: 'harmony_gain', label: "mixer.harmony", max: 12, step: 0.05 },
] as const;
export function MixControls({ value, disabled, onChange, outputMode = 'piano' }: { value: MixSettings; disabled: boolean; onChange: (value: MixSettings) => void; outputMode?: import('../types').OutputMode }) {
  const { t } = useTranslation();
  const forward = outputMode === 'vocal' ? { ...VOCAL_BALANCED, lead_vocal_gain: 0.4, harmony_gain: 1 } : HARMONY_FORWARD;
  const balanced = outputMode === 'vocal' ? VOCAL_BALANCED : BALANCED;
  const matches = (preset: MixSettings) => controls.every(({ key }) => preset[key] === value[key]);
  return <section className="panel mixer-panel" aria-labelledby="mixer-title">
    <div className="section-heading"><div><SlidersHorizontal size={18} className="text-lilac" /><h2 id="mixer-title">{t("mixer.title")}</h2></div><span className="tag">{t("mixer.preview")}</span></div>
    <fieldset disabled={disabled}>
      <legend className="sr-only">{t("mixer.legend")}</legend>
      <div className="mix-presets" role="group" aria-label={t("mixer.preset")}><button className="download-link" type="button" aria-pressed={matches(forward)} onClick={() => onChange({ ...forward })}>{t("mixer.forward")}</button><button className="download-link" type="button" aria-pressed={matches(balanced)} onClick={() => onChange({ ...balanced })}>{t("mixer.balanced")}</button></div>
      <div className="mix-sliders">{controls.map(({ key, label, max, step }) => <label key={key} className="field"><span className="flex justify-between gap-3"><span>{t(label)}</span><span aria-hidden="true" className="text-lilac tabular-nums">{value[key].toFixed(2)}×</span></span><input type="range" aria-label={t(label)} min="0" max={max} step={step} value={value[key]} onChange={(event) => onChange({ ...value, [key]: Number(event.target.value) })} /></label>)}</div>
    </fieldset>
    <p className="section-note">{t("mixer.hint")} {outputMode === 'vocal' ? t("mixer.vocalHint") : t("mixer.pianoHint")}</p>
  </section>;
}
