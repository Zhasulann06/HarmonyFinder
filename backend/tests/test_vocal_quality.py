"""Meaningful audit, scale/curve, loudness, and known-waveform checks."""

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.harmony_curve import build_harmony_curve
from backend.app.audio.vocal_quality import (audit_plan, compare_features, held_interval_curve,
    delay_automation, match_loudness, regions, scheduled_curve, transition_measurements, transient_widths, probe_pitch, without_gate)
from backend.tests.test_dynamic_vocal import fixture
from backend.tests.test_vocal_pitch import require_engine


def test_known_control_has_correct_mapping_and_continuous_changes():
    curve=scheduled_curve(3,[(0,3),(1,4),(2,3)],.02)
    shifts=np.array([p.shift_semitones for p in curve.points])
    assert min(shifts)==pytest.approx(3) and max(shifts)==pytest.approx(4)
    assert np.max(np.abs(np.diff(shifts)))<=.251
    assert all(p.gain==1 for p in curve.points)
    for t,expected in ((.5,3),(1.5,4),(2.5,3)):
        assert min(curve.points,key=lambda p:abs(p.time_seconds-t)).shift_semitones==pytest.approx(expected)


def test_missing_notes_and_gate_are_measured_not_assumed_silence():
    a,q,h=fixture();curve=build_harmony_curve(a,q,h)
    audio=np.full((35200,1),.1)
    audit=audit_plan(audio,16000,a,q,h,curve)
    assert audit['energy_removed_by_mask_fraction']>.25
    assert audit['energetic_unplanned_regions']
    assert not audit['key_verified']
    assert audit['note_count']==2 and audit['interval_math_valid']
    no_gate=without_gate(curve)
    assert all(p.gain==1 for p in no_gate.points)
    assert [p.shift_semitones for p in no_gate.points]==[p.shift_semitones for p in curve.points]
    delayed=delay_automation(curve,.05)
    assert [p.gain for p in delayed.points]==[p.gain for p in curve.points]
    for point in delayed.points:
        if point.detected_midi is not None:
            assert point.expressive_target_midi-point.detected_midi==pytest.approx(point.shift_semitones)
    held=held_interval_curve(h)
    assert all(2.99<=p.shift_semitones<=4.01 for p in held.points)


def test_scale_membership_and_absolute_anchor_errors_are_explicit():
    a,q,h=fixture(pitches=(61,66))
    curve=build_harmony_curve(a,q,h)
    report=audit_plan(np.full((35200,1),.1),16000,a,q,h,curve)
    assert report['source_notes_outside_assumed_scale']==2
    assert report['large_centre_error_notes']==2
    assert all(n['centre_error_cents']==pytest.approx(-100) for n in report['notes'])
    assert report['notes'][1]['expected_waveform_median'] != report['notes'][1]['target']


def test_octave_candidates_are_flagged_without_correcting_data():
    a,q,h=fixture();curve=build_harmony_curve(a,q,h)
    a.frames[50].midi_pitch=72
    audit=audit_plan(np.full((35200,1),.1),16000,a,q,h,curve)
    assert len(audit['octave_jump_candidates'])==2
    assert a.frames[50].midi_pitch==72
    assert regions(np.array([0,1,1,0,1,1,1]),.01,.02)==[
        {'start':.01,'end':.03,'duration':.02},{'start':.04,'end':.07,'duration':.03}]


def test_unmatched_shapes_and_invalid_controls_are_rejected():
    with pytest.raises(ValueError): scheduled_curve(2,[(0,3),(1,20)])
    with pytest.raises(ValueError): scheduled_curve(2,[(1,3)])
    with pytest.raises(ValueError): compare_features(np.zeros((100,1)),np.zeros((101,1)),16000)


def test_known_pulse_width_and_delay_measurement():
    rate=16000;t=np.arange(rate)/rate
    source=((.05+.1*np.exp(-.5*((t-.5)/.008)**2))*np.sin(2*np.pi*220*t))[:,None]
    delayed=np.pad(source,((160,0),(0,0)))[:len(source)]
    measured=transient_widths(source,delayed,rate,(.5,))[0]
    assert measured['peak_lag_ms']==pytest.approx(10,abs=.2)
    assert measured['output_fwhm_ms']==pytest.approx(measured['source_fwhm_ms'],abs=.2)


def test_lufs_matching_reduces_level_bias_without_clipping_or_large_gain():
    pytest.importorskip('pyloudnorm')
    t=np.arange(48000)/16000
    tone=(.08*np.sin(2*np.pi*440*t))[:,None]
    matched,info=match_loudness({'original':tone,'quieter':tone*.3},16000)
    levels=[v['output_lufs'] for v in info['files'].values()]
    assert max(levels)-min(levels)<.01
    assert max(np.max(np.abs(a)) for a in matched.values())<=.90001
    assert max(v['gain'] for v in info['files'].values())<=4.0
    with pytest.raises(ValueError): match_loudness({'silent':np.zeros_like(tone)},16000)


@pytest.mark.parametrize('sign',[1,-1])
def test_native_known_pitch_transition_alignment_and_plateaus(tmp_path:Path,sign):
    require_engine();rate=16000;duration=3
    t=np.arange(rate*duration)/rate
    signal=(.12*np.sin(2*np.pi*220*t))[:,None]
    source,output=tmp_path/'tone.wav',tmp_path/'mapped.wav'
    sf.write(source,signal,rate,subtype='FLOAT')
    curve=scheduled_curve(duration,[(0,sign*3),(1,sign*4),(2,sign*3)],.02)
    report=DynamicVocalRenderer().render(source,output,curve)
    audio,sr=sf.read(output,always_2d=True)
    pitch=probe_pitch(audio,rate)-57
    for centre,expected in ((.5,sign*3),(1.5,sign*4),(2.5,sign*3)):
        assert np.median(pitch[int((centre-.1)*rate):int((centre+.1)*rate)])==pytest.approx(expected,abs=.1)
    changes=transition_measurements(audio,rate,57,[(1,sign*3,sign*4),(2,sign*4,sign*3)])
    # Measure rather than assuming commands line up with their acoustic effect.
    assert all(x['midpoint_lag_ms'] is not None and abs(x['midpoint_lag_ms'])<350 for x in changes)
    lead=-float(np.median([x['midpoint_lag_ms'] for x in changes]))/1000
    assert lead>0
    delayed=delay_automation(curve,lead)
    DynamicVocalRenderer().render(source,tmp_path/'delayed.wav',delayed)
    corrected=sf.read(tmp_path/'delayed.wav',always_2d=True)[0]
    aligned=transition_measurements(corrected,rate,57,[(1,sign*3,sign*4),(2,sign*4,sign*3)])
    assert all(x['midpoint_lag_ms'] is not None and abs(x['midpoint_lag_ms'])<15 for x in aligned)
    assert sr==rate and audio.shape==signal.shape and report.frame_adjustment==0
