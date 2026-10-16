# Phase 4A — neural vocal harmony feasibility and isolated prototype

## Decision and actual outcome

**Recommend a local trial of Seed-VC V1's F0-conditioned 44.1 kHz singing model.**
Its code exposes the required pitch-conditioning path and it does not require
a trained model of this singer. This is a recommendation for an experiment,
not evidence that it improves this recording or that it fits this laptop.
The prior listening feedback, including robotic timing-compensated outputs,
remains the quality baseline.

**Neural +3 / -3 WAVs were not generated.** Both large transfers failed with read
timeouts. The isolated environment exists but still contains only pip/setuptools.
No neural models loaded, no GPU inference ran, and no neural peak VRAM,
processing time, pitch accuracy, naturalness or intelligibility was measured.
The prepared A/B comparison and additional Rubber Band -3 reference are real WAVs.
The offline runner and numerical F0 adapter are implementation prototypes whose
neural integration is not yet runtime-validated. All application code is unchanged.

Machine-readable findings: `experiments/neural_vocals/feasibility.json`.
Pinned model metadata, bytes and LFS hashes:
`experiments/neural_vocals/asset_manifest.json`.

## Inspected project and hardware

Reviewed `dynamic_vocal.py`, `harmony_curve.py`, `vocal_pitch.py`, the vocal-only
`preparation.py`, the existing stem mixer, earlier comparison scripts and stored
Phase 3B-2 / 3B-Q curves, reports and WAVs. The current pipeline applies relative
intervals to the waveform, retains source detuning, smooths control and masks
outside detected note events. Its documented pitch-command timing and consonant
risks remain relevant even when the replacement synthesizer is neural.

Actual local inspection:

| Item | Observed value |
| --- | --- |
| OS | Windows, build 26200; Python identifies NT version 10.0 |
| Python | Existing app environment: 3.11.5, 64-bit |
| NVIDIA GPU | GeForce RTX 3050 Laptop GPU |
| Physical VRAM | 4,096 MiB |
| Free VRAM reported by `nvidia-smi` | 3,888 MiB at inspection; usage changes over time |
| Reported used VRAM / driver | 75 MiB / 610.62 |
| Physical RAM / available | 16,931,676,160 / 3,295,166,464 bytes (80% loaded) |
| Disk free | 83,006,668,800 bytes at inspection |
| App PyTorch | 2.14.1+cpu; `torch.version.cuda=None`; CUDA unavailable to this environment |
| App torchaudio | Not installed |

Driver-reported free VRAM and allocated PyTorch memory are different measures.
No inference peak can be inferred from these idle readings. A CUDA-enabled
separate environment is required; changing the app's CPU torch is unnecessary.
The existing app `.venv` was not modified.

No official 4 GB minimum/guarantee for the complete Seed singing pipeline was
found in the inspected upstream documentation. Weights alone are not the peak:
the content encoder, pitch extractor, speaker encoder, diffusion activations and
vocoder also need memory. The 25M real-time speech model's performance numbers
do not establish the 200M singing model's VRAM requirements. Starting with a
5–6 second source/reference, batch one and FP16 is an experimental strategy,
not a verified fit. More available system RAM would reduce load-time pressure.

## Candidate comparison — official documentation and code

| Candidate | Actual F0 control | Same singer / training | Windows / 4 GB | Decision |
| --- | --- | --- | --- | --- |
| Seed-VC V1 singing (200M, 44.1 kHz) | CLI accepts integer semitone shift, including ±3/±4. Internal F0 tensor varies over frames. External contour needs an adapter. | Use a reference from the same singer; no mandatory fine-tuning. Similarity is not guaranteed. | Windows documented; upstream suggests Python 3.10. This machine has 3.11.5. Singing fit on 4 GB unverified. | Best initial trial for preserving the current singer without a training dataset. |
| DDSP-SVC current reflow workflow | Explicit F0 tensor supplied to synthesizer. CLI `-k` is scalar; external contour adapter needed. | Usually requires training/fine-tuning for the target singer. Demo voices are other singers. | README explicitly reports Python 3.11 on Windows; lower hardware use is claimed, but no validated 4 GB guarantee for this job. | Useful if a suitable singer dataset and checkpoint become available. |
| RVC | Current synthesizer consumes coarse and continuous pitch tensors. Inspected CLI/pipeline computes scalar-shifted F0; external control requires version-specific integration. | Target-singer checkpoint/index normally required; current audio alone is not such a model. | Windows packages/instructions exist; inspected current branch targets Python 3.12. Exact memory unbenchmarked. | Secondary option if the user can supply/train a suitable voice model. |
| Standalone BigVGAN / NSF-HiFiGAN | A vocoder is not a waveform-to-target-F0 harmonizer by itself. It needs appropriate acoustic conditioning upstream. | Does not solve arbitrary same-singer content-to-mel generation alone. | Varies by model. | Not a drop-in alternative. |

