# Phase 4D-1 — experimental guitar-accompaniment chord recognition

This is an **unintegrated feasibility experiment**, not a verified transcription
or a change to the neural harmony planner. The user's Phase 4C-2 listening
feedback is positive for the diatonic neural harmony, while its D-major/B-minor
key assumption remains provisional.

## Inputs and method

The reference input is the existing 20.04-second, stereo 44.1-kHz Demucs
[`instrumental.wav`](../backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/instrumental.wav).
Demucs' two-stem procedure can leave vocals, percussion, and other instruments
in this stem. Other stored full-level stems are near-identical versions of this
same recording (first-channel correlations ~0.998 with the selected stem);
several other stored stems are silent or near-silent. They are **not independent
song examples**. No separately labelled clean guitar recording is available,
and the instrument identity in this recording has not been independently
verified. Synthetic decaying/plucked triads stand in for the clean-guitar test.

The [experimental detector](../experiments/chord_recognition/detector.py)
downmixes and resamples to 11.025 kHz, computes a 4096-point STFT, retains
its harmonic component with HPSS, and forms 12-bin chroma. Every 0.5 seconds,
it compares the median chroma with all 24 major/minor triad templates.
Templates ignore inversions; 3rds and 5ths carry explicit weights. A low
energy region is `no_chord`; weak fit or a close runner-up is `ambiguous`.
An isolated low-confidence chord blip between identical neighbors can be
smoothed, but `no_chord` and `ambiguous` are never overwritten. Confidence is
a **heuristic ranking score, not a calibrated probability**. The implementation
does not force a key, and does not model diminished, seventh, suspended,
power, or slash chords.

## Real-stem candidate timeline — review required

The [full timestamped JSON](../experiments/chord_recognition/runs/reference_instrumental_20261017/chord_timeline.json)
contains every 0.5-second frame, top three candidates, fit, margin, RMS,
smoothed label, and 19 merged segments. Inspect the
[SVG harmonic-chroma plot](../experiments/chord_recognition/runs/reference_instrumental_20261017/chroma.svg)
alongside the [editable human-review worksheet](../experiments/chord_recognition/runs/reference_instrumental_20261017/human_review.csv).
The separate [half-second confidence-region map](../experiments/chord_recognition/runs/reference_instrumental_20261017/confidence_regions.json)
explicitly tags `chord`, `low_confidence`, `ambiguous`, or `no_chord`;
labelled chords below the heuristic 0.5 threshold are low-confidence.
Segment confidence below is the minimum of its half-second frames; none of
these labels are ground truth.

| Time (s) | Candidate | Minimum confidence |
| --- | --- | ---: |
| 0.00–1.00 | no chord | 0.000 |
| 1.00–2.00 | ambiguous | 0.012 |
| 2.00–3.00 | B minor | 0.412 |
| 3.00–4.50 | G major | 0.638 |
| 4.50–5.50 | no chord | 0.000 |
| 5.50–6.50 | ambiguous | 0.006 |
| 6.50–7.00 | D major | 0.316 |
| 7.00–7.50 | ambiguous | 0.023 |
| 7.50–8.00 | G major | 0.210 |
| 8.00–8.50 | ambiguous | 0.055 |
| 8.50–10.50 | A major | 0.205 |
| 10.50–11.00 | ambiguous | 0.013 |
| 11.00–14.00 | D major | 0.239 |
| 14.00–15.00 | ambiguous | 0.057 |
| 15.00–15.50 | G major | 0.207 |
| 15.50–17.50 | ambiguous | 0.008 |
| 17.50–18.00 | A major | 0.180 |
| 18.00–19.00 | ambiguous | 0.010 |
| 19.00–20.04 | D major | 0.597 |

Of the 20.04 seconds, **10.54 seconds** receive a triad label, **7.50 seconds**
are ambiguous, and **2.00 seconds** are no-chord. The 20.04-second silent
control stem produces `no_chord` throughout, as recorded in its separate
[timeline](../experiments/chord_recognition/runs/silent_control_20261017/chord_timeline.json).
Only **5.54 seconds** of the labelled span exceed the heuristic 0.5
confidence threshold; **5.00 seconds** are explicitly low-confidence. The
real-stem run completed in **3.23 seconds** on this laptop after library
startup; that is promising for local CPU analysis but not an end-to-end
production benchmark.

