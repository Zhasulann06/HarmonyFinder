# HarmonyFinder

## Neural vocal experiment (Phases 4A / 4B-1, isolated)

[The historical Phase 4A report](docs/neural_vocal_feasibility.md) selected Seed-VC
V1's F0-conditioned singing model. [Phase 4B-1 recovery and validation](docs/neural_vocal_validation.md)
now includes a successful isolated CUDA run with torch 2.4.1. Six-second
Seed-VC +3 and -3 WAVs and a five-way matched-loudness comparison are under
`experiments/neural_vocals/runs/gpu-20261016T214526/`. Measured device-wide
peak was 2,870 MiB; naturalness awaits listening review. The production
backend/frontend and app environment are unchanged.

## Russian / English and Light / Dark (Phase 3E)

Use **RU | EN** and the theme button in the Studio header. Both preferences are
saved independently. On a first visit, browsers whose language starts with `ru`
get Russian; other browsers get English. The light theme uses a muted,
slightly darker lavender-gray palette. Switching language preserves the uploaded
recording, settings, processing, results and playback.

The UI uses bundled i18next/react-i18next catalogs with **185 translation keys per
language**. API identifiers and audio processing are unchanged. Known errors are
localized; original server details remain available under “Technical details”.
See [localization architecture, changed files and verification](docs/localization.md).

## Input modes and vocal Studio integration (Phase 3D)

Studio now offers **Full Song** (Demucs separation) or **Vocals Only**
(prepare the original vocal and a silent instrumental stem), and **Piano Harmony**
(default) or explicitly selected **Vocal Harmony — Experimental**.
Vocal mode uses the original Phase 3B-2 renderer, including its known quality
limitations; the Phase 3B-Q timing compensation candidates are not enabled.
Choose the recording's key for scale-based harmony; no key is assumed or detected.

See [Phase 3D setup, API examples, tests and limitations](docs/studio_modes.md).
Existing clients default to full-song input and piano output. No new dependencies
are required; vocal rendering uses the optional local Rubber Band executable.

## Vocal quality investigation (Phase 3B-Q)

At the time of Phase 3B-Q, the dynamic vocal prototype was excluded from Studio. The user judged
both dynamic outputs bad. The [quality investigation report](docs/vocal_quality_investigation.md)
documents a measured early pitch-automation defect, unverified C-major planning,
note-centre mismatches, and masking risks. It provides controlled, LUFS-matched
listening excerpts and isolated timing/phrase ablations. Lower error metrics
are not a claim of better sound or approval to release vocal mode.

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-quality.txt
.\.venv\Scripts\python.exe -m backend.scripts.investigate_vocal_quality --job backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83 --run backend/data/dynamic_vocal_comparison/20261015T111811Z-283d44a9
```

Each run is saved separately under `backend/data/vocal_quality_investigation/`.
These investigation scripts remain separate from the explicitly experimental Studio mode added in Phase 3D.

HarmonyFinder generates a second musical voice from a song. Phase 3A accepts
short WAV or MP3 recordings, separates vocals from accompaniment, and detects
the vocal melody as a pitch contour and note events, and quantizes notes to
chromatic or scale pitches, generates a timed second voice, and exports MIDI,
piano WAV, and a preview with independently balanced stems. A responsive React studio now
connects the complete workflow. Phase 3D additionally exposes experimental waveform-based vocal harmony.

## Offline vocal pitch prototype (Phase 3B-1)

Phase 3B-2 adds an isolated continuous dynamic vocal prototype using actual
Rubber Band `--pitchmap` support, with separate curve planning and experimental
negative-shift quality comparisons. Phase 3D integrates its unchanged default renderer into the API/Studio. See
[dynamic vocal documentation](docs/dynamic_vocal_harmony.md) for formats,
measurements, quality concerns, and tests. Run a new, non-overwriting comparison:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.compare_dynamic_vocals --job backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83 --key C --scale major
```

