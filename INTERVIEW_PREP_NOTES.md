# BigHappy E2E Tests — Interview Prep Notes

Compiled from a Claude Code session walking through this repo file-by-file, for interview prep.
If you're opening this in a new Claude session: paste/read this file first for full context, then continue asking questions.

---

## Project overview

Three test suites, one CI pipeline:
- `api-tests/` — Node.js/Jest API tests against reqres.in
- `api-tests-python/` — same coverage, in Python/pytest — a bonus to show the design translates across languages
- `ui-tests/` — Python + Playwright, full login → cart → checkout flow against saucedemo.com
- `.github/workflows/tests.yml` — runs all three in parallel on every push/PR, merges results into one Allure report

### Why this stack (talking points)
- **Jest + Axios** — standard, low-ceremony combo for HTTP-level testing in JS.
- **Playwright over Selenium** — auto-waiting removes a whole class of flaky tests (no manual `sleep()`), Trace Viewer gives a full replay of a CI failure without reproducing locally, one API drives Chromium/Firefox/WebKit.
- **Python for UI tests** — most QA orgs standardize on it; suite leans on real plugins (`pytest-xdist` for parallelism, `allure-pytest` for reporting) instead of hand-rolling.
- **Page Object Model** — keeps locators out of test logic so the suite stays maintainable as more flows are added.
- **Two API suites (JS + Python)** — not a requirement; shows the test design (happy path + negative cases, reusable HTTP client wrapper) holds up across languages.

---

## File-by-file walkthrough

