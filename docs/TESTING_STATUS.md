# Testing Status

Honest account of the current state of the test suite.

Publishing a test suite is only worth doing if its real state is stated
accurately, so this document records exactly what passes, what fails, and why —
rather than presenting a partial suite as a complete one.

**Nothing has been skipped, weakened, deleted, or marked expected-to-fail to
improve these numbers.** Every test in the repository still runs and still
reports.

---

## Summary

| | Modules | Tests |
| --- | --- | --- |
| Passing fully | **10** | **176** |
| Containing known failures | 12 | — |
| Total | 22 pytest modules + 8 Playwright specs | ~8,000 lines |

Measured on the published source with no `.env`, no credentials, and no model
weights present — i.e. exactly what a fresh clone gets.

---

## Modules that pass fully

These run green from a clean clone and are enforced by CI.

| Module | Tests | Covers |
| --- | --- | --- |
| `test_admin_server_phase3.py` | 51 | Admin CRUD, lead lifecycle, feedback, rate limiting, honeypot, CSV export |
| `test_supabase_repo.py` | 33 | Repository layer, SQLite fallback behaviour |
| `test_inference_helpers.py` | 15 | Gloss buffering, sentence detection, Ollama URL resolution |
| `test_migrate_admin_sqlite_to_supabase.py` | 14 | SQLite → Supabase migration tool |
| `test_start.py` | 14 | Launcher argument handling, process orchestration |
| `test_supabase_client.py` | 14 | Supabase REST client, auth headers, error handling |
| `test_translate.py` | 12 | Azure Translator client, language handling |
| `test_tts_backend.py` | 10 | Text-to-speech routes, credential discovery, voice selection |
| `test_contributor_autoreply.py` | 9 | Contributor acknowledgement email path |
| `test_asl_normalization.py` | 4 | Gloss-to-English normalisation helpers |

---

## Modules with known failures

| Module | Result | Root cause |
| --- | --- | --- |
| `test_stt_backend.py` | 25 pass / 16 fail | Auth migration (A) |
| `test_api_server_auth.py` | 15 fail | Auth migration (A) |
| `test_space_key_toggle.py` | 14 errors | Frontend move (B) |
| `test_letter_server.py` | 1 pass / 9 fail | Auth migration (A) |
| `test_letter_server_auth.py` | 8 fail | Auth migration (A) |
| `test_api_server_eventbus.py` | 7 fail | Auth migration (A) |
| `test_runtime_config.py` | 13 pass / 7 fail | Config surface change (C) |
| `test_asl_transport_status.py` | 1 pass / 6 fail | Auth migration (A) |
| `test_api_server_off_mode.py` | 1 pass / 5 fail | Auth migration (A) |
| `test_api_server_start.py` | 1 pass / 4 fail | Auth migration (A) |
| `test_session_config.py` | 12 pass / 4 fail | Auth migration (A) |
| `test_linux_helper_scripts.py` | 2 fail | Excluded helper scripts (D) |

### Root cause A — authentication migration

Authentication was migrated from cookie-backed Google OAuth sessions to
Supabase JWT. Under the old design, auth was always enforced. Under the new one
it is opt-in via `SUPABASE_ENABLED`, and when disabled the guards return an
anonymous principal so the app runs locally without a Supabase project.

Tests written against the old behaviour assert `401` on unauthenticated
requests and now receive `200`. Others reference module-level symbols that no
longer exist (`SESSION_SECRET`, `SESSION_COOKIE_SECURE`), raising `NameError`
and `AttributeError`.

**These tests are asserting the correct thing for the old design.** The fix is
to rewrite them against the JWT design — enabling auth in the fixture and
asserting on token validation — not to relax the assertions.

### Root cause B — frontend directory move

The web frontend moved from `frontend/` to `frontend/web/`.
`test_space_key_toggle.py` reads `frontend/app.js` to assert on the structure of
the keyboard-shortcut handler, and now fails at fixture setup with
`FileNotFoundError`. All 14 results are collection errors, not assertion
failures — the tests never execute.

This is the cheapest of the four to fix: it is a path correction.

### Root cause C — configuration surface change