Results go into a unique directory under `backend/data/dynamic_vocal_comparison/`.
The reported robotic negative-shift quality is not declared resolved by the
technical checks. Piano remains the default Studio output.

A separate waveform prototype now shifts existing Demucs vocals by a constant
semitone offset using Rubber Band R3 with formant preservation. It has no
render-API or studio integration; Studio vocal mode uses the dynamic renderer instead.
See [vocal prototype documentation](docs/vocal_pitch_prototype.md) for Windows
installation, engine evaluation, licensing, measurements, and limitations.

Generate the original and ±3-semitone comparison from a saved real stem:

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.compare_vocal_pitch --input backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav
```

The three WAVs and `measurements.json` are saved in
`backend/data/vocal_pitch_comparison/`. No Python dependency changes or model
downloads are needed. The optional local Rubber Band utility is GPL licensed;
review distribution obligations before shipping a product with it.

## Smart audio mixer (Phase 3A)

The default preview now uses `instrumental.wav`, `vocals.wav`, and the rendered
`harmony_piano.wav`, summed once with three independent linear amplitude gains:

`mix = instrumental_gain * instrumental + lead_vocal_gain * vocals + harmony_gain * piano`

The React studio's **Find your balance** controls set these backend gains on
the next Generate/Regenerate request. They are distinct from player playback
volume. Changing a gain clears the old result; generate again to apply it.

| Preset | Instrumental gain | Lead vocal gain | Harmony gain |
| --- | ---: | ---: | ---: |
| Harmony Forward (default) | 0.85 | 0.40 | 8.00 |
| Balanced | 0.85 | 0.70 | 4.00 |

All values are amplitude multipliers, not percentages or loudness units.
Instrumental and lead gains accept finite values in 0–2; harmony gain accepts
0–12. The larger piano range accommodates the quiet sampled piano output.
The proposed harmony gain of 1 was evaluated on an existing recording and was
still about 14.6 dB below the reduced lead by RMS. Gain 8 raises that reference
ratio to +3.5 dB. These defaults suit this sample and SoundFont, not every song;
adjust by ear. Silent tracks are never automatically amplified or leveled.

The mixer reuses bounded decoding, stereo conversion, and
[polyphase resampling](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.resample_poly.html).
All tracks start at timestamp zero. Leading silence, original stem duration,
and the piano release tail are retained by padding to the longest track.
There is no alignment estimation, pitch processing, or dynamic compression.
At the native sample rate, waveform polarity and stereo phase are retained.
Resampling uses the existing FIR conversion and can alter the waveform around
transients, but synthetic impulse tests verify the same event timestamps.

No upward normalization is applied. Only when the summed sample peak exceeds
0.98 does the mixer apply a common downward gain of `0.98 / peak` to the whole
mix. This preserves relative gain ratios and prevents sample clipping without
limiter pumping; it can make the entire mix quieter when gains are excessive.
The response and studio display disclose the attenuation. This is sample-peak
protection, not a true-peak limiter or a guarantee against inter-sample peaks.
Piano rendering and its existing safety handling are unchanged.

POST `/api/audio/{audio_id}/render` accepts the new gains:

```powershell
$config = @{ velocity = 90; instrumental_gain = 0.85; lead_vocal_gain = 0.40; harmony_gain = 8.0 } | ConvertTo-Json
$render = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/render" -ContentType 'application/json' -Body $config
$render.mix_diagnostics
```

The existing response fields and download routes are retained. The additive
`mix_diagnostics` field contains mode, input and gained peak/RMS levels, sample
rate, channel count, duration, clipping risk, pre-protection and output levels,
applied gains, `headroom_gain`, and `harmony_to_lead_rms_db`. All diagnostics
refer to decoded/resampled 44100 Hz stereo signals. Gained contribution RMS
uses the common padded output duration. The ratio is null if either RMS is at
or below 1e-6; no infinite dB values are emitted. Contributions are measured
before common protection; multiply their amplitude by `headroom_gain` for
their protected levels. RMS is signal energy, not perceived loudness, and the
ratio is not an active-note loudness measure.

Backward compatibility:

- Explicit `original_gain` and/or `piano_gain` selects **original_legacy** mode:
  the exact existing original-plus-piano mix, with defaults 0.8/0.6 for omitted
  legacy fields. No stems are added and the original lead cannot be isolated.
- An omitted body or `{}` selects stem mixing when both stems exist. With both
  stems absent it uses the old original-plus-piano defaults and reports mode
  **original_fallback** with a warning. A partially missing/corrupt stem set
  fails rather than silently falling back.
- Explicit new gains require both stems. Missing stems return 422 with an
  instruction to separate again. Mixing old and new gain fields returns 422
  to avoid ambiguous behavior. Legacy gains retain their 0–2 bounds.
- MIDI and standalone piano outputs are unchanged by mix gains. Existing
  partial artifact publication and restart limitations remain in place.

### Reproduce the real-audio comparison

From the project root, using the existing saved job (or another directory with
an original upload, both stems, and rendered piano):

```powershell
.\.venv\Scripts\python.exe -m backend.scripts.compare_mixes --job backend/data/audio/fa570cb6-1482-4dd2-8907-3ec2c0cbdf83
```

This offline script writes `previous_mix.wav`, `harmony_forward.wav`,
`balanced.wav`, and `measurements.json` under
`backend/data/mix_comparison/<job_id>/`, leaving source artifacts intact.
It needs no server, model inference, or downloads. `--output` selects another
comparison directory outside the source job.

Measured sample comparison, 20.1500 seconds, 44100 Hz stereo:

| Measure | Previous mix | Harmony Forward |
| --- | ---: | ---: |
| Lead contribution RMS | 0.080873* | 0.040436 |
| Harmony contribution RMS | 0.004536 | 0.060474 |
| Instrumental contribution RMS | 0.071557* | 0.076029 |
| Final sample peak | 0.747620 | 0.796204 |
| Final RMS | 0.112054 | 0.106827 |
| Headroom attenuation | None | None |

\* Previous lead/instrument levels are reference estimates from Demucs stems
scaled by the old original gain; the previous mix actually uses the complete
original recording and Demucs reconstruction is not exact. The new values
are the actual separately summed contributions. The harmony-to-lead reference
ratio increases about 26.6 dB. Neither file has clipped samples, and duration
is unchanged. These measurements do not establish subjective audibility,
distortion, vocal intelligibility, or perceptual quality: listening verification
has not been performed. Play both comparison WAVs at the same device/player
volume and check soft/loud passages, vocal understanding, stereo placement,
transients, and the release tail. Adjust the three gains for your recording.

## React studio — local Windows setup

Install Node.js 24 LTS (Node 22.12+ on the 22.x line is also supported), and
verify `node --version` and `npm --version`. The existing Python environment
and local FluidSynth/SoundFont are reused; do not recreate `.venv`.

In PowerShell window 1, from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app
```

