"""Pitch-curve unit tests and real continuous mapped DSP regression checks."""

import math
import subprocess
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.harmony import HarmonyConfig, generate_harmony
from backend.app.audio.harmony_curve import CurvePoint, HarmonyPitchCurve, build_harmony_curve
from backend.app.audio.pitch_models import NoteEvent, PitchAnalysis, PitchFrame
from backend.app.audio.quantization import QuantizationConfig, quantize_melody
from backend.app.audio.vocal_pitch import VocalPitchError, VocalPitchDependencyError, InvalidVocalAudio
from backend.tests.test_vocal_pitch import require_engine


def fixture(direction="above", pitches=(60, 64), bounds=((0.1, 0.9), (1.1, 1.9)), duration=2.2):
    notes = [NoteEvent(midi_note=m, note_name="test", midi_pitch=float(m), median_pitch_hz=440 * 2 ** ((m - 69) / 12),
                       start_time=s, end_time=e, duration=e-s, pitch_deviation_cents=0)
             for m, (s, e) in zip(pitches, bounds)]
    frames = []
    for t in np.arange(0, duration, 0.01):
        note = next((n for n in notes if n.start_time <= t < n.end_time), None)
        midi = note.midi_pitch + 0.2 * math.sin(2 * math.pi * 5 * t) if note else None
        frames.append(PitchFrame(time_seconds=t, midi_pitch=midi, f0_hz=440 * 2 ** ((midi-69)/12) if midi else None,
                                 voiced=note is not None, voiced_probability=0.99 if note else 0))
    analysis = PitchAnalysis(duration_seconds=duration, sample_rate=16000, hop_length=160, frame_length=1024,
                             fmin_hz=65, fmax_hz=1047, notes=notes, frames=frames)
    quantized = quantize_melody(analysis, QuantizationConfig(mode="scale-aware", key="C", scale="major"))
    harmony = generate_harmony(quantized, HarmonyConfig(interval="diatonic_third", direction=direction, key="C", scale="major"))
    return analysis, quantized, harmony


@pytest.mark.parametrize("direction,expected", [("above", (4, 3)), ("below", (-3, -4))])
def test_curve_tracks_variable_scale_intervals_and_preserves_vibrato(direction, expected):
    a, q, h = fixture(direction)
    curve = build_harmony_curve(a, q, h)
    for t, shift in zip((0.4, 1.4), expected):
        p = min(curve.points, key=lambda p: abs(p.time_seconds-t))
        assert p.shift_semitones == pytest.approx(shift)
        assert p.expressive_target_midi - p.detected_midi == pytest.approx(shift)
    p = min(curve.points, key=lambda p: abs(p.time_seconds-0.35))
    assert p.detected_midi == pytest.approx(59.8)
    assert p.expressive_target_midi == pytest.approx(59.8 + expected[0])
    # Automation ramps, rather than instantly jumping at a frame boundary.
    assert max(abs(b.shift_semitones-a.shift_semitones) for a,b in zip(curve.points,curve.points[1:])) <= 1.01


def test_missing_unvoiced_noisy_and_octave_error_frames_do_not_change_interval():
    a, q, h = fixture()
    for i, value in enumerate((None, 72.0, float("nan"))):
        frame = a.frames[30+i]; frame.midi_pitch=value; frame.f0_hz=None; frame.voiced=i != 0
    curve = build_harmony_curve(a,q,h)
    for t in (0.30,0.31,0.32):
        point=min(curve.points,key=lambda p:abs(p.time_seconds-t))
        assert not point.reliable_f0 and point.shift_semitones==pytest.approx(4)
    assert all(p.gain==0 for p in curve.points if 0.95 <= p.time_seconds <= 1.05)


