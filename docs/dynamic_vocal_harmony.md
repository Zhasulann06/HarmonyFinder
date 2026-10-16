# Dynamic vocal harmony prototype — Phase 3B-2

This isolated CPU prototype transforms the existing separated singer waveform
using a continuous variable pitch map. It does not change piano rendering,
the render API, the mixer, or React. Its output is experimental vocal audio
for evaluation, not a claim of production-quality vocal harmonization.

The user's listening feedback remains the quality baseline: fixed +3 was
acceptable; fixed -3 sounded robotic. No new listening verdict has been made.
Pitch correctness alone cannot establish voice identity, lyrics, naturalness,
or musical suitability. In particular, the negative-shift concern is **not
declared solved** by the options or measurements below.

## Actual repository formats

| Data | Actual fields and timing |
| --- | --- |
| Demucs vocal | `vocals.wav`, here PCM16, 44100 Hz stereo; 883764 frames = 20.04 s |
| Pitch frames | `PitchAnalysis.frames`: `time_seconds`, `f0_hz`, fractional `midi_pitch`, `voiced`, nullable `voiced_probability`. Existing pYIN uses 16000 Hz analysis, hop 160 = 10 ms, centred 1024-sample windows. Unvoiced pitches are null. |
| Original notes | `notes`: `midi_pitch` (fractional median), `midi_note` (integer label), `start_time`, `end_time`, `duration` in seconds, frequency/cents/voicing statistics |
| Quantized notes | `QuantizedMelody.notes`: `original_midi_pitch`, integer `corrected_midi_pitch`, unchanged second-based timing and duration |
| Harmony notes | `HarmonyMelody.notes`: integer `original_midi_note` (the corrected lead anchor), `harmony_midi_note`, both note names, unchanged timing/duration |

All three JSON structures must describe the same duration and aligned note
events. The builder checks the existing Harmony Engine's output for the supplied
interval/direction/key/scale, rejects mismatches, and does not change that engine.

## Pitch curve and expression

`backend/app/audio/harmony_curve.py` is pure planning code. Its inputs are a
`PitchAnalysis`, `QuantizedMelody`, and `HarmonyMelody`. Its immutable output,
`HarmonyPitchCurve`, contains ordered points spanning zero to recording duration:

- `time_seconds`, `shift_semitones`, and a separate amplitude `gain`.
- `note_index`, `reliable_f0`, nullable `detected_midi`, and nullable
  `expressive_target_midi` for diagnostics.

For a reliable voiced frame, let `d` be detected MIDI, `q` the corrected lead
anchor, and `h` the planned harmony anchor. The expressive target is
`h + (d - q)`. The shift is `expressive_target - d = h - q`.
This preserves the source's vibrato, detuning, and glissando while moving its
note centre by the planned interval. It intentionally does **not** force every
frame exactly onto integer `h`, which would flatten expression and add autotune.
The existing quantization chooses interval anchors, not a new corrected waveform.

Missing, unvoiced, low-voicing-probability, nonfinite, inconsistent F0/MIDI,
or >2-semitone anchor-outlier frames do not control the shifter. Inside an
already planned event, the interval remains stable. Such frames are marked
unreliable rather than inducing arbitrary shifts; no octave folding/correction
is applied. Larger true glides remain in the waveform even if excluded from
the F0 diagnostic. Outside planned notes, no new notes are added.

Automation uses a 5 ms grid plus exact note edges and short-note midpoints.
A default 20 ms moving average smooths the **interval automation**, not the
detected singer contour. Configurable transition duration is 5–50 ms.
Very short notes retain their event times but may never attain the full
interval before the ramp changes again. This is reported as a limitation,
not silently relabeled as exact short-note rendering.

Amplitude automation fades the edges of planned phrases over up to 5 ms.
Touching notes share a continuous phrase envelope, avoiding a gain dip at
each note. Actual gaps remain muted. Missing detections/short segmentation
can therefore cut breath sounds, consonants, or notes from the harmony:
preservation of every lyric is not guaranteed. No noise gate or aggressive
denoiser is applied, and the input waveform itself remains untouched.

## Genuine continuous Rubber Band integration

`backend/app/audio/dynamic_vocal.py` extends the existing Rubber Band processor
and uses the installed **4.0.0 R3** CLI. Its public operation is
`DynamicVocalRenderer.render(source, output, curve, preset=...)`.
There is one DSP invocation for the full waveform, with stereo channels in
one process. No tiny notes are rendered separately or stitched together.