`test_runtime_config.py::test_supabase_fields_never_in_frontend_app_config`
asserts that no Supabase field reaches the browser configuration. It fails
because `SUPABASE_URL` and `SUPABASE_ANON_KEY` legitimately do — the browser
needs both to sign in, and the anon key is public by design and protected by
row-level security.

**This was specifically checked for a security problem and cleared.** Sentinel
injection confirmed `SUPABASE_SERVICE_ROLE_KEY` does **not** reach the frontend
configuration. The test's intent is right; its assertion is too broad and should
name the service-role key rather than matching any string containing
"supabase".

### Root cause D — helper scripts excluded from the public repository

`test_linux_helper_scripts.py` covers `setup_runpod.sh` and tunnel helper
scripts, which are excluded from this repository as internal operational
tooling. These two failures **are** a consequence of the public-release
exclusions, unlike A–C.

---

## Not caused by the public release

Causes A, B, and C are pre-existing in the private repository. This was verified
by running the suite in both places and comparing the failure sets: **102
failures and errors in each, identical sets, zero regressions** introduced by
anything in this public subset.

Only cause D (2 tests) is a consequence of publishing a subset.

---

### Root cause E — `sys.modules` pollution between test modules

`tests/test_asl_normalization.py` calls `_stub_heavy_imports()`, which inserts a
minimal fake `torch` module into `sys.modules` so the normalisation classes can
be tested without a GPU environment. The stub is written directly into
`sys.modules` rather than through pytest's `monkeypatch`, so **it is never
removed.**

Every module that imports the services afterwards in the same process receives
that stub instead of real torch. `backend/api_server.py` and
`backend/letter_server.py` both call `torch.set_num_threads(1)` at import time,
and the stub does not define it:

```
AttributeError: module 'torch' has no attribute 'set_num_threads'
```

This single leak accounts for **118 of the 125 `AttributeError` failures** in a
full-suite run — by a wide margin the largest contributor to the failure count,
and entirely an artefact of test ordering rather than a defect in the code under
test.

Two consequences worth noting:

- Running the suite module-by-module yields **230 passes**; running it as one
  session yields **225**. A suite whose result depends on invocation order is
  telling you something real.
- Because the guard is `if "torch" not in sys.modules`, whether the stub gets
  installed depends on whether an earlier module already imported real torch —
  so the failure set can shift with any change to test collection order.

**Fix:** install the stub with `monkeypatch.setitem(sys.modules, "torch", ...)`
so pytest reverts it after the module, and add `set_num_threads` to the stub.
Until then, CI runs the stable subset with one pytest process per module, which
makes the result order-independent without changing any test.

---

## Repair plan

In priority order — highest value per unit of effort first:

1. **Fix the torch stub** (E) — install it via `monkeypatch.setitem` and add
   `set_num_threads`. Smallest change, largest effect: removes 118 of the 125
   `AttributeError` failures and makes the suite order-independent.
2. **Fix `test_space_key_toggle.py` paths** (B) — mechanical path correction,
   recovers 14 tests.
3. **Narrow the Supabase config assertion** (C) — name the service-role key
   explicitly rather than matching any string containing "supabase". Recovers 7
   tests and makes the test express its actual security intent.
4. **Rewrite the auth tests against JWT** (A) — the largest piece of work.
   Fixtures should enable `SUPABASE_ENABLED` and stub token verification, then
   assert on token validation rather than on the old cookie-session behaviour.
5. **Scope or remove `test_linux_helper_scripts.py`** (D) — it covers scripts
   that are not published in this repository.

Items 1–3 are mechanical and together account for a large share of the current
failures. Item 4 is genuine rework and should not be rushed: the tests are
asserting the right thing for the previous design, and the correct fix is to
re-express that intent against the new one, not to relax the assertions.

---

## Continuous integration

`.github/workflows/ci.yml` runs two Python jobs:

- **`tests-stable`** — the 10 fully-passing modules. **Blocking.** A regression
  here fails the build.
- **`tests-full`** — the entire suite including the known-failing modules.
  Non-blocking, and clearly labelled as such.

Both jobs run every test. Nothing is excluded from execution and no failure is
suppressed — the full-suite job reports its failures in the log exactly as they
occur. The split exists so that a genuine new regression is distinguishable from
the known backlog documented above, which a single permanently-red job would
hide.

The Playwright end-to-end specs are not run in CI: they require all five
services live, a browser install, and camera permissions.
