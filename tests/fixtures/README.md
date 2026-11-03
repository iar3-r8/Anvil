# Golden fixtures

These files are the **executable specification** for the Python rewrite. They were
captured from the original bash implementation on 2026-08-05, *before* any Python
rendering code existed, so they record real observed behaviour rather than what we
believe the behaviour to be.

The Python implementation is correct when it reproduces these outputs.

| File | Provenance |
| --- | --- |
| `golden_config.yaml` | Verbatim copy of the hand-authored `config.yaml` at the time of capture. The generated llama-swap config must be semantically equal to this. |
| `golden_zoo_settings_anthropic.json` | `templates/zoo-code-settings.json.template` rendered through the original `sed` pipeline with the Anthropic frontier model **accepted**. |
| `golden_zoo_settings_local.json` | Same template rendered with the frontier model **declined**, so architect falls back to the local llama-swap profile. |
| `golden_mcp.json` | `templates/mcp.json.template` rendered with a GitHub token supplied. |
| `golden_ruleset.json` | The expected five-rule ruleset JSON built by `anvilkit/pi/piruleset.py` (the output of behaviours 1+2 in `plans/ruleset-write.md`). Unlike the files above it was authored from the plan's pinned shape at red time, not captured from an existing implementation; the recipes key set comes from `doc/external/github/ruleset-recipes-branch-sample.json`. |
| `golden_pi_models.json` | `json.dumps(piargv.models_document("qwen3-coder", 8000, 262144, 262144), indent=4)` with the default host `127.0.0.1` (behaviours 6–10 in `plans/pi-phase5-render.md`). Like `golden_ruleset.json` it was authored at red time from the delegate's pinned shape, not captured from a prior implementation; the `apiKey` is the fixed synthetic placeholder `llamaswap-local`. |
| `golden_pi_mcp.json` | `templates/mcp.json.template` carried into Pi's shape by `render.pi_mcp_settings("/workspace/anvil")` (behaviour 11 in `plans/pi-phase5-render.md`): `${workspaceFolder}` replaced by the golden path, the env/header tokens `${GITHUB_TOKEN}`, `${OXYLABS_USERNAME}`, `${OXYLABS_PASSWORD}` left verbatim (Pi interpolates them at request time), and the Roo-vocabulary keys `alwaysAllow`, `disabledTools`, `disabled` dropped from every server. Like `golden_pi_models.json` it was authored at red time from the plan's pinned shape, not captured from a prior implementation. |

| `golden_pi_guardrails.json` | The expected guardrails document built by `anvilkit/pi/piguardrails.py` (behaviour 3 in `plans/pi-guardrails.md`). Like `golden_ruleset.json` it was authored at red time from the plan's pinned shape, not captured from a prior implementation; the allowed key sets come from `doc/external/pi-guardrails/schema.md`. Non-obvious values are manager-settled ledger decisions (issue #67): `protectEnvFiles` is explicitly `false` (only `policies` + `permissionGate` are enabled, the `secrets` rule covers env files, and the package built-in env layer is partly `fd`-dependent per the source review); the `guardrails-config` rule is `readOnly` (the threat is an agent editing its own gate — `readOnly` blocks the edit without blocking reads); `autoDenyPatterns` entries carry only the required `pattern` key (the documented match is substring unless `regex: true`); `onlyIfExists` is explicit `true` per the schema ("Block only when file exists on disk. Default true.") so behaviour 7 can assert it is present; no `$schema`/`version` keys (`version` is "stamped by migrations"). |

> `golden_mcp.json` was deliberately changed on 2026-08-19 to add the
> `package-registry` server, because Anvil now owns that MCP entry
> (`plans/package-registry-context.md`, behaviour 2). It was not regenerated
> to silence a failure.

## Capture parameters

Held constant so the fixtures are reproducible:

- `LLM_PORT` = `8000`
- `CONTEXT_WINDOW` = `262144` (extracted from `config.yaml` by the original
  `grep -A50 ... | awk '{print $NF}'` pipeline)
- `LOCAL_PROFILE_ID` = `4aj3zc43616`
- `ANTHROPIC_MODEL_ID` = `claude-opus-5`
- `ANTHROPIC_API_KEY` = `sk-ant-golden-test-key` (accepted) / `to set` (declined)
- `workspaceFolder` = `/golden/target/repo`
- `GITHUB_TOKEN` = `ghp_goldentesttoken`

All values are synthetic. **No real secret belongs in this directory.**

## Rules

- Do not regenerate these files to make a failing test pass. A diff against a
  golden fixture means the rewrite changed observable behaviour — either fix the
  code, or change the fixture deliberately in its own commit with a stated reason.
- Compare parsed structures, not raw strings, wherever key ordering or whitespace
  is not part of the contract.
