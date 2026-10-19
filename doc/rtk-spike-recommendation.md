# RTK spike — recommendation

Spike for [issue #40](https://github.com/iar3-r8/Anvil/issues/40): evaluate
RTK (Rust Token Killer), a CLI proxy that filters bash command output before it
reaches the LLM, for Anvil's agent pipeline. This document is the go/no-go
deliverable. **No implementation in this issue** — see [No implementation in
this issue](#no-implementation-in-this-issue).

The ledger, the measured evidence, the per-point verdict and the fetched pages
behind the citations below are in [plans/rtk-spike.md](../plans/rtk-spike.md).
The six third-party pages are saved in full under
[`doc/external/`](external/); the byte measurements below were taken on this
repo and are ours to state directly.

## Verdict: Reject

**Reject** — do not adopt `rtk`, and do not adopt `rtk-oss` instead.

One paragraph: the decisive unknown was how much of the pipeline's token
spend flows through Bash and through an RTK filter. Measured, it is
negligible — the pipeline's only large bash output is `python -m unittest`,
which is in no RTK filter, and the commands RTK does cover total ≈ 0.9 KB per
iteration (under 2% of total input bytes even in the worst case, ~0.2%
typical, zero in the code/qna-tester subtasks).
The costs that are actually large — the 41 KB of rules re-injected every turn
and the 60–190 KB files read through the agent's own Read tool — are outside
RTK's scope by design, and the one feature that could address them (the
engine's PostToolUse Read-compression) is BUSL-1.1-only and requires a hook
that Roo Code does not expose. For Roo Code the integration is
prompt-level only, so even the covered commands' savings are probabilistic.
There is nothing to adopt that would touch a measurable share of the cost.

## Measured share of token spend that flows through Bash and an RTK filter

Measured on this repo (branch base `main` @ `bb8bc32`), per representative
red/green iteration:

- The pipeline's dominant Bash output is the test suite
  ([`tests/run`](../tests/run), `python -m unittest`): 3,786 B targeted
  (`tests.test_config`), 25,705 B (`tests.test_manager_rules`), 247,024 B full
  suite. `python -m unittest` is in **no** RTK filter — RTK's Python filters
  are `pytest`, `ruff check`, `mypy` and `pip install`, with no stdlib
  unittest filter ([`doc/external/rtk-ai/what-rtk-optimizes.md`](external/rtk-ai/what-rtk-optimizes.md)).
  The full-suite output, at every pre-PR gate and module-blast-radius check,
  therefore passes through RTK unchanged.
- The commands RTK **does** cover in this pipeline are the small git ones,
  and only the manager runs them (the code/qna-tester subtasks run no git at
  all): on a clean tree `git status` and `git diff --stat` are empty, `git
  log --oneline -10` is 863 B and `git branch --show-current` 18 B — ≈ 0.9 KB
  per iteration. That is **19% of the bash bytes in the smallest (3,786 B)
  targeted run, 3.4% in the 25,705 B targeted run, and 0.36% in the full-suite
  run — and < 2% of total input bytes even in the worst case**. A typical
  iteration also reads a 104–190 KB test file via native Read and re-injects
  41,461 B of rules every turn — both outside RTK's reach by design, since
  RTK controls only the bytes a shell command sends back
  ([`doc/external/rtk-ai/what-rtk-optimizes.md`](external/rtk-ai/what-rtk-optimizes.md),
  [`doc/external/rtk-ai/savings-explained.md`](external/rtk-ai/savings-explained.md)).
- Roo Code is RTK's **rules-file tier**: there is no hook at all. `rtk init
  --agent cline` only writes prompt-level guidance, and the model must
  voluntarily prefix `rtk` for any filter to apply
  ([`doc/external/rtk-ai/supported-agents.md`](external/rtk-ai/supported-agents.md)).

RTK's own framing matches the measurement: it cuts "up to 90% of the bash
output your agent reads", and that is "the only thing RTK changes"; the
reduction dilutes from bytes to input tokens to cost at every step, so a
large cut in bash output does not make a session proportionally cheaper
([`doc/external/rtk-ai/savings-explained.md`](external/rtk-ai/savings-explained.md)).

## BUSL-1.1 vs Apache-2.0 for Anvil's use

- Full `rtk` is Apache-2.0 (CLI + all command filters) plus BUSL-1.1
  (compression engine). The BUSL Additional Use Grant permits **free
  production use** — running it is fine; it only forbids offering RTK or a
  derivative to third parties as a commercial product or service
  ([`doc/external/rtk-ai/editions-and-licensing.md`](external/rtk-ai/editions-and-licensing.md)).
  Anvil is open-source tooling for the user's own development, so even the
  full edition sits inside the grant. **Licensing is a non-blocker.**
- `rtk-oss` is Apache-2.0 only and drops the engine — i.e. `rtk pipeline`,
  `rtk methods`, `rtk tasks` and **PostToolUse compression of the agent's own
  `Read` and MCP tool output**; the filters, `rtk init`, `rtk gain` and the
  rest are unchanged
  ([`doc/external/rtk-ai/editions-and-licensing.md`](external/rtk-ai/editions-and-licensing.md)).
- The part of RTK that could touch Anvil's actual big costs (large Read
  outputs, and only via a hook) is precisely the engine's PostToolUse
  compression — BUSL-licensed, and inoperative for Roo Code regardless,
  because Roo Code has no hook API.

## How `.clinerules` would coexist with `.roo/rules/` and `.roo/rules-{slug}/`

`rtk init --agent cline` creates a `.clinerules` in the project root, on the
assumption the agent reads it as custom instructions
([`doc/external/rtk-ai/supported-agents.md`](external/rtk-ai/supported-agents.md)).

Roo Code's rule loading order is: (1) global `~/.roo/` rules, (2) project
`.roo/rules/` plus `.roo/rules-{modeSlug}/` (which take precedence), and
(3) **legacy files (`.roorules`, `.clinerules`) — used only if no generic
rules directory content was loaded**
([`doc/external/roo-code/custom-instructions.md`](external/roo-code/custom-instructions.md)).

Every repo Anvil provisions carries `.roo/rules/` content
([`templates/roo_template/rules/`](../templates/roo_template/rules/): AGENTS.md,
architecture.md, coding-guidelines.md), so a generated `.clinerules` **would
never be loaded** — the RTK shipping mechanism is inert in provisioned repos.
The only way RTK guidance could reach the agents is a file inside
`.roo/rules/` (shared) or `.roo/rules-{slug}/` (per-mode) — ordinary rule
text, identical in mechanism to what the rules already say.

## No implementation in this issue

This issue is a spike. The branch touches documentation only
(`doc/` and the fetched pages under `doc/external/`); no `anvilkit/` or
`tests/` files are changed, and no RTK binary, hook or config is installed.
The Definition of Done for issue #40 requires exactly this: a written
recommendation, the licensing assessment, the `.clinerules` coexistence note,
and no implementation.

### Re-open conditions

Re-open the question if any of these hold — none do today:

- RTK adds a filter that covers `python -m unittest` output (the pipeline's
  only large bash output), or
- Roo Code gains a hook API (a PreToolUse/PostToolUse integration), or
- the pipeline's test runner moves to a tool RTK already covers (e.g.
  `pytest`).
