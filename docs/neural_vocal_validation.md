# Phases 4B-1 / 4B-2 / 4C-1 — isolated Seed-VC validation

This is an experiment, not a production integration. See the historical
[Phase 4A feasibility report](neural_vocal_feasibility.md) for candidate research,
licensing, the exact source revision, and the original failed attempts.

## Phase 4C-2: provisional diatonic thirds and transition refinement (2026-10-17)

This remains an **isolated listening experiment**, not production harmony.
The user found 4C-1 dynamic vocals about as natural as fixed neural vocals,
with occasional unnatural note transitions and good expressiveness. The same
six-second source (`vocals.wav` seconds 7–13, 44.1 kHz mono), same-singer
reference and pinned Seed-VC V1 checkpoint are reused. Five whole-phrase
inferences ran at 40 diffusion steps, CFG 0.7, fixed random seed 1234. There
was no note-by-note audio slicing, model download or checkpoint edit.

### Key evidence and note plan

The cached 20.04-second lead pYIN analysis has 34 note events. Duration-weighted
pitch-class coverage is 8.47/9.99 detected-note seconds (84.78%) for both
**D major and relative B natural minor**; the next pair (A major/F# minor)
covers 7.90/9.99 (79.08%). Melody pitch classes alone do not distinguish D
major from B minor, and there is no verified chord/cadence or user-confirmed
key. We therefore use **provisional D major** for this controlled experiment,
not a claimed confirmed key. D major and B natural minor yield the same
diatonic-third scale notes. Each `shift_map.json` records the full coverage
ranking and all original event pitches. No chord-aware claim is made.

The existing production scale-aware quantizer and diatonic-third planner were
**imported read-only**, not modified. The 19 cropped pYIN events are kept at
their original times. Four out-of-scale events are explicitly snapped for the
plan: A#2→A2, C3→C#3, D#3→E3 and F3→E3 (the latter is nearest to original
52.7 fractional MIDI). The plan does not re-quantize the source waveform.
The neural target offset for each event is `harmony MIDI - original fractional
lead MIDI`, preserving the source's within-note micro-pitch and vibrato
algebraically while centering it on the intended harmony note. Adjacent events
are scale-degree thirds, with no added octave jumps. Large leaps already in
the source remain; they were not concealed by changing the musical interval.

| Start (s) | Lead → selected scale note | Third above (offset st) | Third below (offset st) |
| ---: | --- | --- | --- |
| 0.01 | A#2 → A2* | C#3 (+3.50) | F#2 (−3.50) |
| 0.09 | C3 → C#3* | E3 (+4.00) | A2 (−3.00) |
| 0.17 | C#3 | E3 (+3.00) | A2 (−4.00) |
| 0.29 | E3 | G3 (+3.05) | C#3 (−2.95) |
| 0.53 | D3 | F#3 (+3.90) | B2 (−3.10) |
| 0.85 | E3 | G3 (+2.70) | C#3 (−3.30) |
| 1.13 | F#3 | A3 (+2.75) | D3 (−4.25) |
| 1.35 | E3 | G3 (+2.70) | C#3 (−3.30) |
| 1.88 | B2 | D3 (+2.90) | G2 (−4.10) |
| 2.17 | E3 | G3 (+3.40) | C#3 (−2.60) |
| 2.34 | F#3 | A3 (+3.10) | D3 (−3.90) |
| 2.65 | C#3 | E3 (+2.90) | A2 (−4.10) |
| 3.16 | D3 | F#3 (+3.80) | B2 (−3.20) |
| 3.76 | D#3 → E3* | G3 (+3.65) | C#3 (−2.35) |
| 4.49 | A2 | C#3 (+4.20) | F#2 (−2.80) |
| 5.27 | F3 → E3* | G3 (+2.30) | C#3 (−3.70) |
| 5.59 | G3 | B3 (+4.45) | E3 (−2.55) |
| 5.77 | D3 | F#3 (+4.25) | B2 (−2.75) |
| 5.95 | C#3 | E3 (+3.05) | A2 (−3.95) |

`*` = original integer note class outside provisional D major. Exact times,
fractional offsets and note ends are in each immutable
[`shift_map.json`](../experiments/neural_vocals/runs/harmony-above-baseline80-20261017/shift_map.json).
For unsegmented source-voiced frames between pYIN events, the prior event's
offset is held until the scheduled gap-midpoint transition, then the next
event's offset is held. RMVPE-unvoiced frames remain **zero Hz**, so no pitch
target is imposed on silence or unvoiced consonants. This fallback can still
mislabel an unsegmented voiced sound and needs human review before production.

### Transition treatments and real renders

All variants use cubic smoothstep only on the **semitone-offset envelope**,
not on source F0 itself. An 80-ms baseline and 30-ms short ramp center on the
pYIN note onset for contiguous notes; when an event gap exceeds 30 ms, the
change is centered in that gap. Neighboring boundaries cap ramp width to
prevent overlap. A third **motion30** above-only probe uses the same 30-ms
ramp but aligns six of 18 boundaries to a measured, direction-consistent
source RMVPE pitch movement within ±60 ms; eight boundaries stay in gaps and
four remain at note onsets. It excludes octave-sized jumps from motion
alignment. This is a small controlled timing treatment, not a new melody
detector. No Rubber Band control offset was imported.

| Render | Median / p90 abs F0 error to injected expressive target | Source voiced lost / false voiced (600 frames) | Timed crossings / 18 | Mean absolute crossing error | Sampled device VRAM | Load / render |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Above, 80 ms | 15.9 / 45.6 cents | 17 / 3 | 9 | 22.0 ms | 2,870 MiB | 14.6 / 10.7 s |
| Above, 30 ms | 14.3 / 47.5 | 18 / 3 | 9 | 21.7 ms | 2,870 MiB | 14.7 / 10.4 s |
| Above, motion 30 ms | 16.0 / 45.5 | 17 / 4 | 9 | 28.6 ms | 2,871 MiB | 15.2 / 10.5 s |
| Below, 80 ms | 20.5 / 60.9 | 22 / 10 | 8 | 15.1 ms | 2,869 MiB | 14.1 / 10.5 s |
| Below, 30 ms | 21.0 / 63.0 | 22 / 10 | 7 | 14.7 ms | 2,874 MiB | 13.8 / 10.5 s |