The installed help advertises `--pitchmap`; the
[4.0.0 implementation](https://github.com/breakfastquay/rubberband/blob/v4.0.0/main/main.cpp)
reads input-frame offsets and changes pitch through `setPitchScale`. Mapped
mode enables real-time processing and pitch consistency. It supplies start
padding and removes native start delay. The renderer probes actual CLI support
and fails clearly if it is absent. No DLL/API installation was necessary here.

Each map line is `input_sample_frame semitone_offset`, with frame index rounded
from seconds using the **original waveform** sample rate, not the 16 kHz
analysis rate. Pitch stays piecewise constant between dense map updates; the
builder's small ramps and native continuous engine avoid instantaneous large
control jumps. This is automation smoothing, not an assurance of inaudibility.
`--time 1` preserves tempo. The CLI warns that mapped-mode length is not always
exact; the renderer accepts at most two rounding frames, rejects larger
discrepancies, and verifies rate/channels/finite output before atomic publication.
No large end padding, hidden time stretching, or post-hoc correlation alignment
is used. Measured renders needed zero frame adjustment.

The same source also reveals that `--ignore-clipping` clamps output samples
even for FLOAT WAV, so FLOAT alone is not protection against native clipping.
The new path first supplies fixed input headroom (`0.125 / max(1, input_peak)`),
rejects native output approaching its clipping rails, restores that input gain,
then applies disclosed downward-only protection to 0.98 if required. This is
not presented as the cause or solution of the reported robotic sound. The
old constant processor remains available for exact baseline comparisons.

No upward RMS normalization is used. Silent input and curves with no active
events produce exact silence without the optional executable. Input is bounded
to the existing 30-second mono/stereo WAV limits; output keeps its native rate
and channel count. Temporary outputs are validated before replacement. The
existing 120-second DSP timeout and actionable dependency errors are reused.

## Supported experimental quality presets

| Preset | Actual R3 options | What is being investigated |
| --- | --- | --- |
| `formant_stereo` (default) | `--fine --formant --centre-focus` for stereo | Formant retention and centred stereo voice |
| `formant_independent` | `--fine --formant`, no centre focus | Effect of stereo coupling; stereo width/phase may differ |
| `formant_short` | Default plus `--window-short` | R3 short/draft window, lower CPU and a different transient/frequency-resolution tradeoff |
| `no_formants` | `--fine --centre-focus`, no `--formant` | Whether formant compensation contributes to the robot effect; voice timbre will change |

None is called an artifact-free or improved preset. Existing CLI options for
transient detector, crispness, long windows, lamination, and smoothing are
marked R2-only in the installed help and are not exposed as R3 quality fixes.
`--pitch-hq` does not replace the pitch-map consistency mode in this CLI;
adding it would not constitute a separate mapped quality preset.
See [official CLI help](https://breakfastquay.com/rubberband/usage.txt) and the
locally installed `--full-help` (4.0.0 includes newer details).

## Reproduce without overwriting earlier comparisons

Use the existing Python 3.11 `.venv`, Rubber Band executable, and DLL from
[Phase 3B-1 setup](vocal_pitch_prototype.md). No Python packages, models, GPU,
or downloads were added in this phase. Environment override
`HARMONYFINDER_RUBBERBAND` and project-root path resolution still apply.

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.compare_dynamic_vocals --job backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83 --key C --scale major
```

The key is a **manual diagnostic choice**, not automatic key/chord detection.
The script reuses saved pitch analysis when available, forks a scale-aware
quantization, and calls the existing diatonic-third Harmony Engine above/below.
It does not overwrite the job's pitch, quantization, harmony, audio, or any
earlier comparison. Every run creates a new UTC timestamp/UUID directory under
`backend/data/dynamic_vocal_comparison/` (`--output` can change that root).

Required listening files:

- `original_vocals.wav` — original stem copy.
- `fixed_plus_3.wav`, `fixed_minus_3.wav` — original offline baseline processor.
- `dynamic_third_above.wav`, `dynamic_third_below.wav` — continuous variable map.

Additional files `minus_3_formant_stereo.wav`,
`minus_3_formant_independent.wav`, `minus_3_formant_short.wav`, and
`minus_3_no_formants.wav` use a constant -3 map with the **same mapped renderer**
to compare options. Comparing those to the old offline baseline also changes
processing mode; it is not a controlled single-option comparison.
The directory includes forked lead/harmony JSON, both complete curves, and
`measurements.json`. The script runs existing pYIN to measure the outputs;
evaluation takes longer than native DSP. Engine failures can leave already
generated valid files in that new run directory, but do not publish a fake
successful result or touch older runs.

## Actual saved-job results

Measured run: `20261015T111811Z-283d44a9`. Original job:
`fa570cb6-1482-4dd2-8907-3ec2c0cbdf83`.
All outputs retain **883764 frames, 20.040 s, 44100 Hz, 2 channels** and contain
no NaN/Inf or clipped samples. Original RMS/peak: **0.101368 / 0.872284**.
34 planned events cover 9.99 seconds; the original has 1006 voiced pYIN frames.
The dynamic automation has 4023 points and no post-render frame adjustment.

| Output | RMS | Peak | Envelope lag | Median absolute pitch error | 90th-percentile error | Matched frames | DSP wall time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed +3 baseline | 0.095600 | 0.690948 | 0 ms | 0 cents | 10 cents | 1001 | 3.87 s |
| fixed -3 baseline | 0.101478 | 0.980000 | 0 ms | 0 cents | 10 cents | 996 | 2.82 s |
| dynamic third above | 0.094188 | 0.698801 | -10 ms | ~0 cents | 80 cents | 557 | 3.97 s |
| dynamic third below | 0.102461 | 0.846578 | +10 ms | ~0 cents | 90 cents | 550 | 3.34 s |
| -3 mapped formant/stereo | 0.099131 | 0.980000 | +10 ms | 10 cents | 20 cents | 986 | 3.44 s |
| -3 mapped formant/independent | 0.101732 | 0.980000 | +10 ms | 10 cents | 20 cents | 985 | 3.30 s |
| -3 mapped short window | 0.099654 | 0.902416 | 0 ms | ~0 cents | 20 cents | 984 | 1.73 s |
| -3 mapped no formants | 0.100394 | 0.837448 | +10 ms | 10 cents | 20 cents | 983 | 2.90 s |

Signed median shifts were +3/-3 on the fixed baselines; the dynamic target
changes between +3/+4 or -3/-4, with zero median signed target error on the
selected frames. Rest ramps include zero shift. Above/below dynamic outputs
needed no peak attenuation. Some constant mapped -3 variants required a small
reported common downward gain. These are single-run CPU wall times on this
machine, not portable performance guarantees.

Errors compare rendered-minus-original pYIN MIDI to the applied interval.
Dynamic scoring excludes planned rests, unreliable reference F0, amplitude
ramps, and frames close to event boundaries. pYIN itself has 10-cent bins and
can disagree on voicing or octave. The high 80–90-cent error tail is a material
limitation, not hidden by the near-zero median. Much of the original is
unvoiced or outside planned notes; the matched subset is not full-recording
accuracy. The coarse envelope lag uses 10 ms bins, not syllable-accurate timing.
Small timing differences and transient smearing can remain despite exact length.

## Tests and remaining limitations

```powershell
$env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
Remove-Item Env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS
```

Actual result: **274 passed** (including the historical 249 tests), with the
native engine required and no skips. New checks cover variable thirds in both
directions, +3/+4 and -3/-4 transitions, detuning, vibrato/glissando, missing F0,
octave outliers, empty plans, short notes, alignment/invalid plans, contiguous
note gain continuity, native mono/stereo rendering at 16/44.1 kHz, exact frame
count, silence, waveform vibrato retention, clipping-rail rejection, unsupported
CLI maps, timeouts, corrupt output, and atomic failure behavior. Native tests
do not download dependencies or models.

Listen to the outputs at matched playback volume, especially negative shifts,
consonants, breaths, short notes, transitions, and stereo collapse. Formant
handling, native windows, phase interactions, and separation leakage remain
plausible artifact sources, not proven causes here. The existing user feedback
is the only perceptual verdict so far. Do not enable production vocal mode
without listening review and broader material testing. Chord-aware planning,
automatic key detection, MIDI/piano changes, API/UI integration, and voice
cloning are outside this phase.

Rubber Band remains GPL-2.0-or-later with a vendor commercial licence option.
No native binaries were added to source control or new licence granted to this
project. [Review upstream distribution terms](https://breakfastquay.com/rubberband/license.html)
before shipping a product; a CLI subprocess is not a blanket licence exemption.
