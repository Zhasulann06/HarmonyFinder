import { useTranslation } from "react-i18next";
import "../i18n";
import type { ProcessingModes } from '../types';

export const DEFAULT_MODES: ProcessingModes = { input_mode: 'full_song', output_mode: 'piano' };
export function ModeControls({ value, disabled, onChange }: { value: ProcessingModes; disabled: boolean; onChange: (value: ProcessingModes) => void }) {
  const { t } = useTranslation();
  return <section className="panel mode-panel" aria-label={t("modes.title")}>
    <fieldset disabled={disabled} className="settings-grid">
      <legend className="sr-only">{t("modes.legend")}</legend>
      <label className="field">{t("modes.input")}<select value={value.input_mode} onChange={(event) => onChange({ ...value, input_mode: event.target.value as ProcessingModes['input_mode'] })}>
        <option value="full_song">{t("modes.full")}</option><option value="vocals_only">{t("modes.vocals")}</option>
      </select><span className="text-xs text-muted">{value.input_mode === 'vocals_only' ? t("modes.bypass") : t("modes.separate")}</span></label>
      <label className="field">{t("modes.output")}<select value={value.output_mode} onChange={(event) => onChange({ ...value, output_mode: event.target.value as ProcessingModes['output_mode'] })}>
        <option value="piano">{t("modes.piano")}</option><option value="vocal">{t("modes.vocal")}</option>
      </select><span className="text-xs text-muted">{value.output_mode === 'vocal' ? t("modes.vocalHint") : t("modes.pianoHint")}  {t("modes.reset")}</span></label>
    </fieldset>
    {value.output_mode === 'vocal' && <p className="notice" role="status"><strong>{t("modes.warningTitle")}</strong>  {t("modes.warning")}</p>}
  </section>;
}