Each model run verified the external F0 vector at Seed-VC's source length
regulator. All outputs are valid, finite, non-silent, unclipped 44.1-kHz mono
WAVs of 264,192 frames / **5.990748 s**, 408 frames shorter than the exact
six-second source (same model behavior as prior phases). Per-run
`seed_map_report.json`, `monitor_report.json`, `melodic_metrics.json` and
`melodic_measured_f0.npz` hold exact timings, PyTorch memory, device samples,
per-note errors and contours. Sampled VRAM is device-wide and can miss brief
peaks; the runner report separately records PyTorch allocation/reservation.
Across the five raw renders, RMS spans **0.106–0.140** and sample peak
**0.939–0.962** (below clipping). The generated note-level pitch errors are
also recorded against absolute harmony MIDI pitches separately from the
expressive injected F0 target.

The local pitch-boundary overshoot audit uses generated/source relative cents
beyond the two intended adjacent offsets in ±100 ms voiced windows. P90
overshoot is **59.0, 53.7, 45.6 cents** for the three above treatments and
**60.2, 57.3 cents** for the two below treatments, respectively. Maxima reach
~1,100–1,240 cents around **2.085 s**, where source/output F0 tracking has an
octave-sized jump near the short B2→E3 event sequence. These maxima could
reflect a genuine transition artifact, F0 estimator octave error, or both;
they must not be read as a reliable pitch correction score. Shorter ramps
and motion alignment do **not** consistently improve median/p90 target error,
crossing timing or voicing. Many boundaries overlap unvoiced frames, so their
acoustic crossing cannot be measured. Objective data therefore does **not**
justify declaring any treatment more natural. The difficult ~1.88–2.17 s
region merits hand inspection of source segmentation/F0 before more smoothing.
As a continuity example, at the 1.35-s above boundary the largest adjacent
10-ms output F0 change was **119 cents** for the 80-ms treatment versus
**108 cents** in its injected target; at the 2.085-s gap boundary the
generated and injected contours both jump by about **1,200 cents**, making
that location unsuitable for attributing the jump to the ramp alone.
See the complete [transition audit](../experiments/neural_vocals/runs/melodic-listening-complete-20261017/transition_summary.json).

### Listening set and reproduction

The final [eight-file matched-loudness set](../experiments/neural_vocals/runs/melodic-listening-complete-20261017/)
contains `A_original.wav`, `B_previous_dynamic_plus.wav`,
`C_previous_dynamic_minus.wav`, both 80/30-ms above and below renders,
and `above_motion30.wav`. Its manifest lists raw sources, sample levels,
per-file gains and measured LUFS. All copies are six-second PCM24, near
**−23 LUFS**, with a common 5-ms endpoint fade and only neural end padding;
no onset shift or time warp. The earlier source audio and comparison sets are
untouched. The user has **not yet rated** these five melodic variants.

From the repository root in Windows PowerShell (use *new* run and listening
directory names if repeating; scripts refuse overwrites):

```powershell
.\.venv\Scripts\python.exe -m experiments.neural_vocals.melodic_harmony --run experiments/neural_vocals/runs/harmony-above-baseline80-20261017 --direction above --key D --scale major --treatment baseline80
experiments\neural_vocals\.venv\Scripts\python.exe -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/harmony-above-baseline80-20261017 --steps 40 --cfg-rate 0.7 --shift-map experiments/neural_vocals/runs/harmony-above-baseline80-20261017/shift_map.json
experiments\neural_vocals\.venv\Scripts\python.exe -m experiments.neural_vocals.measure_melodic --run experiments/neural_vocals/runs/harmony-above-baseline80-20261017
```

Repeat with `--direction below` and/or `--treatment short30` or `motion30`;
the actual five run labels and paths are in the listening manifest. Generate
the matched set using:

```powershell
.\.venv\Scripts\python.exe -m experiments.neural_vocals.melodic_listening --output experiments/neural_vocals/runs/melodic-listening-complete-20261017
.\.venv\Scripts\python.exe -m experiments.neural_vocals.compare_transitions --output experiments/neural_vocals/runs/melodic-listening-complete-20261017/transition_summary.json
.\.venv\Scripts\python.exe -m pytest -q
```

Actual final test result: **337 passed in 23.54 s** (including 303 backend and
34 experiment tests). The app `.venv` was used only to run the existing
planning/test dependencies, not altered. Seed-VC inference/measurement used
only the isolated `experiments/neural_vocals/.venv`; no production endpoint,
frontend, model or audio processing component changed.

**Recommendation:** Obtain the user's blind listening ranking of the 80-ms,
30-ms and motion-aligned samples before selecting a transition strategy.
Verify the provisional key against the original accompaniment/chords or an
explicit musician annotation, and manually examine the likely pitch-tracker
ambiguity and very short notes around 1.88–2.17 s. Do not integrate this
planner yet; this is scale-aware diatonic-third F0 control under a provisional
key, **not** confirmed-key or chord-aware harmony.

## Phase 4C-1: full-phrase dynamic F0 feasibility (2026-10-16)

The user now rates lyric and singer-identity preservation in the 4B neural
outputs **good** and hears approximately no quality difference from the 40-step
setting. That updates the earlier subjective feedback recorded below. Phase
4C-1 tests pitch control only; the user has not yet rated these dynamic WAVs.

### What the model actually accepts

The pinned V1 public CLI accepts only one scalar `semi_tone_shift`. Its
inference implementation extracts a full source F0 vector with RMVPE (10-ms
grid), multiplies voiced values by the scalar semitone ratio, and passes that
vector into `model.length_regulator(..., f0=shifted_f0_alt)`. The length
regulator embeds 256 quantized F0 bins and interpolates the embedding to the
mel length before one continuous diffusion/vocoder pass. The reference F0 is
passed separately for the prompt. Thus the architecture supports an external
time-varying source F0 vector even though the stock CLI has no F0-map option.
The experiment wraps only the local Python inference call, never checkpoint
tensors or upstream model files. The adapter applies a semitone *offset* to
each voiced source F0 frame; that algebraically preserves its vibrato and
micro-pitch in the **requested target**. The generated sound must be assessed
separately.

Three pYIN note onsets in the existing six-second excerpt were selected at
**1.35, 2.65, and 4.49 s**. Each transition spans 80 ms, uses cubic smoothstep
easing, and changes between +3/+4 or -3/-4. The first shift lasts to 1.31 s;
subsequent plateaus and ramps are defined exactly in the versioned
[`dynamic_plus_3_4.json`](../experiments/neural_vocals/fixtures/dynamic_plus_3_4.json)
and [`dynamic_minus_3_4.json`](../experiments/neural_vocals/fixtures/dynamic_minus_3_4.json)
fixtures. The F0 adapter leaves unvoiced frames at zero. These are manually
chosen control probes, **not** diatonic harmony or note planning. No source
audio was sliced into independently processed notes.

The existing 40-step/CFG 0.7 fixed +3 and -3 renders in
`runs/quality-steps40_cfg07-20261016T232444/` provide same-setting constant
controls. The dynamic runs reuse the exact same six-second original and
same-singer reference via hard links. Their results are:

- [Dynamic +3/+4 raw WAV](../experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734/dynamic_plus_3_4.wav)
- [Dynamic -3/-4 raw WAV](../experiments/neural_vocals/runs/dynamic-minus34-20261016T234621/dynamic_minus_3_4.wav)
- [Five-file loudness-matched listening set](../experiments/neural_vocals/runs/dynamic-listening-20261017T0000/): original, constant +3, dynamic +3/+4, constant -3, dynamic -3/-4.

Both raw dynamic outputs are finite, non-silent, unclipped mono 44.1-kHz float
WAVs of **264,192 frames / 5.990748 s**, the same 408-frame (9.252-ms) end
shortfall as the constant Seed-VC renders. Raw RMS/peak: +3/+4 **0.1432 / 0.9366**;
-3/-4 **0.1037 / 0.9423**. The matched listening copies are six-second PCM24
at approximately **-23 LUFS**, with only 408-frame end padding and a common
5-ms endpoint fade. There is no time stretching or onset shift, and their
`manifest.json` records each gain. All originals and earlier results remain.

### Acoustic target-following evidence

The wrapper saves `injected_f0.npz` (source and target Hz at each RMVPE frame)
and checks that the mapped contour reaches the **source** length regulator.
Maximum numerical difference after Seed-VC's internal log/exp round-trip was
**0.000076 Hz** for +3/+4 and **0.000061 Hz** for -3/-4. Output and constant
control F0 were then extracted with the same pinned RMVPE checkpoint.
[`dynamic_metrics_final.json` for +3/+4](../experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734/dynamic_metrics_final.json)
and [for -3/-4](../experiments/neural_vocals/runs/dynamic-minus34-20261016T234621/dynamic_metrics_final.json)
contain the full target-versus-generated contours, voicing and transitions;
`measured_f0_final.npz` retains the numeric arrays.

| Full-phrase render | Median / p90 absolute error to injected target | Common voiced frames | Source voiced lost | Output voiced in source-unvoiced frames | GPU device peak | Model load / render |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Dynamic +3/+4 | 15.1 / 45.6 cents | 479 | 20 | 3 | 2,862 MiB | 14.25 / 10.80 s |
| Dynamic -3/-4 | 17.4 / 58.7 cents | 469 | 30 | 10 | 2,862 MiB | 13.70 / 9.68 s |

The source had **499 voiced frames** within the 600 compared 10-ms frames.
The injected F0 had 601 frames and the generated/constant WAVs yielded 600;
the shared 600-frame range was compared without warping. PyTorch tensor
allocation peaked at **2,487,098,368 bytes**, reservation at **2,831,155,200
bytes** in each render; device-wide samples may miss subsecond peaks or include
other processes. Neither run exhausted the 4-GB GPU.

To check that the model follows the external map rather than returning its
fixed-shift output, compare each dynamic output with the constant render at
identical 40 steps, CFG 0.7 and seed. Across four stable intervals (0.2-1.25,
1.45-2.55, 2.75-4.35, 4.65-5.85 s), the median dynamic-minus-constant pitch
differences were:

| Map | Expected relative cents | Observed median relative cents |
| --- | --- | --- |
| +3/+4 | 0, +100, 0, +100 | -0.2, +101.7, +0.2, +103.3 |
| -3/-4 | 0, -100, 0, -100 | -1.2, -94.4, -2.5, -99.5 |

This is direct acoustic evidence for external **time-varying** F0 control.
The first transition at 1.35 s crossed the intended midpoint at **1.367 s**
(+3/+4, +17 ms) and **1.358 s** (-3/-4, +8 ms). The 2.65- and 4.49-second
boundaries overlap unvoiced or unmatched frames, so their exact acoustic
crossing times are **unmeasurable** in this excerpt; do not interpret the
first voiced frame after silence as model delay. Voiced/unvoiced detection and
these crossing estimates depend on RMVPE, not hand-annotated ground truth.

The target map mathematically retains the source's expressive F0 deviations,
and the output tracks its plateaus. A stricter frame-to-frame small-motion
correlation between source and generated F0 was only **0.17** (+3/+4) and
**0.06** (-3/-4) on stable voiced frames. This noisy proxy does **not** establish
that generated vibrato sounds natural or even faithfully preserves each
micro-pitch movement. User listening is essential, especially at the ramps.

### Reproduce without new downloads

Use the existing isolated Python and verified local assets. From project root,
create a new run under `experiments/neural_vocals/runs`, hard-link the six
prepared inputs (`original_vocals.wav`, `reference_same_singer.wav`,
`original_stereo_excerpt.wav`, both Rubber Band WAVs, `preparation.json`) from
`runs/gpu-20261016T214526/`, and copy the desired fixture to
`shift_map.json` in that new run. The runner refuses to overwrite results.
For the completed runs, the exact commands were:

```powershell
$py = '.\experiments\neural_vocals\.venv\Scripts\python.exe'
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734 --steps 40 --cfg-rate 0.7 --shift-map experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734/shift_map.json
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/dynamic-minus34-20261016T234621 --steps 40 --cfg-rate 0.7 --shift-map experiments/neural_vocals/runs/dynamic-minus34-20261016T234621/shift_map.json
& $py -m experiments.neural_vocals.measure_dynamic --run experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734 --constant-run experiments/neural_vocals/runs/quality-steps40_cfg07-20261016T232444
& $py -m experiments.neural_vocals.measure_dynamic --run experiments/neural_vocals/runs/dynamic-minus34-20261016T234621 --constant-run experiments/neural_vocals/runs/quality-steps40_cfg07-20261016T232444
.\.venv\Scripts\python.exe -m experiments.neural_vocals.dynamic_listening --constant-run experiments/neural_vocals/runs/quality-steps40_cfg07-20261016T232444 --dynamic-plus experiments/neural_vocals/runs/dynamic-plus34-retry-20261016T234734 --dynamic-minus experiments/neural_vocals/runs/dynamic-minus34-20261016T234621 --output experiments/neural_vocals/runs/dynamic-listening-20261017T0000
```

Each command above produced an existing artifact; substitute fresh run/output
names when repeating. The first attempt in
`runs/dynamic-plus34-20261016T234621/` stopped before synthesis because an
experimental guard incorrectly demanded **bit equality** after Seed-VC's F0
log/exp operation. Its failure report and injected contour were preserved.
The guard now accepts only a tight numerical tolerance and logs the measured
maximum Hz difference. No source audio, model weight, or earlier render was
overwritten. The generated WAVs came from the successful runs named above.

