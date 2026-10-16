# Phase 3B-Q — vocal quality investigation

## Decision

**Do not release the current vocal mode or connect it to React.** The user's
listening verdict stands: +3 constant was acceptable, -3 constant was robotic,
and both dynamic thirds were bad. No new perceptual improvement is claimed.

This investigation found a measurable **pitch-control timing defect**, plus
independent planning and masking problems. There is a justified DSP repair
candidate to audition before replacing the engine. It remains isolated.

| Finding | Evidence | Interpretation/confidence |
| --- | --- | --- |
| Pitch automation arrives early | Six controlled 44.1 kHz stereo transitions: 87.35–90.27 ms early; median 89.52 ms | Confirmed technical defect for this configuration. Plausible cause of wrong pitch on short syllables. Exact WAV length did not catch it. |
| C major is unverified | Prior comparison script defaulted to C major; 13/34 rounded detected notes are outside it | Confirmed configuration limitation. **Actual song key is unknown**, not established as C major or any other key. |
| Scale labels and waveform centres diverge | 13/34 notes differ >50 cents from planned harmony anchors; range -100 to +95.01 cents | Confirmed consequence of interval-only shifting retaining quantization error. Pitch-offset accuracy alone does not verify the absolute planned notes. |
| Mask cuts nonzero audio | 16 attacks; mask removes 1.70% of source energy; 80 energetic 10 ms blocks attenuate >20 dB | Confirmed amplitude cuts. Potential consonant/breath loss, not proven phoneme identity. |
| Voicing is uncertain | 3.96 of 10.06 voiced seconds have pYIN voicing probability <0.5 | Tracking uncertainty, not proof that those notes are wrong. Voicing probability is not calibrated pitch accuracy confidence. |
| Negative processing remains different | Known pulse widening is greater on the negative synthetic probe; user disliked constant -3 independently of automation | A separate DSP/timbre concern. Timing repair alone cannot establish a cure. |

The original comparison masked about half the **duration**, but this is not
evidence of losing half the lyrics. Most energy is in its planned regions.
Energy-weighted loss is 1.70%; low-energy consonants can still matter greatly.

## Artifacts inspected and preserved

Source job: `backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83`.
The real stem is 883764 frames, 20.040 s, 44100 Hz stereo. Its saved original
plan was chromatic quantization plus a fixed major third. The Phase 3B-2 run
forked that analysis into **C-major scale-aware quantization and diatonic thirds**.
Those are different plans; the script's manual C-major assumption was not song
key detection. Original analysis and previous WAV/JSON artifacts were preserved.

Inspected: original stem, pitch/quantization/harmony JSON, both saved dynamic
curves and WAVs, Rubber Band settings, source-level/voicing measurements,
existing constant and dynamic implementations, and regression tests.
The interval calculations themselves are correct for their assumed scale:
above alternates +3/+4, below -3/-4. The control additionally goes toward zero
in rests, rather than only switching between thirds. The curve is ramped,
but can change a full semitone in a 5 ms knot step near those resets. Continuity
alone therefore does not mean gentle or perceptually correct transitions.

There were **no adjacent 10–14-semitone F0 jump candidates** under the audit's
rule. That does not rule out sustained octave errors or false low-register
notes. Without a musician-checked transcription, neither octave accuracy nor
the inferred melody is ground truth.

## Root cause: time-dependent pitch is not aligned by file length

Controlled tones have known F0 and scheduled transitions at 1, 2, and 3 seconds.
The installed Rubber Band 4.0.0 R3 CLI produces the right stable pitches but
the transitions arrive early. The previous tests checked stable interiors,
duration, and source energy-envelope timing. None of these measures when
the **pitch control** takes effect.

Actual 44100 Hz stereo default-preset measurements:

| Direction | Raw midpoint lead | After probe-calibrated command delay |
| --- | --- | --- |
| +3→+4 / +4→+3 | 89.21–90.27 ms early | 0.86–2.70 ms late |
| -3→-4 / -4→-3 | 87.35–90.07 ms early | Same six-transition median used for diagnostic calibration; negative corrected residual is covered by native tests at 16 kHz, not this table |

