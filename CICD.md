# Agentic Layer in CI/CD

How (and how not) to wire `agentic/` into a real CI/CD pipeline, why it must
be architected differently from `.github/workflows/tests.yml`, and what
triggers each agent. Nothing in this file is enabled yet — no workflow files
have been added under `.github/workflows/`. This is the design, written down
before building it, the way you'd want it reviewed before it runs against a
real repo with real billing attached.

---

## Why this can't just be another job in `tests.yml`

The existing pipeline is a **gate**: three deterministic jobs, each
reproducible, fast, and free, whose only purpose is to block a merge when
something is objectively wrong. The agentic layer fails every property that
role depends on:

| Property | Deterministic suite (`tests.yml`) | Agentic layer |
|---|---|---|
| Output | Pass/fail — a verdict | A diff, a new file, or a report — a **proposal** |
| Cost | Free | Real, metered LLM API cost per run |
| Determinism | Same input → same result | Same input can produce different reasoning across runs |
| Speed | Seconds to a few minutes | Can involve many tool-call round trips; slower and more variable |
| Failure mode | A real bug | Could be a real bug, a bad prompt, a rate limit, or the model being wrong |

**The rule this leads to, and it's not specific to this repo: anything an
LLM produces must land as a human-reviewed proposal, never as a build gate.**
"The agent's own generated tests also pass" doesn't prove the generated
tests are meaningful — a model can write a weak or tautological assertion
that trivially passes. A required status check can't distinguish that from
a real, well-designed test. So:

- **No agent job is ever a required status check.** Branch protection rules
  never reference an agentic job by name.
- **No agent job blocks, delays, or gates the existing three jobs.** They
  run on entirely separate triggers (below), never `needs:` a deterministic
  job or vice versa.
- **An agent never commits directly to `main` (or any protected branch).**
  Its output becomes a new branch + PR via a bot identity, reviewed and
  merged through the exact same path as human-authored code — same branch
  protection, same required reviewers, same required checks (the real
  `tests.yml` suite still has to pass on that PR too, same as any other).

## Why `agentic-claude-code/` specifically cannot run in CI

Worth being precise about this, since it's the one people ask about first.
`agentic-claude-code/`'s entire value proposition — no separate billing — comes
from the fact that a *human's already-open, already-paying-for* Claude
Code/Pro session does the reasoning. There is no way to invoke that
headlessly in a GitHub Actions runner without giving Claude Code its own
API key for non-interactive/`-p` mode — at which point it is paying the
exact same metered Anthropic API cost as `agentic/` does, so there's no
hidden "free automation" path here. **Only `agentic/`'s standalone Python
agents (`anthropic` SDK, direct API key) are real CI candidates.** Everything
below is about `agentic/` only.

## Trigger model per agent

Three different jobs, three different trigger philosophies — matched to
what each agent is actually for, not just to fill out a matrix.

### Smoke-crawler → scheduled (cron) + manual dispatch

This is a **monitoring** job, not a build gate — same shape as a nightly
dependency-audit or scheduled security scan in any mature pipeline. It
should run independently of any PR, look for drift proactively, and surface
findings without ever blocking anything.

```yaml
# .github/workflows/agentic-smoke-crawl.yml (illustrative — not enabled)
name: Agentic Smoke Crawl

on:
  schedule:
    - cron: "0 6 * * *"   # once a day, off peak — tune to actual cost tolerance
  workflow_dispatch: {}    # allow an on-demand run too

jobs:
  crawl:
    runs-on: ubuntu-latest
    continue-on-error: true   # never let this job's outcome affect the run's overall status
    environment: agentic-llm  # see "Secrets" below — gates secret exposure separately from branch protection
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          version: "0.12.5"
      - working-directory: ./ui-tests
        run: uv sync --extra agentic
      - run: npx -y @playwright/mcp@latest install-browser chrome-for-testing
      - name: Run crawler
        working-directory: .
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: ui-tests/.venv/Scripts/python -m agentic.agents.smoke_crawler
      - uses: actions/upload-artifact@v4
        with:
          name: smoke-crawl-report
          path: agentic/reports/
      - name: Post findings if anything drifted
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            // read agentic/reports/*.json, open/update a tracking Issue
            // only if any flow's status isn't "ok" — never fail the job itself
```

### Locator healer / test author → manual dispatch, deliberately triggered

These aren't monitoring jobs — they're one-shot actions someone decides to
take (heal *this* locator, author a test for *this* scenario). Two common,
equally legitimate industry patterns for "deliberately triggered":

