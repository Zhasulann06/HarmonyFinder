"""Non-destructive dynamic harmony and negative-shift quality comparison."""

import argparse
import json
import shutil
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from backend.app.audio.dynamic_vocal import DynamicVocalRenderer
from backend.app.audio.harmony_curve import CurvePoint, HarmonyPitchCurve, build_harmony_curve
from backend.app.audio.harmony import HarmonyConfig, generate_harmony
from backend.app.audio.pitch import PyinPitchDetector
from backend.app.audio.pitch_models import PitchAnalysis
from backend.app.audio.quantization import QuantizationConfig, quantize_melody
from backend.app.audio.vocal_pitch import RubberBandVocalPitchShifter, read_vocal_wav, vocal_levels
from backend.app.core.config import resolve_project_path
from backend.scripts.compare_vocal_pitch import envelope_lag


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job", required=True)
    parser.add_argument("--output", default="backend/data/dynamic_vocal_comparison")
    parser.add_argument("--key", default="C", help="Manual diagnostic key, not automatically detected")
    parser.add_argument("--scale", choices=("major", "natural_minor"), default="major")
    args = parser.parse_args()
    job = resolve_project_path(args.job)
    source = job / "vocals.wav"
    original, rate = read_vocal_wav(source)
    detector = PyinPitchDetector()
    saved = job / "pitch_analysis.json"
    if saved.is_file():
        if saved.stat().st_size > 2_000_000: raise ValueError("Pitch JSON exceeds diagnostic size limit")
        analysis = PitchAnalysis.model_validate_json(saved.read_text(encoding="utf-8"))
    else:
        analysis = detector.detect(source)
    quantized = quantize_melody(analysis, QuantizationConfig(mode="scale-aware", key=args.key, scale=args.scale))
    root = resolve_project_path(args.output)
    output = root / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8])
    output.mkdir(parents=True)
    shutil.copyfile(source, output / "original_vocals.wav")
    (output / "quantized_lead.json").write_text(quantized.model_dump_json(indent=2), encoding="utf-8")
    baseline = RubberBandVocalPitchShifter()
    renderer = DynamicVocalRenderer()
    report: dict = {"source_job": job.name, "manual_key": args.key, "scale": args.scale,
                    "original": asdict(vocal_levels(original, rate)), "outputs": {}}
    curves = {}
    for amount, name in ((3,"fixed_plus_3.wav"),(-3,"fixed_minus_3.wav")):
        report["outputs"][name] = asdict(baseline.shift(source, output / name, amount))
    # Same whole-stream renderer and constant map across quality candidates.
    constant = HarmonyPitchCurve(len(original)/rate, (CurvePoint(0,-3,1),CurvePoint(len(original)/rate,-3,1)))
    for preset in ("formant_stereo", "formant_independent", "formant_short", "no_formants"):
        name = f"minus_3_{preset}.wav"
        report["outputs"][name] = asdict(renderer.render(source,output/name,constant,preset=preset))
    for direction in ("above","below"):
        harmony = generate_harmony(quantized, HarmonyConfig(interval="diatonic_third", direction=direction,
                                                           key=args.key, scale=args.scale))
        curve = build_harmony_curve(analysis,quantized,harmony)
        name = f"dynamic_third_{direction}.wav"
        curves[name] = curve
        (output/f"harmony_{direction}.json").write_text(harmony.model_dump_json(indent=2),encoding="utf-8")
        (output/f"curve_{direction}.json").write_text(json.dumps(asdict(curve),indent=2,allow_nan=False),encoding="utf-8")
        report["outputs"][name] = asdict(renderer.render(source,output/name,curve))
        print(f"Generated {name}",flush=True)
    for name, result in report["outputs"].items():
        samples,_ = read_vocal_wav(output/name)
        result["energy_envelope_lag_seconds"] = envelope_lag(original,samples,rate)
        detected = detector.detect(output/name)
        curve = curves.get(name)
        times = np.array([p.time_seconds for p in curve.points]) if curve else None
        errors=[]; offsets=[]
        for frame, rendered in zip(analysis.frames,detected.frames):
            if not(frame.voiced and rendered.voiced and frame.midi_pitch is not None and rendered.midi_pitch is not None): continue
            if name in curves:
                # Exclude note transitions, planned rests, and unreliable F0.
                index=int(np.clip(np.searchsorted(times,frame.time_seconds),0,len(times)-1))
                point=curve.points[index]
                if not point.reliable_f0 or point.gain<0.99: continue
                nearby=curve.points[max(0,index-8):index+9]
                if any(p.note_index!=point.note_index for p in nearby): continue
                expected=point.shift_semitones
            else:
                expected=3 if name=="fixed_plus_3.wav" else -3
            delta=rendered.midi_pitch-frame.midi_pitch
            offsets.append(delta);errors.append(delta-expected)
        result["matched_voiced_frames"]=len(errors)
        result["median_detected_shift_semitones"]=float(np.median(offsets)) if errors else None
        result["median_error_cents"]=float(100*np.median(errors)) if errors else None
        result["median_absolute_error_cents"]=float(100*np.median(np.abs(errors))) if errors else None
        result["p90_absolute_error_cents"]=float(100*np.percentile(np.abs(errors),90)) if errors else None
        result["checks"]={"same_frames":len(samples)==len(original),
                          "no_clipped_samples":result["output"]["clipped_samples"]==0,
                          "matched_pitch_available":bool(errors),
                          "median_pitch_within_50_cents":bool(errors) and abs(float(np.median(errors)))<=0.5,
                          "coarse_lag_within_30ms":abs(result["energy_envelope_lag_seconds"])<=0.03}
        print(f"Measured {name}: {result['matched_voiced_frames']} matched frames",flush=True)
    report["limitations"] = "User judged prior +3 acceptable and -3 robotic. No new listening assessment; technical metrics do not prove naturalness, identity, or lyrics. Dynamic note masks can omit missed notes/consonants."
    (output/"measurements.json").write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
    print(f"Comparison directory: {output}",flush=True)


if __name__ == "__main__": main()
