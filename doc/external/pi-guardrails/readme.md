# Guardrails — `@aliou/pi-guardrails`

Source: https://github.com/aliou/pi-guardrails/blob/main/README.md
Fetched: 2026-10-22 (GitHub contents API, `main`)
Registry: npm `@aliou/pi-guardrails`, latest 0.19.0, MIT, deps `@aliou/sh`, `@aliou/pi-utils-settings`;
peer deps `@earendil-works/pi-coding-agent` and `@earendil-works/pi-tui` both `"*"`.
No GitHub security advisories as of the fetch date.

---

Guardrails adds safety checks to Pi so agents are less likely to read secrets, write protected files, access paths outside the workspace, or run dangerous shell commands by accident.

This package installs four Pi extensions:

- **guardrails** for file protection policies, settings, onboarding, and examples.
- **path-access** for controlling access outside the current workspace.
- **permission-gate** for confirming or blocking risky shell commands.
- **herdr** for reporting Guardrails approval prompts to Herdr.

## Install

```bash
pi install npm:@aliou/pi-guardrails
```

## First run

After installing, run the onboarding command to choose a starting setup:

```text
/guardrails:onboarding
```

You can change everything later with:

```text
/guardrails:settings
```

## Included extensions

### guardrails

The `guardrails` extension owns file protection policies and the user-facing commands.

Use it to protect files like `.env`, private keys, local credentials, generated logs, database dumps, or any project-specific path you do not want Pi to read or modify without clear intent.

Policy rules respect the working directory by default (`respectCwd: true`): a location-anchored pattern (`~`- or `/`-prefixed glob such as `~/work/**`) that happens to contain the session's cwd does not neuter the workspace. Name-based patterns (`.env`), relative path globs, and regex patterns still apply inside the cwd, so secrets stay protected. Set `respectCwd: false` on a rule to enforce anchored patterns everywhere.

Anchored patterns are matched against every equivalent spelling of a target (cwd-relative, `~/…`, and absolute), so a `~/…`-anchored rule holds no matter where the session starts or how the tool input spelled the path.

Useful commands:

```text
/guardrails:settings
/guardrails:onboarding
/guardrails:examples
```

#### Herdr integration

The included Herdr adapter reports active Guardrails approval prompts through Herdr's `herdr:blocked` event. Herdr can then show the Pi pane as blocked while it waits for a permission-gate or path-access decision.

The adapter has no configuration or direct Herdr dependency. Its emitted events have no effect unless Herdr's Pi integration is active.

### path-access

The `path-access` extension checks tool calls that target paths outside the current working directory.

It can allow, block, or ask before Pi accesses files elsewhere on your machine. In ask mode, you can allow one file or a directory once, for the session, or always.

Which operations are gated is controlled by `pathAccess.applyTo`: `"all"` (default) gates reads and writes outside the workspace, `"write"` gates writes only so read-only tools (`read`, `grep`, `find`, `ls`) can access skill and config files outside the project without a prompt. Bash commands are still gated: a command can write. Configurable through `/guardrails:settings` (Path Access → Applies to).

Where "always" grants are saved is controlled by `pathAccess.alwaysScope`: `"local"` (default) writes them to the project config (`{project}/.pi/extensions/guardrails.json`), `"global"` writes them to the user-wide config (`~/.pi/agent/extensions/guardrails.json`) so they apply in every project. Session grants stay in memory and "once" grants are not persisted, regardless of this setting.

Granted paths are stored in `pathAccess.allowedPaths` as explicit `{ kind, path }` entries: `file` matches the exact path, `directory` matches the directory and its descendants. Paths support `~/` for home. Existing configs using the legacy string form (trailing `/` for directories) are migrated automatically.

### permission-gate

The `permission-gate` extension detects dangerous bash commands before they run.

It catches built-in risky patterns like recursive deletes, privileged commands, disk formatting, broad permission changes, and configured custom patterns. You can allow once, allow for the session, deny, decline and stop (which also aborts the current turn), or configure auto-deny rules.

### Shell substitution checks

Built-in dangerous-command checks, file policies, and path-access extraction inspect commands inside command substitutions (`$(...)` and backticks) and process substitutions (`<(...)` and `>(...)`), including nested substitutions and expanded redirect targets. For example, `echo "$(cat .env)"` exposes the inner file access, while `echo "$(echo .env)"` still treats `.env` as text.

These checks inspect executable nodes provided by the shell parser; they do not evaluate expansions or reparse literal text. Single-quoted text and heredoc delimiters are not executable substitutions. The current parser leaves some constructs as raw text — heredoc bodies (note an *unquoted* heredoc body executes `$(...)` in bash), expansion operands such as `${value:-$(...)}`, and extglob patterns such as `@($(cmd))` — so substitutions in those locations remain outside this traversal.

## Extension events

Guardrails emits paired prompt lifecycle events on Pi's shared event bus:

- `guardrails:prompt:opened` when an interactive Guardrails prompt starts waiting for input.
- `guardrails:prompt:closed` when that prompt stops waiting, including when the UI throws.

Both events include the same `prompt.id` for correlation.

## Configuration

Most configuration should happen through the interactive settings UI:

```text
/guardrails:settings
```

Advanced users can edit the settings file directly:

- Global: `~/.pi/agent/extensions/guardrails.json`
- Project: `.pi/extensions/guardrails.json`

