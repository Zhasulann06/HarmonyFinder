# Phase 3D: input modes and experimental vocal output

## Run locally (Windows PowerShell)

From the project root, use the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm.cmd run dev
```

Open http://127.0.0.1:5173. Select a WAV/MP3 of at most 20 MiB and 30 seconds.
Select an input mode, output mode, interval and direction. For diatonic or
scale-aware processing, explicitly select the recording's key and scale.
There is no automatic key detection; a fixed interval with chromatic quantization
does not need a key. Generate runs all six backend stages.

| Input | Preprocessing when `/separate` is called |
| --- | --- |
| `full_song` (default) | Existing CPU Demucs two-stem separation |
| `vocals_only` | Decode original; write `vocals.wav` and matching all-zero `instrumental.wav` |

Vocal preparation preserves decoded samples, native sample rate, channel count,
leading silence and frame count. It accepts mono/stereo, 8–192 kHz. Stems use
float WAV to avoid unnecessary quantization; the uploaded original is untouched.
MP3 still requires FFmpeg/ffprobe for existing upload validation. If libsndfile
cannot decode it, preparation uses FFmpeg without forcing a rate/channel conversion.
No audio classification is performed. Upload creates a queued job; `/separate`
starts preparation or separation and status progresses processing → completed/failed.
Repeated preprocessing requests return 409. Pitch analysis uses the completed stem.

| Output | Published files |
| --- | --- |
| `piano` (default) | `harmony.mid`, `harmony_piano.wav`, `preview_mix.wav` |
| `vocal` (explicit, experimental) | `harmony_vocals.wav`, `preview_mix.wav` |

Vocal output passes the existing pitch analysis, quantization and harmony to
`build_harmony_curve` and `DynamicVocalRenderer`, using its existing default
`formant_stereo` preset. It keeps the vocal stem's rate, channels and frame count.
There is no new time compensation, preset tuning, key inference or algorithm change.
No MIDI or FluidSynth is invoked for this mode. Diatonic vocal rendering requires
scale-aware quantization with exactly the same normalized key and scale as the harmony.

Both outputs use the existing stem mixer: instrumental + original lead + generated
harmony, each exactly once. Preview WAV is always 44.1 kHz stereo. Conversion keeps
timestamp zero, pads to the longest stem and uses common downward sample-peak
protection at 0.98. Vocal output adds no release tail. Piano retains its existing tail.
The response's `sample_rate`, `channels` and `duration_seconds` describe the preview;
the standalone vocal WAV can have a different native rate/channel count.

Studio defaults to the existing Piano Harmony Forward preset (0.85/0.40/8.0).
Selecting vocal switches to a lower Balanced preset (0.85/0.70/0.60); its Harmony
Forward preset is 0.85/0.40/1.0. Switching back restores piano defaults. All three
sliders remain adjustable. Instrumental gain has no audible effect on vocals-only
input because its instrumental stem is silent. No automatic loudness matching occurs.

## API changes and compatibility

- `POST /api/audio/upload`: optional multipart **form field** `input_mode`,
  `full_song` or `vocals_only`. Omission preserves full-song behavior. The upload
  response adds `input_mode`; existing ID/status/duration fields remain unchanged.
- `POST /api/audio/{id}/render`: optional JSON `output_mode`, `piano` or `vocal`.
  Omission preserves piano behavior, including partial MIDI availability on a
  FluidSynth/SoundFont failure and historical original/piano gain semantics.
- Render response adds `output_mode` and nullable `warning`. `files` contains
  only files published by the current attempt; Studio uses it for downloads.
- `GET /api/audio/{id}/files/harmony_vocals.wav` is now allowed. Other download
  endpoints retain their paths. Rendering again or changing upstream melody data
  invalidates previous downloads, even when old bytes remain on disk.
- Vocal mode requires completed preprocessing, pitch analysis, quantization and
  harmony. Missing prerequisites return 409; invalid modes, incompatible scale
  configuration or legacy gains with vocal mode return 422. Missing Rubber Band
  returns actionable 503; a DSP failure returns 500 and is logged.
- `velocity` is retained for backward compatibility but has no effect on vocal
  rendering. Vocal mode uses `instrumental_gain`, `lead_vocal_gain`, `harmony_gain`;
  it rejects `original_gain` and `piano_gain`. Its omitted harmony gain is 0.6;
  omitted lead/instrumental gains retain API defaults 0.40/0.85.
- Rendering is serialized by the existing semaphore; duplicate rendering and
  quantization/harmony changes while rendering return 409.

Example using a fixed minor third, without guessing the song key:

```powershell
$base = 'http://127.0.0.1:8000/api/audio'
$audioPath = 'C:\Music\my vocals.wav'
$upload = curl.exe --fail-with-body -sS -F "file=@$audioPath" -F 'input_mode=vocals_only' "$base/upload" | ConvertFrom-Json
$id = $upload.audio_id
Invoke-RestMethod -Method Post "$base/$id/separate"
$deadline = (Get-Date).AddMinutes(15)
do {
    Start-Sleep -Milliseconds 500
    $status = Invoke-RestMethod "$base/$id/status"
    if ((Get-Date) -gt $deadline) { throw 'Preprocessing timed out; inspect server logs' }
} while ($status.status -in @('queued', 'processing'))
if ($status.status -ne 'completed') { throw $status.error }
Invoke-RestMethod -Method Post "$base/$id/analyze-pitch" | Out-Null
Invoke-RestMethod -Method Post "$base/$id/quantize" -ContentType 'application/json' -Body '{"mode":"chromatic"}' | Out-Null
Invoke-RestMethod -Method Post "$base/$id/harmony" -ContentType 'application/json' -Body '{"interval":"minor_third","direction":"above"}' | Out-Null
$render = Invoke-RestMethod -Method Post "$base/$id/render" -ContentType 'application/json' -Body '{"output_mode":"vocal","instrumental_gain":0.85,"lead_vocal_gain":0.7,"harmony_gain":0.6}'
Invoke-WebRequest "$base/$id/files/harmony_vocals.wav" -OutFile harmony_vocals.wav
Invoke-WebRequest "$base/$id/files/preview_mix.wav" -OutFile preview_mix.wav
```

For full-song input use `input_mode=full_song`. For piano render with
`{"output_mode":"piano"}`; use the returned file list to download piano/MIDI.
For a diatonic interval, explicitly set the known key/scale identically in
scale-aware quantization and harmony requests. Above and Below both work.

## Optional executables and limitations

Piano uses the existing local FluidSynth/SoundFont configuration. Vocal mode
automatically locates the existing
`tools/rubberband-4.0.0/rubberband-4.0.0-gpl-executable-windows/rubberband.exe`,
or honors `$env:HARMONYFINDER_RUBBERBAND = 'C:\path with spaces\rubberband.exe'`,
or searches PATH. Keep its accompanying DLLs beside the executable. See
[installation and licensing](vocal_pitch_prototype.md). No additional Python
dependencies or models were installed for Phase 3D.

Full-song mode requires the separately installed Demucs dependencies and model;
MP3 upload requires FFmpeg and ffprobe on PATH. Vocals-only WAV input does not
need Demucs. This phase does not download any new models.

**Experimental means known poor audio quality.** The user previously judged
both dynamic directions robotic. The [quality investigation](vocal_quality_investigation.md)
found early pitch commands (about 90 ms at the evaluated 44.1 kHz configuration),
consonant/gap masking and retained note-centre deviations. These are not fixed by
Studio integration. Exact file duration does not prove internal pitch automation
alignment, correct musical targets, intelligibility or naturalness. The isolated
timing compensation candidates remain disabled. Technical checks and successful
playback do not establish perceptual quality.

Only monophonic lead processing is intended. Source detuning is retained in vocal
output; quantized note labels do not auto-tune the waveform. Jobs remain local,
in-memory and non-durable across restarts. Reloading Studio loses its current
session. Changing a mode/settings clears old results; generating starts a fresh
upload. HTTP polling remains bounded and failures appear in the UI.

## Verification and reproduction

```powershell
.\.venv\Scripts\python.exe -m pytest backend/tests -q
cd frontend
npm.cmd test
npm.cmd run typecheck
npm.cmd run build
# With the backend and Vite running:
$env:E2E_AUDIO = '..\backend\data\audio\fa570cb6-1482-4dd2-8907-3ec2c0cbdf83\vocals.wav'
$env:E2E_INPUT_MODE = 'vocals_only'
$env:E2E_OUTPUT_MODE = 'vocal'
$env:E2E_DIRECTION = 'above'
npm.cmd run test:browser
$env:E2E_DIRECTION = 'below'
npm.cmd run test:browser
$env:E2E_OUTPUT_MODE = 'piano'
npm.cmd run test:browser
```

Replace the example file with an available recording. Browser tests use installed
Edge headlessly; `BROWSER_CHANNEL` can select another installed Playwright channel.
`STUDIO_URL` overrides the default localhost:5173. No API mocking is used in browser
tests. Screenshots are written under `frontend/test-results/`.

### Recorded verification (2026-10-15)

- Backend: **303 passed**, no skips, 20.92 seconds (283 previous + 20 new).
- Frontend: **39 passed**, six test files (35 previous + four new).
- TypeScript: passed (`tsc --noEmit`, also executed by the production build).
- Production build: passed, Vite 7.3.7, 1,635 modules.
- Real Edge desktop/mobile browser runs passed for vocals-only input with vocal
  Above, vocal Below, and piano output. They exercised upload, real pYIN,
  quantization, harmony, native Rubber Band or FluidSynth, stem mixing,
  HTTP downloads and advancing browser audio playback. No mocked browser API.
- Browser testing exposed the piano slider's old 0.25 step rounding the new 0.6
  vocal default to 0.5; its step was corrected to 0.05 and checks passed again.
- Full-song routing and existing separation behavior passed regression tests.
  A fresh real Demucs inference was not rerun in this phase; no model was downloaded.

Real browser source: saved `fa570cb6-1482-4dd2-8907-3ec2c0cbdf83/vocals.wav`,
20.04 seconds, 883,764 frames, 44.1 kHz stereo. These runs deliberately used fixed
minor thirds and chromatic quantization, without guessing the song's key.

| Output | Job ID | Harmony duration | Harmony RMS | Harmony peak | Preview peak |
| --- | --- | ---: | ---: | ---: | ---: |
| Vocal Above | `b138d89e-9ade-4b6f-ac7f-4457f42283ae` | 20.04 s | 0.094934 | 0.696113 | 0.949493 |
| Vocal Below | `4ddb3554-a3be-46ff-b6ac-5e9ed194b00e` | 20.04 s | 0.102167 | 0.933768 | 0.882294 |
| Piano Above | `216a0de5-3e80-4a7a-8d72-ecfd510e762c` | 20.150023 s | 0.007679 | 0.053040 | 0.528046 |

All three instrumental stems were exactly silent; all outputs were non-silent
and sample-unclipped. Vocal outputs retained all 883,764 frames. Each analysis
produced 34 harmony events. Outputs remain in `backend/data/audio/{job ID}/`;
the generated files survive on disk, but their API job registry does not survive
stopping the server. No new human listening verdict was obtained.

### Changed files

- Backend: new `backend/app/audio/preparation.py`; updated `audio/jobs.py`,
  `audio/rendering.py` and `api/routes/audio.py`; new `backend/tests/test_modes.py`.
- Studio: `frontend/src/App.tsx`, `types.ts`, `api.ts`, `pipeline.ts`, `styles.css`;
  new `components/ModeControls.tsx`; updated `HarmonyControls.tsx`, `MixControls.tsx`,
  `Progress.tsx`, `Results.tsx`.
- Frontend checks: new `src/test/modes.test.tsx`; updated `studio.test.tsx`,
  `mixer.test.tsx`, and `scripts/browser-smoke.mjs`.
- Documentation: `README.md` and this guide. No dependency, pitch/harmony algorithm,
  dynamic DSP, or quality-investigation algorithm changes.
