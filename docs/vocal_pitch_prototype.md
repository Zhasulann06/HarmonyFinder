# Vocal pitch-shifting prototype — Phase 3B-1

Phase 3B-2's [dynamic prototype and quality investigation](dynamic_vocal_harmony.md)
extend this work in separate modules. That investigation confirmed that the
native CLI's `--ignore-clipping` clamps even FLOAT audio. Its newer mapped
renderer adds input headroom and rejects native clipping rails; this older
constant path is retained as a baseline, not an artifact-free reference.

This is an isolated offline waveform processor. It shifts a separated vocal
WAV by one constant semitone amount. It does not generate speech, detect chords,
change harmony algorithms, add an API endpoint, or change React Studio.
The existing render endpoint continues to produce piano harmony.

## Engine evaluation

| Option | Windows/Python integration | Formants and quality considerations | CPU/setup/licensing |
| --- | --- | --- | --- |
| **Rubber Band R3 CLI — selected** | Official Windows ZIP; Python subprocess, no DLL binding or Python wrapper | Explicit `--fine --formant`; stereo `--centre-focus` | More CPU than R2; small native utility; GPL-2.0-or-later or vendor commercial licence |
| Rubber Band through FFmpeg | Existing FFmpeg can be queried with `ffmpeg -h filter=rubberband`; filter requires a build with librubberband | Documented formant-preservation option; linked version and exposed engine controls need checking | No benchmark here; build/licence depends on included libraries; direct CLI gives explicit R3 selection |
| SoundTouch/SoundStretch | Windows CLI/C++ library; subprocess or native binding | Reviewed interface supports independent pitch/tempo, but does not document an equivalent formant-preservation switch | Designed for real-time CPU processing; LGPL-2.1, commercial alternative; not benchmarked here |
| librosa pitch_shift | Already installed, Python/NumPy | Its reference phase vocoder lacks transient handling; no explicit formant preservation in this path | Easy setup, but not selected for vocal quality; librosa uses ISC licensing; not benchmarked here |
| pyrubberband | Python wrapper around the Rubber Band CLI | Same underlying engine; options still depend on the executable | Would add a package without removing the native dependency; not needed for this prototype |

Primary references:

- [Rubber Band engine and CLI documentation](https://github.com/breakfastquay/rubberband)
- [Rubber Band CLI options](https://breakfastquay.com/rubberband/usage.txt)
- [Rubber Band Windows download](https://breakfastquay.com/rubberband/)
- [FFmpeg rubberband filter](https://ffmpeg.org/ffmpeg-filters.html#rubberband)
- [SoundTouch platform/features](https://soundtouch.surina.net/), [licence](https://www.surina.net/soundtouch/license.html)
- [librosa phase-vocoder limitations](https://librosa.org/doc/0.11.0/generated/librosa.phase_vocoder.html), [licence](https://github.com/librosa/librosa/blob/main/LICENSE.md)

The choice prioritizes a formant-aware CPU algorithm with an official Windows
binary and deterministic explicit options. The alternatives were evaluated
from their documented capabilities, not compared in a listening trial.

## Installation — Windows PowerShell

The official Rubber Band 4.0.0 ZIP is already extracted locally for this
evaluation. No additional Python packages, AI models, or GPU are required.
For another checkout, from the repository root:

```powershell
Invoke-WebRequest -Uri 'https://breakfastquay.com/files/releases/rubberband-4.0.0-gpl-executable-windows.zip' -OutFile '.\tools\rubberband-4.0.0-windows.zip'
Expand-Archive -LiteralPath '.\tools\rubberband-4.0.0-windows.zip' -DestinationPath '.\tools\rubberband-4.0.0'
& '.\tools\rubberband-4.0.0\rubberband-4.0.0-gpl-executable-windows\rubberband.exe' --version
```

Keep `sndfile.dll`, `COPYING.txt`, `README.txt`, and the other upstream files
with the executable. The downloaded ZIP is 1,765,785 bytes. Its observed SHA256
is `F2D47FC64DBB42F6CC62EDF7933AC4FA89D8F0EF8B9CF97B6AFC263A7FE05644`
(an observed checksum, not an independent authenticity signature).
The ZIP and extracted folder are ignored by Git.

Discovery order is a nonempty `HARMONYFINDER_RUBBERBAND` override, the project
local executable above, then `rubberband` on PATH. Overrides containing paths
are anchored to the project root; bare commands use PATH. Invalid overrides
raise an actionable dependency error rather than silently choosing a fallback.

```powershell
$env:HARMONYFINDER_RUBBERBAND = 'C:\Audio Tools\Rubber Band\rubberband.exe'
```

Do not include literal quote characters inside the environment value. Process
arguments are passed as a list without a shell; paths containing spaces work.
The module requires an identifiable Rubber Band version 3+ for R3 support.
To use only the already extracted local utility, leave the override unset.

## Architecture and processing

`backend/app/audio/vocal_pitch.py` provides a `VocalPitchShifter` protocol and
`RubberBandVocalPitchShifter.shift(source, output, semitones)`. The report
contains engine/version, frequency ratio, input/output frames, duration,
sample rate, channels, RMS, peak, clipped-sample count, processing time,
peak-protection gain, and any sample-rounding adjustment.

1. Validate a finite mono/stereo WAV, 8–192 kHz, nonempty and at most 30 seconds.
   Reject corrupt audio, unsupported formats, NaN/Inf, and shifts outside ±12.
2. Write a temporary FLOAT WAV at the original sample rate and channel count.
3. Invoke `rubberband --fine --formant --time 1 --pitch <semitones>
   --ignore-clipping --quiet` with `--centre-focus` for stereo. No resampling,
   tempo scaling, or independent channel jobs are introduced. The frequency
   multiplier is `2 ** (semitones / 12)`: 1.189207 for +3, 0.840896 for -3.
4. Check output format, finite samples, sample rate, channels, and duration.
   Correct only a discrepancy of at most two frames at the end. Larger
   discrepancies or unexpected silence from an audible input fail explicitly.
5. Apply a 5 ms fade only at nonzero file endpoints to avoid file-edge clicks.
   No internal phrase boundaries are cut. Apply common downward peak protection
   only if needed to keep the sample peak at or below 0.98. No RMS normalization
   or upward level matching is performed.
6. Validate and atomically publish a FLOAT WAV with exactly the input frame
   count. FLOAT avoids repeated quantization and is readable by existing
   backend audio utilities. Source audio is never overwritten.

All-zero audio stays exactly silent and zero shift uses a direct sample copy,
both without the optional executable (still subject to peak protection).
Nonzero near-silent signals are not auto-amplified. Silence between phrases
is processed by the engine without a gate; spectral windows may spread very
small energy around onsets/offsets. Synthetic tests verify far-silent margins.
Stereo centre focus helps mono compatibility but can change stereo width;
arbitrary stereo phase is not guaranteed unchanged by pitch shifting.
The executable has a 120-second processing timeout and a 5-second version
probe timeout. Dependency/process failures do not overwrite an existing output.

The protocol separates file orchestration from a replaceable DSP engine so
future phrase/note orchestration can call it. Dynamic shifts, segmentation,
crossfades between shifted phrases, and phase-continuous variable shifting
are deliberately deferred to Phase 3B-2 and will need separate tests.

## Generate the comparison

From the repository root, using the existing `.venv`:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.compare_vocal_pitch --input backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav
```

For another stem, replace `--input`; optionally use `--output` to choose a
comparison directory outside its source job. Both relative paths resolve from
the repository root independently of the working directory. Python's module
invocation itself should be run from the project root.

The script writes under `backend/data/vocal_pitch_comparison/`:

- `original_vocals.wav` — byte-for-byte copy of the source stem.
- `vocals_plus_3.wav` — +3 semitones.
- `vocals_minus_3.wav` — -3 semitones.
- `measurements.json` — measured report and pYIN checks.

It uses existing pYIN only for evaluation, comparing shared voiced frames at
the same timestamps. pYIN bins are 10 cents; the accepted median error is
0.5 semitone. This is not an independent perceptual test, and detector octave
errors, range limits, and inconsistent voicing can affect the comparison.
It also checks a 10 ms energy-envelope grid over lags of ±250 ms, requiring
an estimated lag within 30 ms. This detects gross shifts, not every syllable's
transient alignment. Evaluation is slower than the DSP due to three pYIN runs.
No model is downloaded by this script. Re-running replaces comparison outputs.

## Actual real-audio validation

Source job: `fa570cb6-1482-4dd2-8907-3ec2c0cbdf83`, Demucs `vocals.wav`.
All three files have **883,764 frames**, **20.040 seconds**, **44,100 Hz**, and
**2 channels**. Input is PCM16; shifted outputs are FLOAT.

| Output | RMS | Peak | Clipped samples | Median detected shift | Shared voiced frames | DSP wall time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| original_vocals.wav | 0.101368 | 0.872284 | 0 | — | — | — |
| vocals_plus_3.wav | 0.095600 | 0.690948 | 0 | +3.00 semitones | 1001 | 3.365 s |
| vocals_minus_3.wav | 0.101478 | 0.980000 | 0 | -3.00 semitones | 996 | 2.803 s |

Both estimated energy-envelope lags are 0.000 seconds on the 10 ms grid.
Neither output required frame adjustment or became unexpectedly silent.
The downward shift needed a peak-protection multiplier of 0.982708 (about
-0.15 dB); the upward shift needed none. These times are single-run wall
times on this Windows machine, not hardware-independent CPU benchmarks.
They demonstrate CPU practicality for this short clip, not real-time guarantees.

## Listening and distribution limitations

Technical checks do **not** establish perceptual naturalness, preservation of
lyrics, recognizability of the singer, perfect formant retention, or absence
of audible artifacts. No listening-based assessment or speech transcription
verification has been performed. Listen to all three files at the same player
volume, checking consonants, breaths, sustained vowels, vibrato, onsets,
syllable timing, stereo collapse, and file edges. Whole-waveform DSP retains
the original performance content, but formant preservation is an approximation.
Known possible artifacts include smearing, metallic/phasy vowels, altered
breath/sibilant texture, stereo width changes, and reduced quality at larger
shifts or on Demucs leakage/backing voices. ±3 is the evaluated range here.
Sample peak protection does not measure inter-sample true peaks.

[Rubber Band's vendor licence](https://breakfastquay.com/rubberband/license.html)
is GPL version 2 or later, with a commercial licence for proprietary use.
This evaluation retains the upstream notices locally and does not change the
project's licence or bundle the binary into source control. Before publishing
or redistributing a product that includes/uses this engine, assess GPL/source
and third-party library obligations or obtain the appropriate commercial
licence. A subprocess boundary is not a blanket exemption. The vendor notes
that dependent libraries have their own licence terms; libsndfile is included
in this Windows utility. No voice model, clone, or new speaker identity is used.

## Tests

```powershell
# Require actual installed Rubber Band checks instead of allowing optional skips:
$env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
Remove-Item Env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS
```

Without the optional engine, six real-DSP synthetic cases skip; pure validation,
silence/identity, and mocked failure cases continue running. No test installs
dependencies or downloads audio/models. Actual installed-engine tests measure
tone pitch ±3, timing, duration, sample rates, mono/stereo, silence margins,
and identical-channel consistency. Other tests cover invalid input/shift,
clipping protection, edge fades, atomic failure behavior, dependency versions,
timeouts, corrupt output, and environment path resolution.
