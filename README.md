# BigHappy E2E Test Automation Suite

End-to-end test automation covering a public REST API (reqres.in) and a public web app (Sauce Demo), with CI running both suites on every push/PR.

- **API Testing (Node.js/Jest):** primary backend suite against [reqres.in](https://reqres.in) — happy path + negative cases
- **API Testing (Python/pytest):** same coverage, written in Python — kept as a bonus to show the suite design translates across languages, not a requirement
- **UI Testing (Python/Playwright):** full login → add to cart → checkout flow + negative cases against [saucedemo.com](https://www.saucedemo.com)

## Why These Targets and Frameworks

**ReqRes.in + Node.js/Jest** — ReqRes is a public sandbox that returns realistic REST responses (status codes, pagination, created/updated timestamps) without needing real credentials. Jest/axios is a standard, low-ceremony combo for HTTP-level testing in a JS stack.

**Sauce Demo + Python/Playwright** — Sauce Demo is just a stable demo site for automation practice; the real choice here is Playwright, picked over Selenium for what it brings once a suite has to survive unattended in CI, not just run by hand:

- **Auto-waiting** — every action blocks until its element is visible, stable, and actually interactive before firing, instead of racing the page. This alone removes a whole class of flaky UI tests before they start (no manual `sleep()`/polling).
- **Trace Viewer** — CI runs UI tests with `--tracing=retain-on-failure` (a pytest-playwright CLI flag), capturing a full per-test timeline on failure: DOM snapshots, network calls, console logs, and a screenshot per action, saved under `ui-tests/test-results/` and picked up by the existing `ui-test-results` artifact upload. A CI failure can be diagnosed from the trace file alone, without reproducing it locally. View it with `playwright show-trace <trace.zip>` after downloading the artifact.
- **Network interception/monitoring** — `page.route()` and `page.on("request"/"response")` let tests mock backend responses or assert on the actual calls the frontend made, not just what ends up rendered. Useful once UI tests need to isolate frontend bugs from backend ones.
- **One API, three browser engines** — Chromium, Firefox, and WebKit share the same API. CI only installs Chromium here for speed (see CI/CD below), but cross-browser coverage is a config change, not a rewrite.

Python specifically because it's the language most QA orgs already standardize on for automation scripting, and this suite already leans on its pytest plugin ecosystem (`pytest-xdist` for parallelism, `allure-pytest` for reporting, `pytest-playwright` for the browser lifecycle itself) rather than hand-rolling any of that. Page Object Model keeps locators out of the test logic so the suite stays maintainable as more flows are added.

## Project Structure

```
├── api-tests/            # Node.js API tests (Jest)
│   ├── jest.config.js
│   ├── utils/client.js
│   └── tests/reqres.test.js
├── api-tests-python/     # Python API tests (pytest + requests)
│   ├── api/client.py
│   └── tests/test_reqres.py
├── ui-tests/             # Python Playwright tests
│   ├── pages/            # Page Object Model
│   └── tests/test_login_flow.py
└── .github/workflows/tests.yml   # CI pipeline
```

## Running the Project

| Suite | Commands |
|---|---|
| API — Node.js | `cd api-tests && npm install && npm test` |
| API — Python | `cd api-tests-python && pip install -r requirements.txt && pytest -v` |
| UI — Playwright | `cd ui-tests && pip install -r requirements.txt && playwright install && pytest -v` |

Each suite has a `.env.example` — copy to `.env.local` to override defaults (public demo credentials / reqres.in's public demo API key, both safe to keep as-is).

## CI/CD Pipeline

`.github/workflows/tests.yml` runs on every push/PR to `master`/`develop`:

1. `api-tests`, `api-tests-python`, and `ui-tests` run in parallel, each uploading test output and Allure results as artifacts.
2. `test-summary` posts a pass/fail table to the run summary and fails the build if any suite failed.
3. `allure-report` merges all three suites' results into one HTML Allure report and uploads it as an artifact.

**Viewing the Allure report:** download the `allure-report` artifact, unzip it, then run `allure open <folder>` (or `python -m http.server` inside it). Double-clicking `index.html` won't work — Allure loads data via `fetch()`, which browsers block under `file://`.

## Triaging a Flaky Test

1. **Reproduce locally, 3 runs in a row** (`npm test` / `pytest -v -k test_name`). Passes consistently locally → environment-specific, not a real bug in the test.
2. **Check the usual suspects:**
   - UI: this suite's page objects (`login_page.py`, `inventory_page.py`) call `wait_for_load_state("networkidle")` after navigation and clicks. Fine on a static site like Sauce Demo, but it's the first thing I'd audit on intermittent timeouts — `networkidle` never resolves on pages with recurring background requests. Fix: wait on the specific element the next step needs (`expect(locator).to_be_visible()`) instead of a network-level heuristic.
   - API: shared/mutated test data, or a missing env var silently falling back to something unexpected (this repo hit exactly that with `REQRES_API_KEY` early on).
   - Both: too-tight timeouts under CI load — bump the timeout config before assuming it's the test's fault.
3. **Isolate:** run the test alone, disable parallelism, check for hidden ordering dependencies between tests.
4. **Fix and mark:** fix the root cause (explicit wait, isolated fixture, etc.) rather than just retrying; only add a retry/flaky marker as a stopgap while the real fix is pending.

## Scaling from 1 QA Engineer to 5

- **Ownership:** split by suite/domain (API vs. UI) instead of one person owning everything; add PR review for test code, same as production code.
- **CI:** parallelize suites (already true here), add smoke vs. full-regression tagging so every commit doesn't run everything, schedule slower/extended runs overnight.
- **Environments:** move off shared public demo endpoints to a proper staging environment with seeded, resettable test data — five people hitting reqres.in/Sauce Demo's shared state at once is a race condition waiting to happen.
- **Consistency:** Docker for both toolchains so "works on my machine" stops being a debugging step; a shared fixtures/test-data library instead of everyone rebuilding their own.
- **Visibility:** host the Allure report somewhere with history (e.g. GitHub Pages) instead of a per-run artifact, and add a flaky-test dashboard once failure volume makes it worth tracking.