def test_short_notes_keep_timing_and_glissando_is_not_flattened():
    a,q,h=fixture(pitches=(60,),bounds=((0.123,0.137),),duration=0.3)
    curve=build_harmony_curve(a,q,h)
    assert any(p.note_index==0 and p.gain>0 for p in curve.points)
    assert all(p.gain==0 for p in curve.points if p.time_seconds<0.123 or p.time_seconds>=0.137)
    a,q,h=fixture()
    for frame in a.frames:
        if 0.3 <= frame.time_seconds <= 0.6:
            frame.midi_pitch=60+(frame.time_seconds-0.3)*2
            frame.f0_hz=440*2**((frame.midi_pitch-69)/12)
    c=build_harmony_curve(a,q,h)
    observed=[p for p in c.points if p.reliable_f0 and 0.3<=p.time_seconds<=0.6]
    assert max(p.expressive_target_midi for p in observed)-min(p.expressive_target_midi for p in observed)>0.5


def test_empty_melody_does_not_invent_notes():
    a,q,h=fixture(pitches=(),bounds=())
    curve=build_harmony_curve(a,q,h)
    assert all(p.gain==0 and p.shift_semitones==0 for p in curve.points)


def test_touching_notes_do_not_retrigger_gain_and_detuning_is_retained():
    a,q,h=fixture(bounds=((0.1,1.0),(1.0,1.9)))
    for f in a.frames:
        if f.midi_pitch is not None:
            f.midi_pitch += .35
            f.f0_hz=440*2**((f.midi_pitch-69)/12)
    curve=build_harmony_curve(a,q,h)
    boundary=min(curve.points,key=lambda p:abs(p.time_seconds-1))
    assert boundary.gain==1
    inside=min(curve.points,key=lambda p:abs(p.time_seconds-.4))
    assert inside.shift_semitones==pytest.approx(4)
    assert inside.expressive_target_midi==pytest.approx(64.35)


def test_real_waveform_vibrato_is_retained(tmp_path):
    from scipy.signal import hilbert
    from scipy.ndimage import uniform_filter1d
    require_engine()
    rate=16000
    a,q,h=fixture(pitches=(69,),bounds=((0.1,1.9),),duration=2.1)
    curve=build_harmony_curve(a,q,h)
    t=np.arange(round(2.1*rate))/rate
    frequency=440*2**((.2*np.sin(2*np.pi*5*t))/12)
    audio=.15*np.sin(2*np.pi*np.cumsum(frequency)/rate)
    audio[(t<.1)|(t>=1.9)]=0
    source,output=tmp_path/'vibrato.wav',tmp_path/'vibrato_out.wav'
    sf.write(source,audio,rate,subtype='FLOAT')
    DynamicVocalRenderer().render(source,output,curve)
    shifted=sf.read(output)[0]
    def contour(signal):
        freq=np.gradient(np.unwrap(np.angle(hilbert(signal))))*rate/(2*np.pi)
        freq=uniform_filter1d(freq,size=160)
        return 69+12*np.log2(freq[int(.4*rate):int(1.6*rate)]/440)
    lead,target=contour(audio),contour(shifted)
    assert np.median(target-lead)==pytest.approx(3,abs=.08)
    assert np.std(target)>.08
    assert np.corrcoef(lead,target)[0,1]>.7


@pytest.mark.parametrize("corruption",["duration","timing","target","interval","frame_time","transition"])
def test_invalid_plans_are_rejected(corruption):
    a,q,h=fixture()
    if corruption=="duration": h.duration_seconds+=1
    if corruption=="timing": q.notes[0].start_time+=0.01
    if corruption=="target": h.notes[0].harmony_midi_note+=1
    if corruption=="interval": h.interval="invalid"
    if corruption=="frame_time": a.frames[0].time_seconds=-1
    with pytest.raises(ValueError): build_harmony_curve(a,q,h,transition_seconds=0 if corruption=="transition" else 0.02)


