# ADR: An MCP-based agentic layer alongside the deterministic Playwright suite

## Status

Accepted (2026-08-26). Covers `agentic/mcp_client.py`, `agentic/agent_loop.py`,
and the first two agents, `agentic/agents/locator_healer.py` and
`agentic/agents/test_author.py`. See `AGENTIC_BUILD_LOG.md` for the
file-by-file build history.

## Context

`ui-tests/` is a deterministic Playwright/pytest suite: fixed page objects, fixed
locators, fixed assertions, run the same way every CI build. That's exactly what
a regression suite should be — but it has no mechanism for three related
problems that only an agent with a live browser and reasoning can solve:

1. **Locators drift.** A `data-test` attribute gets renamed upstream; a script
   fails with `TimeoutError` and gives no hint what the *new* selector should be.
2. **Writing a new test from a plain-English scenario** ("verify login shows an
   error for a locked-out user") still means a human opens the app, finds every
   selector by hand, and writes POM code — codegen tools record raw scripts, not
   maintainable POM-conforming test files.
3. **Nobody notices a flow silently changed** (an extra step added to checkout,
   a renamed button) until a scripted test fails in CI — after the fact, not
   before.

None of these are things `pytest`/`playwright` fixtures should try to solve —
they need something that can look at a page, reason about intent, and act. That
is an argument for an *agent*, not a bigger deterministic framework.

## Decision

### Why MCP here, instead of plain Playwright (or Playwright's own codegen)

Playwright's built-in `codegen` records a literal action script — click here,
type there — tied to whatever selectors happened to be under the cursor at
record time. It has no notion of "this element failed, find its replacement" or
"describe what you want in English." It's a recorder, not a reasoning loop.

What we actually need is: **a live browser an LLM can drive through a stable,
introspectable tool interface.** That's what Playwright MCP *is* — the same
Playwright engine, but exposed as a set of typed tools (`browser_navigate`,
`browser_snapshot`, `browser_click`, ...) an LLM can call directly via
tool-use, with `browser_snapshot` giving back an accessibility tree instead of
a screenshot, which an LLM can reason over as text. Using the MCP server means:

- We don't hand-roll a "let the LLM control Playwright" integration — Playwright
  MCP already handles browser lifecycle, tool schemas, and snapshot generation.
- The agent and the deterministic suite can each use a Playwright install
  independently (see `AGENTIC_BUILD_LOG.md`'s note on the MCP server's own
  bundled browser vs. `ui-tests/uv.lock`'s) without coupling their versions.
- Tools are introspectable and restrictable (`agentic/agent_loop.py`'s
  `allowed_tools`) — we can hand an agent exactly the 7 tools it needs and never
  the 17 it doesn't (including `browser_run_code_unsafe`, which the MCP server's
  own docstring calls "RCE-equivalent").

### Why a thin hand-rolled loop, not LangChain (or similar)

`agentic/agent_loop.py` is one ~60-line function: call Claude, execute whatever
tool it asks for via MCP, feed the result back, repeat until it stops asking.
That loop **is** the entire agent framework this repo has. A framework like
LangChain would add: its own tool-calling abstraction on top of Anthropic's
native one, a dependency surface with its own release cadence and breaking
changes, and a layer of indirection between "what the model asked for" and
"what actually got called" that makes debugging a failed agent run slower, not
faster. For three agents whose entire job is "call an LLM, run MCP tools it
asks for," a hand-rolled loop is more auditable, not less capable — every line
of control flow that runs is visible in one file.

### Where the human-in-the-loop gate sits

The two gates differ by agent, matched to what each one actually needs to do.
The locator healer never touches `ui-tests/` at all — `heal_locator()`
returns `(verdict, diff)` and `main()` prints both; no `Path.write_text()` on
an existing file, ever. Applying it means a human runs `git apply` (or pastes
the diff into an editor) and commits like any other change.

The test author's whole job is different — "emit a new test file" is the
deliverable, not a diff — so `test_author.py` *does* call
`Path.write_text()`, but only for a brand-new file (`main()` refuses to
overwrite an existing one without `--force`); it never modifies a file that
already exists. The gate for this one is downstream, not structural: the
generated file lands in the working tree same as anything else in this repo,
and nothing in this layer stages it, commits it, or pushes it — that's a
separate, deliberate human action (`git add`/`git commit`), same review step
every other change here goes through, and the CI workflow only ever runs
whatever's already been committed and pushed to `main`.

The same "propose, don't auto-commit" spirit will extend to the smoke-crawler
agent once built: it proposes a drift report, not a file; a human decides
whether it becomes anything at all.

### How this fits CI without touching the deterministic pipeline

`agentic/` is never invoked from `.github/workflows/tests.yml`. The three CI
jobs (`api-tests`, `api-tests-python`, `ui-tests`) run exactly what they ran
before this layer existed — `uv sync` (no `--extra agentic`) doesn't even
install `anthropic`/`mcp` into the CI environment, since they're an opt-in
dependency group. `agentic/mcp_config.json` is a separate file from the root
`.mcp.json` Claude Code's own session uses, and `agentic/.env.local` is
gitignored, so there's no shared state between "an agent ran locally" and "CI
ran." If/when the smoke-crawler agent is built, the plan is a *separate*,
manually- or schedule-triggered workflow that posts drift findings as an issue
or PR comment — never a required status check the deterministic suites depend
on. An agent run that fails, times out, or produces nonsense should never be
able to block or flake a regression build.

## Consequences

- **New optional dependency surface:** `anthropic`, `mcp`, and their transitive
  deps (see `AGENTIC_BUILD_LOG.md`) — folded into `ui-tests/pyproject.toml`'s
  `agentic` extra rather than a second lockfile/toolchain. `uv sync --extra
  agentic` opts in; plain `uv sync` (CI's path) doesn't.
- **A live ANTHROPIC_API_KEY is required to run any agent** — there is no offline
  mode. Cost is real (metered API usage) and scales with how often agents run;
  this is why none of them run on every CI push.
- **Two independent Playwright installs can exist on one machine**: the one
  `ui-tests/uv.lock` manages for pytest, and the one the Playwright MCP server
  manages for itself (`npx @playwright/mcp install-browser ...`). They were
  version-independent in practice during development (different Chromium
  builds) and that's fine — the agent layer never runs pytest, and the
  deterministic suite never talks to MCP.
- **Every agent's blast radius is capped by `allowed_tools`.** Adding a new
  agent means deciding its tool allow-list deliberately, not inheriting
  whatever the MCP server happens to expose.
