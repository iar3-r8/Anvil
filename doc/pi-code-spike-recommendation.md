# Pi (pi.dev) spike — recommendation

Spike on the user request of 2026-10-20: "a spike on the switch or add of
pi-code as the main harness instead of zoo-code", with https://pi.dev/ supplied
as the referent. There is no GitHub issue; this document is the go/no-go
deliverable for (a) **switch** and (b) **add**. **No implementation in this
spike** — see [No implementation in this spike](#no-implementation-in-this-spike).

The six third-party pages behind the citations are saved in full under
[`doc/external/pi-dev/`](external/pi-dev/); the Anvil-side facts below are
cited from the repository files themselves.

## What Pi is

Pi (pi.dev, Earendil Works; npm
`@earendil-works/pi-coding-agent`) is a **terminal (TUI) coding agent** —
"a minimal, extensible agent harness that you can make your own". It is a
Node.js CLI requiring **Node.js 22.19 or newer**, installed via
`curl -fsSL https://pi.dev/install.sh | sh` or npm, with print/JSON modes, an
RPC mode, and a TypeScript SDK
([`doc/external/pi-dev/readme.md`](external/pi-dev/readme.md)).

It is **not a VS Code extension**. First-party integration is the terminal
TUI, an SDK, and an RPC protocol; VS Code use exists only through community
wrappers ([`Zetaphor/pi-vscode-extension`](https://github.com/Zetaphor/pi-vscode-extension),
[`frostime/pi-vscode-ui`](https://github.com/frostime/pi-vscode-ui)).

It **deliberately ships without sub-agents or plan mode**: "Pi ships with
powerful defaults but skips features like sub-agents and plan mode. Ask Pi to
build what you want, or install a package that does it your way."
([`doc/external/pi-dev/readme.md`](external/pi-dev/readme.md)). Extension
points are extensions, skills, prompt templates, and themes, bundled as "Pi
packages" and shared via npm or git.

Configuration lives in a user-level agent directory (`~/.pi/agent/`) and a
project-level `.pi/` directory: `settings.json`, `models.json`, `mcp.json`,
`auth.json`, instruction files (`AGENTS.md`/`CLAUDE.md`, `SYSTEM.md`,
`APPEND_SYSTEM.md`), and `extensions/`/`skills/`/`prompts/`
([`doc/external/pi-dev/configuration.md`](external/pi-dev/configuration.md)).

## Verdict: switch — reject

**Do not switch.** Zoo Code stays the main harness. Three decisive,
independent reasons:

1. **No per-mode model routing.** Anvil's design is two-tier: a frontier
   model plans and orchestrates (the `architect` and `orchestrator` modes),
   a local llama-swap model codes (`anvilkit/render.py:zoo_code_settings`
   writes the `modeApiConfigs` mapping). Pi selects one default model per
   session — `defaultProvider`/`defaultModel`, `--model`, `Ctrl+P` cycling
   ([`doc/external/pi-dev/settings.md`](external/pi-dev/settings.md),
   [`doc/external/pi-dev/models.md`](external/pi-dev/models.md)) — with no
   built-in concept of "this role uses this model". Emulating per-mode
   routing means hand-building orchestration on top of Pi's extensions or
   SDK: rebuilding the mode system Anvil already has.
2. **The pipeline's own runtime is the harness being swapped.** This
   repository's TDD pipeline dispatches work as Zoo Code-family modes —
   `templates/roo_template/.roomodes` plus one
   `templates/roo_template/rules-<slug>/instructions.xml` per mode. Pi has no
   mode mechanism at all; switching the "main harness" strands the pipeline's
   own dispatcher, and every mode instruction set would need a rewrite into
   `AGENTS.md` + skills — and still lack per-mode models.
3. **No first-party VS Code integration and no codebase index.** Anvil
   provisions a VS Code workspace: extensions (`.vscode/extensions.json`), a
   devcontainer, and a semantic index (embedder model from `config.yaml` +
   Qdrant, wired in `anvilkit/render.py:zoo_code_settings` via
   `codebaseIndexConfig`). Pi is terminal-only first-party, and its built-in
   tools are `read`, `bash`, `edit`, `write`, `grep`, `find`, `ls` —
   retrieval is grep/find, with no embeddings and no first-party equivalent
   of `codebaseIndexConfig`
   ([`doc/external/pi-dev/settings.md`](external/pi-dev/settings.md)).

A switch is therefore a rewrite of `anvilkit/render.py`,
`anvilkit/provision.py`, all six mode instruction sets, the devcontainer
story and the user-facing workflow — with a **capability regression on every
axis the pipeline depends on**. The effort is large and the outcome is worse
for the stated purpose (running the Anvil TDD pipeline against a local
backend).

## Verdict: add — feasible and small, conditional

Adding Pi **alongside** Zoo Code is low-risk and independent:

- Rough shape: a `templates/pi-models.json.template` rendered from the same
  resolved values Anvil already computes (provider `baseUrl`,
  `api: "openai-completions"`, a dummy key, `contextWindow` from
  `config.yaml`, and an explicit `maxTokens` — Pi defaults to 16384, while
  the Zoo Code template passes unlimited), reusing the existing `mcp.json`
  rendering to write `.pi/mcp.json`, a provision step that writes `.pi/`, and
  one devcontainer install line (`npm install -g
  @earendil-works/pi-coding-agent`). That is a normal red/green feature, one
  reviewable PR.
- **Zero impact on the existing Zoo Code path.** Both harnesses point at the
  same llama-swap gateway; nothing in `zoo-code-settings.json`, the mode
  system, or the codebase index changes.

But per the KISS rule ("build the happy path first — nothing nobody asks
for"): nothing in Anvil's current user flow requires a terminal harness.
**Add Pi only if the user wants a terminal agent** — e.g. running an agent
under tmux or over SSH without an editor. If yes, it is a small standalone
feature with its own issue.

## Anvil integration points, mapped

| Anvil integration point (Zoo Code) | Pi equivalent | Verdict |
|---|---|---|
| llama-swap OpenAI gateway as the local model ([`anvilkit/render.py`](../anvilkit/render.py) `zoo_code_settings`) | `models.json` provider, `api: "openai-completions"`, dummy key, `contextWindow` from `config.yaml` ([`doc/external/pi-dev/models.md`](external/pi-dev/models.md), [`doc/external/pi-dev/models-configuration.md`](external/pi-dev/models-configuration.md)) | ✅ drop-in equivalent; `maxTokens` must be set explicitly (Pi defaults to 16384, the Zoo Code template passes unlimited) |
| Anthropic frontier profile for `architect`/`orchestrator` (`modeApiConfigs` in [`anvilkit/render.py`](../anvilkit/render.py)) | built-in `anthropic` provider via `/login` or API key — but a single default model per session ([`doc/external/pi-dev/settings.md`](external/pi-dev/settings.md)) | ❌ gap: the core two-model design (frontier plans, local codes) has no native home |
| Modes: `.roomodes` + per-mode `rules-<slug>/instructions.xml` under [`templates/roo_template/`](../templates/roo_template/) | skills / prompt templates / extensions; per-mode behaviour must be hand-built or a community package installed ([`doc/external/pi-dev/readme.md`](external/pi-dev/readme.md)) | ❌ the biggest gap — this repo's entire TDD pipeline runs as Zoo Code-family modes; the harness that dispatches the work cannot itself be the thing being swapped |
| `.roo/mcp.json` (github, git, oxylabs, package-registry) from [`templates/mcp.json.template`](../templates/mcp.json.template) | `.pi/mcp.json`, same `mcpServers` shape, `${NAME}` env interpolation ([`doc/external/pi-dev/mcp.md`](external/pi-dev/mcp.md)) | ✅ near drop-in; the `disabled` flag has no Pi equivalent — a server with missing credentials simply fails to connect and is reported |
| Codebase index (embedder model from `config.yaml` + Qdrant, wired in [`anvilkit/render.py`](../anvilkit/render.py)) | none built in — `grep`/`find` only ([`doc/external/pi-dev/settings.md`](external/pi-dev/settings.md)) | ❌ capability loss |
| VS Code extension presence ([`templates/extensions.json.template`](../templates/extensions.json.template)) | none first-party; terminal TUI, or a community wrapper | ⚠️ different UX, not a drop-in |
| `anvil.yaml` `zoo_code` section (profile ids, Anthropic model menu) | `anvil.yaml` gains a `pi` section (model id, context window passthrough, optional default thinking level) | ✅ small |
| `config.yaml` read-only parse (`matrix.vars.coder`, `--max-model-len`) | unchanged — same source of truth | ✅ no impact |
| devcontainer (Node.js 22.x already installed in [`templates/devcontainer/Dockerfile`](../templates/devcontainer/Dockerfile)) | `npm install -g @earendil-works/pi-coding-agent` or the pi.dev installer ([`doc/external/pi-dev/readme.md`](external/pi-dev/readme.md)) | ✅ trivial |

## No implementation in this spike

This spike delivers a recommendation, not code. The branch touches
documentation only: this file, the six pages under
[`doc/external/pi-dev/`](external/pi-dev/), and the two link-only entries in
[`doc/external/index.md`](external/index.md). No `anvilkit/` or `tests/` file
is changed, and no `pi` binary is installed.

### Re-open conditions

Re-open the **switch** question if any of these hold — none do today:

- Pi ships a first-party per-mode (or per-role) model routing mechanism,
- Pi gains a first-party VS Code extension and a codebase index, or
- Pi ships a first-party mode/role system compatible with `.roomodes`-style
  per-mode instructions.

Re-open the **add** question when the user wants a terminal agent (tmux,
SSH, CI, no editor) — the rough shape above is ready to be planned as its own
feature.

## Sources

Saved in full (source URL recorded at the top of each file), fetched from the
`main` branch of github.com/earendil-works/pi on 2026-10-20:

- [`doc/external/pi-dev/readme.md`](external/pi-dev/readme.md) — Pi identity, install (Node.js ≥ 22.19), packages, the deliberate absence of sub-agents and plan mode
- [`doc/external/pi-dev/configuration.md`](external/pi-dev/configuration.md) — user-level and project-level configuration layout
- [`doc/external/pi-dev/models.md`](external/pi-dev/models.md) — connecting an OpenAI-compatible endpoint, dummy key, single-model selection
- [`doc/external/pi-dev/models-configuration.md`](external/pi-dev/models-configuration.md) — `models.json` reference, `maxTokens` default 16384, `modelOverrides`
- [`doc/external/pi-dev/mcp.md`](external/pi-dev/mcp.md) — `.pi/mcp.json` format, stdio and streamable-HTTP servers, `${NAME}` interpolation
- [`doc/external/pi-dev/settings.md`](external/pi-dev/settings.md) — settings reference, `defaultProvider`/`defaultModel`, built-in tool list

Link only:

- [`Zetaphor/pi-vscode-extension`](https://github.com/Zetaphor/pi-vscode-extension) — Pi coding agent, as a VS Code extension (community wrapper)
- [`frostime/pi-vscode-ui`](https://github.com/frostime/pi-vscode-ui) — non-intrusive VS Code extension offering a GUI wrapper for the Pi Coding Agent (community wrapper)