Conclusion: **external dynamic F0 conditioning works technically for this
single continuous phrase**, with audible-quality review still pending. This is
not a second musical voice generator: the map was manually set from three
note onsets, contains no key/scale or harmony decisions, and was never mixed
with the original. It is not proof of natural dynamic singing. The next useful
gate is listening to the matched constant/dynamic pair for lyric identity,
vibrato, transition smoothness and artifacts before designing a note planner.

Final checks: **332 passed in 26.28 s** for the backend plus experiment tests;
**26 passed in 0.92 s** in the isolated environment; isolated `pip check`
reported no broken requirements. All five matched listening WAVs reopened as
44.1-kHz mono six-second PCM24 with peaks below full scale. The original full
vocal and the pinned Seed checkpoint still match their SHA-256 hashes. Only
experimental scripts, ignored experiment runs, and this report changed.

## Phase 4B-2 quality investigation (2026-10-16)

User listening feedback on the 4B-1 pair: both neural fixed shifts sounded
better than their Rubber Band counterparts, but singer identity and lyrics were
preserved only partially. That is the only perceptual verdict in this report.
The following variants need a new listening review; numerical pitch checks do
not establish vocal naturalness or word intelligibility.

### Checkpoint audit and root cause of the warning

Run the read-only CPU audit in the isolated environment:

```powershell
.\experiments\neural_vocals\.venv\Scripts\python.exe -m experiments.neural_vocals.checkpoint_audit `
  --output experiments/neural_vocals/runs/gpu-20261016T214526/checkpoint_audit_verified.json
```

The output already exists, so choose a *new* name to repeat the command. The
authoritative result is
[`checkpoint_audit_verified.json`](../experiments/neural_vocals/runs/gpu-20261016T214526/checkpoint_audit_verified.json).
The first, unnormalized audit file in that run is retained as a diagnostic
artifact; it did not remove the checkpoint's `module.` DDP prefixes and is not
a valid loading comparison. The final audit reproduces the official loader's
prefix normalization without altering any weights.

The checkpoint SHA-256 is `42aef93ffe65857c840d270252fa040f7ba04514945ec460f3ac1ac2a96de684`;
the pinned config SHA-256 is `ff86f343b08c2def405f075022eeb10dafba23c4eda36d151010f4ca6d7a1a0a`.
The official V1 inference loader selects this F0-conditioned 44.1 kHz singing
checkpoint and config; the config constructs `final_layer_type: mlp`, 768 hidden
dimensions, 17 transformer layers, and 256 F0 bins. The constructed `cfm`
matched **243 of 245 state entries** (all **243 trainable parameter keys**),
and the length regulator matched **24 of 24** (all trainable). There are **no
shape-mismatched or missing trainable weights** in the active model.

The warning combines two different cases:

- Ten unexpected checkpoint keys belong to the **unused WaveNet output branch**:
  `estimator.conv1.{weight,bias}`, `estimator.conv2.{weight,bias}`,
  `estimator.res_projection.{weight,bias}`, and
  `estimator.t_embedder2.mlp.{0,2}.{weight,bias}`. The configured MLP output
  branch does not instantiate or call these layers. Their presence in the
  checkpoint does not mean active learned weights were skipped.
- `estimator.input_pos` is a non-trainable positional index buffer: 8,192
  elements saved versus 16,384 generated by the pinned code. Its shared prefix
  is **identical**. The six-second inference uses only the initial positions.
- Conversely, the constructed model has `estimator.t_embedder.freqs`, a
  generated frequency buffer absent from the checkpoint. It is not a learned
  parameter. The official loader also ignores checkpoint `style_encoder` and
  `vq` sections because this inference path builds only `cfm` and
  `length_regulator`; it independently loads CAMPPlus for speaker style.

The warning text in the official loader says "shape mismatch" even for keys
absent from the constructed model. These findings rule out this warning as a
direct cause of missing **active** acoustic weights. They do not prove that the
model preserves identity or lyrics. No checkpoint tensor, config architecture,
or upstream model file was changed.

### Conditioning and plausible quality limits

The source and reference are disjoint six-second segments from the same Demucs
vocal stem. The source supplies Whisper semantic features and RMVPE F0; the
reference supplies a mel prompt, Whisper features, CAMPPlus speaker embedding,
and its own F0 prompt. The median pYIN F0 was **149.40 Hz** for the source and
**150.26 Hz** for the reference; automatic F0 level adjustment remained off,
so this small reference/source pitch-level difference did not alter the ±3
requests. The source is mono downmixed from the separated stem, and no clean
independent studio reference is available. Stem leakage, prompt length/quality,
Whisper's compressed content representation, and the generative voice-conversion
model are plausible contributors to changed consonants or singer character.
The experiment does not isolate or prove any one of those as the cause. Neither
the skipped unused checkpoint keys nor a failed CUDA load explains the partial
lyric/identity preservation observed by the user.

### Controlled six-second GPU variants

All variants used the identical hard-linked source/reference and original
Rubber Band WAVs, the same checkpoint and seed 1234, FP16 diffusion, F0
conditioning on, `auto_f0_adjust=False`, and `length_adjust=1`. Only diffusion
steps or inference CFG rate changed. To reproduce, make a **new** run directory
under `experiments/neural_vocals/runs`, hard-link the six inputs listed in the
4B-1 inference contract below, then run a matching command. The completed
runs and their exact commands were:

```powershell
$py = '.\experiments\neural_vocals\.venv\Scripts\python.exe'
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/quality-steps40_cfg07-20261016T232444 --steps 40 --cfg-rate 0.7
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/quality-steps30_cfg05-20261016T232444 --steps 30 --cfg-rate 0.5
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/quality-steps30_cfg10-20261016T232608 --steps 30 --cfg-rate 1.0
```

The runner refuses to overwrite reports or WAV directories; substitute new
prepared run paths to execute again. The baseline used 30 steps/CFG 0.7.
All six new outputs were finite, non-silent, and unclipped. Every native WAV
was 44.1 kHz mono, 264,192 frames (**5.990748 s**), 408 frames shorter than
the source; coarse energy-envelope lag was 0 s, with no >-40 dBFS spill in the
25 source-quiet 10-ms blocks and no dropout in the 498 source-active blocks.
Those are coarse screens, not syllable or phoneme alignment checks.

| Steps / CFG | Load s | +3 render s | -3 render s | Sampled device peak MiB | +3 median / p90 error cents | -3 median / p90 error cents |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 30 / 0.7 baseline | 29.33 | 11.73 | 6.14 | 2,870 | 10 / 40 | 20 / 60 |
| 40 / 0.7 | 15.02 | 11.12 | 7.02 | 2,886 | 10 / 40 | 20 / 50 |
| 30 / 0.5 | 13.55 | 9.31 | 6.16 | 2,880 | 10 / 40 | 20 / 50 |
| 30 / 1.0 | 12.47 | 9.07 | 6.04 | 2,880 | 10 / 40 | 10 / 51 |

Per-run tensor reservation peaked at **2,694–2,700 MiB**; the sampled device
figures include driver/other use and may miss subsecond peaks. The initial
baseline includes a cold model load, so its wall-time difference is not an
isolated step-count benchmark. Every run exited 0 without CUDA OOM. Their
`seed_report.json`, `monitor_report.json`, `inference_console.txt`, and
`listening-*/measurements.json` contain raw measurements, RMS, peaks, native
durations, and loudness gains. Native neural peaks ranged about **0.928–0.983**
with no clipped samples; listening copies were gain-reduced to about -23 LUFS.

The 10-ms pYIN bin report is
[`quality_pitch_bins-20261016.json`](../experiments/neural_vocals/runs/quality_pitch_bins-20261016.json).
For the baseline, +3 had **467** common voiced frames, median/p90 error
**10/40 cents**, and two frames over 100 cents; -3 had **468**, **20/60 cents**,
and ten frames over 100 cents. The 40-step pair had **468**, **10/40 cents**,
two over 100 for +3; and **468**, **20/50 cents**, nine over 100 for -3.
The worst per-second p90 error is around **0–1 and 5–6 s** for +3, and
**3–4 s** for -3 (70 cents in the baseline and 40-step clips). Voiced-frame
disagreement and pitch error can flag listening spots; they cannot identify
pronounced words or measure lyric intelligibility. No transcript or
time-aligned lyric ground truth was available, so pronunciation degradation
cannot be localized honestly from these metrics alone.

### Listening set and decision

The provisional 40-step pair was selected for review because it modestly
improved -3 pitch p90 while maintaining +3 accuracy and voiced-frame coverage.
It is **not** a verified perceptual improvement. The seven files in
[`quality-listening-20261016T2330/`](../experiments/neural_vocals/runs/quality-listening-20261016T2330/)
are `A_original.wav`, `B_rubberband_plus_3.wav`,
`C_neural_baseline_plus_3.wav`, `D_neural_candidate_plus_3.wav`,
`E_rubberband_minus_3.wav`, `F_neural_baseline_minus_3.wav`, and
`G_neural_candidate_minus_3.wav`. All are mono PCM24, 44.1 kHz, six seconds,
gain matched to approximately **-23 LUFS** without peak clipping. The
408-frame neural shortfall is end-padded in listening copies; all receive the
same 5-ms endpoint fade. Raw generated WAVs remain unmodified. The directory's
`manifest.json` records exact gains, sources and audio levels. Reproduce with:

```powershell
.\.venv\Scripts\python.exe -m experiments.neural_vocals.quality_listening `
  --baseline experiments/neural_vocals/runs/gpu-20261016T214526 `
  --candidate experiments/neural_vocals/runs/quality-steps40_cfg07-20261016T232444 `
  --output experiments/neural_vocals/runs/quality-listening-NEW
```

