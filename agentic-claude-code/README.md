# agentic-claude-code/ — the "no separate API key" variant

This is a second implementation of the self-healing locator idea, kept
**completely separate** from [`agentic/`](../agentic/README.md) — no shared
code, no shared config, different mechanism for "the brain." Nothing here was
removed or changed in `agentic/`; both exist side by side so you can compare
them directly.

## The difference in one sentence

`agentic/` has Claude Code call a **second, separate Claude** (via the
Anthropic API, its own key, its own billing) to do the reasoning.
`agentic-claude-code/` has **this Claude Code session itself** do the
reasoning — no second AI call, no API key, no billing beyond your existing
Claude Pro/Code subscription. The tradeoff: it only works interactively,
inside a session like this one — it can't be scheduled or run unattended the
way a standalone script can.

## Why this needed its own approach, not just "reuse `agentic/mcp_client.py`"

`agentic/mcp_client.py` is designed to stay connected for an entire
Claude↔tool conversation happening inside one Python process
(`agent_loop.py`'s loop). Here, *I* (Claude Code) issue commands one Bash call
at a time — a single MCP tool call per Bash invocation would spawn a brand
new, memory-less browser each time (no login, no navigation history carried
over). So `mcp_bridge.py` instead takes a **whole ordered plan** of tool calls
and runs all of them in one persistent browser session, printing every
result — I decide the full plan upfront, then read the combined output to
reason about the fix.

## Files in this folder

| File | What it is | Why it exists |
|---|---|---|
| `mcp_config.json` | Own copy of the Playwright MCP server config | Deliberately duplicated from `agentic/mcp_config.json` rather than shared, so this folder has zero file dependency on `agentic/` |
| `mcp_bridge.py` | Runs an ordered list of MCP tool calls in one browser session, prints each result | The only "tool" this variant needs — no Anthropic SDK import anywhere in it |
| `pom_diff.py` | Turns a healed locator value into a unified diff against a POM file | Intentionally a duplicate of the same ~40 lines of logic in `agentic/agents/locator_healer.py`, kept separate on purpose |
| `examples/heal_add_to_cart_button.steps.json` | A real, saved plan — login to Sauce Demo, navigate to inventory, disambiguate and read the "Add to cart" button for the backpack | Documents exactly what a real run looked like, so you can see it plus re-run it |
| `../.claude/skills/heal-locator-cc/SKILL.md` | The reusable recipe, invokable inside a Claude Code session | Packages the manual steps below into a documented, repeatable procedure instead of one-off chat instructions |

## How a run actually happened (real, not hypothetical)

1. Wrote `examples/heal_add_to_cart_button.steps.json` — a 5-step plan: log
   into Sauce Demo, land on the inventory page, take a snapshot, then run a
   **read-only** JavaScript snippet via `browser_evaluate` that:
   - finds the product container whose text includes "Sauce Labs Backpack"
     (scoped using `.inventory_item`, the same class the POM already uses
     for `PRODUCT_ITEM` — no guessing),
   - finds the "Add to cart" button inside just that container (this step
     matters: every product's button has the identical accessible name
     "Add to cart", so without scoping by container there's no way to tell
     them apart),
   - reads back its real `data-test` attribute.
2. Ran it: `ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py
   agentic-claude-code/examples/heal_add_to_cart_button.steps.json`
3. Got back the real answer straight from the live DOM:
   ```json
   {"found": true, "dataTest": "add-to-cart-sauce-labs-backpack", ...}
   ```
4. Turned that into a diff against the real (already broken)
   `ui-tests/pages/inventory_page.py`:
   ```bash
   ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
     --pom "ui-tests/pages/inventory_page.py" \
     --class-name InventoryPage \
     --locator ADD_TO_CART_BUTTON \
     --new-value "button[data-test='add-to-cart-sauce-labs-backpack']"
   ```
5. Got a clean, human-reviewable diff — printed only, never applied to the
   file. See `../AGENTIC_BUILD_LOG.md`'s entry for this run for the full
   output and exact timeline.

## Running it yourself

```bash
export PATH="/c/Program Files/nodejs:$PATH"   # only if node/npx isn't already on PATH
cd /c/projects/BH-E2E-Tests

# 1. Run a plan (edit examples/heal_add_to_cart_button.steps.json, or write your own)
ui-tests/.venv/Scripts/python.exe agentic-claude-code/mcp_bridge.py \
  agentic-claude-code/examples/heal_add_to_cart_button.steps.json

# 2. Turn the answer into a diff
ui-tests/.venv/Scripts/python.exe agentic-claude-code/pom_diff.py \
  --pom "ui-tests/pages/inventory_page.py" \
  --class-name InventoryPage \
  --locator ADD_TO_CART_BUTTON \
  --new-value "<the value step 1 found>"
```

No `ANTHROPIC_API_KEY` needed — `mcp_bridge.py` and `pom_diff.py` never import
`anthropic`. The only cost is whatever your Claude Pro/Code plan already
covers for the session doing the reasoning.

## Fits with the rest of the repo exactly like `agentic/` does

Nothing here runs in CI, nothing here can be triggered by
`.github/workflows/tests.yml`, and nothing here writes to `ui-tests/pages/` or
`ui-tests/tests/` — same human-review gate as `agentic/`. The `mcp` Python
package (needed by `mcp_bridge.py`) is already installed via
`ui-tests/pyproject.toml`'s `agentic` optional-dependency group — reused
because it's a third-party protocol library, not "the other implementation";
no new dependency was added for this folder.
