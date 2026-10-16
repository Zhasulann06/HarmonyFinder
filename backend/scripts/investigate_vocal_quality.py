"""Controlled Phase 3B-Q audit, renders, probes, and LUFS-matched listening sets."""

import argparse
import json
import math
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.optimize import minimize_scalar

from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.harmony import HarmonyMelody
from backend.app.audio.harmony_curve import CurvePoint, HarmonyPitchCurve
from backend.app.audio.pitch import PyinPitchDetector
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizedMelody
from backend.app.audio.vocal_pitch import RubberBandVocalPitchShifter, read_vocal_wav, vocal_levels
from backend.app.audio.vocal_quality import (audit_plan, compare_features, delay_automation, held_interval_curve, match_loudness,
    scheduled_curve, transition_measurements, transient_widths, without_gate)
from backend.app.core.config import resolve_project_path
from backend.scripts.compare_vocal_pitch import envelope_lag


def read_json(path: Path) -> dict:
    if path.stat().st_size>3_000_000: raise ValueError("Diagnostic JSON exceeds bounded size")
    return json.loads(path.read_text(encoding="utf-8"))


def tone_harmonics(audio: np.ndarray, rate: int, expected_hz: float) -> dict:
    # Finish before the early native transition (~0.875s at 16 kHz),
    # and after the intended amplitude pulse at 0.5s.
    signal=audio[round(.60*rate):round(.80*rate),0].astype(float)
    t=np.arange(len(signal))/rate
    def columns(hz):
        return np.column_stack([f(2*np.pi*k*hz*t) for k in range(1,6) for f in (np.sin,np.cos)]+[np.ones(len(t))])
    def fit(hz):
        design=columns(hz);coeff=np.linalg.lstsq(design,signal,rcond=None)[0]
        return float(np.mean((signal-design@coeff)**2)),coeff
    best=minimize_scalar(lambda hz:fit(hz)[0],bounds=(expected_hz-3,expected_hz+3),method='bounded')
    mse,coeff=fit(best.x)
    powers=coeff[:10].reshape(5,2)**2
    denominator=float(powers[0].sum())
    return {"estimated_fundamental_hz":float(best.x),
            "harmonics_2_to_5_ratio_db":float(10*np.log10(max(float(powers[1:].sum())/max(denominator,1e-20),1e-20))),
            "fit_residual_to_signal_db":float(10*np.log10(max(mse/max(float(np.mean(signal**2)),1e-20),1e-20))),
            "scope":"Known sine only; not THD or formant accuracy of real vocals"}


def review_probes(directory: Path) -> dict:
    """Re-measure saved probes without rerendering or changing prior artifacts."""
    report={"window_seconds":[.60,.80],"reason":"Exclude the early dynamic transition and the intended 0.5-second amplitude pulse","probes":{}}
    source,source_rate=read_vocal_wav(directory/'synthetic_source.wav')
    for label,sign in [('synthetic_tone_above',1),('synthetic_tone_below',-1)]:
        audio,rate=read_vocal_wav(directory/f'{label}.wav')
        if rate!=source_rate or audio.shape!=source.shape: raise ValueError('Synthetic probe alignment mismatch')
        report['probes'][label]=tone_harmonics(audio,rate,220*2**(sign*3/12))
        report['probes'][label]['known_pulse_transients']=transient_widths(source,audio,rate,(.5,1.5,2.5,3.5))
    path=directory/f'probe_review-{uuid.uuid4().hex[:8]}.json'
    path.write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    print(f'Probe review: {path}',flush=True)
    print(json.dumps(report,indent=2),flush=True)
    return report


