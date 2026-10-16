import en from "./locales/en.json";
import { Preferences } from './components/Preferences';
import { LocalizedMessage } from './components/LocalizedMessage';
import { useTranslation } from "react-i18next";
import "./i18n";
import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { ArrowRight, AudioLines, Check, Download, ExternalLink, LoaderCircle, Sparkles, TriangleAlert } from 'lucide-react';
import { API_BASE, ApiError, fileUrl, request } from './api';
import { generate } from './pipeline';
import { inspectDuration, validateFile } from './upload';
import type { HarmonySettings, MixSettings } from './types';
import { UploadCard, type SelectedAudio } from './components/UploadCard';
import { DEFAULT_SETTINGS, HarmonyControls } from './components/HarmonyControls';
import { Progress } from './components/Progress';
import { Results } from './components/Results';
import { HARMONY_FORWARD, VOCAL_BALANCED, MixControls } from './components/MixControls';
import { DEFAULT_MODES, ModeControls } from './components/ModeControls';
import type { ProcessingModes } from './types';

export default function App() {
  const { t } = useTranslation();
  const [selected, setSelected] = useState<SelectedAudio | null>(null);
  const [originalUrl, setOriginalUrl] = useState('');
  const [settings, setSettings] = useState<HarmonySettings>(DEFAULT_SETTINGS);
  const [mix, setMix] = useState<MixSettings>(HARMONY_FORWARD);
  const [modes, setModes] = useState<ProcessingModes>(DEFAULT_MODES);
  const needsKey = (settings.interval.startsWith('diatonic_') || settings.mode === 'scale-aware') && !settings.key;
  const [validationError, setValidationError] = useState('');
  const [checking, setChecking] = useState(false);
  const [stage, setStage] = useState(-1);
  const [audioId, setAudioId] = useState('');
  const pending = useRef(false);
  const validation = useRef<AbortController | null>(null);
  const generation = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const health = useQuery({ queryKey: ['health'], queryFn: ({ signal }) => request<{ status: string; service: string }>('/health', signal, undefined, 'GET'), refetchInterval: 30_000, retry: false });
  const mutation = useMutation({
    mutationFn: ({ file, config, mix, modes, signal }: { file: File; config: HarmonySettings; mix: MixSettings; modes: ProcessingModes; signal: AbortSignal }) => generate(file, config, signal, setStage, setAudioId, mix, modes),
    retry: false,
  });
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; validation.current?.abort(); generation.current?.abort(); }; }, []);
  useEffect(() => {
    if (!selected) { setOriginalUrl(''); return; }
    const url = URL.createObjectURL(selected.file); setOriginalUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [selected]);

  function resetOutput() { mutation.reset(); setStage(-1); setAudioId(''); }
  async function selectFile(file: File) {
    if (pending.current) return;
    validation.current?.abort();
    const controller = new AbortController(); validation.current = controller;
    resetOutput(); setSelected(null); setValidationError('');
    const error = validateFile(file);
    if (error) { setValidationError(error); setChecking(false); return; }
    setChecking(true);
    try { const duration = await inspectDuration(file, controller.signal); if (!controller.signal.aborted) setSelected({ file, duration }); }
    catch (error) { if (!controller.signal.aborted) setValidationError(error instanceof Error ? error.message : en.errors.read); }
    finally { if (!controller.signal.aborted && mounted.current) setChecking(false); }
  }
  async function start() {
    if (!selected || checking || pending.current || needsKey) return;
    pending.current = true; resetOutput();
    const controller = new AbortController(); generation.current = controller;
    try { await mutation.mutateAsync({ file: selected.file, config: { ...settings }, mix: { ...mix }, modes: { ...modes }, signal: controller.signal }); }
    catch { /* TanStack Query retains the actionable error for the UI. */ }
    finally { pending.current = false; }
  }
  const busy = mutation.isPending;
  const midiAvailable = mutation.error instanceof ApiError && mutation.error.midiAvailable && audioId;
  return <div className="studio-shell">
    <header className="site-header"><a className="brand" href="#studio" aria-label={t("header.brand")}><span className="brand-mark"><AudioLines size={23} /></span><span>Harmony<span className="font-normal text-muted">Finder</span></span></a><nav aria-label={t("header.nav")}><a className="nav-active" href="#studio">{t("header.studio")}</a><a href="#results">{t("header.results")}</a></nav><div className="connection"><span className={`status-dot ${health.data?.status === 'ok' ? 'online' : ''}`} />{health.data?.status === 'ok' ? t("header.online") : health.isFetching ? t("header.connecting") : t("header.offline")}</div><Preferences /></header>
    <main id="studio">
      <section className="hero"><div className="eyebrow"><span className="tiny-line" />  {t("hero.eyebrow")}</div><h1>{t("hero.first")}<br />{t("hero.second")} <span>{t("hero.accent")}</span></h1><p>{t("hero.description")}<br className="desktop-break" />  {t("hero.descriptionEnd")}</p><div className="hero-features"><span><Check size={13} />  {t("hero.local")}</span><span><Check size={13} />  {t("hero.daw")}</span></div><div className="hero-art" aria-hidden="true"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="melody-lines">{[38, 68, 47, 100, 70, 126, 85, 150, 98, 122, 62, 92, 50, 72, 36].map((height, i) => <span key={i} style={{ height, animationDelay: `${i * 80}ms` }} />)}</div><span className="art-caption">{t("hero.art")}</span></div></section>
      <div className="workspace-label"><span>{t("workspace.title")}</span><span>{t("workspace.local")} <span className="text-lilac">/</span>  {t("workspace.studio")}</span></div>
      <ModeControls value={modes} disabled={busy} onChange={(value) => { if (value.output_mode !== modes.output_mode) setMix(value.output_mode === 'vocal' ? VOCAL_BALANCED : HARMONY_FORWARD); setModes(value); resetOutput(); }} />
      <div className="workspace-grid"><UploadCard selected={selected} url={originalUrl} disabled={busy || checking} checking={checking} onSelect={(file) => void selectFile(file)} onRemove={() => { validation.current?.abort(); setSelected(null); setValidationError(''); resetOutput(); }} /><HarmonyControls value={settings} disabled={busy} outputMode={modes.output_mode} onChange={(value) => { setSettings(value); resetOutput(); }} /></div>
      {needsKey && <p className="notice">{t("harmony.keyRequired")}</p>}
      <MixControls value={mix} disabled={busy} outputMode={modes.output_mode} onChange={(value) => { setMix(value); resetOutput(); }} />
      {validationError && <div className="error-banner" role="alert"><TriangleAlert size={18} /><div><LocalizedMessage message={validationError} /></div></div>}
      <div className="generate-bar"><div><p className="font-medium">{t("generate.title")}</p><p className="text-sm text-muted mt-1">{selected ? t("generate.ready") : t("generate.empty")}</p></div><button className="generate-button" disabled={!selected || busy || checking || needsKey} onClick={() => void start()}>{busy ? <LoaderCircle size={18} className="animate-spin" /> : <Sparkles size={18} />}{busy ? t("generate.busy") : t("generate.action")}{!busy && <ArrowRight size={17} />}</button></div>
      <Progress stage={stage} busy={busy} failed={mutation.isError} completed={mutation.isSuccess} inputMode={modes.input_mode} outputMode={modes.output_mode} />
      {mutation.isError && <div className="error-banner" role="alert"><TriangleAlert size={19} /><div><h3>{t("generate.failed")}</h3><LocalizedMessage message={mutation.error} />{midiAvailable && <a className="download-link mt-3" href={fileUrl(audioId, 'harmony.mid')} download="harmony.mid"><Download size={14} />  {t("generate.midi")}</a>}<p className="text-xs mt-2">{t("generate.retry")}</p></div></div>}
      <Results result={mutation.data} originalUrl={originalUrl} busy={busy} outputMode={modes.output_mode} onRegenerate={() => void start()} />
      <div className="studio-footnote"><AudioLines size={16} /><p>{t("footer.note")}</p></div>
    </main>
    <footer><span>HarmonyFinder <span className="text-dim">/</span>  {t("footer.tagline")}</span><a href={`${API_BASE.replace(/\/api$/, '')}/docs`} target="_blank" rel="noreferrer">{t("footer.api")} <ExternalLink size={12} /></a></footer>
  </div>;
}
