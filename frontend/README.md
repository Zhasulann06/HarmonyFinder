# HarmonyFinder Studio

React + strict TypeScript + Vite, with Tailwind CSS, Lucide icons, and TanStack
Query. This is the real client for the existing FastAPI pipeline. No mock API
or generated sample audio is included in the application.

From this directory, using Node.js 24 LTS (or 22.12+ on the 22.x line):

```powershell
npm ci
npm run dev
```

Open http://127.0.0.1:5173. Start the backend separately from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app
```

See the [project README](../README.md) for Python, Demucs, FFmpeg, FluidSynth,
SoundFont, and troubleshooting instructions. Keep a single backend worker.

## Configuration

Optional `frontend/.env.local` (restart Vite after editing):

```dotenv
VITE_API_BASE_URL=/api
API_PROXY_TARGET=http://127.0.0.1:8000
```

`VITE_API_BASE_URL` is the API prefix exposed to the browser; it includes `/api`.
It is embedded at build time and must never contain secrets. `API_PROXY_TARGET`
is the backend origin used by the Vite development and preview servers only.
Their proxy forwards `/api`, `/docs`, and `/openapi.json`. The default setup is
same-origin from the browser's perspective and needs no backend CORS changes.
An absolute cross-origin API URL requires separately configured backend CORS;
the current API does not allow cross-origin browser requests by default.
For a future static host, configure a same-origin reverse proxy to FastAPI.
Vite preview is a local build check, not a production server.

## Checks

```powershell
npm test
npm run typecheck
npm run build
npm run preview
```

The unit/component tests mock the network and browser metadata only in tests.
They never run Demucs or download a model. Coverage includes validation,
settings, request handling, finite status polling, cancellation, duplicate
submission, empty results, partial MIDI availability, audio controls, and
download links.

With Vite and FastAPI running, the browser smoke check uses installed Microsoft
Edge in headless mode (no browser download):

```powershell
npm run test:browser
# Optional real end-to-end run with your own <=30-second WAV or MP3:
$env:E2E_AUDIO = 'C:\Music\short-vocal.wav'
npm run test:browser
Remove-Item Env:E2E_AUDIO
```

`BROWSER_CHANNEL=chrome` uses installed Chrome instead. `STUDIO_URL` selects a
different frontend origin (for example `http://127.0.0.1:4173` for preview).
Screenshots are saved under ignored `test-results/`. The optional end-to-end run
uploads a new copy and uses the actual backend, including installed Demucs;
ensure the model is cached if you do not want its first-run model download.

## Behavior and limitations

- WAV/MP3 extension, nonempty content, 20 MiB size, and browser-readable duration
  up to 30 seconds are checked before generation. The backend still validates
  the actual content. Browser codec support can reject unusual WAV encodings.
- Each generation (including regeneration) starts a fresh upload/session and
  runs the six stages. Settings are locked during generation. Changing a file
  or settings clears previous results. There is no session persistence.
- Diatonic intervals always use scale-aware quantization with matching key and
  scale. Choose the key manually; no automatic key/chord detection is implied.
- The **Find your balance** section sends independent instrumental, lead, and
  harmony gains to rendering. Harmony Forward uses 0.85/0.40/8.00; Balanced uses
  0.85/0.70/4.00. Values are amplitude multipliers, not perceived loudness.
  Gains affect the generated preview, while audio-player volume affects local
  playback only. Generate again after changing a gain. The standalone piano
  WAV is unchanged by mix gains. Peak-protection attenuation is disclosed in
  results. See the project README for measured comparisons and compatibility.
- Separation polls every two seconds and stops at completion, failure, or
  15 minutes. Individual requests have a 20-minute timeout. Unmounting aborts
  requests and polling, but does not cancel work already running on the server.
- A missing SoundFont/FluidSynth error retains the MIDI link when the API says
  MIDI is available. Fix backend dependencies and regenerate for WAV output.
- Original playback uses a local object URL which is revoked on replacement or
  unmount. Output players use API download routes. Only one player plays at a
  time. Empty detected melodies produce silent piano and are labeled as such.
- Restarting FastAPI clears job IDs. A refresh clears the studio session.
  Regenerate after either event. No vocal harmony synthesis is implemented;
  the generated second voice is a sampled piano.