The pinned V1 CLI accepts a **scalar** `semi_tone_shift`. Internally, RMVPE
generates a time-varying F0 contour, and the length regulator interpolates it
onto the mel grid and quantizes it to 256 bins over the configured F0 range.
An injected contour is technically plausible, but neither variable-target
tracking nor lyric/identity quality at pitch changes was tested here. The
recommended next step is **further quality investigation and user listening**,
particularly the 3–4 s region and consonants, before investing in dynamic
neural F0 control. A cleaner same-singer reference and additional phrases
would test whether the prompt or this model is the stronger limitation.

Final checks: **330 passed in 24.43 s** in the main environment
(`.\.venv\Scripts\python.exe -m pytest backend/tests experiments/neural_vocals -q`)
and **24 passed in 0.95 s** in the isolated experiment environment. All seven
listening WAVs reopened as valid 44.1 kHz mono, 264,600-frame audio with peaks
below full scale; the original full vocal WAV's SHA-256 is unchanged. Only
experiment scripts, ignored experiment artifacts, and this report changed.

## Latest result: real CUDA inference (2026-10-16)

The user installed official torch **2.4.1+cu121** and torchaudio
**2.4.1+cu121** into the existing isolated `experiments/neural_vocals/.venv`.
Both import successfully. A CUDA matrix multiplication returned the expected
result on the **RTX 3050 Laptop GPU (4,096 MiB)**; CUDA runtime is 12.1.
`python -m pip check` in that environment reported **No broken requirements
found**. All 15 local model/config/card assets passed the pinned size checks;
the five weight files also passed their published SHA-256 checks. The original
full vocal stem still matches the SHA-256 in the preparation record. The ten
smaller assets have local hashes recorded for reproducibility, not published
checksums. The two 2.4.1 wheel files passed their official index SHA-256
checks. No downloads or package installs were made during this run.

The previous six-second source, disjoint six-second same-singer reference, and
Rubber Band baselines were hard-linked into a fresh attempt at
`experiments/neural_vocals/runs/gpu-20261016T214526/`. The earlier failed run
and all original audio remain intact. From the project root, the exact inference
and comparison commands were:

```powershell
$py = '.\experiments\neural_vocals\.venv\Scripts\python.exe'
& $py -u -m experiments.neural_vocals.monitor --run experiments/neural_vocals/runs/gpu-20261016T214526
.\.venv\Scripts\python.exe -m experiments.neural_vocals.compare --assess experiments/neural_vocals/runs/gpu-20261016T214526
```

The monitored runner exited **0** and generated both playable, non-silent,
finite, unclipped raw WAVs:

- [`neural_plus_3.wav`](../experiments/neural_vocals/runs/gpu-20261016T214526/neural_plus_3.wav)
- [`neural_minus_3.wav`](../experiments/neural_vocals/runs/gpu-20261016T214526/neural_minus_3.wav)

These are mono, 44,100 Hz, 264,192-frame float WAVs of **5.990748 s** each,
**408 frames / 9.252 ms shorter** than the six-second source due to the model's
output grid. Raw outputs were not stretched or overwritten. Model loading took
**29.334 s**; +3 rendering **11.726 s**; -3 rendering **6.144 s**; runner total
**47.643 s** and monitored wall time **51.743 s**. The first render includes
some one-time execution overhead. Peak PyTorch tensor allocation was
**2,482,242,560 bytes (2,367 MiB)** and reservation **2,824,863,744 bytes
(2,694 MiB)**. One-second NVIDIA device-wide samples peaked at **2,870 MiB**;
that includes other GPU use and may miss brief peaks. Peak process working set
was **2,420,748,288 bytes (2,309 MiB)**. The GPU did not run out of memory.
Measurements and the complete console log are in `seed_report.json`,
`monitor_report.json`, and `inference_console.txt` in the attempt directory.

