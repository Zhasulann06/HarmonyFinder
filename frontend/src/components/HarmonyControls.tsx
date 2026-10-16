import { useTranslation } from "react-i18next";
import "../i18n";
import { ArrowDown, ArrowUp, Piano } from 'lucide-react';
import { isDiatonic } from '../api';
import type { HarmonySettings, Interval } from '../types';

export const INTERVALS: { value: Interval; label: string }[] = [
  { value: 'diatonic_third', label: "interval.diatonic_third" },
  { value: 'diatonic_sixth', label: "interval.diatonic_sixth" },
  { value: 'major_third', label: "interval.major_third" },
  { value: 'minor_third', label: "interval.minor_third" },
  { value: 'perfect_fourth', label: "interval.perfect_fourth" },
  { value: 'perfect_fifth', label: "interval.perfect_fifth" },
  { value: 'octave', label: "interval.octave" },
];
export const DEFAULT_SETTINGS: HarmonySettings = { interval: 'diatonic_third', direction: 'above', key: '', scale: 'major', mode: 'scale-aware' };
export function HarmonyControls({ value, disabled, onChange, outputMode = 'piano' }: { value: HarmonySettings; disabled: boolean; onChange: (value: HarmonySettings) => void; outputMode?: import('../types').OutputMode }) {
  const { t } = useTranslation();
  const diatonic = isDiatonic(value);
  function update(patch: Partial<HarmonySettings>) {
    const next = { ...value, ...patch };
    if (isDiatonic(next)) next.mode = 'scale-aware';
    onChange(next);
  }
  return <section className="panel" aria-labelledby="harmony-title">
    <div className="section-heading"><div><span className="step-number">02</span><h2 id="harmony-title">{t("harmony.title")}</h2></div><Piano size={19} className="text-muted" /></div>
    <fieldset disabled={disabled} className="settings-grid">
      <legend className="sr-only">{t("harmony.legend")}</legend>
      <label className="field full">{t("harmony.interval")}<select value={value.interval} onChange={(event) => update({ interval: event.target.value as Interval })}>
        <optgroup label={t("harmony.diatonicGroup")}>{INTERVALS.slice(0, 2).map((interval) => <option key={interval.value} value={interval.value}>{t(interval.label)}</option>)}</optgroup>
        <optgroup label={t("harmony.fixedGroup")}>{INTERVALS.slice(2).map((interval) => <option key={interval.value} value={interval.value}>{t(interval.label)}</option>)}</optgroup>
      </select></label>
      <div className="field full"><span id="direction-label">{t("harmony.direction")}</span><div className="segmented" role="group" aria-labelledby="direction-label"><button type="button" aria-pressed={value.direction === 'above'} onClick={() => update({ direction: 'above' })}><ArrowUp size={15} />  {t("harmony.above")}</button><button type="button" aria-pressed={value.direction === 'below'} onClick={() => update({ direction: 'below' })}><ArrowDown size={15} />  {t("harmony.below")}</button></div></div>
      <label className="field">{t("harmony.key")}<select value={value.key} onChange={(event) => update({ key: event.target.value })}><option value="" disabled>{t("harmony.selectKey")}</option>{['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B'].map((key) => <option key={key}>{key}</option>)}</select></label>
      <label className="field">{t("harmony.scale")}<select value={value.scale} onChange={(event) => update({ scale: event.target.value as HarmonySettings['scale'] })}><option value="major">{t("harmony.major")}</option><option value="natural_minor">{t("harmony.minor")}</option></select></label>
      <label className="field full">{t("harmony.quantization")}<select value={diatonic ? 'scale-aware' : value.mode} disabled={diatonic} aria-describedby="quantization-hint" onChange={(event) => update({ mode: event.target.value as HarmonySettings['mode'] })}><option value="chromatic">{t("harmony.chromatic")}</option><option value="scale-aware">{t("harmony.scaleAware")}</option></select></label>
      <p className="text-xs text-muted full leading-relaxed" id="quantization-hint">{diatonic ? t("harmony.diatonicHint") : t("harmony.fixedHint")}</p>
    </fieldset>
    <div className="instrument-note"><Piano size={17} /><span>{outputMode === 'vocal' ? t("harmony.vocalSource") : t("harmony.pianoSource")}</span><span className="tag ml-auto">{outputMode === 'vocal' ? t("harmony.experimentalTag") : 'GM 01'}</span></div>
  </section>;
}
