# pi-git-guardrails · Packages · Pi

Source: https://pi.dev/packages/pi-git-guardrails
Fetched: 2026-10-22 (Oxylabs universal scraper, rendered)
Source code read the same day from https://github.com/ramaaudra/pi-git-guardrails
(`src/index.ts`, `src/rules.cjs` on `main`).

---

## Package details

Native Pi extension that blocks dangerous git operations, including git calls hidden
inside scripts.

| Field | Value |
|---|---|
| Package | `pi-git-guardrails` |
| Version | `0.1.1` |
| Published | Apr 29, 2026 |
| Downloads | not available |
| Author | ramaaudra |
| License | MIT |
| Types | extension |
| Size | 26.3 KB |
| Dependencies | 0 dependencies · 1 peer |

Registry check (npm, same day): **2 published versions total** (`0.1.0`, `0.1.1`);
**no GitHub security advisories**. The declared peer dependency is
`@mariozechner/pi-coding-agent": "*"`, and `src/index.ts` imports `ExtensionAPI`,
`ExtensionContext` and `isToolCallEventType` from that same package — **not** from
`@earendil-works/pi-coding-agent`, which is the package Anvil installs
(`doc/external/pi-dev/readme.md`).

Pi manifest JSON:

```json
{
  "extensions": [
    "./src/index.ts"
  ]
}
```

### Security note (from the package page)

> Pi packages can execute code and influence agent behavior. Review the source before
> installing third-party packages.

## README

### Install

```
pi install npm:pi-git-guardrails
```

From GitHub:

```
pi install git:github.com/ramaaudra/pi-git-guardrails
```

Project-local install from GitHub:

```
pi install git:github.com/ramaaudra/pi-git-guardrails -l
```

Try a local checkout for one run:

```
pi -e ./pi-git-guardrails
```

### Blocked by Default

* `git push` in all variants
* `git reset --hard`
* `git clean -f`, `git clean -fd`, `git clean --force`
* `git branch -D` and force branch deletion
* `git checkout .`, `git checkout -- .`, `git restore .`

Path-specific restore/checkout remains allowed, for example `git restore src/app.ts`
and `git checkout -- src/app.ts`.

### Commands

* `/git-guardrails status` shows ON/OFF, session block count, pending allow-next,
  active rules, and recent audit entries.
* `/git-guardrails allow-next push` allows exactly one matching `git push`, including
  from nested scripts.
* `/git-guardrails off 5m` disables the guardrail temporarily. Supports `s`, `m`, and
  `h` suffixes.
* `/git-guardrails on` re-enables immediately and clears any temporary off timer.

### Nested Script Protection

The extension prepends a session-local directory containing a `git` shim to `PATH` for
assistant Bash calls. This catches normal `git ...` calls inside scripts, package
scripts, Makefiles, and similar child processes.

Known limits (the package's own wording):

* It does not catch scripts that call an absolute git path such as `/usr/bin/git`.
* It does not catch programs that use a Git library directly instead of spawning `git`.
* It is a coding-agent safety guardrail, not an OS-level sandbox.

---

## Source-level facts

Read from `src/rules.cjs` and `src/index.ts` on `main`, 2026-10-22.

### The rule set is hard-coded, with no configuration

`RULES` is a module-level constant of exactly five entries — `push`, `reset-hard`,
`clean-force`, `branch-force-delete`, `mass-discard`. `evaluateGitArgv` dispatches on
the git subcommand against those five and returns `null` for everything else. There is
no settings file, no schema, and no documented config key anywhere in the package: the
blocked set cannot be extended or narrowed without forking.

### `git commit` is not blocked, by design or omission

`evaluateGitArgv` has no `commit` branch, so `git commit` returns `null` and the call
proceeds. The same is true of `git merge`, `git rebase`, `git cherry-pick`, `git tag`,
`git stash drop`, `git remote` and `git config`. The package's stated threat model is
losing work and publishing to a remote, not keeping an agent out of history entirely.

### How a block is produced, and whether it needs a TTY

The `tool_call` handler returns `{ block: true, reason }` for a violation
(`src/index.ts`). That is a plain refusal with no prompt and no `ctx.ui.select` call,
so it does not depend on a UI. `ctx.ui.notify` is called alongside it, and
`ctx.ui.setStatus` on `session_start`.

### The shim rewrites the agent's bash command

For every non-violating bash call, the handler mutates `event.input.command`,
prepending three `export` lines (`PI_GIT_GUARDRAILS_STATE`,
`PI_GIT_GUARDRAILS_REAL_GIT`, `PATH`) joined with `;\n`. The real git path is resolved
once per session by running `/bin/sh -lc "command -v git"` via `spawnSync`, and a shim
is written to a `mkdtempSync` directory under the OS temp dir with mode `0o755`.

Two consequences worth recording: the command the model wrote is not the command that
runs, which changes what a captured event stream shows; and the guard's own state lives
in a world-readable temp directory as JSON.

### The parser is hand-rolled, not a shell parser

`shellSegments` is a character loop handling quotes, escapes, `;`, `&&`, `||` and `|`.
It does not parse command substitution, process substitution or heredocs. It does
handle env-assignment prefixes and the `command`/`builtin`/`noglob`/`env` wrappers
(`stripCommandWrappers`), and git's global options that take a value (`-C`, `-c`,
`--git-dir`, `--work-tree`, and others) before reading the subcommand.

### The guard can be turned off from inside the session

`/git-guardrails off 5m` sets `disabledUntil` in the state file, and
`/git-guardrails allow-next push` sets a one-shot bypass. Both are registered commands,
so they are reachable by whatever drives the session.