In PowerShell window 2, from the project root:

```powershell
cd frontend
npm ci
npm run dev
```

Open **http://127.0.0.1:5173**. Drop or browse for a WAV/MP3 recording up to
30 seconds and 20 MiB. Choose an interval, direction, key, scale, and
quantization. Diatonic intervals automatically use scale-aware quantization in
the same key. Select **Generate harmony**, follow the six stages, then listen
to Original, Piano harmony, or Preview mix and download MIDI/WAV files.
The key is selected manually. Regeneration starts a new upload and pipeline.

The frontend uses React, TypeScript, Lucide, TanStack Query, and
[Tailwind's Vite integration](https://tailwindcss.com/docs/installation/using-vite).
The [Vite development proxy](https://vite.dev/config/server-options.html#server-proxy)
forwards API requests to port 8000, avoiding cross-origin requests without
changing backend CORS. Optional `frontend/.env.local` settings:

```dotenv
VITE_API_BASE_URL=/api
API_PROXY_TARGET=http://127.0.0.1:8000
```

Restart Vite after changes. `VITE_API_BASE_URL` includes the `/api` prefix and is
public, build-time configuration; never put secrets in frontend variables.
`API_PROXY_TARGET` is the server-side Vite proxy target. For an absolute API URL
on another origin, CORS must be configured separately; it is not enabled by
default. Local `npm run preview` proxies API requests too. No cloud deployment
or production web server is configured in this phase.

Frontend checks, from `frontend`:

```powershell
npm test
npm run typecheck
npm run build
npm run preview
```

See [frontend/README.md](frontend/README.md) for real browser smoke-test commands
and configuration details. Browser checks use installed Edge; automated unit
tests do not download models. The UI contains no mock functionality.

Troubleshooting:

- **Engine offline / cannot reach API:** start FastAPI, verify
  `http://127.0.0.1:8000/api/health`, and check `API_PROXY_TARGET`. If PowerShell
  blocks `npm.ps1`, use `npm.cmd` for the commands above.
- **File rejected:** trim it to 30 seconds, use WAV/MP3 under 20 MiB, and ensure
  it plays normally. Server content validation remains authoritative.
- **Separation failed:** check backend logs, optional Demucs installation, model
  cache, and FFmpeg on the backend process's PATH. The UI polls every two
  seconds and stops after 15 minutes; backend work may continue after timeout
  or closing the page. Individual requests time out after 20 minutes.
- **Piano render failed:** see FluidSynth setup below. If the API confirms MIDI
  was generated, the UI provides its download even when a dependency is missing.
- **Session disappeared / audio unavailable:** restarting FastAPI loses its
  process-local IDs. Generate again. Refreshing the page also resets the studio.
- **Silent piano:** no voiced notes may have been detected. The UI labels empty
  melodies; use a clearer lead vocal. Piano quality depends on the SoundFont.

Keep one API worker and avoid reloading backend code during generation. The
frontend aborts requests on unmount and releases object URLs, but cannot cancel
backend jobs. Uploaded/rendered files follow existing local storage behavior.

## Windows PowerShell setup

Use Python 3.11 and the existing `.venv` from the project root:

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements-dev.txt
```

If activation is blocked, call `.\.venv\Scripts\python.exe` in place of
`python` in the commands below.

Install FFmpeg (including `ffprobe`) and make sure both executables are on
`PATH`. With [winget](https://learn.microsoft.com/windows/package-manager/winget/):

```powershell
winget install --id Gyan.FFmpeg -e
```

Open a new PowerShell window and verify:

```powershell
ffmpeg -version
ffprobe -version
```

WAV upload validation uses Python's built-in WAV reader. FFmpeg and ffprobe
are required to validate and decode MP3 uploads, and FFmpeg is needed by the
Demucs pipeline.

To enable actual separation, install the optional Demucs dependency in the
same environment. This installs PyTorch and may download the `htdemucs` model
on the first separation request:

```powershell
python -m pip install -r .\backend\requirements-demucs.txt
```

The default separator runs the Demucs `htdemucs` model in two-stem vocals
mode on CPU. CPU inference can take several minutes. GPU selection is not
configured in this phase.

## Run the API

From the project root:

```powershell
python -m uvicorn backend.app.main:app --reload
```

The API runs at `http://127.0.0.1:8000`; API documentation is at `/docs`.
Upload files must be actual WAV or MP3 audio, at most 20 MiB and 30 seconds.
Stored files live under `backend/data/audio/` and are excluded from Git. The
server generates a UUID for each upload and does not use uploaded filenames
as storage paths.

## Local smoke test

In a second PowerShell window from the project root, with `sample.wav` or
`sample.mp3` under 30 seconds:

```powershell
$upload = curl.exe -s -F "file=@sample.wav" http://127.0.0.1:8000/api/audio/upload | ConvertFrom-Json
$upload
$audioId = $upload.audio_id
curl.exe -X POST "http://127.0.0.1:8000/api/audio/$audioId/separate"
curl.exe "http://127.0.0.1:8000/api/audio/$audioId/status"
curl.exe -o vocals.wav "http://127.0.0.1:8000/api/audio/$audioId/files/vocals"
curl.exe -o instrumental.wav "http://127.0.0.1:8000/api/audio/$audioId/files/instrumental"
```

Poll status until it is `completed` before downloading. A failed job exposes a
generic error in status; the server log has details. Local background jobs and
their status are held in process memory and **are not durable across server
restarts**. Uploaded files remain on disk, but their IDs are no longer known
to the restarted process. Run one Uvicorn worker for this local workflow.

## Analyze the vocal melody

After the separation status is `completed`, use the same audio ID:

```powershell
$pitch = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/analyze-pitch"
$pitch.notes | Format-Table note_name, start_time, end_time, median_pitch_hz, pitch_deviation_cents
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/audio/$audioId/pitch"
```

POST waits for analysis and returns HTTP 200 with structured JSON. GET returns
the cached result. Repeated POST requests return the cached result; a duplicate
request during analysis receives HTTP 409. Analysis requires completed
separation (409 otherwise); unknown IDs return 404, invalid vocal WAV input
returns 422, and detection/export failures return 500. Failed analysis can be
retried and does not change the separation status. The JSON is also saved
atomically as `backend/data/audio/<audio_id>/pitch_analysis.json`.

The result contains a `frames` array with time in seconds, uncorrected `f0_hz`,
fractional `midi_pitch`, `voiced`, and pYIN `voiced_probability`. Unvoiced frames
have null frequency and MIDI values. A `notes` array contains integer
`midi_note`, `note_name`, median fractional `midi_pitch`, start/end time,
duration, median frequency, and cents deviation from the nearest equal-tempered
note (A4 = 440 Hz). The integer note is a label; it does not retune the audio
or contour. A positive cents deviation means sharp and a negative value means
flat. Note `confidence` is null because pYIN does not supply calibrated pitch
accuracy confidence; the separate `voiced_probability` is the median voicing
probability of the note's voiced frames.

Detection uses [librosa pYIN](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)
with mono audio at 16 kHz, 1024-sample centered windows, a 160-sample hop
(10 ms), and the C2–C6 range (about 65–1047 Hz). Pitch bins have 10-cent
resolution; deviations are estimates, not exact measurements. The service
accepts vocal WAVs of at most 30 seconds, one or two channels, and sample rates
up to 192 kHz. It resamples without changing the time origin. A -60 dBFS gate
rejects silent frames. Segmentation smooths boundaries, bridges dropouts up to
40 ms when adjacent pitches agree, ignores events shorter than 80 ms, and
requires a sustained change of at least 75 cents to split a note. The original
voiced samples are used for all pitch statistics. These choices reduce notes
caused by vibrato but may merge very fast notes or repeated notes separated by
brief silence.

One pitch analysis runs at a time per process, outside the API event loop.
The first call can be slower because Numba compiles pYIN routines. pYIN is a
monophonic estimator: backing vocals, residual instruments, breathy singing,
glides, and pitches outside the configured range can produce missing pitches
or octave errors. It cannot reliably select a lead singer from overlapping
voices. No ML model is downloaded for pitch detection.

## Quantize the detected melody

After pitch analysis, chromatic quantization rounds each note's fractional MIDI
pitch to the nearest integer. A POST with no body defaults to chromatic:

```powershell
$quantized = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/quantize"
$quantized.notes | Format-Table original_note_name, corrected_note_name, correction_cents
```

For scale-aware quantization, send both a tonic key and scale:

```powershell
$config = @{ mode = "scale-aware"; key = "C"; scale = "major" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/quantize" -ContentType "application/json" -Body $config
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/audio/$audioId/quantized"
```

Supported keys are C, C#, D, D#, E, F, F#, G, G#, A, A#, and B. Equivalent
Db, Eb, Gb, Ab, and Bb spellings are accepted and normalized to sharps. Scales
are `major` and `natural_minor` (`minor` is an alias). `scale_aware` is also
accepted as an alias for `scale-aware`. Key and scale are optional and ignored
for chromatic snapping, but supplied values must still be valid. Invalid
parameters return 422, missing pitch analysis returns 409, and unknown IDs
return 404.

The response contains `original_midi_pitch`, `corrected_midi_pitch`, both note
names, and `correction_cents` for each existing note. Correction is
`100 * (corrected - original)`: positive raises pitch, negative lowers it.
Timestamps, durations, and original median frequencies are copied unchanged.
Equally close pitches choose the higher note, including across octave
boundaries. Output pitches are MIDI integers in 0-127; invalid original pitches
outside this range or nonfinite values are rejected. Silence and empty note
lists produce no new notes. Quantization operates on note events, without
altering the original frame contour or audio.

The latest successful output is available through GET `/api/audio/{audio_id}/quantized`
and saved atomically as `backend/data/audio/<audio_id>/quantized_melody.json`.
A new configuration replaces that quantization result. Export errors return
500 and retain any previous result. `pitch_analysis.json` remains unchanged.
The process-local retrieval and restart limitations above still apply.
Scale selection is manual, and snapping does not repair detection mistakes.

## Generate a harmony voice

Harmony requires an existing quantized melody for the same audio ID:

```powershell
$config = @{ interval = "diatonic_third"; direction = "above"; key = "C"; scale = "major" } | ConvertTo-Json
$harmony = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/harmony" -ContentType "application/json" -Body $config
$harmony.notes | Format-Table original_note_name, harmony_note_name, start_time, end_time, duration
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/audio/$audioId/harmony"
```

The interval is required. Direction is `above` (the default) or `below`.
Fixed intervals are `major_third` (4 semitones), `minor_third` (3),
`perfect_fourth` (5), `perfect_fifth` (7), and `octave` (12). Key and scale
are optional for fixed intervals; supplied values must still be valid.

`diatonic_third` moves two scale degrees and `diatonic_sixth` moves five,
in the selected direction. Both require an explicit key and scale with the
same 12 tonic classes and major/natural minor options as quantization. For
example, C major thirds above C4, D4, E4 are E4, F4, G4; A natural minor
thirds above A3, B3, C4 are C4, D4, E4. Octave boundaries are handled in both
directions.

Source notes must already belong to the selected scale for diatonic intervals.
An out-of-scale note returns 422 with its index and name; the engine never
quantizes source notes again. Invalid configuration, source/output MIDI outside
0-127, and invalid/overlapping source timing also return 422. Missing
quantization or harmony returns 409; unknown IDs return 404. There is no octave
folding or automatic key selection.

The response includes `original_midi_note`, `harmony_midi_note`, both names,
and unchanged `start_time`, `end_time`, and `duration`. Here "original" means
the quantized melody's `corrected_midi_pitch`. Naming uses sharps consistently
with MIDI 60 = C4: the minor third above C4 is D#4, equivalent to Eb4. Existing
gaps and empty sequences are preserved without adding notes. This phase
produces JSON note events consumed by the rendering step below.

POST returns HTTP 200 and atomically saves the latest successful result in
`backend/data/audio/<audio_id>/harmony_melody.json`; GET retrieves that result.
Validation/export failures retain any previous harmony result; export errors
return 500. Pitch analysis, quantization, and audio files remain unchanged.
Successfully quantizing again invalidates the API's cached harmony, so regenerate
it for the new melody. The previous disk export remains a snapshot until the
next successful harmony generation. Restart limitations above still apply.
Simple interval harmonies do not account for chords, voice leading, or vocal
range, and inherit any source melody detection mistakes.

## FluidSynth and piano SoundFont setup on Windows 11

The API automatically uses these local files when they are present:

```text
tools/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe
assets/soundfonts/FluidR3 GM2-2.SF2
```

Both paths are anchored to the project root derived from the configuration
module, so detection does not depend on the shell's current directory. With
this local installation, no environment variables are needed. From the project
root, verify FluidSynth and start the API:

```powershell
& .\tools\fluidsynth-v2.6.1-win10-x64-cpp11\bin\fluidsynth.exe --version
Test-Path '.\assets\soundfonts\FluidR3 GM2-2.SF2'
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload
```

Nonempty `HARMONYFINDER_FLUIDSYNTH` and `HARMONYFINDER_SOUNDFONT` environment
variables override these defaults. Relative override paths are also resolved
against the project root; absolute paths work unchanged. A bare executable
name such as `fluidsynth` uses `PATH`. Without an override, if the local
executable is absent the renderer falls back to system-wide `fluidsynth` on
`PATH`. Invalid overrides report an error rather than silently using another
installation. Missing executable/SoundFont behavior still preserves the MIDI
download. SoundFont paths containing spaces work without adding quote characters
to the environment value: subprocess arguments are passed as a list, with all
CLI options preceding the positional SoundFont and MIDI paths.

MIDI export uses `pretty_midi`, installed with the backend requirements.
Piano rendering uses the separate [FluidSynth command-line program](https://github.com/FluidSynth/fluidsynth/releases),
not a Python sine-wave synthesizer. Download a Windows x64 binary ZIP from the
official release assets, extract the complete archive to a folder you control,
and keep the included DLLs alongside the executable. Locate `fluidsynth.exe`
inside the extracted folder; the exact archive/folder name depends on the
release. To override the local default with a different installation, configure
its full path in PowerShell, adjusting the example path:

```powershell
$env:HARMONYFINDER_FLUIDSYNTH = "C:\Tools\FluidSynth\bin\fluidsynth.exe"
& $env:HARMONYFINDER_FLUIDSYNTH --version
```

Alternatively, add the directory containing that executable and its DLLs to
`PATH`. This project does not install FluidSynth automatically and does not
need `pyfluidsynth` or an audio device for offline file rendering.

Provide a SoundFont `.sf2` you own or are licensed to use. It must contain an
actual piano preset at General MIDI bank 0, program 0. The downloaded local
SoundFont above is used as provided; the application does not download additional
SoundFonts. If redistributing a SoundFont, check its license and retain the
required attribution/license files. To use another font, configure a path:

```powershell
$env:HARMONYFINDER_SOUNDFONT = "C:\SoundFonts\MyLicensedPiano.sf2"
Test-Path $env:HARMONYFINDER_SOUNDFONT
.\.venv\Scripts\Activate.ps1
python -m pip install -r .\backend\requirements-dev.txt
python -m uvicorn backend.app.main:app --reload
```

Set these variables in the shell used to start Uvicorn and restart the API
after changing them. They apply to the current shell session; existing job IDs
are not restored after that restart, so repeat upload/analysis as needed.
SoundFonts are ignored by Git.

## Render and download MIDI, piano, and preview

After generating harmony for `$audioId`:

```powershell
$config = @{ velocity = 90; instrumental_gain = 0.85; lead_vocal_gain = 0.40; harmony_gain = 8.0 } | ConvertTo-Json
$render = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/audio/$audioId/render" -ContentType "application/json" -Body $config
$render
curl.exe --fail -o harmony.mid "http://127.0.0.1:8000/api/audio/$audioId/files/harmony.mid"
curl.exe --fail -o harmony_piano.wav "http://127.0.0.1:8000/api/audio/$audioId/files/harmony_piano.wav"
curl.exe --fail -o preview_mix.wav "http://127.0.0.1:8000/api/audio/$audioId/files/preview_mix.wav"
```

POST waits for rendering and returns 200 with download URLs, sample rate,
channels, and preview duration. Omitting the body uses the defaults above.
Velocity must be an integer in 1-127 (0 means note-off); gains must be finite
values in 0-2 for instrumental/lead and 0-12 for harmony. Legacy gain handling
is documented above. Invalid configuration or harmony JSON returns 422, missing
harmony returns 409, and unknown IDs return 404. Only one render runs at a time
per process, outside the event loop. Duplicate rendering or changing harmony/
quantization while rendering returns 409.

The MIDI is generated directly from `harmony_melody.json` with piano program 0,
velocity 90 by default, and absolute note times. No harmony rules are rerun.
Export is deterministic for identical input and velocity. MIDI times have
1/44100-second tick resolution (rounding by at most half a tick). Leading,
inter-note, and trailing rests are retained. All MIDI pitches 0-127 are supported;
invalid pitches, overlapping events, and zero-length notes are rejected.

FluidSynth renders with sample-clock timing to a floating-point WAV before
peak reduction and conversion to 44100 Hz stereo PCM16. Reverb and chorus are
disabled. A 0.75-second release tail follows the last note; the piano is padded
through the melody's full duration when that is longer. The tail ends with a
20 ms fade. Empty melodies produce a valid note-free MIDI and silent piano WAV
without requiring FluidSynth or a SoundFont.

The default preview mixes the instrumental stem, lead stem, and generated piano
once each. Legacy requests instead mix the original uploaded song once with
the piano. All tracks start at zero without trimming leading silence. Mono inputs
are duplicated to stereo; other multichannel inputs are downmixed, and sample
rates are converted to 44100 Hz. Original MP3 uses libsndfile decoding, with
FFmpeg fallback if unavailable. Original and generated audio are zero-padded
to the longer duration so the release tail is retained. Piano and preview use
whole-file peak reduction only when necessary to keep peaks below 0.98; gains
therefore control the balance rather than guaranteeing absolute loudness.
Original audio and all pitch/quantization/harmony JSON files remain unchanged.

Each validated artifact is published independently. MIDI remains downloadable
if piano synthesis fails; MIDI and piano remain downloadable if preview
mixing fails. A new render hides previous WAVs until they have been rendered
again successfully. Regenerating harmony or quantization invalidates download
availability for old renders. Old files may remain as disk snapshots, but
unavailable/stale downloads return 409. All artifacts are under
`backend/data/audio/<audio_id>/` and share the existing restart limitations.

## Rendering troubleshooting

- **503, SoundFont missing:** Set `HARMONYFINDER_SOUNDFONT` to an existing
  `.sf2` file and restart. The error includes the MIDI download URL.
- **503, FluidSynth missing:** Check the executable path with `Test-Path`, run
  `--version`, and set `HARMONYFINDER_FLUIDSYNTH` or update `PATH`.
- **500, synthesis failed:** Check the server log for the underlying exception,
  keep the release's DLLs with its executable, and confirm the SoundFont has
  a bank 0/program 0 piano preset. A corrupt or unsupported SoundFont can fail
  even if the path exists. Rendering has a 120-second synthesizer timeout.
- **503, MP3 decoder missing:** Install FFmpeg using the setup above and ensure
  `ffmpeg.exe` is on `PATH`. Completed MIDI/piano files remain downloadable.
- **409:** Complete the preceding harmony step or rerender after changing the
  melody. Restarted servers need a new upload workflow.
- **Unexpected piano sound:** Program 0's samples come from your SoundFont.
  Use a piano/GM bank with the intended preset. Very high/low MIDI pitches may
  be quiet or unnatural depending on the SoundFont. This project does not
  evaluate SoundFont quality or implement pedal/expressive performance.

## Tests

```powershell
python -m pytest .\backend\tests
```

Tests use a mock separator and synthetic tones, silence, detuned notes, and
vibrato to test real pYIN detection. Rendering tests validate real MIDI files
and mock the external synthesizer; they do not require FluidSynth, a SoundFont,
or model downloads.