@pytest.mark.parametrize("direction",["above","below"])
@pytest.mark.parametrize("rate,channels",[(16000,1),(44100,2)])
def test_real_mapped_pitch_duration_silence_and_channels(tmp_path:Path,direction,rate,channels):
    require_engine()
    a,q,h=fixture(direction)
    curve=build_harmony_curve(a,q,h)
    t=np.arange(round(a.duration_seconds*rate))/rate
    audio=np.zeros((len(t),channels),dtype=np.float32)
    for note in a.notes:
        mask=(t>=note.start_time)&(t<note.end_time)
        audio[mask]=(.15*np.sin(2*np.pi*note.median_pitch_hz*t[mask]))[:,None]
    source,output=tmp_path/'input with spaces.wav',tmp_path/'out.wav'
    sf.write(source,audio,rate,subtype='FLOAT')
    before=source.read_bytes()
    report=DynamicVocalRenderer().render(source,output,curve)
    shifted,sr=sf.read(output,always_2d=True)
    assert shifted.shape==audio.shape and sr==rate and report.frame_adjustment==0
    assert source.read_bytes()==before and not report.output.clipped_samples
    assert np.all(np.isfinite(shifted)) and report.output.rms>0.01
    assert not np.any(shifted[int(.95*rate):int(1.05*rate)])
    for start,note in zip((0.35,1.35),h.notes):
        part=shifted[int(start*rate):int((start+.3)*rate),0]
        spectrum=np.abs(np.fft.rfft(part*np.hanning(len(part))))
        hz=np.fft.rfftfreq(len(part),1/rate)[np.argmax(spectrum)]
        assert hz==pytest.approx(440*2**((note.harmony_midi_note-69)/12),abs=4)
    active=np.flatnonzero(np.abs(shifted[:,0])>0.03)
    assert abs(active[0]/rate-.1)<.04 and abs(active[-1]/rate-1.9)<.04
    if channels==2: assert np.max(np.abs(shifted[:,0]-shifted[:,1]))<1e-5


def test_silent_and_no_note_output_need_no_dependency(tmp_path):
    a,q,h=fixture(pitches=(),bounds=())
    source=tmp_path/'in.wav'; sf.write(source,np.zeros((35200,1)),16000)
    report=DynamicVocalRenderer(executable='missing').render(source,tmp_path/'out.wav',build_harmony_curve(a,q,h))
    assert report.output.rms==0 and report.output.frames==35200


@pytest.mark.parametrize("failure",["unsupported","process","length","channels","rails","nonfinite"])
def test_native_failures_do_not_publish(tmp_path,monkeypatch,failure):
    a,q,h=fixture(); curve=build_harmony_curve(a,q,h)
    source,output=tmp_path/'in.wav',tmp_path/'out.wav'
    sf.write(source,np.full((35200,1),0.1),16000,subtype='FLOAT');output.write_bytes(b'keep')
    monkeypatch.setattr(DynamicVocalRenderer,'_dependency',lambda self:('rubberband.exe','4.0.0'))
    def run(args,**kwargs):
        if '--full-help' in args: return subprocess.CompletedProcess(args,0,'--pitchmap' if failure!='unsupported' else '', '')
        assert '--pitchmap' in args
        assert len(Path(args[args.index('--pitchmap')+1]).read_text().splitlines())>100
        if failure=='process': raise subprocess.TimeoutExpired(args,120)
        audio,rate=sf.read(args[-2],always_2d=True)
        if failure=='length': audio=audio[:-100]
        if failure=='channels': audio=np.repeat(audio,2,axis=1)
        if failure=='rails': audio[:]=1
        if failure=='nonfinite': audio[:]=np.nan
        sf.write(args[-1],audio,rate,subtype='FLOAT')
        return subprocess.CompletedProcess(args,0,'','')
    monkeypatch.setattr('backend.app.audio.dynamic_vocal.subprocess.run',run)
    with pytest.raises((VocalPitchError,VocalPitchDependencyError)):
        DynamicVocalRenderer().render(source,output,curve)
    assert output.read_bytes()==b'keep'


def test_bad_curve_audio_and_presets(tmp_path):
    bad=HarmonyPitchCurve(1,(CurvePoint(0,3,1),CurvePoint(1,float('nan'),1)))
    with pytest.raises(ValueError): DynamicVocalRenderer().render(tmp_path/'in.wav',tmp_path/'out.wav',bad)
    a,q,h=fixture();c=build_harmony_curve(a,q,h)
    with pytest.raises(ValueError): DynamicVocalRenderer().render(tmp_path/'in.wav',tmp_path/'out.wav',c,preset='invented')
    with pytest.raises(InvalidVocalAudio): DynamicVocalRenderer().render(tmp_path/'in.wav',tmp_path/'out.wav',c)