The calibration **delays commands by 89.5238 ms**, without moving audio or
amplitude automation. It is measured at this rate/channel/preset combination,
not assumed from a library constant. At 16 kHz mono, the probes lead by about
121–125 ms. **Do not hardcode 89.5 ms for other configurations.** Short windows,
different engines, ratios, and stereo options require their own verification.

Rubber Band's [integration notes](https://breakfastquay.com/rubberband/integration.html)
warn that dynamic ratio timing depends on internal buffering and start-delay
handling. That library guidance does not justify blindly applying a correction
with an assumed sign to the CLI: the actual executable here was measured early.
The CLI accepts input-frame maps and compensates initial padding, but that
does not make every subsequent control change acoustically aligned.

The new `delay_automation` helper is an **experimental diagnostic ablation**.
The production/public renderer was not patched with a universal offset.
The next implementation should use a validated latency-aware library adapter
or configuration-specific timing strategy, not a magic number.

## Planning error that interval accuracy conceals

The current curve intentionally uses `shift = harmony_anchor - lead_anchor`,
preserving vibrato and source detuning. It does not apply the quantizer's
correction to the waveform. This preserves expression but also preserves an
off-scale note's entire correction error. For example:

| Time | Detected median MIDI | C-major lead anchor | Planned harmony | Applied shift | Expected waveform centre |
| --- | ---: | ---: | ---: | ---: | ---: |
| 8.13–8.35 | 54.25 | 55 | 59 | +4 | 58.25 (75 cents below the planned note) |
| 9.34–9.59 | 53.90 | 53 | 57 | +4 | 57.90 (90 cents above) |
| 9.65–10.16 | 49.10 | 50 | 53 | +3 | 52.10 (90 cents below) |

These are arithmetic predictions from detected note medians, not a verified
musical transcription. A wrongly assumed key can make these discrepancies
worse; an actually intended chromatic tone should not be forcibly corrected
without musical review. The old pitch score compared **applied interval**,
not absolute scale membership of the rendered voice, and could miss this issue.

Recommended planning prerequisite: establish the key and manually verify one
reference phrase, including which chromatic notes are intentional. Then choose
explicitly between strict target-note centres and transposed expression. Do
not silently equate scale-snapped labels with a scale-correct vocal waveform.
No chord or key detector was implemented in this investigation.

## Suspicious source timestamps

The generated `report.md` lists every note, centre discrepancy, and flag;
`report.json` contains all timings, low-voicing regions, mask cuts, shift
discontinuity candidates, and feature measurements. Priorities for listening:

| Timestamp | Why inspect it |
| --- | --- |
| 7.01–7.26 | Three 80–90 ms notes, first probability ~0.01; comparable in length to the measured automation lead |
| 8.13–8.35 | Off-scale source and 75-cent centre mismatch |
| 8.88–9.28 | Low voicing; energetic material omitted at 9.00–9.17 |
| 9.34–10.16 | ±90-cent centre mismatches and a gate gap at 9.61–9.65 |
| 10.76–10.88 | Short, low-voicing, ~65-cent mismatch before a rest |
| 11.49–12.23 | Sustained low-voicing note; unverified low-register estimate |
| 12.51–12.59 | Energetic audio outside detected note mask |
| 12.95–13.05 | Short event with ~95-cent centre mismatch |
| 15.74–15.90; 16.36–16.42 | Energetic audio outside mask; could include breath/consonant/leakage |
| 16.98–17.06 | 80 ms event, voicing probability ~0.03, ~80-cent mismatch |
| 17.69–17.76 | Another energetic masked gap |
| 17.76–18.50 | Low-voicing/short events and ~75–90-cent centre discrepancies |

“Energetic” uses 10 ms RMS >= max(0.003, 3% of the peak block RMS), here
0.011146. It is not a validated vocal/sibilant detector. Background leakage
can also trigger this rule. No phoneme alignment or lyric transcription was
invented to label these intervals.

