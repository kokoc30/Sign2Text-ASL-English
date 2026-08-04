# My Contributions to Sign2Text

**Koko Jamgotchian**

Sign2Text was built by a four-person team. This document describes the work I
personally authored, scoped to what `git blame` supports. Where a subsystem was
built by a teammate, it is credited to them rather than claimed here — see
[`THIRD_PARTY_ATTRIBUTION.md`](THIRD_PARTY_ATTRIBUTION.md) for full team attribution.

I worked across the full product surface: the browser application, four Python
services, the runtime configuration and launch layer, the landing site, and the
test suite.

---

## System and architecture

- Designed and built the multi-service architecture that separates ASL
  inference, voice/auth, letter recognition, and admin behind a single shared
  frontend, with one static server routing all four browser surfaces.
- Built the runtime configuration layer (`backend/runtime_config.py`) that
  resolves ports, public URLs, credential paths, checkpoint paths, and hardware
  profile behaviour before any service starts.
- Built the launcher (`start.py`) that supervises five processes, generates a
  frontend runtime-config bridge so the browser discovers service endpoints
  instead of hardcoding them, and handles restart-safe shutdown.
- Implemented CUDA/CPU profile detection (`backend/hardware.py`) that requires
  **both** PyTorch and ONNX Runtime CUDA support before selecting the GPU path,
  falling back to CPU when either is incomplete — the failure mode that
  actually occurs in practice.
- Added headless and reverse-proxy startup paths (`start_server.sh`,
  `tunnel_proxy.py`) for hosted and demo environments.

## Backend services

- **ASL service** (`backend/api_server.py`, ~2,100 lines, ~80% mine) — pipeline
  lifecycle management, status and runtime diagnostics endpoints, SSE event
  delivery, MJPEG video streaming, and remote frame upload. I integrated the
  ASL recognition pipeline behind this service; the pipeline itself was written
  by Stepan Karapetyan.
- **Voice/auth service** (`backend/stt_backend.py`, ~890 lines) — WebSocket STT
  streaming, Google Speech-to-Text integration, Azure Translator requests,
  mounted TTS routes, transcript sync endpoints, and health reporting.
- **Letter service** (`backend/letter_server.py`, ~740 lines, ~81% mine) —
  receives browser frames, runs MediaPipe hand-landmark detection, classifies
  handshapes, and publishes letter and word events over SSE with repeat
  suppression and idle word completion. The MLP loader module was written by
  Stepan Karapetyan.
- **Admin service** (`backend/admin_server.py`, ~1,030 lines) — public
  contributor intake, public feedback collection, rate limiting, honeypot
  handling, lead lifecycle management, CSV export, and an optional
  acknowledgement email path.
- **Persistence layer** (`backend/supabase_client.py`,
  `backend/supabase_repo.py`, `tools/migrate_admin_sqlite_to_supabase.py`) —
  optional Supabase-backed storage for profiles, transcripts, leads, and
  feedback, with automatic SQLite fallback when Supabase is unavailable, plus a
  migration tool between the two.
- **Supporting modules** — credential discovery (`backend/secret_config.py`),
  browser-origin/CORS resolution (`backend/browser_origin.py`), session
  configuration, translation (`backend/translate.py`), and TTS
  (`backend/tts_backend.py`).

## Frontend

- Built the multi-mode browser application (`frontend/web/app.js`, ~2,900
  lines) — a three-mode state machine coordinating ASL, Voice, and Letter
  workflows through one shared caption and session model.
- Implemented the live caption panel, rolling display behaviour, caption-size
  control, transcript export, and browser-local session history with a New Chat
  flow that archives non-empty sessions without changing modes.
- Wired consent handling, auth-aware UI state, and per-user scoping of local
  storage.
- Built browser camera capture and frame streaming (`frontend/web/camera.js`)
  over both WebSocket and HTTP upload paths.
- Built the admin dashboard (`frontend/web/admin.html`, ~3,900 lines) — lead and
  feedback views, summary cards, search and status filtering, inline editing,
  CSV export, and a guarded delete-all flow.
- Built the standalone legal pages and the shared legal stylesheet.

## Landing site

- Built the entire landing site (`landing/`, React 19 + Vite 6, ~3,300 lines) —
  Home, About, and Contribute pages, navigation, footer, and a canvas-based
  particle hero animation.
- Implemented the contributor interest form and public feedback form with
  client-side validation and inline loading, success, error, and rate-limit
  states.

## Machine learning — integration and evaluation

Scoped honestly: **the ASL recognition pipeline and its training framework were
authored by Stepan Karapetyan.** My ML-adjacent work was:

- Integrating the trained checkpoints into the live runtime, including
  config-driven model loading so training and inference stay aligned.
- Building the gloss-to-English normalization path
  (`backend/new_Inference.py`, ~1,890 lines, ~97% mine) — gloss buffering,
  sentence detection, and LLM-based caption generation through an
  Ollama-compatible endpoint.
- Evaluating and replacing the fingerspelling classifier: the original Letter
  mode used logistic regression; I benchmarked alternatives on an identical
  stratified 80/20 split and moved it to a 3×256 MLP, taking test accuracy from
  92.66% to **99.56%**, and to **99.68%** with a wrist-centred, palm-normalized
  variant that generalizes across signers.
- Verifying and documenting all published model results against their source
  artifacts — see [`MODEL_RESULTS.md`](MODEL_RESULTS.md), which also records one
  internal figure I could **not** verify and therefore excluded.

## Testing

- Wrote the test suite: 22 pytest modules (~7,000 lines) and 8 Playwright
  end-to-end specs (~1,000 lines).
- Coverage includes runtime configuration and profile resolution, launcher
  behaviour, the ASL event bus and transport status, inference helpers,
  letter-recognition endpoints, per-service auth guards, translation and TTS
  paths, the Supabase client and repository layers, the SQLite→Supabase
  migration, and admin CRUD including rate limiting and honeypot behaviour.
- Set up the GitHub Actions CI pipeline covering Python tests and the landing
  build.

**Stated plainly:** part of this suite is currently stale. 10 modules (176
tests) pass from a clean clone; 12 contain failures caused by two later
refactors — a frontend directory move and the migration from cookie sessions to
Supabase JWT — that landed without the corresponding test updates. That is my
own maintenance debt, not a defect introduced by publishing a subset, and it is
documented with root causes and a repair plan in
[`docs/TESTING_STATUS.md`](docs/TESTING_STATUS.md) rather than hidden.

## Documentation and legal infrastructure

- Wrote the architecture, API reference, configuration reference, installation,
  and quick-start documentation.
- Established a document-first legal infrastructure using Markdown as the single
  source of truth, with standalone public HTML pages reusing the project design
  system, and consistent legal links across the landing site, main app, admin
  dashboard, and contributor form.

---

## Key technical highlights

- Coordinated three distinct real-time transports where each fits best:
  WebSocket for bidirectional audio, SSE for one-way event push, MJPEG for
  annotated video.
- Built a single application surface unifying three very different input
  modalities behind one caption and session model.
- Made runtime behaviour configurable across local, headless, CPU, CUDA, and
  proxied environments without branching the service layout.
- Backed the product with a test suite covering both unit behaviour and
  end-to-end user flows.

---

## Team

| Contributor | Area |
| --- | --- |
| **Koko Jamgotchian** | Backend services, web frontend, admin dashboard, landing site, runtime/launch layer, test suite, documentation |
| **Stepan Karapetyan** | ASL recognition pipeline and ML training framework, Supabase auth module, letter MLP, mobile app |
| **Christopher Casas** | Mobile app |
| **armbotzzz** | Project contributions |