Seed's official [model table and Windows setup](https://github.com/Plachtaa/seed-vc/blob/51383efd921027683c89e5348211d93ff12ac2a8/README.md)
distinguish the singing model from the smaller speech models. The repository is
archived, so this experiment pins its source revision rather than tracking main.
The official [DDSP workflow](https://github.com/yxlllc/DDSP-SVC/tree/88f157c03dfea4855e9b7101897bac174fd9b53d)
includes target-model training. Its newer 6.3/reflow model format is not compatible
with older demo checkpoints; an old release is not automatically a current-model
smoke test. The inspected [RVC project](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI)
also has a target-voice training workflow; its public encoder/pretraining assets
do not constitute the user's trained voice.

## Dynamic target F0: what is and is not supported

In the pinned Seed [inference code](https://github.com/Plachtaa/seed-vc/blob/51383efd921027683c89e5348211d93ff12ac2a8/inference.py),
the source F0 is multiplied by `2**(semitones/12)` and passed into the length
regulator. Automatic median pitch adjustment can be disabled. There is no stock
`--target-f0` input flag. Our runner uses the unmodified official fixed-shift path
for the planned ±3 trials, with the user's separate reference excerpt.

The [length regulator](https://github.com/Plachtaa/seed-vc/blob/51383efd921027683c89e5348211d93ff12ac2a8/modules/length_regulator.py)
accepts a sequence, quantizes F0 to bins and interpolates conditioning to the
mel frame grid. This makes time-varying target F0 architecturally possible;
conditioning is not a guarantee of exact acoustic pitch. The native RMVPE grid
is 10 ms, while the singing mel grid is 512/44100 ≈11.61 ms. Control alignment
and voiced/unvoiced behavior must be verified acoustically.

`control.py` implements the numeric contract `target[i] = source_f0[i] *
2**(shift[i]/12)` with an optional time-varying map. It preserves unvoiced zeros,
rejects invalid data and rejects voiced targets outside the evaluated 50–1100 Hz
conditioning range. Tests cover ±3, ±4 and changing signs within one contour.
The optional runner callback replaces only the source F0 extraction result;
the reference is untouched. That callback has not been run with actual weights.
It is a control-feasibility probe, not an implemented note-level harmony system.
There is no automatic key/chord detection or harmony planning in this experiment.

DDSP's [reflow inference](https://github.com/yxlllc/DDSP-SVC/blob/88f157c03dfea4855e9b7101897bac174fd9b53d/main_reflow.py)
likewise passes segment F0 tensors into its model after scalar transposition.
Its default F0 path interpolates unvoiced regions; blindly substituting a curve
would need separate consonant/mask validation. Current [RVC pitch code](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI/blob/81eed5e8f68b6bed1789f682fe78cdd324495afc/infer/vc/pipeline.py)
exposes both coarse and continuous F0 internally but does not provide an external
F0-file argument in the inspected pipeline signature. We do not assume old
community interfaces are available in the current version.

## Verified downloads and licences

Sizes below come from official Hugging Face tree/GitHub release metadata and a
PyTorch wheel HEAD response, checked on 2026-10-15. GB means decimal bytes.
Download sizes and resource requirements were reported in chat before large
downloads were attempted. Only public asset GETs were used; no user audio was uploaded.

| Selected Seed component | Exact bytes | Host licence metadata |
| --- | ---: | --- |
| F0 singing checkpoint, ft_ema_v2 | 820,865,494 | GPL-3.0 |
| BigVGAN 44.1k / 128band / 512x generator only | 489,041,291 | MIT |
| Whisper-small `model.safetensors` | 966,995,080 | Apache-2.0 on inspected HF repository |
| RMVPE `rmvpe.pt` from the upstream-selected RVC host | 181,184,272 | MIT on that host repository |
| CAMPPlus `campplus_cn_common.bin` | 28,036,335 | Apache-2.0 |
| **Five weight files** | **2,486,122,472** | Component-specific terms |
| Configs/cards/licence files plus weights | **2,486,344,604** | Pinned manifest records revisions |
| CUDA torch 2.4.0 Windows cp311 wheel | **2,441,950,418** | Framework terms; dependencies additional |

Checkpoint locations and licence declarations:
[Seed](https://huggingface.co/Plachta/Seed-VC),
[BigVGAN](https://huggingface.co/nvidia/bigvgan_v2_44khz_128band_512x),
[Whisper](https://huggingface.co/openai/whisper-small),
[RMVPE host](https://huggingface.co/lj1995/VoiceConversionWebUI),
[CAMPPlus](https://huggingface.co/funasr/campplus).
The empty Seed/RMVPE model cards give limited provenance information beyond
repository metadata; retain this limitation when assessing distribution.

The initial upstream source archive was 49,003,480 bytes; the final downloader
can fetch only 82 code/config/licence files totaling 768,696 bytes, excluding
sample audio. Their Git blob hashes are verified. Only one Whisper weights
format and the BigVGAN generator are needed: discriminator/optimizer files and
alternate checkpoint versions would waste multiple GB. Allow roughly 12–15 GB
disk space for this experiment, unpacked CUDA libraries and download caches;
that is a planning budget, not measured installation size. The full dependency
transfer was not completed, so no exact transitive total is claimed.

The initial source archive also included upstream-bundled CAMPPlus weights
(28,036,335 bytes), two ONNX utility models (1,157,965 and 224,860 bytes), and a
demo video. These remain in ignored `vendor/`; none was executed. Thus some
pretrained bytes are present even though no complete selected-model set exists
in the runner's allowlisted `assets/` locations. The final source-only downloader
omits these binaries and fetches the verified code/config/licence subset.

Other candidate asset facts (not downloaded):

- DDSP's linked `model_0.pt` is 236,346,125 bytes; release 5.0's different
  `model_0.pt` is 67,878,441 bytes. Neither proves compatibility with the current
  reflow configuration or represents the user's voice.
- DDSP-linked HuBERT-soft: 378,435,957 bytes; linked RMVPE ZIP: 340,638,958 bytes;
  linked NSF-HiFiGAN ZIP: 52,814,405 bytes. Encoder/vocoder/pitch assets are
  additional to a compatible trained singer model and its training dataset.
- DDSP dependencies include fairseq, pyworld and parselmouth; Windows native
  builds/version resolution add complexity. Their full install size was not
  measured. RVC's downloaded package total likewise was not measured.

Seed code is [GPL-3.0](https://github.com/Plachtaa/seed-vc/blob/51383efd921027683c89e5348211d93ff12ac2a8/LICENSE),
and the selected Seed checkpoint host declares GPL-3.0. Distribution requires
review of those terms and bundled component notices; a subprocess or separate
environment is not a blanket exemption. The experiment does not change this
project's licence. DDSP and RVC code are MIT, but code licences alone do not
clear every downloaded weight or dataset. In particular, the DDSP-linked
[NSF-HiFiGAN release explicitly declares CC BY-NC-SA 4.0 for its weights](https://github.com/openvpi/vocoders/releases/tag/nsf-hifigan-44.1k-hop512-128bin-2024.02).
That noncommercial restriction matters for product distribution/use. A target
singer model also needs appropriate recording/dataset rights. No new production
redistribution decision has been made.

## Actual experiment and measurements

Run: `experiments/neural_vocals/runs/20261015T182215Z-ddacdb38/`.
Source is the existing job `fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav`.
The 20.04-second Demucs stem is not a studio-clean ground truth recording;
leakage or reverb may remain. Seconds 7–13 provide a 6-second, mostly voiced
excerpt (495/600 voiced pYIN frames). Seconds 13.2–19.2 are the disjoint reference
from the same singer. The source file's SHA-256 was unchanged after preparation.

To avoid a stereo-versus-mono comparison confound, all inference inputs and
listening tracks are mono at the original 44.1 kHz. A native stereo excerpt is
also saved. Original full-length audio and all earlier comparisons are untouched.
Rubber Band uses the existing constant-shift implementation unchanged.

| Trial | Frames / duration | RMS | Peak | Processing time | pYIN median shift / p90 absolute offset error |
| --- | --- | ---: | ---: | ---: | --- |
| A original mono excerpt | 264,600 / 6.000 s | 0.124470 | 0.784088 | N/A | Reference |
| B Rubber Band +3 | 264,600 / 6.000 s | 0.117303 | 0.645073 | 0.7545 s | +3.0 semitones / 10 cents; 490 matched frames |
| C neural +3 | **Not generated** | — | — | — | — |
| D neural -3 | **Not generated** | — | — | — | — |
| E extra Rubber Band -3 reference | 264,600 / 6.000 s | 0.127977 | 0.790158 | 0.7546 s | -3.0 semitones / 10 cents; 493 matched frames |

Both DSP outputs have zero measured coarse energy-envelope lag (10 ms grid),
finite samples and no sample clipping. These measures do not validate syllable
timing or intelligibility. pYIN measures all shared voiced frames; it is an
imperfect detector, not a reference transcription. The historical constant
shifter's CLI clipping limitations remain unchanged; this baseline is not a
new processing preset.

Listening files are in `listening-4fde07c0/`: `A_original.wav`,
`B_rubberband_plus_3.wav`, `E_rubberband_minus_3.wav`, with `measurements.json`.
All three are BS.1770 matched to -23 LUFS, mono 44.1 kHz PCM24, with identical
5 ms endpoint fades and a shared maximum-peak safeguard (no extra reduction
was needed). Native/raw exports are retained separately. These new excerpts
have no new user listening verdict.

For future neural output, comparison exports disclose native frame differences
and permit only ≤50 ms of end padding/cropping for grid rounding. There is no
time stretch or automatic content shift. Native output remains intact. A
larger mismatch fails comparison preparation for manual inspection.

### Actual failures and recovery path

1. Initial Seed HTTPS download raised a read timeout after **199,229,440 bytes**.
   That `.partial` file remains isolated and is never loaded as a checkpoint.
2. CUDA torch pip transfer timed out from `download-r2.pytorch.org`; pip reported
   approximately 422.7 kB/s and a >90 minute remaining estimate. No neural
   packages were installed. This is a transfer failure, not an out-of-VRAM result.
3. A bounded range probe subsequently read 8 MiB successfully in 10.79 seconds.
   The downloader now resumes exact HTTP ranges with size/LFS-hash verification
   and a wall-clock budget. It does not imply all remaining multi-GB transfers
   have completed or that throughput will persist.
4. A runner preflight using the separate Python correctly failed on missing
   `numpy`; `prerequisite_failure-*.json` records the dependency stage and
   `models_loaded=false`. No failed inference was disguised as a neural WAV.

All download processes from these attempts have exited. No background neural
inference or model transfer is left running. The source archive and unverified
partial checkpoint are retained in the ignored experiment assets folder.

## Reproduction and next steps (Windows PowerShell)

The source snapshot, output folders and `.venv` below are isolated. The app
environment is used only for existing baseline analysis; never install these
ML dependencies into it. Source was pinned to
`51383efd921027683c89e5348211d93ff12ac2a8`. Official requirements mix nightly and
fixed torch entries; the experiment specifies a single 2.4.0 CUDA stack instead.
The reduced requirements are source-inspected, **not installation/inference
validated**; additional version fixes may be needed once the downloads complete.

```powershell
# From the HarmonyFinder root. This separate environment already exists locally.
if (-not (Test-Path 'experiments/neural_vocals/.venv/Scripts/python.exe')) {
    .\.venv\Scripts\python.exe -m venv experiments/neural_vocals/.venv
}
# Show pinned download sizes without model transfer:
.\.venv\Scripts\python.exe experiments/neural_vocals/download_assets.py
# Resume model files; timeout leaves partial data for the next invocation:
.\.venv\Scripts\python.exe experiments/neural_vocals/download_assets.py --download --max-seconds 900
if ($LASTEXITCODE -ne 0) { throw 'Assets incomplete; rerun the resumable downloader before inference' }
# Source-only recovery is also available with --download --source-only.

.\experiments\neural_vocals\.venv\Scripts\python.exe -m pip install --timeout 120 torch==2.4.0 torchaudio==2.4.0 --index-url https://download.pytorch.org/whl/cu121
if ($LASTEXITCODE -ne 0) { throw 'CUDA dependency download failed; do not proceed or alter the app environment' }
.\experiments\neural_vocals\.venv\Scripts\python.exe -m pip install -r experiments/neural_vocals/requirements.txt
if ($LASTEXITCODE -ne 0) { throw 'Experiment dependencies failed; inspect output' }
.\experiments\neural_vocals\.venv\Scripts\python.exe -m pip check

# Creates a NEW run; never overwrites the source or an earlier run:
.\.venv\Scripts\python.exe -m experiments.neural_vocals.compare --source backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav --start 7 --duration 6 --reference-start 13.2
# Substitute the printed new directory below:
$run = 'experiments/neural_vocals/runs/NEW_RUN_DIRECTORY'
.\experiments\neural_vocals\.venv\Scripts\python.exe experiments/neural_vocals/seed_runner.py --run $run --steps 30
if ($LASTEXITCODE -ne 0) { throw 'Neural trial failed; retain its report and inspect before retrying in a new run' }
.\.venv\Scripts\python.exe -m experiments.neural_vocals.compare --assess $run
```

The runner routes model loading to the local allowlisted assets with Hugging Face
offline mode, disabled telemetry, and CUDA kernel compilation disabled. It records
model-load/end-to-end times and `max_memory_allocated/reserved` if it gets that far;
these exclude some driver/process memory, so also sample `nvidia-smi` during a run.
It uses 30 diffusion steps, fixed random seed, `length_adjust=1`, and no automatic
reference-pitch adjustment. Source/reference never leave the machine.

After successful C/D generation, user listening is the next gate: assess
naturalness, lyric intelligibility, singer identity, consonants, warble/metallic
artifacts and timing against the matched A/B/E tracks. No perceptual metric here
substitutes for that review. If fixed shifts pass, an isolated known 3↔4 and
-3↔-4 control probe should test F0 transitions before connecting actual note
events. If 4 GB fails, record the OOM/peak and assess explicit offloading or a
larger local GPU separately; do not claim a 4 GB solution without measurement.

## Files and tests

Created `experiments/neural_vocals/{download_assets.py,asset_manifest.json,
control.py,seed_runner.py,compare.py,requirements.txt,feasibility.json,
test_control.py,test_downloads.py}`, plus this report. Updated `.gitignore`
for isolated assets/environments/runs and added a README link. Downloaded source
is retained with its upstream licence under ignored `vendor/`.

Final command:

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests experiments/neural_vocals/test_control.py experiments/neural_vocals/test_downloads.py -q
```

**321 passed, no skips, 25.54 seconds**: 303 existing backend tests and 18
experiment tests. Tests verify fixed/dynamic numeric F0 and silence handling,
range resume correctness, hash rejection, deadlines and preservation of existing
files; they never download neural checkpoints. The actual CUDA/model downloads
and runner preflight failed as recorded above. There is no neural audio-quality
test result. Frontend checks were not rerun because no frontend files changed.

Stopped at Phase 4A; production API, React, piano renderer, vocal renderer,
harmony algorithms, stem mixer and existing audio files were preserved.