## Controlled renders and measured ablations

Canonical run:
`backend/data/vocal_quality_investigation/20261015T164724Z-1b67a1b8/`.
The earlier initial investigation run is retained too.
All real-source files preserve 20.040 s / 883764 frames / 44100 Hz / stereo,
with no NaN/Inf, clipped samples, or frame correction. All native settings and
peak-protection gains are recorded in `report.json`.

| Comparison | How it isolates a factor |
| --- | --- |
| `constant_plus_3`, `constant_plus_4`, `constant_minus_3`, `constant_minus_4` | A–D: original offline R3/formant/centre-focus baseline on the complete same source |
| `mapped_constant_plus/minus_3/4` | Same fixed shifts through mapped mode; separates fixed ratio from offline/real-time processing |
| `known_3_4_20ms`, `known_3_4_80ms`, `known_minus_3_4_20ms` | E: deliberately scheduled ±3/±4 controls without detected notes or muting. Correct DSP controls, **not verified harmony for this song** |
| `real_dynamic_above`, `real_dynamic_below` | F: unchanged copies of the saved bad outputs |
| `gate_only_no_pitch` | Original waveform times the original amplitude mask, without pitch DSP |
| `real_no_gate` | Same real pitch curve, amplitude mask disabled |
| `held_intervals_80ms` | Holds intervals through gaps, 80 ms control ramps, no mask; isolates resets/speed of automation |
| `real_control_delayed` | Same real curve and mask, only measured pitch-command timing compensation |
| `held_80ms_control_delayed` | Combined experimental candidate: timing compensation, held intervals, no mask |
| `real_short_window` | Same real curve and mask with supported R3 short window |
| `minus_3_no_formants` | Prior constant-map formant-disabled comparison, copied unchanged |

No “improved preset” is endorsed. Held/no-mask controls also shift breath,
leakage, or unplanned source notes. These are factor-isolation experiments,
not an approved strategy for producing a complete harmony.

### Real-source pitch diagnostics

Unlike Phase 3B-2's selected note interiors, this score includes **all shared
voiced frames**, including transitions. It measures offset error against the
intended curve, not the song's correct melody/key. Each render's voiced match
set is measured separately; the pYIN detector has 10-cent bins and can make
octave/voicing errors. Counts and selection rules are saved alongside results.

| Render | Matched frames | Median absolute error | 90th percentile |
| --- | ---: | ---: | ---: |
| Mapped constant +3 | 985 | ~0 cents | 20 cents |
| Known 3↔4, 20 ms | 984 | 10 cents | 67 cents |
| Real curve, original bad output | 980 | 10 cents | 181 cents |
| Real curve, mask removed | 980 | 10 cents | 170 cents |
| Held intervals, 80 ms | 984 | 10 cents | 70 cents |
| Real curve, timing compensated | 980 | 10 cents | 30 cents |
| Held 80 ms, timing compensated | 985 | 10 cents | 30 cents |

The drop in the error tail supports the timing diagnosis. It does **not**
prove better perceived sound, correct harmony, or fixed singer identity.
Near-zero median values in previous phases concealed meaningful bad regions.

### Signal, phase, formant and sibilance proxies

| Measure | Original | Gate only | Original bad above | No gate | Timing-compensated above |
| --- | ---: | ---: | ---: | ---: | ---: |
| RMS | 0.101368 | 0.100503 | 0.094188 | 0.095013 | 0.093817 |
| Peak | 0.872284 | 0.872284 | 0.698801 | 0.698801 | 0.734985 |
| 4–10 kHz fraction of spectral power | 1.223% | 0.324% | 0.279% | 0.932% | 0.317% |
| Energetic 10 ms blocks down >20 dB | — | 80 | 80 | 0 | 80 |

The spectral change under gating makes possible consonant/sibilant loss a
priority for listening. This fraction is **not** identified consonant energy.
Timing compensation alone intentionally does not restore muted audio.