The model loader warned about skipped checkpoint keys because of shape
mismatches. Both renders completed, but the warning warrants investigation
before judging the checkpoint as a dependable production candidate. The
upstream inference also warned that a sampling-rate argument was omitted at
one call site; this experiment kept the pinned upstream code unchanged.

| Native candidate | Duration | RMS | Peak | Median shift | Median / p90 pitch error | Common voiced frames |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Original | 6.000 s | 0.1245 | 0.7841 | — | — | — |
| Rubber Band +3 | 6.000 s | 0.1173 | 0.6451 | +3.00 | 0 / 10 cents | 490 |
| Seed-VC +3 | 5.991 s | 0.1427 | 0.9739 | +3.00 | 10 / 40 cents | 467 |
| Seed-VC -3 | 5.991 s | 0.1082 | 0.9396 | -3.00 | 20 / 60 cents | 468 |
| Rubber Band -3 | 6.000 s | 0.1280 | 0.7902 | -3.00 | 0 / 10 cents | 493 |

These are pYIN measurements on common voiced 10-ms frames, not pitch ground
truth. All four candidates had **0.000 s coarse energy-envelope lag**, zero
clipped samples, no >-40 dBFS spill in the 25 source-quiet 10-ms blocks, and no
dropout in the 498 source-active blocks. Those energy checks do not establish
consonant preservation or exact phoneme timing.

Five matched-loudness listening files are in
[`listening-471fda75/`](../experiments/neural_vocals/runs/gpu-20261016T214526/listening-471fda75/):
`A_original.wav`, `B_rubberband_plus_3.wav`, `C_neural_plus_3.wav`,
`D_neural_minus_3.wav`, `E_rubberband_minus_3.wav`. Each is 44.1 kHz mono PCM24
at approximately **-23 LUFS**. The listening copies have the 408-frame shortfall
end-padded and a common 5-ms endpoint fade; there is no time warp or onset
shift. `measurements.json` records the precise loudness gains and metrics.
The user needs to listen to assess naturalness, intelligibility, timbre,
consonants, and phrasing. Numerical checks cannot settle those questions.

This verifies fixed ±3 shifts only. The pinned CLI has no external time-varying
F0 input, and no dynamic neural harmony was run. Next, listen to the five files
and decide whether Seed-VC improves the robotic quality enough to justify a
separate variable-F0 experiment. Check the loader's skipped-key warning and
repeat on more than one vocal phrase before any production decision.

Regression checks after inference: the main project environment ran
`.\.venv\Scripts\python.exe -m pytest backend/tests experiments/neural_vocals -q`
with **330 passed in 25.66 s**. The isolated environment ran
`test_control.py`, `test_downloads.py`, and `test_runner_guards.py` with
**24 passed in 0.75 s**. The main environment's backend/frontend code and
dependencies were not changed. The experiment's `phase4b1.json` records the
final machine-readable status and links to the preserved earlier failure.

## Scope and recovery

The user approved approximately 5–6 GB of downloads on 2026-10-16. Existing
contiguous checkpoint bytes and completed range pieces are reused; a completed
asset is accepted only after its expected size and published SHA-256 match.
The upstream-bundled CAMPPlus checkpoint is reused via a verified hard link.
No second Whisper weight format, optimizer, discriminator, or alternate model is
downloaded. TLS verification remains enabled. Public downloads are from official
Hugging Face repositories, download.pytorch.org, and PyPI/files.pythonhosted.org.
No user audio is uploaded.

The selected weights total 2,486,122,472 bytes. The Windows Python 3.11 CUDA 12.1
torch 2.4.0 wheel is 2,441,950,418 bytes; matching torchaudio is 4,115,561 bytes.
Smaller Python dependencies and configs are additional. The pinned
`experiments/neural_vocals/asset_manifest.json` and `recover.py` record expected
sizes/hashes; per-run recovery JSON records completed verification.

Failures encountered during recovery are not inference/OOM results:

- A Whisper range request raised `TimeoutError: The read operation timed out`;
  retained pieces are retried, with errors in `assets/*/download_errors.jsonl`.
- pip 23.2.1 timed out on the official SciPy 1.13.1 wheel at about 10.8/46.2 MB,
  reporting `HTTPSConnectionPool(host='files.pythonhosted.org', port=443): Read
  timed out.` pip discarded that incomplete temporary transfer. Subsequent
  staging uses persistent range pieces and the SHA-256 from PyPI metadata.
- A later pip 23.2.1 attempt timed out near 61.4/80.2 kB of tqdm, on the same
  official host. The isolated pip was upgraded to verified PyPI wheel 26.2.1,
  with `--resume-retries 10`. Thirty-five completed wheels (26,312,275 bytes)
  were recovered from the experiment's legacy pip cache with download-only
  operations and then installed offline. The app's pip/environment was not
  upgraded. Transient handshake/read errors on HF/PyTorch were retried.

All 15 selected model/config/card files and both CUDA wheels subsequently
completed verification, with empty failure lists in
`recovery_models-1792140051102694300.json` and
`recovery_wheels-1792140055789228400.json`. All five weight hashes match the
official LFS SHA-256 values; both CUDA wheels match official index hashes.
Small configs/cards without published SHA-256 are size-checked and their local
SHA-256 values recorded for reproducibility, not labeled official checksums.

## Windows PowerShell recovery procedure

The commands in this historical subsection reproduce the earlier 2.4.0 setup,
which failed Windows DLL preflight. The 2.4.1 installation and successful GPU
run are recorded above; no recovery download is needed for the current setup.

Run from the HarmonyFinder root. The experiment environment already exists;
do not recreate either environment. Run only one transfer for each asset at a
time. The following model and CUDA-wheel commands may run in separate terminals.

```powershell
.\.venv\Scripts\python.exe -u -m experiments.neural_vocals.recover models
.\.venv\Scripts\python.exe -u -m experiments.neural_vocals.recover wheels
```

Both commands reuse complete verified files and resume `.partial`/`.parts`
files. Failure reports include exact official URLs and errors. Do not delete
partials, disable TLS, or install an incomplete wheel. Keep at least 15 GB free.
The default recovery deadline is two hours; `--max-seconds` changes the bounded
transfer budget, not verification requirements.

For a slow PyPI wheel, stage its explicit version first:

