# Project Functionality Overview

This document reflects the current implementation in the repository. It is intended as the detailed internal overview of how the current Sign2Text stack is wired together, what each runtime service does, and which behaviors are directly verified from code.

## 1. System Summary

Sign2Text is a multi-surface application made up of:

- a routing-aware frontend server
- a main browser app at `/index.html`
- a React/Vite landing site at `/` when a landing build is present
- a dedicated admin page at `/admin.html`
- four Python API/services for ASL, Voice, Letter, and Admin responsibilities

The landing site, legal pages, and public contributor/feedback intake routes are accessible without sign-in. The interactive ASL, Voice, and Letter pipelines rely on Supabase JWT authentication. The browser signs in through the Supabase JS SDK (email+password or Google OAuth via Supabase's provider) and attaches the resulting Bearer token to every backend request. Each service validates the token via `backend/auth_supabase.py`.

The runtime and admin services are implemented with FastAPI apps and launched through Uvicorn or Uvicorn-style entrypoints. The frontend itself is not served by FastAPI; it is served by `backend/frontend_server.py`, which uses Python's built-in HTTP server machinery and custom route handling.

## 2. Startup Flow

### Standard Windows path

1. `setup.ps1` creates `.venv` if needed, detects `auto`/`cuda`/`cpu`, and installs the matching runtime requirements.
2. `start.ps1` sets `ASL_RUNTIME_PROFILE`, activates `.venv`, and runs `start.py`. It also supports `-Tunnel` and `-NoOllama`.
3. `start.py`:
   - loads shared runtime settings from `backend/runtime_config.py`
   - loads environment-derived secrets and credential paths
   - fails fast if the resolved ASL checkpoint file is missing
   - writes `runtime-config.js` for frontend URL discovery
   - configures service commands
   - launches the frontend server plus ASL, Voice, Letter, and Admin services

### Other supported launcher paths

- `python start.py --headless` for non-interactive startup
- `python start.py --proxy` for a consolidated reverse-proxy flow
- `python start.py --tunnel` for Cloudflare Quick Tunnel-based testing
- `start_server.sh` for Linux/Azure-VM-style headless startup

### Startup/runtime notes verified in code

- `setup.ps1` installs `requirements.runtime.txt` for CUDA-capable setups and `requirements.runtime-cpu.txt` for CPU-only setups.
- `start.ps1 -NoOllama` sets `ASL_DISABLE_TRANSLATION=1`, which keeps ASL recognition active while disabling the gloss-to-English normalization step.
- In `--proxy` and `--tunnel` modes, `start.py` writes proxy-aware frontend URLs such as `/asl-api`, `/voice-api`, `/letter-api`, `/admin-api`, and `/voice-api/ws/stt` into `frontend/runtime-config.js`.

## 3. Default Services And Ports

| Service | Default port | Entry point | Current responsibility |
| --- | --- | --- | --- |
| Frontend | `5500` | `backend/frontend_server.py` | Serves landing, app, and admin HTML/assets |
| ASL | `8000` | `backend/api_server.py` | ASL inference, SSE, MJPEG, camera input, runtime diagnostics |
| Voice | `8001` | `backend/stt_backend.py` | STT WebSocket, translation, mounted TTS routes, `/auth/me`, `/auth/logout` |
| Letter | `8002` | `backend/letter_server.py` | Fingerspelling recognition, SSE, frame upload, word assembly |
| Admin | `8003` | `backend/admin_server.py` | Public contributor intake, public feedback collection, and private admin APIs |

These values are defaults. `backend/runtime_config.py` can override hosts, ports, and public URLs through environment variables.

## 4. Frontend Routing Behavior

`backend/frontend_server.py` is the routing layer in front of the app surfaces.

### When `landing/dist/index.html` exists

- `/` -> `landing/dist/index.html`
- `/index.html` -> `frontend/index.html`
- `/admin.html` -> `frontend/admin.html`
- `/privacy.html` -> `frontend/privacy.html`
- `/terms.html` -> `frontend/terms.html`
- `/assets/...` and other built landing files -> `landing/dist/...`
- unknown landing SPA routes such as `/about` and `/contribute` -> `landing/dist/index.html`
- app files such as `runtime-config.js`, `app.js`, and `style.css` -> `frontend/` files

### When the landing build is missing

- `/` falls back to `frontend/index.html`
- app files are served directly from `frontend/`

### Safety behavior

The server uses `_safe_resolve()` to guard against path traversal. It rejects backslashes, null bytes, and any resolved path that escapes the intended base directory.

## 5. Main User Surfaces

### Landing site

- Source lives under `landing/src`
- Built output lives under `landing/dist`
- Uses React, React Router, and Vite
- Current routes in the landing app are `/`, `/about`, and `/contribute`
- The Home page (`/`) includes an optional public feedback section that submits to the admin backend
- The landing app resolves its app/admin URLs from `landing/src/config.js`, not from generated `frontend/runtime-config.js`
- In the current source, dev mode uses direct localhost URLs, while production builds target `/index.html` and `/admin-api`

### Main app

- Served from `/index.html`
- Built from static HTML/CSS/JS files in `frontend/`
- Main browser logic lives in `app.js`
- Uses one shared caption/session surface across ASL, Voice, and Letter modes
- Supports transcript download and session history for non-empty session text
- Session history is always stored locally in per-user scoped browser localStorage
- When authenticated, the frontend also loads and merges backend transcript rows through the Voice service's `/api/transcripts` endpoints and best-effort migrates unsynced local entries to backend storage
- When transcript storage is unavailable, those transcript endpoints return `503` and the local history path remains available
- Supports starting a blank active session with New Chat while archiving non-empty current session text into history
- Uses generated `runtime-config.js` to discover backend URLs at runtime

### Admin page

- Served from `/admin.html`
- Implemented as a single HTML file with inline JavaScript
- The admin logic currently lives inline in `admin.html` rather than in a separate script asset
- Uses generated `runtime-config.js` to resolve the admin backend URL

## 6. ASL Mode

ASL mode is powered by `backend/api_server.py`.

### Current frontend behavior

- The browser starts ASL mode by calling `POST /start` with `camera_source: "remote"` from `app.js`.
- The browser camera is opened locally and frames are uploaded to `POST /upload_frame`.
- The frontend opens `GET /stream` for real-time SSE events.
- The frontend also requests `GET /video_feed` for the backend's annotated MJPEG stream.
- The ASL source language is fixed to `ASL`, but the target language dropdown is selectable from the same supported list used by Voice and Letter mode (`en`, `es`, `ar`, `hy`). The per-mode target language is persisted per user in localStorage and is independent of the Voice and Letter selections.
- Live sign detection and gloss updates continue to render in the under-camera status area (`#ui-status-text`) and are never translated or spoken.
- Only finalized English text emitted by the ASL SSE `translation` event is routed into the shared caption surface. If the target language is English, the finalized English text is appended directly with no translation request. If the target language is not English, the frontend calls the Voice service's `POST /api/translate` endpoint to translate the finalized English, and appends the translated result; if the translate request fails, the finalized English text is appended as a safe fallback.
- TTS reuses the Voice service's `POST /api/tts` endpoint and speaks only the finalized ASL output when TTS is enabled. All three finalized branches (English direct, translated, English fallback) are covered. A session-generation guard ensures that stale async translate/TTS callbacks from a previous session cannot leak into a newly started session.

### Current backend behavior

`backend/api_server.py` wraps the ASL inference runtime around:

- RTMW whole-body pose estimation
- frame feature extraction
- sign spotting
- checkpoint-based classification
- gloss buffering
- sentence boundary detection
- asynchronous Ollama-backed normalization against a local or remote Ollama-compatible endpoint

The backend exposes:

- `POST /start`
- `POST /stop`
- `GET /status`
- `GET /runtime`
- `GET /stream`
- `GET /video_feed`
- `WS /ws/frames`
- `POST /upload_frame`
- `POST /manual_sign`
- `POST /threshold`
- `POST /clear`
- `POST /reset`

### Important implementation notes

- ASL inference runs on the host or deployment machine. The current frontend default uploads browser camera frames to that backend.
- The current frontend uses browser-camera upload by default.
- The ASL backend still supports local-camera operation and can choose local/remote/auto camera sources.
- The backend caches the ASL model and RTMW resources across stop/start cycles.
- `backend/new_Inference.py` includes a rule-based fallback normalizer for request-time Ollama failures.
- The ASL service also exposes `/runtime` for hardware/runtime diagnostics.

### Authentication

All ASL endpoints except `GET /` are protected by Supabase JWT authentication. Unauthenticated requests receive `401 {"detail": "Missing Bearer token."}`. The ASL service uses `backend/auth_supabase.py` to validate the `Authorization: Bearer <token>` header (or `?token=` query param for browser WebSocket/EventSource connections, which cannot set custom headers).

## 7. Voice Mode

Voice mode is powered by `backend/stt_backend.py`.

### Current frontend behavior

- The main app requires Google sign-in before it will start ASL, Voice, or Letter pipelines.
- Voice mode requires an authenticated user.
- The browser requests microphone access and streams audio through `googleSttSource.js`.
- The frontend connects to `WS /ws/stt`.
- Finalized text can then be sent through:
  - `POST /api/translate`
  - `POST /api/tts`

### Current backend behavior

`backend/stt_backend.py` provides:

- `GET /auth/me` (returns current user from the Bearer token) and `POST /auth/logout` (no-op)
- STT over `WS /ws/stt` (token passed via `?token=` query param)
- translation via `POST /api/translate`
- mounted TTS routes from `backend/tts_backend.py`
- `GET /health`

### Security/auth behavior verified in code

- Supabase JWT validation via `auth_supabase.verify_jwt()` (delegates to Supabase `/auth/v1/user` with 60 s cache)
- Bearer token enforcement on translate, transcript, and STT routes
- `POST /api/tts` is mounted into the same Voice service and is used by the authenticated browser flow, but the current route code does not add a separate auth dependency

### Runtime dependencies

The voice path is implemented in code, but live behavior depends on configured:

- Supabase project (for auth token validation)
- Google Speech-to-Text credentials
- Google Text-to-Speech credentials
- Azure Translator credentials
- session secret configuration

## 8. Letter Mode

Letter mode is powered by `backend/letter_server.py`.

### Current frontend behavior

- The browser starts the Letter backend via `POST /start`.
- The browser opens the camera locally.
- Frames are uploaded to `POST /upload_frame`.
- The frontend listens to `GET /stream` for SSE events such as letter detection, letter acceptance, and word completion.
- The Letter source language is fixed to `Letter`, but the target language dropdown is selectable from the same supported list used by Voice mode (`en`, `es`, `ar`, `hy`).
- Live recognized English letters and the in-progress word remain in the under-camera status area.
- Only committed/finalized words (emitted via `word_completed`) are translated. Translation reuses the Voice service's `POST /api/translate` endpoint and the translated result is shown in the caption area.
- TTS reuses the Voice service's `POST /api/tts` endpoint and speaks only the committed/final output when TTS is enabled and the target language differs from English.
- When the target language is English, translation and TTS are skipped and committed English letters go directly to the caption area.

### Current backend behavior

`backend/letter_server.py`:

- receives browser-uploaded JPEG frames
- runs MediaPipe Hands landmark extraction
- trains and uses a Logistic Regression classifier from CSV data
- applies duplicate-letter control and stable-letter acceptance rules
- publishes real-time SSE events
- emits `word_completed` when a word boundary is reached

Exposed endpoints:

- `POST /start`
- `POST /stop`
- `GET /status`
- `GET /stream`
- `POST /upload_frame`
- `GET /health`

This mode is not a vague UI-only helper. It is a dedicated backend-driven fingerspelling pipeline implemented in `backend/letter_server.py`.

### Authentication

All Letter endpoints except `GET /` and `GET /health` are protected by session-based authentication, using the same shared session middleware as ASL and Voice.

## 9. Contributor Intake And Landing Integration

The current landing Contribute page is a live email waitlist for a planned future contributor portal.

### Current landing behavior

`landing/src/pages/Contribute.jsx`:

- presents the contributor program as planned/future
- includes a live "Notify Me" email form today
- posts form submissions to `POST /api/public/contributor-leads`
- links "Try the App" to `/index.html` in production builds
- uses `landing/src/config.js` for backend resolution instead of `frontend/runtime-config.js`

### Current backend intake behavior

`backend/admin_server.py` accepts waitlist submissions at:

- `POST /api/public/contributor-leads`

Stored fields are written into the default SQLite database at:

- `data/admin.sqlite3`

When `SUPABASE_ENABLED=true` and `SUPABASE_USE_FOR_ADMIN=true`, the admin service uses the Supabase-backed contributor repository instead. If Supabase admin initialization fails at startup, it falls back to SQLite automatically.

The public intake flow currently includes:

- email validation
- duplicate-email idempotency
- a honeypot field (`website`)
- request rate limiting with `Retry-After`
- optional acknowledgement email for newly inserted contributor leads only

The acknowledgement email path is best-effort. It is scheduled via FastAPI
`BackgroundTasks`, does not run for duplicate, honeypot, invalid-email, or
rate-limited submissions, and SMTP failure does not change the public intake
response.

### Current deployment caveat

The landing site does not consume `frontend/runtime-config.js` at runtime. Instead, it relies on build-time values from `landing/src/config.js`. In the current source, production builds target `/index.html` and `/admin-api`, so the shipped landing build works in proxy or tunnel mode as long as `landing/dist` is current.

## 10. Public Feedback

The Home landing page includes an optional feedback section for visitors.

### Current landing behavior

`landing/src/pages/Home.jsx`:

- presents an optional name field and message textarea
- validates client-side that a message is present before submitting
- posts to `POST /api/public/feedback` with `source: "home"`
- includes the same honeypot field pattern used by contributor intake
- handles rate limiting, success, and error states inline
- uses `landing/src/config.js` for backend resolution instead of `frontend/runtime-config.js`

### Current backend feedback behavior

`backend/admin_server.py` accepts feedback at:

- `POST /api/public/feedback`

Feedback is stored in its own `feedback` table in `data/admin.sqlite3` by default, separate from contributor leads. When admin persistence is switched to Supabase, the same route writes through the Supabase feedback repository instead. Both name and message fields are optional, but submissions with no message after trimming are silently dropped without creating a database row. The endpoint reuses the same IP-based rate limiting and honeypot protection used by contributor intake.

### Admin feedback visibility

The admin dashboard provides a Feedback view (toggled from the top of the page) that lists submitted feedback entries with name, message, source, and timestamp. Feedback can be exported as CSV. Feedback stats (total count and recent 7-day count) are shown in the Feedback view's summary cards.

## 11. Admin System

The admin system is split across `admin.html` and `backend/admin_server.py`.

### Current admin UI behavior

`admin.html` provides:

- token-gated dashboard unlock
- a view toggle to switch between Contributor Leads and Feedback views
- summary cards (leads stats plus feedback counts)
- search and status filtering for leads
- search filtering for feedback
- inline status updates and notes editing for leads
- CSV export for both leads and feedback
- single-record deletion and delete-all confirmation for leads
- loading, empty, filtered-empty, and error states

Important current implementation details:

- the admin token is stored in `sessionStorage`
- the page resolves its backend URL from generated runtime config instead of hardcoding a browser-facing localhost admin API
- the admin JS is inline inside `admin.html`

### Current admin API behavior

`backend/admin_server.py` exposes:

- `GET /health`
- `POST /api/public/contributor-leads`
- `POST /api/public/feedback`
- `GET /api/admin/stats`
- `GET /api/admin/contributor-leads`
- `GET /api/admin/contributor-leads/export`
- `PATCH /api/admin/contributor-leads/{id}`
- `DELETE /api/admin/contributor-leads/{id}`
- `DELETE /api/admin/contributor-leads`
- `GET /api/admin/feedback`
- `GET /api/admin/feedback/export`

### Admin/security behavior verified in code

- admin endpoints require `X-Admin-Token`
- insecure or placeholder admin tokens disable admin access and cause protected admin routes to return `503`
- public intake requests are rate-limited
- honeypot submissions return safe success without storage
- optional contributor acknowledgement email uses env-configured sender identity
- some SMTP providers require `CONTRIB_FROM_EMAIL` to match the authenticated account or a verified alias
- email addresses are masked in relevant logs
- optional trusted-proxy IP extraction is available through `TRUSTED_PROXY=true`

## 12. Runtime Configuration

`backend/runtime_config.py` is the shared runtime settings layer.

It currently handles:

- ASL, Voice, Letter, and Frontend host/port resolution
- public URL generation
- frontend runtime URL payload generation
- explicit frontend/backend base URL overrides such as `FRONTEND_PUBLIC_URL`, `ASL_API_BASE_URL`, `VOICE_API_BASE_URL`, `LETTER_API_BASE_URL`, `ADMIN_API_BASE_URL`, and `VOICE_WS_URL`
- checkpoint path resolution
- Ollama URL/model/timeout/auth settings (local and remote), with auth token handling kept backend-only
- `OLLAMA_MODE` for launcher and deployment helper behavior
- service timeout settings
- hardware profile selection and reporting

`start.py` writes these resolved frontend values into `runtime-config.js` so the main app and admin page can discover backend URLs at launch. The landing site still relies on build-time `landing/src/config.js` instead of reading that file at runtime. In the current source, production builds target `/index.html` and `/admin-api`. The generated frontend config does not include `OLLAMA_AUTH_TOKEN`, and `OLLAMA_MODE` is not part of the browser-facing runtime contract.

## 13. Reverse Proxy And Tunnel Behavior

`tunnel_proxy.py` provides a single-port reverse proxy for proxy/tunnel use.

It currently proxies:

- frontend traffic
- ASL traffic under `/asl-api`
- Voice traffic under `/voice-api`
- Letter traffic under `/letter-api`
- Admin traffic under `/admin-api`
- Voice STT WebSocket traffic
- ASL frame WebSocket traffic

In proxy and tunnel mode, the main app and admin page follow those prefixed routes through generated runtime config. The landing site still uses build-time config, but the current production build targets `/admin-api`; if `landing/dist` is stale relative to `landing/src/config.js`, rebuild the landing app to pick up the current proxy-aware behavior.

## 14. Major Repository Responsibilities

```text
backend/
  api_server.py            ASL runtime service
  stt_backend.py           Voice/auth/STT/translation service
  tts_backend.py           Google TTS routes mounted into the voice service
  letter_server.py         Letter recognition service
  admin_server.py          Contributor intake, feedback collection, and admin API
  frontend_server.py       Routing-aware frontend static server
  runtime_config.py        Shared runtime and URL configuration
  new_Inference.py         ASL inference and normalization logic
landing/
  src/                     React/Vite landing source
frontend/
  index.html               Main app shell
  admin.html               Admin dashboard with inline JS
  app.js                   Main browser-side app logic
  camera.js / captions.js / googleSttSource.js / textSource.js / style.css / favicon.png
start.py                   Main multi-service launcher
start.ps1                  Windows startup wrapper
tunnel_proxy.py            Proxy/tunnel router for selected services
tests/                     Automated test coverage
```

## 15. Operational Notes

- Voice features are implemented, but they depend on external Google/Azure configuration at runtime.
- ASL English output depends on the ASL service's normalization path; the code includes a rule-based fallback for request-time normalization failures.
- `start.ps1 -NoOllama` intentionally disables that normalization layer and leaves ASL output in raw gloss form.
- Fresh VM deployments still need the ASL checkpoint bundle plus any secret or credential files placed on disk before startup.
- Default ports are configurable through environment/runtime config.
- This document intentionally avoids claiming full deployment readiness or a fully green suite from this pass. It is focused on the current verified implementation and code paths.
