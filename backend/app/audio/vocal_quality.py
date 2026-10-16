"""Isolated measurement and ablation helpers; never imported by production routes."""

import math
from dataclasses import replace

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import hilbert, welch

from backend.app.audio.harmony import HarmonyConfig, HarmonyMelody, generate_harmony
from backend.app.audio.harmony_curve import CurvePoint, HarmonyPitchCurve
from backend.app.audio.music import KEYS, SCALES
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizedMelody


def rms_grid(audio: np.ndarray, rate: int, step: float = .01) -> np.ndarray:
    hop = round(rate * step)
    if audio.ndim != 2 or not len(audio) or hop < 1 or not np.all(np.isfinite(audio)):
        raise ValueError("Expected finite nonempty audio and positive grid")
    pad = (-len(audio)) % hop
    padded = np.pad(audio.astype(np.float64), ((0, pad), (0, 0)))
    return np.sqrt(np.mean(padded.reshape(-1, hop, audio.shape[1]) ** 2, axis=(1, 2)))


def regions(mask: np.ndarray, step: float = .01, minimum: float = .04) -> list[dict]:
    edges = np.diff(np.r_[False, mask, False].astype(int))
    return [{"start": round(s*step,6), "end": round(e*step,6), "duration": round((e-s)*step,6)}
            for s,e in zip(np.flatnonzero(edges==1), np.flatnonzero(edges==-1)) if (e-s)*step >= minimum-1e-9]