```powershell
.\.venv\Scripts\python.exe -u -m experiments.neural_vocals.stage_wheels scipy==1.13.1
$env:PIP_CACHE_DIR = "$PWD\experiments\neural_vocals\cache\pip"
$py = '.\experiments\neural_vocals\.venv\Scripts\python.exe'
# The existing isolated environment now has pip 26.2.1 (app pip is unchanged).
# If recovering an older isolated environment, stage/install this verified wheel:
# .\.venv\Scripts\python.exe -m experiments.neural_vocals.stage_wheels pip==26.2.1
# & $py -m pip install --no-index 'experiments/neural_vocals/assets/wheels/pip-26.2.1-py3-none-any.whl'
# Explicit local paths prevent pip preferring an equal-version online candidate.
# Install other staged large wheels the same way before resolving dependencies.
& $py -m pip install --no-index --no-deps `
  'experiments/neural_vocals/assets/wheels/scipy-1.13.1-cp311-cp311-win_amd64.whl'
& $py -m pip install --timeout 120 --resume-retries 10 --find-links experiments/neural_vocals/assets/wheels `
  'experiments/neural_vocals/assets/wheels/torch-2.4.0+cu121-cp311-cp311-win_amd64.whl' `
  'experiments/neural_vocals/assets/wheels/torchaudio-2.4.0+cu121-cp311-cp311-win_amd64.whl'
if ($LASTEXITCODE -ne 0) { throw 'CUDA installation incomplete' }
& $py -m pip install --timeout 120 --resume-retries 10 --find-links experiments/neural_vocals/assets/wheels `
  -r experiments/neural_vocals/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation incomplete' }
& $py -m pip check
& $py -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available())"
```

Never install these requirements into the app `.venv`. A validated complete
installation should be recorded separately from successful checkpoint downloads.

## Inference and comparison contract

Use the existing six-second `20261015T182215Z-ddacdb38` run's mono 44.1 kHz
source and disjoint same-singer reference. Original full-length audio and
Rubber Band baselines remain untouched. Failed attempts must be retained;
use a new attempt directory with identical prepared inputs for subsequent trials.

The baseline now contains a preserved failed-attempt log. After fixing the
runtime, create a new attempt with hard-linked, unchanged prepared inputs:

```powershell
$baseline = Join-Path $PWD 'experiments/neural_vocals/runs/20261015T182215Z-ddacdb38'
$run = Join-Path $PWD ('experiments/neural_vocals/runs/retry-' + (Get-Date -Format 'yyyyMMddTHHmmss'))
New-Item -ItemType Directory -Path $run -ErrorAction Stop | Out-Null
foreach ($name in @('original_vocals.wav', 'reference_same_singer.wav',
    'original_stereo_excerpt.wav', 'rubberband_plus_3.wav', 'rubberband_minus_3.wav', 'preparation.json')) {
    New-Item -ItemType HardLink -Path (Join-Path $run $name) -Value (Join-Path $baseline $name) -ErrorAction Stop | Out-Null
}
& $py -u -m experiments.neural_vocals.monitor --run $run
if ($LASTEXITCODE -ne 0) { throw 'Inspect seed_report.json and inference_console.txt before retrying' }
.\.venv\Scripts\python.exe -m experiments.neural_vocals.compare --assess $run
```

The runner selects the official F0-conditioned 44.1 kHz model with 30 diffusion
steps, FP16 diffusion autocast, `length_adjust=1`, CFG 0.7, fixed seed 1234, and
automatic reference-F0 adjustment disabled. Models load only from allowlisted
local assets with Hugging Face offline mode and telemetry disabled. BigVGAN's
custom CUDA-kernel compilation is disabled. Fixed +3 and -3 trials reuse loaded
models. No dynamic harmony or production renderer is invoked.

`seed_report.json` records load time, individual render times, tensor allocation
and reservation peaks, CPU working-set/private-commit counters, errors and raw
WAV paths. `monitor_report.json` and `gpu_samples.jsonl` record approximately
one-second device-wide NVIDIA usage, including other processes and driver memory;
this may miss short peaks. Neither metric should be mislabeled as the other.

Comparison metrics include native duration/frame count, RMS, peak, rate,
channels, common-voiced-frame pYIN pitch offset/error, coarse energy-envelope
lag, and energy-based silence spill/dropout screening. No source-quiet blocks
means silence preservation is unmeasured, not a pass. Unvoiced consonants are
not treated as silence. These are technical checks, not naturalness verdicts.

Raw model WAVs are retained. Listening exports use identical mono 44.1 kHz
format, PCM24, common 5-ms endpoint fades and BS.1770 loudness matching. Up to
50 ms of native end-grid rounding may be padded/cropped only in listening copies;
differences are reported. There is no time stretching or hidden onset correction.

## Dynamic F0 boundary

The pinned official CLI implements scalar semitone shifts, not an external F0
file API. Internally it passes a time-varying F0 tensor to the length regulator.
An external relative-shift trajectory is architecturally possible; the existing
numeric adapter preserves unvoiced zeros and can represent +3/+4 or -3/-4.
It does not establish acoustic tracking, smooth transitions, natural vibrato,
or a working dynamic neural harmony system. Those need a subsequent controlled
audio experiment after constant shifts and user listening pass.

## Licensing and quality gate

Seed code and the selected checkpoint declare GPL-3.0. Other component terms
remain separate (BigVGAN MIT; Whisper/CAMPPlus host metadata Apache-2.0;
RMVPE host metadata MIT). Preserve notices and review checkpoint provenance
before distribution; isolation is not a licence exemption. No product licence
or redistribution decision is made by this experiment.

The user must listen for naturalness, intelligibility, singer identity,
consonants, warble/metallic artifacts and phrasing. Passing tests or pitch
measurements cannot validate neural vocal quality.

## Historical outcome before the user's torch 2.4.1 installation

**Downloads completed; neural inference remains blocked before model loading.**

Installed in the existing separate Python 3.11.5 environment:
torch **2.4.0+cu121**, torchaudio **2.4.0+cu121**, transformers 4.46.3,
huggingface-hub 0.28.1, numpy 1.26.4, scipy 1.13.1, librosa 0.10.2,
numba 0.61.2, llvmlite 0.44.0, soundfile 0.12.1, descript-audio-codec 1.0.0,
descript-audiotools 0.7.2, and their dependencies. `pip check` reports
**No broken requirements found**, but dependency metadata consistency is not
runtime validation. Full installed versions are in the prerequisite failure JSON;
`installed_dependencies.json` records the final pip transaction.

Actual monitored runner attempt, original baseline run directory:

- `prerequisite_failure-1792141083379113300.json`: `stage=dependency_preflight`,
  `models_loaded=false`, full installed versions and traceback.
- `inference_console.txt`, `gpu_samples.jsonl`, `monitor_report.json` retain the
  failed attempt. Exit code **1**; bootstrap wall time **0.700 s**, not inference time.
