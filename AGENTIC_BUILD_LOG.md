# Agentic Layer Build Log

Running log of every change made while building the MCP-based agentic layer on top
of this repo, kept one file/step at a time per project convention. Each entry lists
what changed, why, and the exact commands run so the steps are reproducible and
reviewable individually. Newest entry at the bottom.

---

## 2026-08-25 — Pre-flight: repo audit

**Why:** goals doc referenced a `framework/` directory, ParaBank as the target app,
and `uv` for dependency management — none of which matched this repo. Confirmed via
clarifying questions before scaffolding anything.

**Findings:**
- No `framework/` dir. Real layout: `ui-tests/` (Python/Playwright + POM), `api-tests/`
  (Node/Jest), `api-tests-python/` (Python/pytest).
- `ui-tests/` targets Sauce Demo (saucedemo.com), not ParaBank.
- Dependency management was pip + `requirements.txt`, no `uv` anywhere.
- A root-level `.mcp.json` already existed (Claude Code's own session MCP config for
  `@playwright/mcp`, unrelated to the test framework) — left as-is.

**Decisions (from user):**
- Target app: Sauce Demo (use what's actually in the repo).
- `agentic/` lives at repo root, sibling to `ui-tests/`; generates/updates files under
  `ui-tests/tests/` and `ui-tests/pages/`.
- Migrate `ui-tests/` to `uv` first, as an isolated step, before creating `agentic/`.
- Root `.mcp.json` stays; `agentic/` gets its own separate `agentic/mcp_config.json`.

---

## 2026-08-25 — Step 1: Migrate `ui-tests/` from pip to `uv`

**Why:** agreed dependency manager for the new `agentic/` layer is `uv`; rather than
running two toolchains, `ui-tests/` (the only Python suite the agent layer touches)
was migrated first as its own reviewable step. `api-tests-python/` was deliberately
left on pip — out of scope, not requested.

**Files added:**
- `ui-tests/pyproject.toml` — 1:1 port of `ui-tests/requirements.txt`'s pinned
  versions (`pytest==7.4.3`, `playwright==1.55.0`, `pytest-playwright==0.9.0`,
  `python-dotenv==1.0.0`, `pytest-html==4.1.1`, `pytest-xdist==3.5.0`,
  `allure-pytest==2.16.0`), `requires-python = ">=3.11"`, `[tool.uv] package = false`
  (it's a test suite, not an installable library).
- `ui-tests/uv.lock` — generated lockfile, 29 resolved packages.

**Files removed:**
- `ui-tests/requirements.txt` — superseded by `pyproject.toml` + `uv.lock`.

**Files edited:**
- `.github/workflows/tests.yml` (`ui-tests` job) — replaced `actions/setup-python`
  + `pip install -r requirements.txt` with `astral-sh/setup-uv@v3` (pinned
  `version: '0.12.5'`, `enable-cache: true`,
  `cache-dependency-glob: 'ui-tests/uv.lock'`) + `uv python install 3.11` +
  `uv sync --locked`. All subsequent steps in that job (`playwright install`,
  smoke/regression `pytest` runs) prefixed with `uv run`.
- `README.md` — UI suite run command updated from
  `pip install -r requirements.txt && playwright install && pytest -v` to
  `uv sync && uv run playwright install && uv run pytest -v`.

**Commands run (local verification, from `ui-tests/`):**
```bash
uv lock                          # generate uv.lock from pyproject.toml
uv sync                          # create .venv, install all 28 resolved packages
uv run pytest --collect-only -q  # sanity-check test discovery still works
uv run playwright install chromium   # browser binary wasn't present in the new env yet
uv run pytest -v --tb=short -m smoke # 2 passed — real run against saucedemo.com
```

**Result:** `2 passed, 2 deselected in 11.24s`. `api-tests/` and `api-tests-python/`
untouched. `.venv/` already covered by existing `.gitignore` entry.

---

## 2026-08-26 — Step 2: `agentic/` package skeleton

*(in progress — filled in as each file lands)*

### File: `agentic/mcp_config.json`

**Why:** isolates the Playwright MCP server config used by our Python agent runner
from the root `.mcp.json` (Claude Code's own interactive session config). Different
consumers, different lifecycle — agents run headless/unattended, so this config
passes `--headless` explicitly; the root file (interactive Claude Code use) doesn't.
Keeps `pytest.ini`/`conftest.py` for the deterministic suite completely untouched.

**Content:** one `mcpServers.playwright` entry (stdio transport via `npx -y
@playwright/mcp@latest --browser chromium --headless`) plus a `defaultServer` key
so `mcp_client.py` has an unambiguous default when multiple servers are configured
later.

**Commands run:** none yet — no code reads this file until `mcp_client.py` (next file).

### File: `ui-tests/pyproject.toml` — added `agentic` optional-dependency group

**Why:** per user decision, agentic deps fold into the same `pyproject.toml`/`uv.lock`
as the deterministic UI suite rather than a second toolchain. Kept as an optional
group (`[project.optional-dependencies] agentic = [...]`) so a plain `uv sync` for
CI/deterministic runs never pulls in `anthropic`/`mcp` — only `uv sync --extra
agentic` does, opt-in for anyone actually running the agent layer.

**Added:** `anthropic>=0.40.0` (direct Anthropic API calls — no LangChain, per
constraint), `mcp>=1.2.0` (official Python MCP SDK, provides the stdio client used
by `mcp_client.py`).

**Commands run (from `ui-tests/`):**
```bash
uv lock                       # re-resolve with the new optional group (60 packages total)
uv sync --extra agentic       # install agentic extras into the same .venv
```

**Result:** resolved `anthropic==1.0.0`, `mcp==2.1.1` and transitive deps (httpx,
pydantic, jsonschema, sse-starlette, etc.) into `ui-tests/.venv` alongside the
existing pytest/playwright stack. `uv sync` (no `--extra`) still installs only the
original 28 packages — deterministic CI job is unaffected.

### File: `agentic/mcp_client.py`

**Why:** single place where the `mcp` SDK's stdio transport is wired up, so every
agent (locator healer, test author, smoke crawler) talks to a shared `MCPClient`
instead of each reimplementing connection/session handling. Also owns the one
non-obvious translation step: converting MCP's `Tool` schema (`name`,
`description`, `inputSchema`) into the `{name, description, input_schema}` shape
the Anthropic Messages API expects for its `tools` parameter — that's the seam
between "MCP server" and "LLM agent" the whole layer is built around.

**Design notes:**
- Installed `mcp` SDK is v2.1.1 — newer than any documentation I had memorized —
  so the actual installed API was inspected via `inspect.signature()` before
  writing this file (`StdioServerParameters`, `ClientSession`, `types.Tool`,
  `types.CallToolResult`) rather than guessing. Confirmed: `stdio_client()` is an
  async context manager yielding a 2-tuple `(read_stream, write_stream)`;
  `ClientSession` is itself an async context manager; tool results carry Python
  snake_case attributes (`result.is_error`, `result.content`,
  `tool.input_schema`) despite camelCase on the wire.
- `MCPClient.from_config()` reads `mcp_config.json`, so swapping/adding MCP
  servers later never touches this file.
- `call_tool()` raises `MCPToolError` on `isError=True` rather than returning a
  silent failure string — callers (agents) need to branch on success/failure.

**Commands run (real end-to-end smoke test, not just unit-level):**
```bash
where node                      # confirmed Node.js installed but not on this shell's PATH
                                 # (C:\Program Files\nodejs) — added to PATH for these commands only
npx --version && node --version # v11.17.0 / v24.19.0, confirmed working once PATH included nodejs dir

# scratch script: connect via MCPClient.from_config(), list_tools_as_anthropic(),
# then call_tool("browser_navigate", {"url": "https://www.saucedemo.com"})
.venv/Scripts/python.exe <scratch_script>.py
```

**Result (1st run):** connected, listed 24 real tools from the Playwright MCP
server (`browser_close`, `browser_navigate`, `browser_snapshot`, etc.). The
`browser_navigate` call failed with `MCPToolError` — correctly surfaced — because
the MCP server's own bundled Playwright install (separate from the one
`ui-tests/uv.lock` manages for pytest) didn't have its browser binary yet:
```
Error: Browser "chrome-for-testing" is not installed; expected executable at
...\ms-playwright\chromium-1237\chrome-win64\chrome.exe
```

**Fix:** `npx -y @playwright/mcp@latest install-browser chrome-for-testing`
(downloaded Chrome for Testing 152.0.7977.8 + headless shell, ~307MiB total).

**Result (2nd run):** clean success — `browser_navigate` returned a real
snapshot of saucedemo.com ("Swag Labs", page URL confirmed).

**Cleanup:** removed the `ui-tests/.playwright-mcp/` artifact directory the MCP
server writes snapshots/console logs to on every run, added `.playwright-mcp/` to
the root `.gitignore`, and deleted the throwaway scratch script (kept out of the
repo — this build log is the record of what it did).

### File: `agentic/agent_loop.py` (+ `agentic/__init__.py`)

**Why:** every agent (locator healer, test author, smoke crawler) needs the same
control flow — call Claude, execute whatever tool it asks for via `MCPClient`,
feed the result back, repeat until Claude stops calling tools. Factoring that into
one ~50-line function keeps every individual agent file small and keeps the
"why MCP + direct Anthropic API, not LangChain" architecture auditable in one
place, per the no-heavyweight-framework constraint.

**Design notes:**
- `anthropic` SDK installed is v1.0.0 — also newer than my training knowledge —
  so `Messages.create`'s signature and `ToolUseBlock`/`TextBlock` field shapes
  were inspected the same way as the `mcp` SDK before writing this. Confirmed
  `max_tokens`/`messages`/`model`/`system`/`tools` params and
  `response.content` blocks carry a `.type` discriminator (`"text"` vs
  `"tool_use"`) plus `.id`/`.name`/`.input` on tool-use blocks — matches the
  well-known Claude tool-use pattern.
- Tool failures (`MCPToolError` or a transport exception) are caught and fed back
  to Claude as an `is_error` tool_result instead of crashing the loop — an agent
  should get a chance to retry or explain itself, not die on the first bad
  selector.
- `AGENTIC_MODEL` env var overrides the default model (`claude-sonnet-5`) without
  a code change.
- `agentic/__init__.py` added (empty) so `agentic` and `agentic.agents` are
  regular packages, not implicit namespace packages — avoids edge cases with
  tooling that expects a real `__init__.py`.

**Commands run:**
```bash
python -c "import ast; ast.parse(open('agentic/agent_loop.py').read())"  # syntax check
python -c "import agentic.agent_loop as al; print(al.DEFAULT_MODEL)"     # import check
```
Both passed. **Not yet run end-to-end** — this environment has no
`ANTHROPIC_API_KEY` set, so the real Claude round-trip is unverified pending the
user supplying a key (asked, see conversation). MCP-side plumbing (`MCPClient`)
is already proven live in the previous step.

### File: `agentic/.env.example` + dotenv loading in `agent_loop.py`

**Why:** decided to store the Anthropic key in `agentic/.env.local`, mirroring the
existing `ui-tests/.env.example` → `.env.local` convention rather than requiring
the key be exported manually every session. `python-dotenv` is already a base
dependency (`ui-tests/pyproject.toml`, shared by both `ui-tests` and `agentic`),
so no new package was needed.

**Content:** `agentic/.env.example` documents `ANTHROPIC_API_KEY` (with a link to
where to generate one — console.anthropic.com/settings/keys) and the optional
`AGENTIC_MODEL` override. `agent_loop.py` now calls `load_dotenv()` on
`agentic/.env.local` at import time if it exists, same pattern as
`ui-tests/conftest.py`.

**Gitignore:** already covered — root `.gitignore`'s existing `.env.local` /
`.env.*.local` patterns match at any depth, so `agentic/.env.local` never needs
its own entry.

**Commands run:** none yet — real key not supplied to this session. User will
create `agentic/.env.local` (gitignored, never committed) locally.

### File: `agentic/agent_loop.py` — added `allowed_tools` allow-listing

**Why:** discovered while designing the locator healer that Playwright MCP
exposes 24 tools, including `browser_run_code_unsafe` ("RCE-equivalent",
per its own tool description), file upload/drop, tab management, etc. An
autonomous agent has no business seeing tools irrelevant or dangerous for its
specific task. Added `allowed_tools: list[str] | None` to `run_agent_loop()`:
filters what the model is shown *and* re-checked before executing any tool call
the model requests (defense in depth against the model naming a tool it wasn't
offered). Every future agent should pass the narrowest tool set its task needs.

**Commands run:** `ast.parse()` syntax check only (no live call).

### Real finding that shaped the design: accessible names are ambiguous

Before writing the healer, ran two manual probes against the live Playwright MCP
server (`browser_navigate` + `browser_snapshot`) to understand what the
accessibility snapshot actually exposes:
- Saucedemo login page: fields expose clean roles/names (`textbox "Username"`,
  `textbox "Password"`, `button "Login"`) — no raw CSS/data-test attributes are
  visible in the accessibility tree, only role + accessible name + an ephemeral
  session-scoped `ref`.
- Saucedemo inventory page (after logging in via `browser_fill_form` +
  `browser_click`): **every** "Add to cart" button across all 6 products has the
  identical accessible name `"Add to cart"` — role+name alone cannot disambiguate
  which product's button is which.

**Implication for the design:** a role-based locator like
`role=button[name="Add to cart"]` would be genuinely wrong here — it matches all
6 buttons, not just the backpack's. This is why the healer's system prompt
requires falling back to `browser_evaluate` (explicitly scoped to read-only
DOM queries — never `browser_run_code_unsafe`) to re-derive the same kind of
stable, product-specific attribute (`data-test`, `data-testid`, `id`) the
existing POM convention already uses, only reading it fresh from the live DOM
instead of trusting the old/broken value.

### File: `agentic/agents/__init__.py` + `agentic/agents/locator_healer.py`

**Why:** the self-healing locator agent — start here per user's original ROI
call-out. Given a POM class + locator constant name, it drives the live page via
MCP tools, re-locates the element per the strategy above, and returns a unified
diff against the POM file. It never writes to the POM file — human review gate
first, matching the "propose a diff, not an auto-commit" requirement.

**Design notes:**
- `ALLOWED_TOOLS` restricted to 7: navigate, snapshot, find, fill_form, click,
  evaluate, wait_for. No file upload, drag/drop, tab management, or
  `browser_run_code_unsafe`.
- `find_locator()` uses `ast.parse()` (not regex) to find the exact
  `CONST_NAME = "value"` assignment inside the named class — gets the precise
  line number needed for a correct diff, and only matches string constants, not
  arbitrary expressions.
- `build_healed_line()` preserves original indentation and quote style when
  substituting the new value, and switches quote character automatically if the
  new value contains the original quote (e.g. a value containing `'` gets
  wrapped in `"`).
- `extract_json()` tolerates the model wrapping its final JSON answer in a
  \`\`\`json fence, since models don't always follow "no markdown" perfectly.
- The system prompt encodes the accessible-name-ambiguity finding directly:
  step 3 explicitly tells the agent accessible names can collide and to use
  `browser_evaluate` (read-only only) to disambiguate and recover a stable
  attribute.

**Bug fixed during self-testing:** `build_diff()` initially had a dead,
nonsensical line left over from drafting
(`new_lines[...] = build_healed_line(...).__class__ and new_lines[...]`) that
did nothing — cleaned up to just build the healed line once, using
`site.const_name` (added to the `LocatorSite` dataclass) instead of re-deriving
the constant name via a fragile `line.split("=")[0]`. Also fixed
`difflib.unified_diff` output: content lines from `splitlines(keepends=True)`
already carry `"\n"`, but header/hunk lines don't (`lineterm=""`) — naively
joining with `"".join(...)` mashed the `---`/`+++`/`@@` header lines together
with no separator. Fixed by stripping every line's trailing newline and
rejoining with `"\n"` uniformly.

**Commands run (pure-logic verification, no API key needed):**
```bash
python -c "import ast; ast.parse(open('agentic/agents/locator_healer.py').read())"  # syntax check

# scratch script exercising, against the REAL ui-tests/pages/inventory_page.py:
#   find_locator(source, "InventoryPage", "ADD_TO_CART_BUTTON")
#   build_healed_line(...) with a substitute value
#   build_diff(...) and asserting the unified diff contains the expected -/+ lines
#   extract_json() on both a plain JSON string and a ```json-fenced one
```
**Result:** all assertions passed; diff output confirmed readable (correct
`---`/`+++`/`@@` headers, correct `-`/`+` lines, unrelated lines unchanged).

**Not yet run end-to-end** (the actual Claude tool-use loop driving a live
browser to heal a real broken locator) — pending `ANTHROPIC_API_KEY` in
`agentic/.env.local`. Everything it depends on (`MCPClient`, `run_agent_loop`,
the pure diff/AST logic) is independently verified live/tested above.

### File: `agentic/ADR.md`

**Why:** the requested ADR-style doc covering why MCP vs. plain
Playwright/codegen, where the human-in-the-loop gate sits, and how this avoids
polluting the deterministic CI pipeline. Written while waiting on the API key
since it doesn't depend on a live run — captures the reasoning made during
`mcp_client.py`/`agent_loop.py`/`locator_healer.py` while it's fresh, rather
than reconstructed after the fact.

**Commands run:** none — documentation only.

---

## 2026-08-26 — Option 3: `agentic-claude-code/`, a fully separate implementation

**Why a whole separate folder, not a flag/mode inside `agentic/`:** user
explicitly asked to explore running the locator healer with no separate
Anthropic API key — using this Claude Code session itself as the reasoning
engine instead of `agent_loop.py`'s standalone Claude API call — and asked
that it be kept structurally separate from the existing implementation, not
mixed in. Nothing in `agentic/` was changed or removed; this is a new sibling
directory plus one new skill file.

### File: `agentic-claude-code/mcp_bridge.py`

**Why:** the one real technical wrinkle in "let Claude Code drive the browser
directly" — Claude Code issues shell commands one Bash call at a time, and a
single MCP tool call per Bash invocation would spawn a brand-new, memory-less
browser each time (login and navigation state lost between calls). This
script instead takes a whole **ordered plan** of MCP tool calls (a JSON file)
and executes all of them against one persistent browser session, printing
every result — Claude Code decides the full plan upfront (informed by real
exploration, not guesswork) and reads the combined output afterward to reason
about next steps.

**Design notes:**
- Deliberately does **not** import anything from `agentic/mcp_client.py`,
  despite doing a similar (smaller) job — connects to the MCP server directly
  using the same `mcp` SDK primitives, so this folder has zero code coupling
  to the other implementation, per the user's separation request.
- No `anthropic` import anywhere in this file or this folder.

**Commands run (smoke test before the real run):**
```bash
export PATH="/c/Program Files/nodejs:$PATH"
ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py <2-step plan: navigate + snapshot>
```
**Result:** confirmed state persists correctly across steps in one run (page
URL after navigate matched the snapshot's page URL).

### File: `agentic-claude-code/mcp_config.json`

**Why:** own copy of the Playwright MCP server config (identical content to
`agentic/mcp_config.json`), duplicated rather than shared, for the same
separation reason as `mcp_bridge.py`.

### File: `agentic-claude-code/pom_diff.py`

**Why:** turns a healed locator value into a unified diff against the POM
file — the same ~40 lines of AST-parsing + diff-building logic that live in
`agentic/agents/locator_healer.py` (`find_locator`, `build_healed_line`,
`build_diff`), intentionally duplicated rather than imported so this folder
never depends on `agentic/`. Never writes to the POM file — only prints a
diff, same human-review gate as the standalone agent.

**Design difference from the `agentic/` version:** simpler CLI —
`--pom --class-name --locator --new-value` — because there's no agent loop
producing a JSON verdict to parse; Claude Code (the reasoning engine) already
knows the healed value by the time this runs, so it's passed straight in.

### File: `agentic-claude-code/examples/heal_add_to_cart_button.steps.json`

**Why:** the actual plan used for the real run below, saved as a documented
example rather than a throwaway scratch file, so the exact sequence (login →
navigate → snapshot → scoped read-only DOM query) is visible and re-runnable.

### File: `.claude/skills/heal-locator-cc/SKILL.md`

**Why:** packages the manual procedure below into a reusable, documented
recipe — a future Claude Code session (or the user, via `/heal-locator-cc`)
can follow it without re-deriving the approach from scratch. Explicitly
documents the accessible-name-ambiguity lesson from the `agentic/` build
(every "Add to cart" button shares one accessible name — must scope by a
sibling locator already in the POM, like `.inventory_item`) and the same tool
safety rule (`browser_evaluate` read-only only, never `browser_run_code_unsafe`).

### The real, live run (real site, real already-broken file, zero API cost)

The user had already manually broken the real
`ui-tests/pages/inventory_page.py` line 14 to:
```python
ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack-OLD-RENAMED']"
```
(original value preserved as a comment on line 13 above it).

**Command run:**
```bash
export PATH="/c/Program Files/nodejs:$PATH"
cd /c/projects/BH-E2E-Tests
ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py \
  agentic-claude-code/examples/heal_add_to_cart_button.steps.json
```

**What the plan did:** navigated to saucedemo.com, logged in
(`standard_user`/`secret_sauce`) via `browser_fill_form` + `browser_click`,
landed on `/inventory.html`, took a `browser_snapshot` (confirmed: all 6
products' "Add to cart" buttons share the identical accessible name — same
ambiguity problem found during the `agentic/` build), then ran one read-only
`browser_evaluate`:
```js
() => {
  const container = Array.from(document.querySelectorAll('.inventory_item'))
    .find(el => el.textContent.includes('Sauce Labs Backpack'));
  if (!container) return { found: false, reason: 'container not found' };
  const btn = Array.from(container.querySelectorAll('button'))
    .find(b => /add to cart/i.test(b.textContent));
  if (!btn) return { found: false, containerFound: true, reason: 'button not found in container' };
  return { found: true, dataTest: btn.getAttribute('data-test'), id: btn.id || null,
           classes: btn.className || null, text: btn.textContent.trim() };
}
```
scoped using `.inventory_item` — the same CSS class already defined as
`InventoryPage.PRODUCT_ITEM` in the real POM file, read beforehand for
grounding instead of guessing a class name blindly.

**Result — the real answer, straight from the live DOM:**
```json
{"found": true, "dataTest": "add-to-cart-sauce-labs-backpack", "id": "add-to-cart-sauce-labs-backpack",
 "classes": "btn btn_primary btn_small btn_inventory ", "text": "Add to cart"}
```
(The live site itself was never actually changed — only the local POM file
was deliberately corrupted to simulate drift — so the recovered value
correctly matches the site's real, original attribute.)

**Diff generation command:**
```bash
ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
  --pom "ui-tests/pages/inventory_page.py" \
  --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON \
  --new-value "button[data-test='add-to-cart-sauce-labs-backpack']"
```

**Result — the actual diff produced (not applied):**
```diff
--- ui-tests\pages\inventory_page.py
+++ ui-tests\pages\inventory_page.py
@@ -11,7 +11,7 @@
     PRODUCT_ITEM = ".inventory_item"
     PRODUCT_NAME = ".inventory_item_name"
     # ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack']"
-    ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack-OLD-RENAMED']"
+    ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack']"
     REMOVE_FROM_CART_BUTTON = "button[data-test='remove-sauce-labs-backpack']"
     CART_BADGE = ".shopping_cart_badge"
     CART_LINK = ".shopping_cart_link"
```

**Cleanup:** removed the `.playwright-mcp/` artifact directory the MCP server
wrote during this run (already gitignored from the earlier `agentic/` work).

**Cost:** $0 in Anthropic API usage — the reasoning (deciding the plan,
scoping the DOM query, reading the results, deciding the diff was correct)
was done by this Claude Code session under the user's existing subscription;
`mcp_bridge.py`/`pom_diff.py` never call any LLM.

### File: `agentic-claude-code/README.md`

**Why:** the plain-English map for this variant, mirroring `agentic/README.md`
in structure (big picture, file-by-file table, how a real run happened) so
the two implementations can be compared side by side without either one
referencing or depending on the other.

**Commands run:** none — documentation only.

## 2026-08-26 — Live demo attempt: blocked on Anthropic account billing

**Command run** (from repo root, `node`/`npx` added to PATH for this shell):
```bash
export PATH="/c/Program Files/nodejs:$PATH"
cd /c/projects/BH-E2E-Tests
ui-tests/.venv/Scripts/python.exe -m agentic.agents.locator_healer \
  --pom "<scratch copy of inventory_page.py>" \
  --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON \
  --description "the Add to cart button for the Sauce Labs Backpack product on the inventory/products page" \
  --url "https://www.saucedemo.com/inventory.html" \
  --login-url "https://www.saucedemo.com" \
  --username standard_user \
  --password secret_sauce
```

**Break used for the demo:** a scratch copy of `ui-tests/pages/inventory_page.py`
(never the real file — agents don't touch POM files) had line 13 changed from
```python
ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack']"
```
to
```python
ADD_TO_CART_BUTTON = "button[data-test='add-to-cart-sauce-labs-backpack-OLD-RENAMED']"
```
simulating the site renaming its `data-test` attribute.

**Result:** confirmed `agentic.agents.locator_healer` runs as a module from
repo root (must `cd` to repo root first — `agentic` doesn't resolve as a
package from inside `ui-tests/`), `.env.local` loads correctly, and the script
reached a real Anthropic API call — i.e. everything except the actual model
call is proven working. The call itself failed:
```
anthropic.BadRequestError: Error code: 400 - Your credit balance is too low to
access the Anthropic API. Please go to Plans & Billing to upgrade or purchase
credits.
```

**Root cause:** account-level billing, not a code defect. The user's Claude
Pro/Claude Code subscription does not cover this — `agent_loop.py` calls the
Anthropic Developer Platform API directly with `ANTHROPIC_API_KEY`, which is a
separate metered product from claude.ai/Claude Code subscriptions, billed on
its own credit balance (console.anthropic.com → Settings → Billing).

**Not fixed yet — waiting on user to fund the API account.** No code changes
needed once that happens; the exact command above (with `--pom` pointed at
the real `ui-tests/pages/inventory_page.py` once it's actually broken) is
ready to re-run as-is.

### File: `agentic/README.md`

**Why:** user asked for a consolidated plain-language explanation of the big
picture, why each file exists, and the three ways "the agent's brain" could be
built (the hand-written loop already in place, LangChain, or running inside
Claude Code itself) — with pros/cons — surfaced while troubleshooting the
billing block above. `ADR.md` covers the formal architecture rationale and
this build log covers chronological history; `README.md` is the plain-English
entry point tying both together, plus a file-by-file map and the exact
runnable demo command.

**Commands run:** none — documentation only.

---

## 2026-08-26 — First real `/heal-locator-cc` invocation: `REMOVE_FROM_CART_BUTTON`

User broke a second real locator and invoked the skill directly via
`/heal-locator-cc` with just plain English ("remove from cart button on
inventory page is not working. needs login, use standard_user/secret_sauce")
— no file path, class name, or current value given; all found by reading
`ui-tests/pages/inventory_page.py` per the skill's procedure. Found at
[inventory_page.py:15](../ui-tests/pages/inventory_page.py#L15):
```python
REMOVE_FROM_CART_BUTTON = "button[data-test='remove-sauce-labs-backpack-OLD']"
```

**Extra wrinkle this locator has that `ADD_TO_CART_BUTTON` didn't:** Sauce
Demo's "Remove" button only exists *after* a product is already in the cart —
so the plan needed an extra step (add the backpack to cart first) before the
button to heal even exists on the page.

### Real problem hit and diagnosed live: MCP's synthetic click silently no-op'd

First plan (`examples/heal_remove_from_cart_button.steps.json`: login → click
`button[data-test='add-to-cart-sauce-labs-backpack']` → snapshot → evaluate)
ran with no errors, but the follow-up snapshot showed the button still said
"Add to cart" — the click had no effect. Investigated with four follow-up
scratch plans (each deleted after use), in order:
1. `browser_console_messages` before/after the click — no real errors (only a
   pre-existing autocomplete-attribute warning).
2. `browser_wait_for` on the text "Products" before clicking, and on "Remove"
   after — the "Remove" wait timed out at 5s, proving the click truly had no
   effect, not just a timing race.
3. Read-only `browser_evaluate` checking `elementFromPoint` at the button's
   center — confirmed the button itself was on top (no covering overlay) and
   not disabled.
4. Clicking via a **fresh snapshot ref** (`e54`) instead of a CSS selector —
   the MCP server's own trace showed it resolves to the identical underlying
   Playwright locator, so this wasn't actually a different code path.
5. A plain multi-second `browser_wait_for {"time": ...}` before and after the
   click (ruling out JS hydration timing) — still no state change.

**Root-caused with one diagnostic exception to the "evaluate must stay
read-only" rule:** ran `element.click()` (the raw DOM method) inside
`browser_evaluate` — this immediately worked: cart badge became `"1"`, button
text became `"Remove"`, real `data-test` read back as
`remove-sauce-labs-backpack`. Confirms the *app* and the *element* are both
fine — the issue is specifically Playwright MCP's synthetic mouse click not
registering on this element in this headless session. Documented as a known
issue directly in `.claude/skills/heal-locator-cc/SKILL.md` (with the
sanctioned one-off diagnostic technique) so a future run doesn't have to
re-derive this from scratch.

**Cross-checked against the existing deterministic suite:** confirmed
`ui-tests/tests/test_login_flow.py:92` calls
`inventory_page.add_product_to_cart(add_to_cart_btn)` using this exact
selector via normal `pytest-playwright` (not MCP), and that test passed
during the earlier `uv` migration verification — proving this is an MCP-click
quirk, not an app bug or a bad locator.

**Diff generated:**
```bash
ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
  --pom "ui-tests/pages/inventory_page.py" \
  --class-name InventoryPage \
  --locator REMOVE_FROM_CART_BUTTON \
  --new-value "button[data-test='remove-sauce-labs-backpack']"
```
```diff
-    REMOVE_FROM_CART_BUTTON = "button[data-test='remove-sauce-labs-backpack-OLD']"
+    REMOVE_FROM_CART_BUTTON = "button[data-test='remove-sauce-labs-backpack']"
```

**Cost:** $0 — same as the first `agentic-claude-code` run. **Cleanup:** all
scratch diagnostic `.steps.json` files deleted, `.playwright-mcp/` artifact
directory removed.

**New permanent file:**
`agentic-claude-code/examples/heal_remove_from_cart_button.steps.json` — kept
as a second documented example, distinct from the first one in that it needs
a state-changing action (add to cart) before the target element even exists.

---

## 2026-08-28 — GitHub push: baseline + full history reconstruction

Pushed to `github.com/ramanwaliagithub/BH-E2E-Test-MCP-Agents` on branch
`main`, as two phases per user request: a baseline commit representing the
repo exactly as it was before any MCP/agentic work, then the real
step-by-step history layered on top as separate reviewed commits.

**Environment note discovered mid-task:** this session's working directory
resolves to `D:\Work\Github\BH-E2E-Tests` — a different path from
`C:\projects\BH-E2E-Tests`, which every earlier command in this log used.
Both pointed at the same underlying files (some drive alias/mount from the
prior environment), but that alias is not present in this shell — confirmed
by `ui-tests/.venv` referencing a now-nonexistent interpreter path
(`C:\Users\rwalia\...`) under a different Windows user account than this one
(`hp`). Fixed by deleting and recreating `.venv` via `uv sync --extra
agentic` in this environment — a pure build-artifact rebuild, already
gitignored, no source impact. Re-verified `MCPClient` still connects
(24 tools) after the rebuild. All file paths in this log from this point on
use `D:\Work\Github\BH-E2E-Tests`.

**Baseline commit** (`edeb175`): temporarily reverted 5 files to their exact
pre-MCP content — `README.md`, `.github/workflows/tests.yml`, `.gitignore`,
`ui-tests/pages/inventory_page.py` (real, unbroken locators), and recreated
the deleted `ui-tests/requirements.txt` — reversing my own earlier `Edit`
calls exactly (old_string/new_string swapped) rather than retyping from
memory, for byte-perfect accuracy. New-only content (`agentic/`,
`agentic-claude-code/`, `.claude/skills/`, `AGENTIC_BUILD_LOG.md`,
`ui-tests/pyproject.toml`/`uv.lock`) simply stayed untracked — never moved or
deleted. Took a full working-tree backup to the scratchpad first as a safety
net; diffed all 3 non-locator files against it afterward to confirm
byte-perfect restoration to final state.

**Branch name:** user chose `main` over `master` (which `tests.yml` already
hardcoded) — folded the trigger-branch update into the uv-migration commit
since both touch the same file, with a note in that commit's message.

**Locator state decision:** user chose to keep both `ADD_TO_CART_BUTTON` and
`REMOVE_FROM_CART_BUTTON` broken in the final pushed history (not restore
them) — each break now lands in the commit where it chronologically
happened (`ADD_TO_CART_BUTTON` with the locator-healer agent commit,
`REMOVE_FROM_CART_BUTTON` with the agentic-claude-code commit), original
value preserved as a comment above each, matching the existing pattern.

**7 layered commits after the baseline**, one per real development step,
each shown for review (diff stat + proposed message) and pushed individually
per user's chosen cadence:
1. `dddb757` uv migration (+ branch trigger fix)
2. `464a4fe` agentic/ MCP client + config
3. `7b0c026` agent_loop.py
4. `eaedad9` locator_healer.py + ADD_TO_CART_BUTTON break
5. `f97a742` agentic/ ADR + README
6. `26ea4d3` agentic-claude-code/ + heal-locator-cc skill + REMOVE_FROM_CART_BUTTON break
7. `b500174` root README pointer + this build log

**Verification after every push:** `git check-ignore agentic/.env.local`
before the first commit, and after the last commit,
`git log --all --full-history -- "**/.env.local"` returned empty — confirmed
the real API key was never staged in any commit.

**One transient issue:** `git push` failed twice with
`Could not resolve host: github.com` while `curl`/`gh api` both succeeded
against the same host — resolved itself on retry (`GIT_CURL_VERBOSE=1 git
ls-remote` showed a normal successful connection); no config change needed.

---

## 2026-08-28 — Second agent: `agentic/agents/test_author.py`

Original goals asked for three agents in `agentic/`: the self-healing locator
agent (built), a natural-language test-authoring agent, and an exploratory
smoke-crawler agent. This is the second one. Not yet run live — same blocker
as the locator healer (`agentic/.env.local`'s Anthropic account still has no
funded credit balance) — but the pure logic is built and tested.

**Why it needed no new infrastructure:** reuses `agent_loop.py` and
`mcp_client.py` exactly as-is — the only new work is (1) grounding the model
in this repo's *real* conventions instead of letting it invent plausible-
looking ones, and (2) turning its final answer into a validated file.

**Design:**
- `gather_pom_conventions()` reads the actual `ui-tests/pages/*.py`,
  `conftest.py`, `pytest.ini`, and `test_login_flow.py` (as a style
  reference) from disk and hands them to the model verbatim — so it can't
  invent a Page Object method, fixture, or marker that doesn't exist. Stays
  accurate automatically as the real POM evolves, since nothing is
  hardcoded.
- System prompt requires the agent to **walk the scenario live first** (same
  navigate/login/click/snapshot tools as the locator healer) before writing
  anything, and to verify any raw selector it falls back to (this repo's own
  precedent: `add_product_to_cart("button[data-test='...']")` with a literal
  selector, not a wrapped method) against the live DOM rather than memory —
  same "ground truth over guesswork" principle as `locator_healer.py`.
- Explicitly forbidden from inventing new Page Object classes/methods; told
  to leave a comment instead if the scenario genuinely needs one.
- `extract_python_code()` pulls the fenced ` ```python ` block from the final
  answer; `author_test()` then runs the result through `ast.parse()` before
  ever writing a file — a syntactically invalid generation fails loudly
  instead of landing a broken test file in `ui-tests/tests/`.
- `main()` refuses to overwrite an existing test file unless `--force` is
  passed.

**Commands run (pure-logic verification only, no API key needed):**
```bash
python -c "import ast; ast.parse(open('agentic/agents/test_author.py').read())"  # syntax check

# scratch script:
#   gather_pom_conventions(ui_tests_dir) against the REAL ui-tests/ files —
#     asserted it actually contains "class LoginPage", "class InventoryPage",
#     "env_config", and the pytest markers
#   extract_python_code() on a fenced block (succeeds) and on text with no
#     fenced block (raises ValueError as expected)
#   ast.parse() on deliberately invalid Python (raises SyntaxError as expected)
```
**Result:** all assertions passed. Also re-verified `MCPClient` connects live
(24 tools) after the `.venv` rebuild above — confirms the shared MCP
infrastructure this agent depends on is unaffected.

**Not yet run end-to-end** — pending a funded `ANTHROPIC_API_KEY`, same as
`locator_healer.py`. Planned demo scenario once unblocked: "add the Sauce
Labs Backpack and the Bike Light to the cart, then verify the cart shows 2
items" — a real scenario not already covered by `test_login_flow.py`.
