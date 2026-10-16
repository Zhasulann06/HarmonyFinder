import { useTranslation } from "react-i18next";
import "../i18n";
import { useRef, useState } from 'react';
import { FileAudio2, UploadCloud, X } from 'lucide-react';
import { AudioPlayer, timeLabel } from './AudioPlayer';

export interface SelectedAudio { file: File; duration: number }
export function UploadCard({ selected, url, disabled, checking, onSelect, onRemove }: { selected: SelectedAudio | null; url: string; disabled: boolean; checking: boolean; onSelect: (file: File) => void; onRemove: () => void }) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  return <section className="panel" aria-labelledby="upload-title">
    <div className="section-heading"><div><span className="step-number">01</span><h2 id="upload-title">{t("upload.title")}</h2></div><span className="tag">WAV / MP3</span></div>
    <input ref={input} id="audio-file" tabIndex={-1} className="sr-only" type="file" accept=".wav,.mp3,audio/wav,audio/mpeg" disabled={disabled} aria-label={t("upload.choose")} onChange={(event) => { const file = event.target.files?.[0]; if (file) onSelect(file); event.target.value = ''; }} />
    {!selected ? <button type="button" disabled={disabled} className={`dropzone ${dragging ? 'dragging' : ''}`} onClick={() => input.current?.click()}
      onDragOver={(event) => { event.preventDefault(); if (!disabled) setDragging(true); }} onDragLeave={() => setDragging(false)}
      onDrop={(event) => { event.preventDefault(); setDragging(false); if (!disabled && event.dataTransfer.files[0]) onSelect(event.dataTransfer.files[0]); }}>
      <span className="upload-icon"><UploadCloud size={28} strokeWidth={1.5} /></span>
      <strong>{checking ? t("upload.reading") : t("upload.drop")}</strong>
      <span className="text-sm text-muted">{t("upload.or")} <span className="text-lilac">{t("upload.browse")}</span>  {t("upload.start")}</span>
      <span className="upload-limits">{t("upload.duration")} <span>·</span>  {t("upload.size")}</span>
    </button> : <div className="selected-track">
      <div className="file-row"><FileAudio2 size={22} className="text-lilac shrink-0" /><div className="min-w-0 flex-1"><p className="truncate font-medium" title={selected.file.name}>{selected.file.name}</p><p className="text-xs text-muted mt-1">{timeLabel(selected.duration)} · {(selected.file.size / 1024 / 1024).toFixed(2)}  {t("upload.unit")}</p></div><button disabled={disabled} className="icon-button" aria-label={t("upload.remove")} onClick={onRemove}><X size={18} /></button></div>
      {url && <AudioPlayer key={url} src={url} title={t("upload.original")} subtitle={t("upload.untouched")} />}
      <button className="text-button" disabled={disabled} onClick={() => input.current?.click()}>{t("upload.replace")}</button>
    </div>}
    <p className="section-note">{t("upload.hint")}</p>
  </section>;
}
