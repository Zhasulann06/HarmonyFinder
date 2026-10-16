import en from "../locales/en.json";
import { LocalizedMessage } from './LocalizedMessage';
import { useTranslation } from "react-i18next";
import "../i18n";
import { useEffect, useId, useRef, useState } from 'react';
import { LoaderCircle, Pause, Play, RotateCcw, Volume2 } from 'lucide-react';

export function timeLabel(seconds: number): string {
  if (!Number.isFinite(seconds)) return '0:00';
  return `${Math.floor(seconds / 60)}:${Math.floor(seconds % 60).toString().padStart(2, '0')}`;
}
export function AudioPlayer({ src, title, subtitle, accent = false }: { src: string; title: string; subtitle: string; accent?: boolean }) {
  const { t } = useTranslation();
  const audio = useRef<HTMLAudioElement>(null);
  const seekId = useId();
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [current, setCurrent] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  useEffect(() => {
    setPlaying(false); setDuration(0); setCurrent(0); setLoading(true); setError('');
  }, [src]);
  async function toggle() {
    const element = audio.current;
    if (!element) return;
    if (!element.paused) { element.pause(); return; }
    try { element.volume = volume; await element.play(); }
    catch { setError(en.errors.playback); }
  }
  return <div className={`player ${accent ? 'player-accent' : ''}`}>
    <audio ref={audio} src={src} preload="metadata"
      onLoadedMetadata={(event) => { setDuration(event.currentTarget.duration); setLoading(false); }}
      onCanPlay={() => setLoading(false)} onWaiting={() => setLoading(true)}
      onPlaying={() => setLoading(false)}
      onPlay={(event) => { document.querySelectorAll('audio').forEach((other) => { if (other !== event.currentTarget) other.pause(); }); setPlaying(true); }}
      onPause={() => setPlaying(false)} onEnded={() => setPlaying(false)}
      onTimeUpdate={(event) => setCurrent(event.currentTarget.currentTime)}
      onError={() => { setLoading(false); setError(en.errors.unavailable); }} />
    <div className="flex items-center gap-3">
      <button className="play-button" aria-label={t(playing ? 'player.pause' : 'player.play', { title })} disabled={!!error} onClick={() => void toggle()}>
        {loading ? <LoaderCircle size={18} className="animate-spin" /> : playing ? <Pause size={18} fill="currentColor" /> : <Play size={18} fill="currentColor" />}
      </button>
      <div className="min-w-0 flex-1"><h3>{title}</h3><p className="text-xs text-muted mt-1">{subtitle}</p></div>
      <button className="icon-button" aria-label={t('player.replay', { title })} disabled={!!error || !duration} onClick={() => { if (audio.current) { audio.current.currentTime = 0; if (audio.current.paused) void toggle(); } }}><RotateCcw size={15} /></button>
    </div>
    <label className="sr-only" htmlFor={seekId}>{t('player.seek', { title })}</label>
    <input id={seekId} className="seek" type="range" min="0" max={duration || 0} step="0.01" value={current} disabled={!duration || !!error} onChange={(event) => { const value = Number(event.target.value); if (audio.current) audio.current.currentTime = value; setCurrent(value); }} />
    <div className="flex items-center justify-between text-xs text-muted tabular-nums"><span>{timeLabel(current)} <span className="text-dim">/ {timeLabel(duration)}</span></span>
      <label className="flex items-center gap-2"><Volume2 size={14} aria-hidden="true" /><span className="sr-only">{t('player.volume', { title })}</span><input className="volume" type="range" min="0" max="1" step="0.01" value={volume} onChange={(event) => { const value = Number(event.target.value); setVolume(value); if (audio.current) audio.current.volume = value; }} /></label>
    </div>
    {error && <div className="player-error" role="alert"><LocalizedMessage message={error} /></div>}
  </div>;
}