Whole-file left/right correlation is ~0.999995 in the source and near 1 in
these outputs. The source is effectively centred; there is no demonstrated
large interchannel decorrelation here. That statistic cannot exclude spectral
phase-vocoder artifacts, stereo-width changes, or metallic timbre.

A 400 Hz-smoothed, total-power-normalized Welch spectral-envelope MAE over
300–3500 Hz is 0.80 dB for offline +3, 0.61 dB for offline -3, 0.91 dB for bad
dynamic above, 0.86 dB for timing-compensated above, and 2.14 dB for the
formant-disabled negative comparison. This is an envelope proxy affected by
pitch, gating, windowing, and phoneme mix—not measured F1/F2 stability.
No trustworthy true formant estimate or “vocal THD” can be extracted from this
unannotated, already separated performance with these measurements alone.

### Known-waveform distortion/transient probes

Use `probe_review-49f1cf01.json` for the reviewed stable-window statistics.
The initial `report.json` sine fit sampled 0.65–0.90 s, which overlaps the
unexpectedly early pitch change; its residual is not a stationary-tone metric.
The review uses 0.60–0.80 s and retains the initial report for traceability.
Future normal runs use the corrected window as well.

| 16 kHz known sine probe | +3 plateau | -3 plateau |
| --- | ---: | ---: |
| Fitted fundamental | 261.6257 Hz | 184.9973 Hz |
| Harmonics 2–5 / fundamental | -83.50 dB | -88.22 dB |
| Fitted residual / signal | -33.46 dB | -45.20 dB |
| Known pulse half-height width | 18.44–21.44 ms | 24.50–28.06 ms |
| Pulse peak offset | 12.56–15.38 ms early | 12.25–18.75 ms late |

Source pulse width is 18.875 ms. The negative probe broadens these short
transients more. Stable harmonic distortion of this sine is small; a small
harmonic ratio is not evidence of natural vocal sound. Residual includes
phase/amplitude changes and numerical fitting effects. These probes use
16 kHz mono and are not claimed to quantify the real singer's consonants at
44.1 kHz. They identify mechanisms to test, not a proven perceptual root cause.

## Listening package

Three consistent source windows: **7.0–10.0**, **10.5–13.5**, and **16.4–19.4 s**.
Each folder `excerpts_<start>-<end>s/` contains the same labeled original,
constant, synthetic-control, real-curve, gate ablation, and experimental
candidate WAVs. Crops occur **after full-recording processing**, preserving
the same native context for every condition. Every file gets the same 5 ms
file-edge fades and exact 132300-frame boundaries.

Excerpts are matched with pyloudnorm's BS.1770 meter, bounded to at most +12 dB
gain, with a common downward peak safeguard at 0.90. Near-silent material is
not boosted. All eligible excerpts in all three measured sets reach **-23.00
LUFS**, and no common peak attenuation was required. These are listening-only
copies; production/audio gains are unchanged. `listening_manifest.json` records
input/output LUFS and exact applied gains. LUFS reduces level bias; timbre and
phrasing can still affect perceived loudness.

Start with original vs `gate_only_no_pitch`, then constant +3/+4 vs mapped
constant +3/+4, then `known_3_4_20ms`, bad real above, `real_control_delayed`,
and `held_80ms_control_delayed`. For below, compare -3/-4, the known negative
control, saved bad below, and no-formant -3. Assess lyrics, robotic texture,
consonants, pitch timing, and musical suitability separately. Solo listening
tests transformation; use the song context later to judge harmony selection.
No listening verdict is fabricated by this report.

## Reproduce and run tests

Existing Python 3.11 `.venv` and Rubber Band 4.0.0 are reused. Only the small
optional diagnostic meter was installed (`pyloudnorm 0.1.1`, MIT, and its `future`
dependency); no AI models, new audio engine, GPU, or cloud service was installed.