- Exact failure: **`OSError [WinError 126]` loading `torch/lib/fbgemm.dll` or one
  of its dependencies**. Its imported `libomp140.x86_64.dll` is unavailable;
  `MSVCP140.dll`, `VCRUNTIME140.dll`, and `VCRUNTIME140_1.dll` load successfully.
- RTX 3050 Laptop: **4,096 MiB**, driver **610.62**. Before the attempt:
  device used **50 MiB**, free **3,913 MiB**, as separately reported by NVIDIA.
  The monitor sampled **50 MiB device usage** during bootstrap only. **This is
  not model peak VRAM.** No CUDA tensor test or model inference succeeded.
- Model loading time, inference time, CPU model-memory peak, neural pitch
  accuracy, and neural timing/silence measurements are **unavailable**.
- **No `neural_plus_3.wav` or `neural_minus_3.wav` exists.** No new five-way
  listening set was created. The original three-way original/Rubber Band set
  remains under `listening-4fde07c0/`; its historical measurements are in Phase 4A.
- No CUDA OOM occurred: execution never reached CUDA/model loading. CPU fallback
  cannot resolve this import failure either, because it uses the same torch DLLs.

The [upstream PyTorch Windows issue](https://github.com/pytorch/pytorch/issues/131662)
identifies the missing OpenMP dependency and records the maintainer's 2.4.1 fix.
No random DLL sites, DLL renaming, mixed-version torch binaries, global PATH
changes, registry changes, system installers, or GPU-setting changes were used.

### Rejected small-runtime recovery route

Microsoft's official VS channel declared `VisualStudio.vsman` as 30,443,686 bytes,
SHA-256 `a871a5ff41acebbe5037455fd6f51fcd4907b47d8f3c9860871ea0b222a2fd45`.
The official payload URL instead served 17,954,770 bytes, SHA-256
`99dda859c4ae3c446eb25620d1a6237bb135d95d14d55cd1d30a15340bb39d80`.
Both size and hash checks rejected it. The received bytes remain explicitly
`.partial`, not accepted as a verified catalogue. A cache-busted request showed
the same size discrepancy. A separate official LTSC channel also had a size
discrepancy; it was not downloaded.

The rejected catalogue was inspected only as non-executable discovery data.
Two candidate official MSVC packages also returned HTTP sizes different from
their declared sizes (3,434,354 vs 3,446,332; 50,053,268 vs 50,755,605 bytes).
Their transfers were rejected before publication. **No DLL was extracted,
signature-accepted, copied into torch, or executed.** No cause for Microsoft's
metadata/content discrepancies is asserted. Integrity checks were not relaxed.
These findings concern the Microsoft recovery route, not the successfully
verified HF/PyTorch assets. The proposed component downloads were tens of MB,
not another multi-GB framework download.

Microsoft also [warns that the LLVM OpenMP DLLs are not redistributable](https://learn.microsoft.com/en-us/cpp/build/reference/openmp-enable-openmp-2-0-support?view=msvc-170).
They must not be casually bundled into the product even if a local development
runtime is obtained. That workaround was not applied here.

### Historical 2.4.1 recovery instructions (already completed by the user)

The user subsequently installed the replacement wheels in the isolated
environment. The following earlier recovery instructions are retained only for
provenance; the successful CUDA trial above reused the installed files without
downloading anything.

| Required replacement | Bytes | Official SHA-256 |
| --- | ---: | --- |
| torch 2.4.1+cu121 / cp311 / win_amd64 | 2,444,893,595 | `bc1e21d7412a2f06f552a9afb92c56c8b23d174884e9383259c3cf5db4687c98` |
| torchaudio 2.4.1+cu121 / cp311 / win_amd64 | 4,115,589 | `06095d5941a2843663a230bef739680541e0a491caf41df8fb1552eeefd212b0` |

Original recovery commands:

```powershell
.\.venv\Scripts\python.exe -u -m experiments.neural_vocals.recover wheels --torch-version 2.4.1 --workers 16
if ($LASTEXITCODE -ne 0) { throw 'Replacement wheels incomplete; rerun to resume' }
$py = '.\experiments\neural_vocals\.venv\Scripts\python.exe'
& $py -m pip install --no-index --no-deps `
  'experiments/neural_vocals/assets/wheels/torch-2.4.1+cu121-cp311-cp311-win_amd64.whl' `
  'experiments/neural_vocals/assets/wheels/torchaudio-2.4.1+cu121-cp311-cp311-win_amd64.whl'
& $py -m pip check
& $py -c "import torch; x=torch.ones((32,32),device='cuda'); y=x@x; torch.cuda.synchronize(); print(torch.__version__,torch.version.cuda,torch.cuda.get_device_name(),y[0,0].item())"
```

If that preflight succeeds, create a fresh hard-linked attempt as above and
run the monitored, unchanged 30-step singing configuration. All verified model
files are reused. The patch-release fix is documented upstream, **not yet
locally validated**; it does not guarantee 4 GB fit or natural singing quality.
If inference subsequently OOMs, preserve the exact report before considering
explicit encoder/vocoder offloading or CPU execution. No such fallback was
implemented or claimed during this pre-CUDA failure.

### Tests and preservation

- Main environment: **330 passed in 23.78 s**, comprising 303 existing backend
  tests and 27 experiment tests. Command:
  `.\.venv\Scripts\python.exe -m pytest backend/tests experiments/neural_vocals -q`.
- Separate experiment environment: **24 passed in 0.58 s**, using
  `test_control.py`, `test_downloads.py`, and `test_runner_guards.py`.
  The remaining three measurement tests use existing backend analysis utilities
  and run in the app environment. Tests never download or load neural weights.
- Separate environment's final `pip check`: passed.
- These passing tests do **not** validate neural naturalness or GPU inference.
- Main torch still imports as **2.14.1+cpu**, CUDA runtime `None`; its installed
  dependencies were not changed. The full original vocal stem's SHA-256 still
  matches `preparation.json`. All production source/audio and frontend files are
  preserved. No experiment download or inference is left running.

Changed experiment files: `download_assets.py`, `seed_runner.py`, `compare.py`,
`requirements.txt`, `test_downloads.py`. Added `recover.py`, `range_transfer.py`,
`stage_wheels.py`, `resources.py`, `monitor.py`, `test_measurements.py`,
`test_runner_guards.py`, and `phase4b1.json`. README links this report. Download
verification/installation JSON records are retained alongside the experiment;
large assets, environment, caches, and local audio runs remain ignored.

That was the status of the earlier attempt. The later CUDA trial above completed
constant-shift inference; perceptual quality remains pending user review.
