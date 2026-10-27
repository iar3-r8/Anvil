# pi-roles · Packages · Pi

Source: https://pi.dev/packages/pi-roles
Fetched: 2026-10-27

> Role-based session configuration for pi coding agent. Launch a session as a named role and
> hot-swap roles mid-session, with optional pi-intercom and pi-mcp-adapter integration.

## Package details

Type: `extension`

Install `pi-roles` from npm and Pi will load the resources declared by the package manifest.

* npm: https://www.npmjs.com/package/pi-roles
* repo: https://github.com/lojacobs/pi-roles

```
$ pi install npm:pi-roles
```

| Field | Value |
| --- | --- |
| Package | `pi-roles` |
| Version | `0.2.3` |
| Published | May 5, 2026 |
| Downloads | 110/mo · 12/wk |
| Author | lojacobs |
| License | MIT |
| Types | extension |
| Size | 74 KB |
| Dependencies | 1 dependency · 5 peers |

Pi manifest JSON

```json
{
  "extensions": [
    "./dist/index.js"
  ]
}
```

### Security note

> Pi packages can execute code and influence agent behavior. Review the source before
> installing third-party packages.

---

## README

# pi-roles

> Role-based session configuration for [pi coding agent](https://github.com/badlogic/pi-mono).
> Launch a session as a named role (architect, planner, marketing-strategist, …) and hot-swap
> roles mid-session — without restarting Pi.

`pi-roles` is to **top-level pi sessions** what [`pi-subagents`](https://github.com/nicobailon/pi-subagents)
is to **sub-agents**: same `.md` + YAML frontmatter convention, same project/user scope rules,
drop-in flow. The extension is **agnostic of which roles exist** — roles are just markdown files
you create.

```
pi --role architect              # launch as architect
PI_ROLE=planner pi               # or via env

/role list                       # inside the session
/role planner                    # swap role mid-session, keep history
/role planner --reset            # swap role and clear history
/role current
/role reload                     # re-read the active role file from disk
```

When you swap roles, the session's **system prompt, model, thinking level, and active tool set**
are replaced according to the new role's definition. Conversation history is preserved by default.

---

### Install

```
pi install npm:pi-roles
```

Then restart pi. The extension is auto-discovered; the `--role` flag and `/role` command become
available.

To try without installing:

```
pi -e git:github.com/lojacobs/pi-roles
```

---

### Why this exists

When you build a multi-agent dev workflow with specialized roles — architect (design), planner
(decompose), orchestrator (dispatch), or any equivalent for marketing, research, ops — the
*top-level* role is a property of the whole session, not of an individual sub-agent dispatch. You
want different system prompts, different models, different tool restrictions per role, and you
want to switch between them without restarting.

`pi-roles` is the cleanest way to do that. No shell aliases, no separate workspace directories,
no forking pi-subagents into something it isn't.

---

### Role files

Roles are markdown files with YAML frontmatter, identical in shape to `pi-subagents` agent files:

```markdown
---
name: architect
description: Defines the WHAT. Owns architecture and specs. Never codes.
model: anthropic/claude-opus-4-7
thinking: high
tools: read, grep, find, ls, write, edit
intercom: send             # optional, per-role override
extends: base-reviewer     # optional, role inheritance
---

# Role

You are the Architect. Your job is to define WHAT the system should
do, never HOW to build it...

(everything below the frontmatter is the system prompt body)
```

#### Frontmatter reference

| Field | Required | Behavior when omitted |
| --- | --- | --- |
| `name` | yes | — must match the filename without `.md` |
| `description` | yes | — shown in `/role list` and selectors |
| `model` | no | keeps the session's current model |
| `thinking` | no | keeps the session's current thinking level (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`) |
| `tools` | no — see below | inherits from parent (if `extends`) or keeps current active set |
| `intercom` | no | falls back to the global `intercomMode` setting |
| `extends` | no | role inherits from another role |

##### `tools` — the tri-state

Three explicit states with three different meanings:

| YAML | Meaning |
| --- | --- |
| `tools: read, bash` | **set** — exactly these tools, nothing else |
| `tools:` (present, empty) | **disable all tools** — read-only conversation, no actions |
| field absent | **inherit** — from parent role (`extends`), else keep session default |

You can also include MCP tool refs in the same field, mirroring `pi-subagents`:

```
tools: read, grep, mcp:chrome-devtools, mcp:github
```

`mcp:server-name` entries require [`pi-mcp-adapter`](https://github.com/nicobailon/pi-mcp-adapter)
to be installed. If it's not, the entry is logged and skipped — the role still loads.

##### `model` — provider/id format

Matches Pi's CLI `--model` syntax:

```
model: anthropic/claude-opus-4-7
model: openai/gpt-5
model: deepseek/deepseek-v4-pro
```

If the model isn't available (no API key, unknown provider), the role load surfaces a warning and
the session keeps its current model.

##### `intercom` — per-role override

Values: `off`, `receive`, `send`, `both`. Defaults to the global `intercomMode` setting (which
itself defaults to `off`).

##### `extends` — role inheritance

```
extends: architect
```

A child role inherits everything from its parent and overrides selectively. Chains are supported
(`A extends B extends C`); cycles are detected at load time and produce a hard error.

**Merge rules:**

* `model`, `thinking`, `description`, `intercom`: child wins if set, else parent value.
* `tools`: see the tri-state above. **Set overrides; empty disables; absent inherits.**
* Markdown body: parent's body is **prepended** to child's body with a separator. Useful for
  "stricter variant" patterns (`architect-strict extends architect`).
* `name`: never inherited — always the child's own filename.

---

### Discovery

Roles are looked up in this order, **first match wins** for any given name:

| Scope | Path | Marker in `/role list` |
| --- | --- | --- |
| project | `<repo>/.pi/roles/<name>.md` (or any ancestor) | `[project]` |
| user | `~/.pi/agent/roles/<name>.md` | `[user]` |
| built-in | bundled with the package | `[built-in]` |

When a project-scope role shadows a user-scope role of the same name, the user-scope entry is
listed under a separate "Shadowed" heading in `/role list` output so you know it exists but won't
load.

The default `roleScope` is `both` (project + user + built-in). Override via settings:

```json
// ~/.pi/agent/settings.json
{
  "pi-roles": {
    "roleScope": "both",
    "defaultRole": "architect",
    "intercomMode": "off",
    "titleModel": "openai/gpt-4o-mini"
  }
}
```

---

### Built-in `role-assistant`

`pi-roles` ships **one** built-in role: `role-assistant`. It's the default fallback when no
`defaultRole` is configured and you don't pass `--role` or `PI_ROLE`.

The role-assistant:

1. Lists the roles available on your machine (project + user + built-in) on its first turn.
2. Shows the exact command to switch to one (e.g. `/role architect`).
3. Offers to help you build a **new** role: it asks the questions, drafts the markdown, shows it
   for your approval, writes it to project or user scope (your choice), and then prints the
   command for you to launch it (`/role <new-name> --reset`).

You can override the built-in by dropping a `role-assistant.md` into your project or user roles
directory — the same priority rules apply.

---

### Slash command

`/role <subcommand>` — Tab-completes role names against the current scope.

| Form | Behavior |
| --- | --- |
| `/role <name>` | Switch to `<name>`. **Preserves history.** Re-reads the file from disk (no caching). |
| `/role <name> --reset` | Switch to `<name>` **and** clear history (equivalent to `/new` + apply role). |
| `/role list` | List discovered roles with scope markers and shadowing info. |
| `/role current` | Show the currently active role's name, extends chain, description, and source path. |
| `/role reload` | Re-read the **currently active** role's file from disk and re-apply. |

---

### CLI flag and env var

```
pi --role architect "Help me design the auth schema"
PI_ROLE=architect pi
```

Resolution order: `--role` > `PI_ROLE` > `defaultRole` setting > built-in `role-assistant`.

---

### Session name and footbar

Each session is named `<role-name>`. The session name is set via Pi's native
`pi.setSessionName()` API, so it shows in Pi's session selector and `/resume` listings, and
[`pi-intercom`](https://github.com/nicobailon/pi-intercom) automatically uses it as the session
target.

**Title generation model** (planned). The `titleModel` setting is reserved for the future
intent-summarization step; it has no effect today.

---

### pi-intercom integration

[`pi-intercom`](https://github.com/nicobailon/pi-intercom) is an **optional peer dependency**.
`pi-roles` works without it; intercom features are no-ops when it's not installed.

| Mode | Behavior |
| --- | --- |
| `off` | Default. No intercom tools, no prompt mentions. |
| `receive` | Role can be targeted by other sessions but won't proactively send. |
| `send` | Role can send to other sessions but doesn't expect inbound coordination. |
| `both` | Full bidirectional coordination — `intercom` tool active, prompt encourages use. |

**Inter-session messaging is always between named sessions on the same machine** — `pi-roles`
only opts roles in or out, it doesn't manage the broker, the protocol, or the message store.

---

### pi-mcp-adapter integration

When [`pi-mcp-adapter`](https://github.com/nicobailon/pi-mcp-adapter) is installed, you can list
MCP tools alongside built-ins in the `tools` field with the `mcp:server-name` syntax. If
`pi-mcp-adapter` isn't installed, the `mcp:*` entries are logged and skipped — the role still
loads with its built-in tools.

---

### Hot reload

`/role reload` re-reads the **currently active** role's file from disk and re-applies it.

`/role <name>` (without `--reset`) also always re-reads from disk — there's no hidden cache
between switches. For roles with `extends`, the entire chain is re-resolved on every load.

---

### Settings reference

```json
// ~/.pi/agent/settings.json (global) or .pi/settings.json (project)
{
  "pi-roles": {
    "roleScope": "both",
    "defaultRole": "role-assistant",
    "intercomMode": "off",
    "titleModel": "openai/gpt-4o-mini",
    "warnOnMissingMcp": true
  }
}
```

| Key | Default | Description |
| --- | --- | --- |
| `roleScope` | `"both"` | Discovery scope. `"user"`, `"project"`, or `"both"`. |
| `defaultRole` | `"role-assistant"` | Role applied at session start when no `--role` or `PI_ROLE`. |
| `intercomMode` | `"off"` | Default intercom behavior for roles that don't set it explicitly. |
| `titleModel` | `null` (auto) | Model used for session-intent summarization. |
| `warnOnMissingMcp` | `true` | Whether to surface a warning when a role's `mcp:*` entry can't be resolved. |

Project settings beat global settings, per Pi's standard precedence.

---

### What this extension does **not** do

* **Spawn sub-agents.** That's [`pi-subagents`](https://github.com/nicobailon/pi-subagents).
* **Define any built-in roles other than `role-assistant`.** Roles are user content.
* **Manage parallel sessions.** Use multiple terminals or `tmux`.
* **Persist which role was active across pi restarts** — except via `--role` / `PI_ROLE` /
  `defaultRole`. By design.
* **Restrict which tools a role can request.** If a role lists `bash`, it gets `bash`. Permission
  boundaries are your call — pair with
  [`permission-gate.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/examples/extensions/permission-gate.ts)
  or a similar guard if you need them.

---

### Design choices worth knowing

These are decided, not configurable, so the extension behaves predictably:

* **Markdown body fully replaces Pi's default system prompt.** No silent merging — most
  non-coding roles are polluted by the default "expert coding assistant" framing, so by design the
  role body is authoritative. The handler returns `{ systemPrompt: <role body> }` from
  `before_agent_start` and ignores the upstream chain value. If you want to keep Pi's default
  content (or compose with another extension), include the relevant text in your role body
  explicitly.
* **Role inheritance**: `model`/`thinking` override; `tools` is tri-state (set/empty/absent);
  markdown body is **prepended**.
* **Cycle detection in `extends`** is a hard error at load time, not a warning.
* **`/role <name>` always re-reads from disk.** No staleness between switches, ever.
* **`--reset` is explicit.** Resetting is destructive enough to deserve a deliberate keystroke.
* **Title generation** (planned, not yet implemented).
* **Built-in `role-assistant` lives at the lowest discovery priority.**
* **`/role list` shows shadowed entries** with a `(shadowed)` marker.

---

### Layout on disk

```
~/.pi/agent/roles/
  architect.md
  planner.md
  orchestrator.md

<repo>/.pi/roles/
  architect.md          # overrides the user one for this project
```

The extension itself ships only `role-assistant.md` (built-in scope) and the runtime code.

---

### License

MIT.

### Credits

Inspired by and structurally indebted to [`pi-subagents`](https://github.com/nicobailon/pi-subagents)
(frontmatter convention, scope discovery),
[`pi-prompt-template-model`](https://github.com/nicobailon/pi-prompt-template-model) (per-trigger
model/skill/thinking switching), and the
[`preset.ts`](https://github.com/badlogic/pi-mono/blob/main/packages/coding-agent/examples/extensions/preset.ts)
example in pi-mono.
