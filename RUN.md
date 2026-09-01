# Running the Agentic Layer

How to actually run `agentic/` and `agentic-claude-code/` — setup, commands
for all three agents in both implementations, and a set of practices worth
following any time you're running LLM agents against a real codebase, not
just in this repo.

---

## One-time setup (both implementations share this)

```bash
# From the repo root. Node/npx must be on PATH — on Windows, if it isn't:
export PATH="/c/Program Files/nodejs:$PATH"

cd ui-tests
uv sync --extra agentic          # installs anthropic, mcp, plus the base test deps
uv run playwright install chromium   # the browser pytest itself drives
cd ..

# The Playwright MCP server manages its own separate browser install —
# needed once per machine/user account:
npx -y @playwright/mcp@latest install-browser chrome-for-testing
```

**If you're on a new machine or user account and `ui-tests/.venv` already
exists but errors with "did not find executable at ...":** it was built
under a different environment. Just rebuild it — it's a gitignored build
artifact, not source:
```bash
rm -rf ui-tests/.venv
cd ui-tests && uv sync --extra agentic && cd ..
```

All commands below assume you're running from the **repo root**, using
`ui-tests/.venv/Scripts/python.exe` as the interpreter (not a bare `python`).

---

## Running `agentic/` (standalone, own Anthropic API key)

Needs a funded Anthropic account. Get a key at
console.anthropic.com → Settings → API Keys, add billing under Settings →
Billing (separate from any claude.ai/Claude Code subscription — this is
metered API usage), then:

```bash
cp agentic/.env.example agentic/.env.local
# edit agentic/.env.local, set ANTHROPIC_API_KEY=sk-ant-...
```

**Self-healing locator agent** — requires a locator to actually be broken
first (both `ADD_TO_CART_BUTTON` and `REMOVE_FROM_CART_BUTTON` already are,
in this repo, on purpose):
```bash
ui-tests/.venv/Scripts/python.exe -m agentic.agents.locator_healer \
  --pom "ui-tests/pages/inventory_page.py" \
  --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON \
  --description "the Add to cart button for the Sauce Labs Backpack product on the inventory/products page" \
  --url "https://www.saucedemo.com/inventory.html" \
  --login-url "https://www.saucedemo.com" \
  --username standard_user \
  --password secret_sauce
```
Prints a JSON verdict and a unified diff. Nothing is written to disk.

**Natural-language test author:**
```bash
ui-tests/.venv/Scripts/python.exe -m agentic.agents.test_author \
  --scenario "Add the Sauce Labs Backpack and the Bike Light to the cart, then verify the cart shows 2 items" \
  --output test_multi_item_cart_v2.py \
  --login-url "https://www.saucedemo.com" \
  --username standard_user \
  --password secret_sauce
```
Writes `ui-tests/tests/test_multi_item_cart_v2.py` (refuses to overwrite an
existing file — pass `--force` to allow it). Review it, then run it through
the real suite before trusting it:
```bash
ui-tests/.venv/Scripts/python.exe -m pytest -v ui-tests/tests/test_multi_item_cart_v2.py
```

**Smoke crawler** — defaults already point at the real test file:
```bash
ui-tests/.venv/Scripts/python.exe -m agentic.agents.smoke_crawler
```
Writes a timestamped JSON report to `agentic/reports/` (gitignored) and
prints a summary.

---

## Running `agentic-claude-code/` (no API key — this Claude Code session reasons)

Only works inside an interactive Claude Code session opened in this repo —
it cannot run unattended or in CI.

**Easiest path for all three:** open a Claude Code session here and invoke
the skill directly:
```
/heal-locator-cc <describe the broken locator and where it is>
/author-test-cc <describe the scenario and the output filename>
/crawl-flows-cc <optionally: which test file to check>
```
Each skill (`.claude/skills/heal-locator-cc|author-test-cc|crawl-flows-cc/SKILL.md`)
documents the exact procedure Claude Code follows — what it reads, what it
verifies live, and what it writes.