From the project root in PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-quality.txt
.\.venv\Scripts\python.exe -m backend.scripts.investigate_vocal_quality --job backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83 --run backend/data/dynamic_vocal_comparison/20261015T111811Z-283d44a9
```

Each investigation creates a new timestamp/UUID directory, preserving earlier
source and comparison files. Render settings, processing times, complete note
tables, statistical proxies, and listening gains are saved in JSON/Markdown.
The script refuses a mismatched prior source. To review the saved synthetic
probes without rerendering or altering earlier reports:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.investigate_vocal_quality --review-probes backend/data/vocal_quality_investigation/20261015T164724Z-1b67a1b8
```

That command creates another `probe_review-<id>.json`, not an overwrite.

```powershell
$env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS = '1'
.\.venv\Scripts\python.exe -m pytest backend/tests -q
Remove-Item Env:HARMONYFINDER_REQUIRE_RUBBERBAND_TESTS
.\.venv\Scripts\python.exe -m pip check
```

New tests measure the timing defect and verify calibrated synthetic transition
residuals <15 ms, rather than merely relaxing an alignment threshold. They
also cover curve continuity, semitone mapping, scale-centre mismatches,
missing-note energy loss, candidate octave flags, known pulse width/delay,
level-matched listening copies, invalid inputs, and actual native output.
They supplement the entire original backend suite. The meter test may skip on
machines without the optional quality requirements; it ran here.

Actual final validation: **283 backend tests passed, no skips**, with the native
engine required. `pip check` reported no broken requirements. The earlier
274 tests remain intact; nine quality-investigation cases were added.

## Supported strategies and recommended next step

| Strategy | Practicality and limits | Decision |
| --- | --- | --- |
| Rubber Band R3 continuous maps | Installed Windows CPU utility; formant/centre-focus/default vs short window tested; GPL-2.0-or-later or commercial licence | Repair/validate automation timebase first. Retain only as experimental until listening approves. |
| Rubber Band native API adapter | Would need a Windows library/wrapper and explicit latency/buffer handling; same underlying DSP | Evidence justifies a narrowly scoped latency-managed adapter investigation, not an engine rewrite or universal offset. |
| R3 independent stereo / formants off | Existing supported prior variants; formants off changes voice envelope substantially | Diagnostic options, not quality endorsements. Current nearly mono source does not establish stereo coupling as the principal cause. |
| R2 / SoundTouch | Windows CPU options; R2 different transient settings, SoundTouch LGPL with a different approach | Not benchmarked here. Do not mistake R2-only flags for R3 improvements or assume formant/naturalness equivalence. |
| Signalsmith Stretch | C++11, MSVC-tested; variable-pitch processing and formant compensation; MIT; Python binding exists but exposed controls/wheels need verification | Plausible controlled alternative benchmark if repaired Rubber Band remains unacceptable; not installed or declared superior. |
| Neural singing/vocal resynthesis | Separate data/licence/identity/compute study; different product tradeoffs | Recommend a separate research phase **if** reviewed DSP approaches remain unacceptable. Do not equate waveform shifting with natural human singing. |

References: [Rubber Band integration](https://breakfastquay.com/rubberband/integration.html),
[CLI options](https://breakfastquay.com/rubberband/usage.txt),
[Rubber Band licensing](https://breakfastquay.com/rubberband/license.html),
[Signalsmith API, Windows support and licensing](https://github.com/Signalsmith-Audio/signalsmith-stretch),
[SoundTouch](https://soundtouch.surina.net/),
[pyloudnorm](https://github.com/csteinmetz1/pyloudnorm).

Recommended order: (1) musician-verify the key and one phrase's lead/target
notes; (2) establish correct pitch-control timing at supported configurations;
(3) redesign phrase coverage after reviewing gate-only excerpts; (4) conduct
level-matched, preferably blinded listening across directions. Only then decide
between a DSP alternative benchmark and a separate neural research phase.
The candidate's lower pitch error is not sufficient release approval.

No public API, React code, piano mode, harmony planner, pitch tracker, separator,
or production vocal renderer was changed in Phase 3B-Q.