### `api-tests/tests/reqres.test.js`
4 tests: GET single user (200 + schema check), POST create user (201 + echoed fields), GET non-existent user (404), POST missing required field (reqres doesn't validate server-side, documented via comment rather than asserting a 400 that never comes). `beforeAll` builds one shared `HTTPClient` reused by every test in the file.

**Added during this session:** a `setHeader Tests` block demonstrating `client.setHeader('x-api-key', ...)` mid-suite — swap to an invalid key (verified live against reqres.in: no key → 401, invalid key → 403), assert `403`, then restore the valid key before the test ends. Teaching point: because `client` is shared across the whole file, a header left broken here would leak into later tests — must reset it.

### `api-tests/utils/client.js`
Wraps Axios into one class exposing `get/post/put/delete`, all returning the same shape: `{ statusCode, statusText, data, headers, isSuccess }`. Key design: Axios throws on non-2xx by default; `_handleError()` catches that and reshapes it into the *same* response shape as a success (`isSuccess: false`), so tests never need a separate code path for errors vs. successes. Genuine network failures (no response at all) still re-throw — that's an infra problem, not testable API behavior.
`setHeader(key, value)` mutates the shared Axios instance's default headers — affects every request made after it's called, on that same client.

### `api-tests/utils/client-native.js` (created this session, for comparison only — not wired into any test)
Same public interface as `client.js`, built on Node's core `http`/`https` modules instead of Axios — to show what Axios abstracts away: base-URL joining, JSON stringify/parse, non-2xx → error, network-error handling, timeout handling (including manually calling `req.destroy()` on timeout to avoid a socket leak). Point for interview: tests depend on the `HTTPClient` abstraction, not on Axios directly, so swapping the underlying library is a one-line change in `beforeAll`, not a rewrite of every test.

### `api-tests/jest.config.js`
`coverageThreshold.global` requires 50% branches/functions/lines/statements or Jest exits non-zero — but only when run **with** `--coverage`.

**Found gap:** CI's "Run API tests" step runs `npm test` (`jest --verbose`, no `--coverage`), not `npm run test:ci` (which has `--coverage`). So the threshold is never actually enforced in CI, and the "Upload API test results" artifact (`api-tests/coverage/`) is empty every run. **Not yet fixed** — one-word fix (`npm test` → `npm run test:ci`) if wanted.

### `api-tests-python/api/client.py`
Python equivalent of `client.js`, using `requests.Session()`. Returns a small `Response` class (`status_code`, `data`, `headers`, `is_success`).
**Found gap:** no equivalent of `_handleError` — every method's `except Exception` catches everything generically (server error response, connection failure, bad JSON) and re-raises as one generic exception. It *happens* to work for 404s because `requests` doesn't throw on non-2xx by default (unlike Axios) — that's a library default, not a deliberate design decision like the JS side made.
`close()` is defined (releases the session's connection pool) but **never called anywhere** — see conftest.py gap below.

### `api-tests-python/conftest.py`
`env_config` (session-scoped) reads `REQRES_BASE_URL`/`REQRES_API_KEY`/`REQUEST_TIMEOUT` from env, converts timeout ms→s. `api_client` (function-scoped) builds a **new** `HTTPClient` per test — unlike the shared JS client, so no cross-test header leakage risk.
**Found gap:** the fixture is `yield client` with nothing after — no teardown, so `client.close()` is never invoked. New session/connection pool created every test, cleaned up only by Python's GC eventually, not deterministically. **Fix (not yet applied):** add `client.close()` after the `yield`.

### `api-tests-python/tests/test_reqres.py`
Same 4 scenarios as the JS suite. Uses `@pytest.mark.smoke` / `@pytest.mark.regression` tags (declared in `pytest.ini`) so CI can run smoke and regression as separate steps — something the JS suite doesn't have yet. Every assert has a custom message string, which Jest's `expect()` doesn't give you the same way.

### `api-tests-python/pytest.ini`
Declares `smoke`/`regression`/`slow` markers, `addopts = -v --tb=short`.
**Found gap:** `ui-tests/pytest.ini` has `--strict-markers` (errors on an undeclared/typo'd marker); this file doesn't. Small, easy consistency fix — not yet applied.

### `ui-tests/pages/login_page.py`
Page Object for the Sauce Demo login screen. Locators use `data-test` attributes (stable, meant for automation, survive CSS/style refactors). `login()` composes `enter_username` + `enter_password` + `click_login`. Exposes `get_error_message()`, `is_error_displayed()`, `is_username_field_visible()`, `is_password_field_visible()` for tests to assert on.
`navigate()` and `click_login()` both call `wait_for_load_state("networkidle")` — works fine on a static site like Sauce Demo, but the README itself flags this as the first thing to audit if UI tests start flaking (fix: wait on the specific next element instead of a network-level heuristic).

### `ui-tests/conftest.py`
`env_config` — same pattern as the Python API suite, with `os.environ.setdefault(...)` fallbacks if no `.env.local` exists. `browser_type_launch_args` — a fixture name `pytest-playwright` specifically looks for, used here to route the `HEADLESS` env var into Playwright's launch options.

**Important mechanic clarified this session:** `env_config` is never mentioned in `login_page.py` — and that's correct, not a bug. Pytest injects `env_config` into the **test function** (by parameter-name matching), and the test function reads plain strings out of it (`env_config["url"]`, etc.) and passes those strings into `LoginPage` methods. The Page Object only ever sees plain strings, never the fixture — keeping it decoupled from config/fixture machinery so it can also be called with arbitrary literals (e.g. `"wrong_password"` in the negative test).

### `.env.example` pattern (all three suites)
Committed template, no real secrets. `.env.local` is gitignored, holds real local values. In CI, real values come from GitHub Actions' encrypted secrets store (`secrets.SAUCE_DEMO_USERNAME`, etc.), never a file. In real production, a dedicated secrets manager (AWS Secrets Manager, Vault, etc.) replaces even that.
**Why hardcoded fallbacks are OK here specifically:** `standard_user`/`secret_sauce` are Sauce Demo's own publicly documented demo credentials, and the reqres key is their public free-tier key — not real secrets. Would NOT be OK to hardcode a fallback for an actual production secret (it'd sit in git history forever).

### `.github/workflows/tests.yml`
Triggers on push/PR to `main`/`develop`. Three parallel jobs (`api-tests`, `api-tests-python`, `ui-tests`), each: checkout → set up runtime → install deps → run tests (Python suites run smoke then regression as separate steps) → upload artifacts (`if: always()` so failures still leave artifacts behind). Two downstream jobs `needs: [all three]`: `test-summary` (writes a pass/fail table to the run summary, `exit 1` if anything failed) and `allure-report` (merges all three suites' Allure results into one HTML report).

**Changes made this session:**
- Added `--tracing=retain-on-failure` to both UI test steps (smoke + regression) — Playwright now captures a full failure trace (DOM snapshots, network, console, screenshots) saved under `ui-tests/test-results/`, already picked up by the existing artifact upload. Updated README to match (removed the "not wired in yet" note).

**Required status check mechanics (explained, not changed):** GitHub branch protection matches by the job's `name:` field — here that's `"Test Summary"` (not the job id `test-summary`, not the workflow name `E2E Tests`). Set in repo Settings → Branches → require status checks → search "Test Summary". Only appears in that list after the workflow has run at least once.

**Why `test-summary` has `if: always()`:** without it, if a suite job fails, `test-summary` (which `needs` that job) would be *skipped*, not failed — and a skipped required check doesn't block a merge the way a failed one does. `if: always()` makes it run anyway and explicitly `exit 1`, so it visibly fails instead of silently not running.

---

## Gaps found this session (not yet fixed, good "what would you improve" answers)

1. **`npm test` in CI doesn't pass `--coverage`**, so `jest.config.js`'s `coverageThreshold` is never enforced, and the coverage artifact upload is empty every run. Fix: `npm test` → `npm run test:ci` in `tests.yml`.
2. **`client.py`'s `close()` is never called** — `api_client` fixture in `conftest.py` has no teardown. Fix: add `client.close()` after `yield` in the fixture.
3. **`api-tests-python/pytest.ini` lacks `--strict-markers`** (the UI suite's `pytest.ini` has it) — a marker typo would silently warn instead of erroring.
4. **`client.py`'s error handling is coarser than `client.js`'s** — one generic `except Exception` instead of a deliberate split between "server responded with an error" and "no response at all."
5. **`networkidle` waits in `login_page.py`** — fine for Sauce Demo today, first place to check if UI tests get flaky later.
6. Broader, repo-level (from README): tests run against shared public infrastructure (reqres.in, Sauce Demo) rather than a controlled staging environment with resettable data.

## Changes actually made this session

- `.github/workflows/tests.yml` — added `--tracing=retain-on-failure` to UI smoke/regression steps.
- `README.md` — updated the Trace Viewer note to reflect it's now wired in.
- `api-tests/tests/reqres.test.js` — added `setHeader Tests` describe block (verified 401/403 behavior against live reqres.in first).
- `api-tests/utils/client-native.js` — new file, Axios-free comparison client (not used by any test).

## Proposed but not yet applied: Dockerization

- `api-tests/Dockerfile` — `node:18-slim`, `npm ci`, `CMD ["npm", "test"]`.
- `api-tests-python/Dockerfile` — `python:3.11-slim`, `pip install -r requirements.txt`, `CMD ["pytest", "-v", "--tb=short"]`.
- `ui-tests/Dockerfile` — `mcr.microsoft.com/playwright/python:v1.55.0-jammy` (matches pinned `playwright==1.55.0`) instead of plain Python + `playwright install --with-deps`, since the Microsoft image ships browsers + OS deps preinstalled.
- Root `docker-compose.yml` for one-command local runs per suite.
- CI change: replace `setup-node`/`setup-python`/install steps with `docker build` + `docker run` (with a volume mount for `allure-results` so results survive the container exiting).
- **Benefits:** environment consistency ("works on my machine" stops being a debugging step), reproducible CI failures locally, portable off GitHub Actions specifically.
- **Honest trade-off:** real overhead (build time, image maintenance) for a benefit that mostly pays off at team scale — not obviously worth it for a 4-test demo suite solo.

## Prepared answers for likely interview questions

**"How would you debug a flaky test?"**
Reproduce locally 3x first — passes consistently locally means it's environment-specific. Check the usual suspects: `networkidle` waits on UI side, shared/mutated test data or a silently-defaulting env var on API side (this repo hit exactly that with `REQRES_API_KEY` early on), too-tight timeouts under CI load. Isolate by running alone with no parallelism to rule out ordering dependencies. Fix the root cause (explicit wait, isolated fixture) rather than just retrying; a retry/flaky marker is only a stopgap while the real fix is pending.

**"How would this scale from 1 QA engineer to 5?"**
Split ownership by suite (API vs UI), PR review for test code same as production code. Parallelize CI further, add smoke/regression tagging everywhere (Node suite doesn't have this split yet). Move off shared public endpoints to a real staging environment with seeded, resettable data. Docker for consistency across machines. Host the Allure report somewhere with history (GitHub Pages) instead of per-run artifacts.

**"Why two languages for the same API tests?"**
Not a requirement — shows the test design (happy path + negative cases, reusable HTTP client wrapper) holds up across languages, not that I only know one framework.

**"What's the biggest weakness in this suite right now?"**
Testing against shared public infrastructure (reqres.in, Sauce Demo) instead of a controlled environment — fine for a demo, but in a real job I'd want seeded, resettable test data and no risk of another test run's state colliding with mine.

**"Isn't hardcoding a credential fallback a bad practice?"**
Normally yes — I did it here specifically because these are intentionally public demo credentials (Sauce Demo's own published test login, reqres.in's public free-tier key), not real secrets. Would never do this for an actual production secret.

**"Do you need cloud-based testing services for something like this?"**
Not at this scale — but I'd bring in specific ones for specific gaps if it grew: Codecov to fix the currently-broken/empty coverage reporting with PR-visible trend graphs; Microsoft Playwright Testing or BrowserStack/Sauce Labs if I needed real cross-browser/device coverage beyond headless Chromium; Currents.dev for flaky-test analytics if failure volume grew enough to need tooling instead of manual triage.

**"What's next after the CI pipeline goes green?"**
Right now it ends at "tests passed, here's an artifact." A mature pipeline would gate an actual deployment on it (auto-deploy to staging on merge, re-run smoke tests there), persist reports with history instead of per-run artifacts, notify a channel on failure, and track flaky tests over time instead of letting them erode trust silently.