**Manual path for `heal-locator-cc`** (the only one with a dedicated CLI,
since it has a reusable diff-building step):
```bash
ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py \
  agentic-claude-code/examples/heal_add_to_cart_button.steps.json

ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
  --pom "ui-tests/pages/inventory_page.py" --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON --new-value "<the value the plan found>"
```
`author-test-cc` and `crawl-flows-cc` have no standalone script to run
outside a session — they're Claude Code's own `Read`/`Write` tools plus
`mcp_bridge.py`, per their `SKILL.md` procedures.

---

## Applying a proposed fix

Every agent in both implementations only *proposes* — a diff, a new file, or
a report. To actually apply a locator fix, edit the line yourself (or
`git apply` the diff), then verify:
```bash
ui-tests/.venv/Scripts/python.exe -m pytest -v ui-tests/tests/test_login_flow.py
```

---

## Practices worth following (not just in this repo)

**Never commit a key, and don't trust `.gitignore` blindly — verify it.**
`agentic/.env.local` holds a real API key. Before your first commit in any
repo with secrets, confirm the ignore rule actually matches:
`git check-ignore -v path/to/.env.local`. A pattern typo or an
unexpectedly-scoped rule is a real, common way keys end up in git history.

**Metered LLM API usage needs its own cost control, separate from any chat
subscription.** A Claude Pro/Code plan does not cover calls made through the
raw Anthropic API with your own key — that's a different, pay-per-token
product. Any agent that calls an LLM in a loop (`agent_loop.py`'s
`max_iterations` cap exists for exactly this) needs an explicit ceiling on
tool-call turns, or a runaway loop becomes a runaway bill.

**Least-privilege tool access, enforced twice.** `agent_loop.py`'s
`allowed_tools` restricts what an agent is even shown *and* re-checks before
executing anything it asks for. Playwright MCP exposes 24 tools, several
with real side effects or arbitrary code execution
(`browser_run_code_unsafe`, file upload, tab management) that no single
agent here needs. Default to the narrowest tool list a task requires, not
whatever the server happens to expose.

**Pin versions of third-party MCP servers/tools you don't control.**
`mcp_config.json` runs `npx -y @playwright/mcp@latest` — convenient during
development, but `@latest` means the exact tool surface and behavior can
change under you between runs with no warning. For anything beyond local
experimentation, pin an exact version and upgrade deliberately, the same way
you'd pin any other dependency.

**Never let an agent write, commit, and merge in one motion.** Every agent
here stops at "propose" — a diff, a new file, a report. Nothing in either
implementation calls `git add`/`git commit`, let alone pushes or merges. The
human decision point is structural, not a policy someone has to remember.

**Validate generated code before trusting it — syntax is the floor, not the
ceiling.** `test_author.py` runs `ast.parse()` on its own output before
writing anything, which only proves the file parses. The real bar is running
it: `test_multi_item_cart.py` wasn't trusted until it was actually executed
through `pytest` and passed. A generated test that merely "looks right" is
not verified.

**Isolate agent-driven browser state — don't assume a fresh session.**
Discovered here the hard way: the MCP server's browser profile carries
`localStorage` (and therefore Sauce Demo's cart) across separate script
invocations, unlike `pytest-playwright`'s fresh isolated context per test.
This caused a real false-positive drift finding until traced and fixed with
an explicit `localStorage.clear()`. Any browser-automation agent that
doesn't control its own session lifecycle needs the same caution — verify
isolation, don't assume it.

**Keep exploratory/agentic work structurally outside the deterministic CI
critical path.** Nothing under `agentic/` or `agentic-claude-code/` is
installed or invoked by `.github/workflows/tests.yml` — a plain `uv sync`
(CI's path) doesn't even pull in `anthropic`/`mcp`, since they're an opt-in
dependency group. An agent that hallucinates, times out, or costs money on a
bad day should never be able to block or flake a required build.

**Keep a real audit trail, not just the final state.** `AGENTIC_BUILD_LOG.md`
records every file, every command, and every real bug found in the order it
happened — including the false starts. When an agent's output looks
surprising later, the log is what lets you reconstruct why it did what it
did, instead of re-deriving it from scratch.
