# RTK — supported agents

Source: https://www.rtk-ai.app/docs/getting-started/supported-agents/
Retrieved: 2026-10-19 (fetched by the tdd-manager via oxylabs `universal_scraper` during the RTK spike, [plans/rtk-spike.md](../../plans/rtk-spike.md); transcribed here, not re-fetched)

The agent integrations, their tiers, and where Cline / Roo Code sit (rules-file, prompt-level).

Each agent integration intercepts CLI commands before execution and rewrites
them to their RTK equivalent. The agent runs `rtk cargo test` instead of
`cargo test`, sees filtered output, and reads up to 90% fewer bash output
bytes — without any change to your workflow. All rewrite logic lives in the
RTK binary (`rtk rewrite`); agent hooks are thin delegates that parse the
agent-specific JSON format and call `rtk rewrite` for the actual decision.

Supported agents (integration tier; can rewrite transparently?):

| Agent | Integration tier | Can rewrite transparently? |
| --- | --- | --- |
| Claude Code | Rust binary (`PreToolUse`, `rtk hook claude`) | Yes |
| Trae | Rust binary (`PreToolUse`, matcher `RunCommand`) | Yes |
| VS Code Copilot Chat | Rust binary (`PreToolUse`, `rtk hook copilot`) | Yes |
| GitHub Copilot CLI | Rust binary (`PreToolUse`, `rtk hook copilot`) | Yes |
| Cursor | Rust binary (`preToolUse`, `rtk hook cursor`) | Yes |
| Gemini CLI | Rust binary (`BeforeTool`) | Yes |
| OpenCode | TypeScript plugin (`execute.before` in 2.0, `tool.execute.before` in 1.x >= 1.18.29) | Yes |
| OpenClaw | TypeScript plugin (`before_tool_call`) | Yes |
| Pi | TypeScript extension (`tool_call` event) | Yes |
| Oh My Pi (OMP) | TypeScript extension (`tool_call` event, shared with Pi) | Yes |
| Hermes | Python plugin (`terminal` command mutation) | Yes |
| Factory Droid | Rust binary (`PreToolUse`, matcher `Execute`) | Yes |
| **Cline / Roo Code** | **Rules file (prompt-level)** | **N/A** |
| Windsurf | Rules file (prompt-level) | N/A |
| Codex CLI | Rust binary (`PreToolUse`) | Yes |
| Kilo Code | Rules file (prompt-level) | N/A |
| Google Antigravity | Rust binary (`PreToolUse` plugin) | Yes |
| Mistral Vibe | Rust binary (`pre_tool`) | Yes |

Agents that rewrite transparently receive the awareness file selected by
`awareness.level` in `config.toml` (`default` says nothing about RTK).
Rules-file agents **cannot rewrite, so the agent must prefix `rtk` itself**;
they always receive the `full` awareness file and `rtk init` says so.

Integration tiers explained:

| Tier | Mechanism | How rewrites work |
| --- | --- | --- |
| **Full hook** | Rust binary command (or a thin wrapper around one), intercepts via agent API | Transparent — agent never sees the raw command |
| **Plugin** | TypeScript, JavaScript, or Python in agent's plugin system | Transparent, in-place mutation when the agent allows it |
| **Rules file** | Prompt-level instructions | Guidance only — agent is told to prefer `rtk <cmd>` |

Rules file integrations (Cline, Windsurf, Kilo Code) rely on the model
following instructions. Full hook integrations (Claude Code, Trae, Cursor,
Gemini, Codex, Factory Droid, Antigravity) apply rewrites before execution
whenever RTK supports and can safely attest the command. Plugin integrations
(OpenCode, Pi, Hermes) use in-place mutation via the agent's extension or
plugin API.

Cline / Roo Code installation:

    rtk init --agent cline    # creates .clinerules in current project

Cline reads `.clinerules` as custom instructions. RTK adds guidance telling
Cline to prefer `rtk <cmd>` over raw commands.

Graceful degradation: hooks never block command execution. If RTK is missing,
the hook exits cleanly and the raw command runs unchanged (RTK binary not
found → warning to stderr, exit 0; invalid JSON → pass through unchanged;
RTK version too old → warning, exit 0; filter logic error → fallback to raw
command output). Override: `RTK_DISABLED=1 git status` runs raw; or
`exclude_commands` in `~/.config/rtk/config.toml`.