def scheduled_curve(duration: float, schedule: list[tuple[float,float]], transition: float = .02) -> HarmonyPitchCurve:
    """Known control schedule, not a musically validated harmony for a song."""
    if (not math.isfinite(duration) or not 0 < duration <= 30 or not .005 <= transition <= .2
            or not schedule or schedule[0][0] != 0
            or any(not math.isfinite(t) or not math.isfinite(s) or not 0 <= t < duration or not -12 <= s <= 12 for t,s in schedule)
            or any(b[0]<=a[0] for a,b in zip(schedule,schedule[1:]))):
        raise ValueError("Invalid known pitch schedule")
    times=np.r_[np.arange(0,duration,.005),duration]
    raw=np.array([schedule[max(0,np.searchsorted([x[0] for x in schedule],t,side='right')-1)][1] for t in times])
    width=max(1,round(transition/.005))
    smooth=np.convolve(np.pad(raw,(width//2,width-1-width//2),mode='edge'),np.ones(width)/width,mode='valid')
    curve=HarmonyPitchCurve(duration,tuple(CurvePoint(float(t),float(np.clip(s,-12,12)),1) for t,s in zip(times,smooth)),transition)
    curve.validate()
    return curve


def without_gate(curve: HarmonyPitchCurve) -> HarmonyPitchCurve:
    return replace(curve,points=tuple(replace(p,gain=1.0) for p in curve.points))


def delay_automation(curve: HarmonyPitchCurve, seconds: float) -> HarmonyPitchCurve:
    """Measured diagnostic compensation only; amplitude timing is not delayed."""
    if not math.isfinite(seconds) or not 0 <= seconds <= .35: raise ValueError("Invalid measured control delay")
    times=np.array([p.time_seconds for p in curve.points]); shifts=np.array([p.shift_semitones for p in curve.points])
    delayed=np.interp(times-seconds,times,shifts)
    result=replace(curve,points=tuple(replace(p,shift_semitones=float(s),
        expressive_target_midi=p.detected_midi+float(s) if p.detected_midi is not None else None)
        for p,s in zip(curve.points,delayed)))
    result.validate()
    return result


def held_interval_curve(harmony: HarmonyMelody, transition: float = .08) -> HarmonyPitchCurve:
    if not harmony.notes: raise ValueError("Cannot infer held control from empty notes")
    schedule=[(0.0,float(harmony.notes[0].harmony_midi_note-harmony.notes[0].original_midi_note))]
    for note in harmony.notes[1:]:
        shift=float(note.harmony_midi_note-note.original_midi_note)
        if shift!=schedule[-1][1]: schedule.append((note.start_time,shift))
    return scheduled_curve(harmony.duration_seconds,schedule,transition)


def audit_plan(audio: np.ndarray, rate: int, analysis: PitchAnalysis, lead: QuantizedMelody,
               harmony: HarmonyMelody, curve: HarmonyPitchCurve) -> dict:
    curve.validate()
    expected=generate_harmony(lead,HarmonyConfig(interval=harmony.interval,direction=harmony.direction,key=harmony.key,scale=harmony.scale))
    if expected!=harmony: raise ValueError("Invalid harmony intervals or timing")
    if len(lead.notes)!=len(analysis.notes) or len(audio)/rate != analysis.duration_seconds:
        raise ValueError("Source/analysis alignment mismatch")
    times=np.array([f.time_seconds for f in analysis.frames]); step=analysis.hop_length/analysis.sample_rate
    covered=np.array([any(n.start_time<=t<n.end_time for n in harmony.notes) for t in times])
    voiced=np.array([f.voiced for f in analysis.frames])
    energy=rms_grid(audio,rate,step)[:len(times)]
    threshold=max(.003,float(energy.max())*.03)
    energetic=energy>=threshold
    allowed={(KEYS[harmony.key]+x)%12 for x in SCALES[harmony.scale]} if harmony.key and harmony.scale else set(range(12))
    rows=[]
    for original,q,h in zip(analysis.notes,lead.notes,harmony.notes):
        rounded=math.floor(original.midi_pitch+.5)
        flags=[]
        if rounded%12 not in allowed: flags.append("rounded source outside assumed scale")
        if original.voiced_probability is not None and original.voiced_probability<.5: flags.append("low voicing probability (not calibrated pitch confidence)")
        if original.duration<.12: flags.append("short note / little stable interior")
        centre_error=100*(q.original_midi_pitch-q.corrected_midi_pitch)
        if abs(centre_error)>50: flags.append("interval-only waveform centre differs >50 cents from planned anchor")
        rows.append({"start":q.start_time,"end":q.end_time,"duration":q.duration,"detected_midi":original.midi_pitch,
                     "rounded_source_in_scale":rounded%12 in allowed,"corrected_lead":q.corrected_midi_pitch,
                     "target":h.harmony_midi_note,"shift":h.harmony_midi_note-h.original_midi_note,
                     "expected_waveform_median":q.original_midi_pitch+h.harmony_midi_note-h.original_midi_note,
                     "centre_error_cents":centre_error,"voicing_probability":original.voiced_probability,"flags":flags})
    shifts=np.array([p.shift_semitones for p in curve.points]); ct=np.array([p.time_seconds for p in curve.points])
    gain=np.array([p.gain for p in curve.points]); dg=np.diff(gain)
    sample_gain=np.interp(np.arange(len(audio))/rate,ct,gain)
    total=float(np.sum(audio.astype(float)**2))
    removed=float(np.sum(audio.astype(float)**2*(1-sample_gain[:,None]**2))) / total if total else 0
    octave=[]
    for a,b in zip(analysis.frames,analysis.frames[1:]):
        if a.voiced and b.voiced and a.midi_pitch is not None and b.midi_pitch is not None and b.time_seconds-a.time_seconds<=.03 and 10<=abs(b.midi_pitch-a.midi_pitch)<=14:
            octave.append({"start":a.time_seconds,"end":b.time_seconds,"delta_semitones":b.midi_pitch-a.midi_pitch})
    low=np.array([f.voiced and f.voiced_probability is not None and f.voiced_probability<.5 for f in analysis.frames])
    return {"key":harmony.key,"scale":harmony.scale,"key_verified":False,"interval_math_valid":True,
            "note_count":len(rows),"planned_seconds":sum(n.duration for n in lead.notes),"notes":rows,
            "voiced_seconds":int(voiced.sum())*step,"voiced_fraction":float(voiced.mean()),
            "low_voicing_seconds":int(low.sum())*step,"low_voicing_regions":regions(low,step),
            "unplanned_voiced_regions":regions(voiced & ~covered,step,.01),
            "energetic_threshold_rms":threshold,"energetic_unplanned_regions":regions(energetic & ~covered,step),
            "energy_removed_by_mask_fraction":removed,
            "energetic_unvoiced_seconds":int((energetic & ~voiced).sum())*step,
            "octave_jump_candidates":octave,
            "source_notes_outside_assumed_scale":sum(not r['rounded_source_in_scale'] for r in rows),
            "large_centre_error_notes":sum(abs(r['centre_error_cents'])>50 for r in rows),
            "centre_error_cents_range":[min((r['centre_error_cents'] for r in rows),default=0),max((r['centre_error_cents'] for r in rows),default=0)],
            "curve":{"points":len(shifts),"range":[float(shifts.min()),float(shifts.max())],
                     "maximum_knot_jump_semitones":float(np.max(np.abs(np.diff(shifts)))),
                     "jumps_over_half_semitone":[float(ct[i+1]) for i in np.flatnonzero(np.abs(np.diff(shifts))>.5)],
                     "gain_attack_count":int(np.count_nonzero((gain[:-1]==0)&(dg>0))),
                     "active_near_unison_seconds_estimate":float(np.sum(np.diff(ct)*((gain[:-1]>.9)&(np.abs(shifts[:-1])<2.5))))}}


def audio_features(audio: np.ndarray, rate: int) -> dict:
    frequencies,power=welch(audio,fs=rate,nperseg=min(2048,len(audio)),axis=0)
    spectrum=power.mean(axis=1); total=float(spectrum.sum())
    high=(frequencies>=4000)&(frequencies<=min(10000,rate/2))
    corr=None
    if audio.shape[1]==2 and np.all(audio.std(axis=0)>1e-8): corr=float(np.corrcoef(audio.T)[0,1])
    return {"high_band_power_fraction":float(spectrum[high].sum()/total) if total else 0,
            "spectral_centroid_hz":float(np.sum(frequencies*spectrum)/total) if total else 0,
            "stereo_zero_lag_correlation":corr}


def compare_features(original: np.ndarray, processed: np.ndarray, rate: int) -> dict:
    if original.shape!=processed.shape: raise ValueError("Audio comparison must use matching sample timelines/channels")
    f,a=welch(original,fs=rate,nperseg=min(2048,len(original)),axis=0)
    _,b=welch(processed,fs=rate,nperseg=min(2048,len(processed)),axis=0)
    a=a.mean(axis=1);b=b.mean(axis=1)
    width=max(1,round(400/(f[1]-f[0])))
    ea=uniform_filter1d(a/max(float(a.sum()),1e-20),width)
    eb=uniform_filter1d(b/max(float(b.sum()),1e-20),width)
    band=(f>=300)&(f<=3500)
    spectral=float(np.mean(np.abs(10*np.log10(np.maximum(ea[band],1e-12))-10*np.log10(np.maximum(eb[band],1e-12)))))
    x,y=rms_grid(original,rate),rms_grid(processed,rate)
    active=x>=max(.003,float(x.max())*.03)
    delta=20*np.log10(np.maximum(y[active],1e-9)/x[active])
    return {"source":audio_features(original,rate),"processed":audio_features(processed,rate),
            "normalised_smoothed_spectral_envelope_mae_db":spectral,
            "active_rms_delta_p10_p50_p90_db":np.percentile(delta,[10,50,90]).tolist() if len(delta) else [],
            "active_blocks_attenuated_over_20db":int(np.count_nonzero(delta < -20))}


def match_loudness(excerpts: dict[str,np.ndarray], rate: int) -> tuple[dict[str,np.ndarray],dict]:
    """BS.1770 matching for listening only; never modifies production audio gains."""
    try: import pyloudnorm as pyln
    except ImportError as exc: raise RuntimeError("Install backend/requirements-quality.txt for loudness-matched excerpts") from exc
    if not excerpts or any(a.ndim!=2 or len(a)<rate*.4 or not np.all(np.isfinite(a)) for a in excerpts.values()):
        raise ValueError("Listening excerpts must be finite, >=400 ms, and share their boundaries")
    if len({a.shape for a in excerpts.values()})!=1: raise ValueError("Excerpt shapes differ")
    meter=pyln.Meter(rate)
    levels={name:float(meter.integrated_loudness(a)) for name,a in excerpts.items()}
    eligible=[v for v in levels.values() if math.isfinite(v) and v>=-60]
    if not eligible: raise ValueError("Excerpts are silent/near-silent; do not auto-amplify")
    target=min(-23.0,min(eligible)+12)
    gains={name:10**((target-level)/20) if math.isfinite(level) and level>=-60 else 1.0 for name,level in levels.items()}
    peak=max(float(np.max(np.abs(excerpts[n])))*g for n,g in gains.items())
    protection=min(1.0,.90/peak) if peak else 1
    matched={n:a*gains[n]*protection for n,a in excerpts.items()}
    details={n:{"input_lufs":v if math.isfinite(v) else None,"gain":gains[n]*protection,
                "output_lufs":float(meter.integrated_loudness(matched[n])) if math.isfinite(v) and v>=-60 else None,
                "eligible":math.isfinite(v) and v>=-60} for n,v in levels.items()}
    return matched,{"target_lufs_before_common_peak_protection":target,"common_peak_gain":protection,"files":details}


def probe_pitch(audio: np.ndarray, rate: int) -> np.ndarray:
    mono=audio.mean(axis=1)
    hz=uniform_filter1d(np.gradient(np.unwrap(np.angle(hilbert(mono))))*rate/(2*np.pi),max(1,round(rate*.01)))
    return 69+12*np.log2(np.maximum(hz,1e-6)/440)


def transient_widths(original: np.ndarray, processed: np.ndarray, rate: int, centres: tuple[float,...]) -> list[dict]:
    """Known isolated amplitude pulses only; not inferred syllable/phoneme boundaries."""
    def pulse(audio,t):
        envelope=uniform_filter1d(np.abs(hilbert(audio.mean(axis=1))),max(1,round(.002*rate)))
        lo,hi=max(0,round((t-.1)*rate)),min(len(audio),round((t+.1)*rate))
        segment=envelope[lo:hi];peak=int(np.argmax(segment));floor=float(np.percentile(segment,10))
        threshold=floor+(float(segment[peak])-floor)/2
        left=peak;right=peak
        while left>0 and segment[left-1]>=threshold: left-=1
        while right<len(segment)-1 and segment[right+1]>=threshold: right+=1
        return (lo+peak)/rate,1000*(right-left+1)/rate
    result=[]
    for t in centres:
        source_t,source_width=pulse(original,t);out_t,out_width=pulse(processed,t)
        result.append({'centre_seconds':t,'source_fwhm_ms':source_width,'output_fwhm_ms':out_width,
                       'peak_lag_ms':1000*(out_t-source_t)})
    return result


def transition_measurements(audio: np.ndarray, rate: int, base_midi: float, centres: list[tuple[float,float,float]]) -> list[dict]:
    pitch=probe_pitch(audio,rate)-base_midi
    results=[]
    for t,a,b in centres:
        lo,hi=max(0,round((t-.35)*rate)),min(len(pitch),round((t+.35)*rate))
        segment=pitch[lo:hi]; mid=(a+b)/2
        crossings=np.flatnonzero(((segment[:-1]<mid)&(segment[1:]>=mid)) if b>a else ((segment[:-1]>mid)&(segment[1:]<=mid)))
        closest=min(crossings,key=lambda i:abs(lo+i-t*rate)) if len(crossings) else None
        results.append({"scheduled_seconds":t,"from":a,"to":b,
                        "observed_midpoint_seconds":(lo+int(closest))/rate if closest is not None else None,
                        "midpoint_lag_ms":1000*((lo+int(closest))/rate-t) if closest is not None else None})
    return results