**A. `workflow_dispatch` with input fields** — a person goes to the Actions
tab and fills in a form:
```yaml
# .github/workflows/agentic-heal-locator.yml (illustrative — not enabled)
name: Agentic Heal Locator

on:
  workflow_dispatch:
    inputs:
      pom:
        description: "Path to the POM file"
        required: true
      class_name:
        required: true
      locator:
        required: true
      description:
        required: true
      url:
        required: true

jobs:
  heal:
    runs-on: ubuntu-latest
    environment: agentic-llm
    steps:
      - uses: actions/checkout@v4
      # ...same setup as above...
      - name: Run healer
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          ui-tests/.venv/Scripts/python -m agentic.agents.locator_healer \
            --pom "${{ inputs.pom }}" --class-name "${{ inputs.class_name }}" \
            --locator "${{ inputs.locator }}" --description "${{ inputs.description }}" \
            --url "${{ inputs.url }}" > diff.patch
      - name: Open a PR with the proposed fix
        uses: peter-evans/create-pull-request@v6
        with:
          title: "agentic: heal ${{ inputs.locator }}"
          branch: agentic/heal-${{ inputs.locator }}
          commit-message: "Propose fix for ${{ inputs.locator }} (agentic locator healer)"
          # apply diff.patch to the working tree before this step in a real setup
```

**B. Comment-triggered, on a real PR/issue** — the pattern most engineers
have actually seen (Renovate, Dependabot, "explain this CI failure" bots): a
human comments `/heal-locator ADD_TO_CART_BUTTON` on a PR or issue, an
`issue_comment` trigger picks it up, runs the agent, and posts the diff back
as a reply — or opens a follow-up PR the same way as above. More
discoverable for a team than remembering to go find the Actions tab.

The test-author workflow is structurally identical to the healer's, with
`scenario`/`output` inputs instead.

## Secrets: gate exposure before the job even runs, not just before merge

Use GitHub **Environments** (not just repo-level secrets) for
`ANTHROPIC_API_KEY`:
- Scope the key to an `agentic-llm` environment, separate from any
  deployment environment — an agent job should never sit in the same trust
  boundary as a job that can push to production.
- Require a reviewer approval on that environment. This means a human signs
  off **before the job runs and the key is even exposed to it** — a stronger
  gate than only reviewing the PR the job produces afterward.
- Never grant the agent job's `GITHUB_TOKEN` more than it needs — `contents:
  write` and `pull-requests: write` to open its proposal PR, nothing else
  (no `packages:`, no `deployments:`, no admin scopes).

## Cost control

A metered LLM API with no ceiling in a CI system is a real, not
hypothetical, way to get an unpleasant bill:
- **`max_iterations` in `agent_loop.py`** already caps tool-call turns per
  run — keep this even in CI, don't raise it "just in case."
- **`concurrency:`** on each workflow to prevent duplicate/overlapping runs
  from a burst of comment triggers or accidental re-dispatches.
- **A run-count or budget guard** for comment-triggered jobs specifically,
  since anyone who can comment on a PR could otherwise spam `/heal-locator`
  — rate-limit per user/per day, not just per workflow.
- Treat the smoke-crawler's cron schedule as a cost dial, not a fixed fact —
  daily vs. weekly is a real cost/staleness tradeoff to make consciously.

## Status reporting: advisory, not pass/fail

- `continue-on-error: true` on every agentic job — its own failure (rate
  limit, model error, timeout) must never show as a red X on the run or
  affect `test-summary`'s verdict.
- Results go out as **PR/issue comments or a tracking Issue**
  (`actions/github-script`, `peter-evans/create-or-update-comment`), not as
  a check — a check implies pass/fail, which doesn't fit "here's a drift
  report" or "here's a proposed diff."
- Persist raw output as a build artifact (`actions/upload-artifact`) the
  same way `allure-report` already is — anyone should be able to download
  the exact report/diff a run produced, not just read a summarized comment.

## What actually changes vs. what stays the same

Nothing about `.github/workflows/tests.yml` changes. It keeps running the
same three jobs, on the same triggers, with the same required-status-check
role in branch protection. The agentic workflows are new, separate files,
on separate triggers, feeding a separate outcome (a proposal PR or a report)
that goes through the exact same human-reviewed merge path as any other
change to this repo.

## Status

Design only — no workflow files have been added yet. Before actually
enabling any of this: fund the Anthropic API account (see `RUN.md`), verify
`agentic/`'s three agents run correctly locally first (they haven't, yet),
then implement one workflow at a time, starting with the lowest-risk one
(smoke-crawler, since it only ever posts a report) before the two that open
PRs.