The detected labelled chords are Bm, G, D and A. All 10.54 labelled seconds
belong to the shared diatonic triad vocabulary of D major and B natural minor,
but those relative modes are **indistinguishable from this vocabulary alone**.
The [24-key vocabulary comparison](../experiments/chord_recognition/runs/reference_instrumental_20261017/key_comparison.json)
gives D major/B minor 10.54 seconds each, followed by 8.04 seconds for
A major/F# minor and G major/E minor. This does **not** confirm D major or
B minor: 9.5 seconds were withheld, the labelled chords have no human truth,
and the detector could be biased by harmonics, bass or leakage.

## Controlled checks and known failure modes

The automated synthetic tests correctly identify root-position C major,
C-major inversion, A minor and G major, preserve silence, and avoid forcing
ambiguous C–Eb–E–G chroma into a triad. A four-chord C–Am–G–D progression
is identified **4/4** both with moderate and strong synthetic overtones.
These synthetic oscillators with decay are only guitar-like; they are **not**
recorded guitar ground truth. Four 250-ms chords collapse into two 500-ms bins
(observed C, D), demonstrating the short-chord resolution limit. Tests do not
establish accuracy on expressive guitar strums, non-triad voicings or mixes.

The [stress report](../experiments/chord_recognition/runs/reference_instrumental_20261017/stress_analysis.json)
perturbs the *same* real stem without saving or modifying its audio:

| Controlled addition | Changed half-second labels | Changed originally labelled frames |
| --- | ---: | ---: |
| 25% of separated vocal stem | 6/41 | 2/22 |
| D2 bass sine, 0.07 peak | 7/41 | 1/22 |
| Broadband percussive bursts every 0.5 s | 4/41 | 0/22 |

These are **sensitivity measurements**, not accuracy scores or measured
Demucs leakage rates. HPSS reduces transient influence but does not remove
every percussive or guitar attack component. Guitar overtones can strengthen
false pitch classes, while an unrelated bass note can favor the wrong root;
vocal leakage can add melody pitch classes. Chroma's inversion independence
helps with voicings but intentionally discards bass/inversion evidence.
Long 0.5-second pooling and three-frame smoothing can hide genuine fast
changes. Low-confidence and ambiguous regions require human annotation.

## Reproduce (Windows PowerShell)

No models or new packages were installed. From the repository root, use the
existing Python only to execute this experiment. Every command writing an
artifact requires a *new* output path; scripts refuse overwrite.

```powershell
.\.venv\Scripts\python.exe -m experiments.chord_recognition.run_analysis --input backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/instrumental.wav --output experiments/chord_recognition/runs/reference_instrumental_20261017
.\.venv\Scripts\python.exe -m experiments.chord_recognition.rank_keys --timeline experiments/chord_recognition/runs/reference_instrumental_20261017/chord_timeline.json --output experiments/chord_recognition/runs/reference_instrumental_20261017/key_comparison.json
.\.venv\Scripts\python.exe -m experiments.chord_recognition.stress_analysis --instrumental backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/instrumental.wav --vocals backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav --output experiments/chord_recognition/runs/reference_instrumental_20261017/stress_analysis.json
.\.venv\Scripts\python.exe -m experiments.chord_recognition.make_annotation --timeline experiments/chord_recognition/runs/reference_instrumental_20261017/chord_timeline.json --output experiments/chord_recognition/runs/reference_instrumental_20261017/human_review.csv
.\.venv\Scripts\python.exe -m experiments.chord_recognition.flag_confidence --timeline experiments/chord_recognition/runs/reference_instrumental_20261017/chord_timeline.json --output experiments/chord_recognition/runs/reference_instrumental_20261017/confidence_regions.json
.\.venv\Scripts\python.exe -m pytest experiments/chord_recognition -q
```

## Recommendation for 4D-2

**Do not drive the neural harmony planner from these predictions yet.** First,
ask a musician/listener to correct the CSV timeline against the instrumental,
especially 1–2, 5.5–8.5, 10.5–11, and 14–19 seconds. Obtain at least one
independently labelled guitar-accompanied excerpt, including short chords and
non-triad voicings, to measure recall, timing, and false-chord rate. For 4D-2,
consider an offline, reviewable chord map with explicit confidence/unknown
gates before any note selection. A chord map could then constrain harmony
choices, but cannot by itself prove song key or naturalness. No chord-aware
harmony, neural inference, production API, frontend, or environment was changed
in this phase.

Final regression result: **348 Python tests passed in 22.52 seconds**,
including 11 new chord-experiment tests. No test downloaded a model.