Guardrails writes a `$schema` field to saved settings files, so modern editors provide autocomplete and validation. The generated schema is committed at `schema.json`.

## Examples

Use the examples command to add common policy and command presets without replacing your existing config:

```text
/guardrails:examples
```

The available presets live in `extensions/guardrails/commands/settings/examples.ts`.

## Similar but different

Pi is designed to make agent safety extensible. Guardrails focuses on deterministic, configurable file policies, outside-workspace path access, and dangerous-command prompts. Other packages tend to fall into two useful groups.

See https://pi.dev/packages for the full registry of Pi extensions.

### Make one yourself

If Guardrails or the alternatives below do not fit your needs, you can also make your own. Start from the Pi permission gate example
(https://github.com/earendil-works/pi/blob/main/packages/coding-agent/examples/extensions/permission-gate.ts), then ask Pi to customize it for your workflow.

### Permission and policy gates

- `@gotgenes/pi-permission-system` — broad permission enforcement for Pi tool calls.
- `@vtstech/pi-security` — command, path, network, mode, and audit controls.
- `pi-control` (https://github.com/mcowger/pi-control) — location-scoped, action-based policies for tool calls, with allow, log, ask, and deny outcomes before execution.
- `@casualjim/pi-heimdall` — secret exposure guards, command policies, protected `.env` files, and a sandbox guard.
- `pi-file-permissions` — file-level permissions for read, write, edit, find, grep, and ls tools.
- `pi-secret-guard` — focused protection against committing or pushing secrets to git.

### Sandboxes and containment

- Pi + Gondolin sandbox example (https://github.com/earendil-works/gondolin/blob/main/host/examples/pi-gondolin.ts) — upstream example that runs Pi tools inside a Gondolin micro-VM.
- `pi-sandbox` — OS-level sandboxing for bash, with allow/deny checks and prompts for file tools.
- `pi-container-sandbox` — runs read, write, edit, bash, and user bash operations inside a Docker or Apple container session.
- `@alexanderfortin/pi-freestyle-sandbox` — runs sandboxed subagents in Freestyle cloud VMs.
- `@the-agency/vmpi` — runs Pi inside a QEMU microVM with limited filesystem and network access.
- `pi-claude-sandbox` — Claude-style OS sandboxing with interactive permission prompts.

---

## Configuration surface relevant to an unattended run

From the committed `schema.json` (https://github.com/aliou/pi-guardrails/blob/main/schema.json,
same fetch). These are the fields a headless pipeline would set in
`.pi/extensions/guardrails.json`, none of which require a TTY:

| Field | Type | Meaning |
|---|---|---|
| `enabled` | boolean | Enable or disable all Guardrails checks. |
| `applyBuiltinDefaults` | boolean | Include built-in policy rules before user rules are merged. |
| `features.{protectEnvFiles,policies,permissionGate,pathAccess}` | boolean | Per-extension toggles. |
| `policies.rules[]` | `PolicyRule` | `{ id, patterns[], protection }` required; `protection` is one of `none`, `readOnly`, `noAccess`. Optional `allowedPatterns`, `onlyIfExists` (default true), `respectCwd` (default true), `blockMessage`, `enabled`. |
| `pathAccess.mode` | `allow` \| `ask` \| `block` | Outside-workspace gate. `block` needs no prompt. |
| `pathAccess.applyTo` | `all` \| `write` | `all` (default) gates reads and writes; `write` lets `read`/`grep`/`find`/`ls` pass. |
| `pathAccess.allowedPaths[]` | `{ kind: "file"\|"directory", path }` | Always-allowed paths. |
| `permissionGate.autoDenyPatterns[]` | `PatternConfig` | "Command patterns that are always blocked without prompting." |
| `permissionGate.allowedPatterns[]` | `PatternConfig` | Command patterns that bypass dangerous-command prompts. |
| `permissionGate.customPatterns[]` | `DangerousPattern` | If set, **replaces** the default dangerous-command patterns entirely. |
| `permissionGate.patterns[]` | `DangerousPattern` | Additional dangerous-command patterns. |
| `permissionGate.requireConfirmation` | boolean | When true, prompt before dangerous commands; when false, only warn. |

`PatternConfig` is `{ pattern, description?, regex? }` — glob for files, substring for
commands by default; `regex: true` switches to full regex matching.

## Behaviour without a TTY

Guardrails' documented UX is interactive prompts, but its own issue tracker records
that a session with no UI **fails closed** rather than hanging — the relevant decision
degrades to a hard block:

- Issue #123: "Non-interactive sessions (subagents, `!ctx.hasUI`): a hard block."
  (https://github.com/aliou/pi-guardrails/issues/123)
- Issue #136: "In subagents, the command is blocked outright."
  (https://github.com/aliou/pi-guardrails/issues/136)
- Issue #122: the annotation gate is specified to "fail closed" "without a UI".
  (https://github.com/aliou/pi-guardrails/issues/122)

The same tracker records that path-extraction **false positives** are frequent and, in
a no-UI session, become hard failures of the run rather than a dismissable prompt:
`sed -n '/pat/,$p' file` (#123, fixed in 0.20.0), `node -e` / `python -c` fragments
such as `/1.055` and `/api/items` (#136, open), `2>/dev/null` under `mode: "block"`
(#89, open), and fd duplications such as `2>&1` (#90, open).