def main() -> None:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job')
    parser.add_argument('--run',help='Existing Phase 3B-2 run containing curves and forked harmony JSON')
    parser.add_argument('--review-probes',help='Only re-measure saved synthetic probes; preserve all earlier artifacts')
    parser.add_argument('--output',default='backend/data/vocal_quality_investigation')
    args=parser.parse_args()
    if args.review_probes:
        review_probes(resolve_project_path(args.review_probes))
        return
    if not args.job or not args.run: parser.error('--job and --run are required unless reviewing saved probes')
    job,previous=resolve_project_path(args.job),resolve_project_path(args.run)
    source=job/'vocals.wav';audio,rate=read_vocal_wav(source);duration=len(audio)/rate
    saved_original,_=read_vocal_wav(previous/'original_vocals.wav')
    if not np.array_equal(audio,saved_original): raise ValueError('Comparison run uses another source waveform')
    analysis=PitchAnalysis.model_validate(read_json(job/'pitch_analysis.json'))
    lead=QuantizedMelody.model_validate(read_json(previous/'quantized_lead.json'))
    harmony=HarmonyMelody.model_validate(read_json(previous/'harmony_above.json'))
    data=read_json(previous/'curve_above.json')
    curve=HarmonyPitchCurve(data['duration_seconds'],tuple(CurvePoint(**p) for p in data['points']),data['transition_seconds'])
    root=resolve_project_path(args.output)
    output=root/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    print(f'Investigation directory: {output}',flush=True)
    report={'source_job':job.name,'previous_run':previous.name,'user_feedback':{
        'constant_plus_3':'acceptable','constant_minus_3':'robotic','dynamic_above':'bad','dynamic_below':'bad'},
        'planning':audit_plan(audio,rate,analysis,lead,harmony,curve),'renders':{},'probes':{},'listening':{}}
    sf.write(output/'original.wav',audio,rate,subtype='FLOAT')
    files={'original':output/'original.wav'}
    fixed=RubberBandVocalPitchShifter();renderer=DynamicVocalRenderer()
    # Calibrate control timing at the recording's actual rate/channel configuration.
    # Exact WAV duration or energy-envelope lag cannot reveal early pitch commands.
    probe_t=np.arange(round(4.2*rate))/rate
    calibration_audio=np.repeat((.12*np.sin(2*np.pi*220*probe_t))[:,None],audio.shape[1],axis=1)
    sf.write(output/'calibration_source.wav',calibration_audio,rate,subtype='FLOAT')
    calibration={};lags=[]
    for sign in (1,-1):
        control=scheduled_curve(4.2,[(0,sign*3),(1,sign*4),(2,sign*3),(3,sign*4)],.02)
        path=output/f'calibration_{sign:+d}.wav'
        renderer.render(output/'calibration_source.wav',path,control)
        samples,_=read_vocal_wav(path)
        rows=transition_measurements(samples,rate,57,[(1,sign*3,sign*4),(2,sign*4,sign*3),(3,sign*3,sign*4)])
        calibration[str(sign)]=rows
        lags.extend(r['midpoint_lag_ms']/1000 for r in rows if r['midpoint_lag_ms'] is not None)
    if len(lags)!=6 or not all(-.35<x<0 for x in lags): raise RuntimeError('Timing calibration is inconclusive; do not guess compensation')
    control_delay=-float(np.median(lags))
    report['control_timing_calibration']={'rate':rate,'channels':audio.shape[1],'raw_transitions':calibration,'experimental_command_delay_seconds':control_delay}
    corrected_probe=delay_automation(scheduled_curve(4.2,[(0,3),(1,4),(2,3),(3,4)],.02),control_delay)
    renderer.render(output/'calibration_source.wav',output/'calibration_delayed.wav',corrected_probe)
    shifted,_=read_vocal_wav(output/'calibration_delayed.wav')
    report['control_timing_calibration']['delayed_transitions']=transition_measurements(shifted,rate,57,[(1,3,4),(2,4,3),(3,3,4)])
    print(f'Measured experimental control delay: {control_delay*1000:.2f} ms',flush=True)
    for amount in (3,4,-3,-4):
        label=f'constant_{amount:+d}'.replace('+','plus_').replace('-','minus_')
        path=output/f'{label}.wav'; files[label]=path
        report['renders'][label]={'settings':'original offline R3/formant/centre-focus baseline',**asdict(fixed.shift(source,path,amount))}
        print(f'Rendered {label}',flush=True)
    schedule=[(0,3.)]+[(float(t),4. if i%2==0 else 3.) for i,t in enumerate(np.arange(8.,duration,2.))]
    jobs={
        'mapped_constant_plus_3':(scheduled_curve(duration,[(0,3.)]),'formant_stereo'),
        'mapped_constant_minus_3':(scheduled_curve(duration,[(0,-3.)]),'formant_stereo'),
        'mapped_constant_plus_4':(scheduled_curve(duration,[(0,4.)]),'formant_stereo'),
        'mapped_constant_minus_4':(scheduled_curve(duration,[(0,-4.)]),'formant_stereo'),
        'known_3_4_20ms':(scheduled_curve(duration,schedule,.02),'formant_stereo'),
        'known_3_4_80ms':(scheduled_curve(duration,schedule,.08),'formant_stereo'),
        'known_minus_3_4_20ms':(scheduled_curve(duration,[(t,-s) for t,s in schedule],.02),'formant_stereo'),
        'real_no_gate':(without_gate(curve),'formant_stereo'),
        'held_intervals_80ms':(held_interval_curve(harmony,.08),'formant_stereo'),
        'real_control_delayed':(delay_automation(curve,control_delay),'formant_stereo'),
        'held_80ms_control_delayed':(delay_automation(held_interval_curve(harmony,.08),control_delay),'formant_stereo'),
        'real_short_window':(curve,'formant_short'),
    }
    for label,(control,preset) in jobs.items():
        path=output/f'{label}.wav';files[label]=path
        report['renders'][label]={'settings':f'continuous R3 pitchmap preset={preset}',**asdict(renderer.render(source,path,control,preset=preset))}
        print(f'Rendered {label}',flush=True)
    for label,name in [('real_dynamic_above','dynamic_third_above.wav'),('real_dynamic_below','dynamic_third_below.wav'),('minus_3_no_formants','minus_3_no_formants.wav')]:
        path=output/f'{label}.wav';shutil.copyfile(previous/name,path);files[label]=path
        report['renders'][label]={'settings':f'copied unchanged from {previous.name}/{name}'}
    envelope=np.interp(np.arange(len(audio))/rate,[p.time_seconds for p in curve.points],[p.gain for p in curve.points])
    sf.write(output/'gate_only_no_pitch.wav',audio*envelope[:,None],rate,subtype='FLOAT')
    files['gate_only_no_pitch']=output/'gate_only_no_pitch.wav'
    report['renders']['gate_only_no_pitch']={'settings':'source waveform * real curve amplitude envelope; no pitch DSP'}
    # Measure signal proxies, not inferred formants/THD of an unknown clean singer.
    for label,path in files.items():
        if label=='original': continue
        samples,sr=read_vocal_wav(path)
        if sr!=rate or samples.shape!=audio.shape: raise ValueError(f'Alignment mismatch: {label}')
        report['renders'][label]['levels']=asdict(vocal_levels(samples,rate))
        report['renders'][label]['features']=compare_features(audio,samples,rate)
        report['renders'][label]['envelope_lag_seconds']=envelope_lag(audio,samples,rate)
    # Score control and real curves on the same voiced frames; no boundary exclusion.
    detector=PyinPitchDetector()
    for label in ('mapped_constant_plus_3','known_3_4_20ms','real_dynamic_above','real_no_gate','held_intervals_80ms','real_control_delayed','held_80ms_control_delayed'):
        detected=detector.detect(files[label]);errors=[]
        control=curve if label=='real_dynamic_above' else jobs[label][0]
        if label=='real_control_delayed': control=curve
        if label=='held_80ms_control_delayed': control=jobs['held_intervals_80ms'][0]
        times=np.array([p.time_seconds for p in control.points]);shifts=np.array([p.shift_semitones for p in control.points])
        for a,b in zip(analysis.frames,detected.frames):
            if not(a.voiced and b.voiced and a.midi_pitch is not None and b.midi_pitch is not None): continue
            errors.append(100*(b.midi_pitch-a.midi_pitch-float(np.interp(a.time_seconds,times,shifts))))
        report['renders'][label]['pitch_tracking']={'matched_frames':len(errors),'median_absolute_error_cents':float(np.median(np.abs(errors))) if errors else None,
                                                   'p90_absolute_error_cents':float(np.percentile(np.abs(errors),90)) if errors else None,
                                                   'selection':'All shared voiced frames; no transition/interior exclusions'}
        print(f'Measured pitch {label}',flush=True)
    # Known sine with known transient envelopes: separate processing from pYIN/key.
    probe_rate=16000;length=4.2;t=np.arange(round(length*probe_rate))/probe_rate
    amp=.08+sum(.07*np.exp(-.5*((t-c)/.008)**2) for c in (.5,1.5,2.5,3.5))
    signal=(amp*np.sin(2*np.pi*220*t))[:,None].astype('float32')
    sf.write(output/'synthetic_source.wav',signal,probe_rate,subtype='FLOAT')
    for sign in (1,-1):
        control=scheduled_curve(length,[(0,sign*3),(1,sign*4),(2,sign*3),(3,sign*4)],.02)
        label='synthetic_tone_above' if sign==1 else 'synthetic_tone_below'
        path=output/f'{label}.wav'
        stats=renderer.render(output/'synthetic_source.wav',path,control)
        shifted,_=read_vocal_wav(path)
        report['probes'][label]={'render':asdict(stats),'transitions':transition_measurements(shifted,probe_rate,57,[(1,sign*3,sign*4),(2,sign*4,sign*3),(3,sign*3,sign*4)]),
                                'stable_sine_fit':tone_harmonics(shifted,probe_rate,220*2**(sign*3/12)),
                                'envelope_lag_seconds':envelope_lag(signal,shifted,probe_rate)}
    # Same source boundaries, same fades, LUFS matching, bounded gain, common peak headroom.
    for start,end in ((7.,10.),(10.5,13.5),(16.4,19.4)):
        label=f'{start:.1f}-{end:.1f}s';folder=output/f'excerpts_{label}';folder.mkdir()
        excerpts={}
        for name,path in files.items():
            samples,_=read_vocal_wav(path);part=samples[round(start*rate):round(end*rate)].astype(float)
            fade=round(.005*rate);part[:fade]*=np.linspace(0,1,fade)[:,None];part[-fade:]*=np.linspace(1,0,fade)[:,None]
            excerpts[name]=part
        matched,manifest=match_loudness(excerpts,rate)
        for name,part in matched.items(): sf.write(folder/f'{name}.wav',part,rate,subtype='FLOAT')
        manifest.update({'start':start,'end':end,'sample_rate':rate,'frames':round((end-start)*rate),'fade_seconds':.005})
        (folder/'listening_manifest.json').write_text(json.dumps(manifest,indent=2,allow_nan=False),encoding='utf-8')
        report['listening'][label]=manifest
    report['limitations']=['Song key unknown; C major was an unverified prior diagnostic setting.',
        'Energy is not proof of a missed vocal or consonant. Voicing probability is not calibrated pitch confidence.',
        'Spectral-envelope/centroid, stereo correlation, and high-band energy are proxies, not measured true formants or vocal THD.',
        'LUFS matching reduces level bias but does not make timbres equally loud perceptually.',
        'User listening feedback is the only perceptual verdict; ablations are not approved improvements.']
    (output/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    rows=report['planning']['notes']
    text=['# Phase 3B-Q measured audit','',f'Source: `{job.name}`. Key UNKNOWN; prior plan assumes C major.','',
          'See report.json and the listening manifests for all measurements. No new listening verdict.', '',
          '| Start | End | Detected MIDI | Quantized | Target | Shift | Centre error cents | Flags |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for n in rows: text.append(f"| {n['start']:.2f} | {n['end']:.2f} | {n['detected_midi']:.2f} | {n['corrected_lead']} | {n['target']} | {n['shift']} | {n['centre_error_cents']:.1f} | {'; '.join(n['flags'])} |")
    text += ['','## Potentially missed regions (energy proxy only)','',json.dumps(report['planning']['energetic_unplanned_regions'],indent=2),
             '', '## Possible octave jumps (not confirmed errors)','',json.dumps(report['planning']['octave_jump_candidates'],indent=2),
             '', 'No API/UI/production DSP changes; see docs/vocal_quality_investigation.md for interpretation.']
    (output/'report.md').write_text('\n'.join(text),encoding='utf-8')
    print(f'Completed report: {output}',flush=True)


if __name__=='__main__': main()
