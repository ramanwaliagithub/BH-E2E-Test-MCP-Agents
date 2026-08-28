---
name: heal-locator-cc
description: Self-healing Playwright locator agent driven by Claude Code itself, with no separate Anthropic API key or standalone agent script. Given a broken (or suspected broken) POM locator constant, drives a live browser via the Playwright MCP server, re-locates the intended element, and proposes a fix as a diff for human review — never edits the POM file directly.
---

# heal-locator-cc

This is the "run inside Claude Code" variant of the self-healing locator agent
in `agentic/agents/locator_healer.py`. That version makes a second, standalone
call to the Anthropic API (its own API key, its own billing). This version has
no second AI call at all — **you** (this Claude Code session, covered by the
user's existing subscription) are the reasoning engine. `agentic-claude-code/`
only gives you two small tools: a way to run a batch of browser actions
(`mcp_bridge.py`) and a way to turn a healed value into a diff (`pom_diff.py`).

## Inputs needed from the user (ask if not given)

- `pom` — path to the POM file, e.g. `ui-tests/pages/inventory_page.py`
- `class_name` — the class inside it, e.g. `InventoryPage`
- `locator` — the broken constant's name, e.g. `ADD_TO_CART_BUTTON`
- `description` — plain English of what the element does, e.g. "the Add to
  cart button for the Sauce Labs Backpack product"
- `url` — page the element lives on
- optionally `login_url`/`username`/`password` if the page requires auth

## Procedure

1. **Read the POM file** (the `Read` tool) and find the current value of
   `locator` inside `class_name`, for context — don't trust it, the whole
   point is it may be stale.
2. **Read sibling locators in the same class.** They're a free source of
   grounding — e.g. if `PRODUCT_ITEM = ".inventory_item"` already exists in
   the same class, you can scope a DOM query with it instead of guessing
   class names blindly. This mattered in the first real run: every
   "Add to cart" button on Sauce Demo's inventory page shares the exact same
   accessible name, so accessibility role/name alone can't tell them apart —
   scoping by the sibling `.inventory_item` locator plus the product's name
   text is what disambiguates.
3. **Plan the full sequence of MCP tool calls** needed to reach the element
   and confirm its real, current identity — typically: `browser_navigate`
   (+ `browser_fill_form` and `browser_click` for login, if needed),
   `browser_snapshot` to see the page, and a **read-only** `browser_evaluate`
   call to recover a stable attribute (`data-test`, `data-testid`, `id`) once
   you've identified the right element. Never write a `browser_evaluate`
   function that clicks, types, submits, or otherwise changes page state —
   only ones that read (`querySelector`, `textContent`, `getAttribute`).
4. **Write that plan as a JSON file** (a temp file — use the scratchpad
   directory if configured, or `agentic-claude-code/examples/` if you want to
   keep it as a documented example) shaped like:
   ```json
   [
     {"tool": "browser_navigate", "args": {"url": "..."}},
     {"tool": "browser_fill_form", "args": {"fields": [...]}},
     {"tool": "browser_click", "args": {"target": "...", "element": "..."}},
     {"tool": "browser_snapshot", "args": {}},
     {"tool": "browser_evaluate", "args": {"function": "() => {...}"}}
   ]
   ```
5. **Run it**: `python agentic-claude-code/mcp_bridge.py <path-to-plan.json>`
   (must run with `node`/`npx` on `PATH`, and from a directory where the
   Python environment has the `mcp` package installed — this repo's
   `ui-tests/.venv`, e.g. `ui-tests/.venv/Scripts/python.exe
   agentic-claude-code/mcp_bridge.py <plan.json>`).
6. **Read the output yourself.** If the evaluate step didn't find the element,
   or the snapshot shows something unexpected, revise the plan and re-run —
   you're doing the reasoning a second Claude API call would otherwise do.
7. **Once confident**, generate the diff:
   ```bash
   python agentic-claude-code/pom_diff.py \
     --pom <pom> --class-name <class_name> --locator <locator> \
     --new-value "<healed selector>"
   ```
8. **Present the diff to the user as the final answer. Do not edit the POM
   file yourself** — same human-review gate as the standalone agent.
9. **Clean up**: delete the temporary plan JSON (unless it's meant to stay as
   a documented example) and remove any `.playwright-mcp/` directory the MCP
   server wrote snapshot/console logs into during the run.

## Known issue: MCP's synthetic click can silently no-op on Sauce Demo

Discovered while healing `REMOVE_FROM_CART_BUTTON`: `browser_click` targeting
`button[data-test='add-to-cart-sauce-labs-backpack']` (also tried via a fresh
snapshot ref, which resolves to the same underlying selector) reported success
every time — no error, normal Playwright trace — but the page's state never
actually changed (cart badge stayed empty, button text stayed "Add to cart").
Ruled out, in order: a covering overlay (`elementFromPoint` confirmed the
button itself was on top), the button being disabled, and hydration timing
(`browser_wait_for` on text and on a plain time delay, both up to several
seconds, made no difference). What actually worked: calling the DOM's native
`element.click()` from inside `browser_evaluate` — this fired the app's real
click handler immediately (cart badge went to "1", button flipped to
"Remove"). Root cause not fully identified — likely something specific to how
this Playwright MCP server's headless Chromium build (`chromium_headless_shell`)
synthesizes mouse events for this exact element, since the *app* clearly works
fine and the *element* is genuinely clickable.

**If you hit a `browser_click` that reports success but nothing changes:**
don't assume the locator itself is wrong. Verify with a **one-off** diagnostic
`browser_evaluate` call that does `element.click()` directly — this is the one
sanctioned exception to the "evaluate must stay read-only" rule above, and
only for this specific diagnosis (confirming whether the app responds to a
click at all). Once confirmed, still report both facts to the user: the
healed locator value, and that the MCP click mechanism itself has this quirk
on this element — don't silently paper over it, since it affects whether a
real Playwright test (which also uses `.click()`) would work the same way. (In
this case it's specifically the automation-driven click that misbehaves, not
a Sauce Demo bug that would affect a real test run — `ui-tests`' existing
`inventory_page.py.add_product_to_cart()` uses the same selector via
`page.click()` and is a separately verified, working test path.)

## What this skill deliberately does NOT do

- No `ANTHROPIC_API_KEY`, no `anthropic` package, no `agentic/agent_loop.py`.
- No import from `agentic/` at all — `agentic-claude-code/` is a fully
  separate implementation on purpose, so the two approaches never share code.
- No tool outside the safe set: navigate, snapshot, fill_form, click,
  evaluate (read-only only). Never call `browser_run_code_unsafe`.
