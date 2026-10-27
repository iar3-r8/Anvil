# pi-crew · Packages · Pi

Source: https://pi.dev/packages/pi-crew
Fetched: 2026-10-27

> Pi extension for coordinated AI teams, workflows, worktrees, and async task orchestration

## Package details

Types: `extension`, `skill`

Install `pi-crew` from npm and Pi will load the resources declared by the package manifest.

* npm: https://www.npmjs.com/package/pi-crew
* repo: https://github.com/baphuongna/pi-crew

```
$ pi install npm:pi-crew
```

| Field | Value |
| --- | --- |
| Package | `pi-crew` |
| Version | `0.11.47` |
| Published | Oct 27, 2026 |
| Downloads | 10.2K/mo · 3,358/wk |
| Author | bom0792 |
| License | MIT |
| Types | extension, skill |
| Size | 10.5 MB |
| Dependencies | 7 dependencies · 5 peers |

Pi manifest JSON

```json
{
  "skills": [
    "./skills"
  ],
  "extensions": [
    "./index.ts"
  ]
}
```

### Security note

> Pi packages can execute code and influence agent behavior. Review the source before
> installing third-party packages.

---

## README

# pi-crew

**Multi-agent team orchestration for [Pi](https://github.com/nicekate/pi-coding-agent).**

pi-crew is a Pi extension that adds one `team` tool for coordinating autonomous agent workflows —
research, implementation, review, testing, and cleanup. Each task runs as a real child Pi process,
with durable on-disk state, parallel execution, and opt-in git-worktree isolation. Runs can be
monitored, steered, resumed, scheduled, and exported.

```
npm:   pi-crew
repo:  https://github.com/baphuongna/pi-crew
```

> ### ⚠️ IMPORTANT — Read before using
>
> **pi-crew was developed almost entirely by AI, for the author's own workflow.** It is not a
> hardened, audited product:
>
> * **AI-generated code, limited human review.** Every change ships after static review + runtime
>   tests, but nothing is independently audited.
> * **It acts on your machine.** It spawns processes, runs shell commands, and writes files —
>   including project-defined `.dwf.ts` scripts, which carry the same trust as any
>   `node script.js` you downloaded.
> * **Built for one workflow** (the author's). It may not fit yours — that's fine.
>
> If that's too risky, don't use it — no hard feelings. If you still want it: **fork it, read the
> parts you'll touch, and adapt it to your setup.**
> Details: trust model · security issues · Known limitations.

### Features

* **One `team` tool, 57 actions** — run, monitor, steer, schedule, and manage agents/teams/workflows.
* **Real child Pi workers** — each task spawns an isolated `pi` process; `runtime.mode: "scaffold"`
  gives a dry-run with prompts only.
* **Built-in teams & adaptive planning** — 6 teams and 11 workflows ship in the box; the `default`
  and `implementation` workflows let a planner agent pick the smallest effective crew.
* **Parallel execution + worktree isolation** — tasks in the same phase run concurrently;
  `workspaceMode: "worktree"` gives each task its own git worktree for safe parallel edits.
* **Durable runs** — manifest, tasks, events, and artifacts persist under `.crew/`; resume, retry,
  or steer in-flight tasks; export/import run bundles. `.crew/knowledge.md` injects durable project
  learnings into every worker prompt.
* **Async background runs** — `async: true` detaches a run so it survives session switches, with
  completion notification.
* **Dynamic workflows** — author orchestration as a `.dwf.ts` script with real JS loops/branching,
  typed `ctx`, phases, and token budgets.
* **Autonomous goal loops** — `action: "goal"` runs worker → LLM judge → feedback turns until the
  goal is achieved or budget/turn limits hit.
* **Inter-pi broker** — concurrent Pi sessions exchange messages and steering over a unix socket;
  on by default (Linux/macOS), three kill switches.
* **Observability & UI** — task list above the editor, agent dock, inline transcript panel,
  dashboard; per-run resource sampler + auto-generated performance report and cost breakdown.

### Install

```
pi install npm:pi-crew
```

> The `npm:` prefix is required — without it, `pi install` treats the argument as a local path.
> Requires Node ≥ 22.19.0 (`engines.node`).

#### Uninstall

`pi uninstall npm:pi-crew` removes the package, but pi has no uninstall hook — pi-crew-created
state is left behind. Reverse it explicitly:

```
team action=cleanup dryRun=true            # preview, no writes
team action=cleanup force=true             # remove project guidance block + .crew/
team action=cleanup scope=user force=true  # + user-level state and global config
pi uninstall npm:pi-crew                   # finally, the package itself
```

### Quick start

```
/team-init
/team-run Investigate failing tests and propose a fix
```

Or via tool calls:

```json
{ "action": "run", "team": "default", "goal": "Investigate failing tests and propose a fix" }
{ "action": "status", "runId": "team_..." }
{ "action": "recommend", "goal": "Refactor auth flow and add tests" }
{ "action": "run", "team": "implementation", "goal": "Refactor auth", "async": true, "workspaceMode": "worktree" }
```

`action: "recommend"` picks a team/workflow when you're unsure which fits. 42 slash commands
(`/team-status`, `/team-dashboard`, `/team-config`, …) cover ops and debugging.

### Built-in teams

| Team | Workflow shape | Use for |
| --- | --- | --- |
| `default` | adaptive: assess → parallel tasks → verify | general-purpose work |
| `fast-fix` | explore → execute → verify | small bug fixes |
| `implementation` | adaptive planner decides fanout | multi-file features/refactors |
| `review` | explore → code-review → security-review → verify | code + security review |
| `research` | explore → analyze → write | investigation and documentation |
| `parallel-research` | parallel shards → synthesize → write | multi-source audits |

18 built-in agents ship in `agents/` (explorer, planner, executor, critic, reviewer, verifier,
test-engineer, writer, analyst, oracle, librarian, …). Resources are discovered in three layers —
builtin package < user (`~/.pi/agent/`) < project (`.crew/`) — and project resources cannot shadow
builtin ones.

### Configuration

Config files (first found wins per scope):

| Scope | Path |
| --- | --- |
| User | `~/.pi/agent/pi-crew.json` |
| User (legacy, still read) | `~/.pi/agent/extensions/pi-crew/config.json` |
| Project | `.crew/config.json` (legacy layout: `.pi/teams/config.json`; alt: `.pi/pi-crew.json`) |

Most-used keys:

| Key | What it does |
| --- | --- |
| `runtime.mode` 🔒 | `auto \| scaffold \| child-process \| live-session` — how workers execute |
| `runtime.embeddedWorkers` | U11 hybrid tier, **DEFAULT-OFF**: opt roles into in-process (embedded) workers with 2-fault fallback to subprocess |
| `executeWorkers` 🔒 | `false` = dry-run planning only, no child processes |
| `asyncByDefault` 🔒 | detach every run by default (survives session switches) |
| `limits.maxConcurrentWorkers` | hard cap on parallel workers |
| `runtime.maxTurns` | per-task turn ceiling |
| `runtime.requirePlanApproval` | pause at the plan→execute boundary for approval |
| `worktree.linkNodeModules` | symlink `node_modules` into task worktrees |
| `agents.overrides` 🔒 | per-agent `model` / `skills` / `tools` override |
| `reliability.autoRetry` | auto-retry failed tasks |
| `broker.enabled` | inter-session message bus; default `true` (`PI_CREW_BROKER=0` always wins; auto-off on native Windows) |
| `notifications.webhook` 🔒 | opt-in outbound webhook on run completion — one POST per terminal run, quiet-hours-aware, SSRF-guarded |

🔒 = sensitive: settable in **user config only** — project config silently drops these keys with a
warning, so untrusted repos can't escalate privileges. Environment variables (`PI_CREW_BROKER`,
`PI_CREW_USE_BUNDLE`, …) are listed in `src/config/env-vars.ts`.

#### Webhook notifications (US-030)

Disabled by default — **no URL configured means zero network calls**. When a run reaches a terminal
status (`completed` / `failed` / `cancelled`), and it is outside `notifications.quietHours`,
pi-crew POSTs one JSON document to your URL (5 s timeout, exactly one retry on 5xx/network error,
failures never affect the run):

```json
"notifications": {
  "quietHours": "22:00-07:00",
  "webhook": {
    "url": "https://hooks.example.com/pi-crew",
    "enabled": true,
    "secret": "shared-secret",
    "allowLocalhost": false
  }
}
```

Payload (PII-safe — no transcripts or events, goal is first-line only):
`{ "event": "run.terminal", "runId": …, "status": …, "team": …, "goal": …, "durationMs": …, "cost": …, "tokens": …, "at": "<ISO>" }`.
With `secret` set, every request carries
`x-pi-crew-signature: sha256=<hmac-sha256(raw body, secret)>`. Non-http(s) URLs and
loopback/link-local targets (`localhost`, `127.0.0.0/8`, `[::1]`, `fe80::/10`, `169.254.0.0/16`)
are refused unless you set `allowLocalhost: true` explicitly. The whole `webhook` block is 🔒 —
user config only, so an untrusted repo cannot point your runs at an attacker URL.

### Where things live

| Doc | Contents |
| --- | --- |
| `docs/README.md` | index of all docs (living + archive) |
| `docs/usage.md` | usage patterns + config examples |
| `docs/actions-reference.md` | all 57 `team` actions with examples |
| `docs/commands-reference.md` | slash commands + `/team-api` |
| `docs/architecture.md` | internal architecture + run flow |
| `docs/troubleshooting.md` | common errors, recovery, error codes |
| `docs/trust-model.md` | trust boundaries + accepted risks |
| `docs/dynamic-workflows.md` | `.dwf.ts` runtime + its security model |
| `docs/resource-formats.md` | agent/team/workflow file formats |
| `docs/publishing.md` | release & publish process |

### Known limitations

* **`.dwf.ts` scripts are not sandboxed.** They run in plain module scope with full
  `require`/`process` access (postinstall-equivalent trust). Only run scripts you have reviewed.
* **Workers run with your privileges; verification is best-effort.** Guards (read-only defaults for
  unknown roles, path allowlists, sensitive-key sanitizing) raise the bar, but they are not a
  boundary against a malicious worker in the same process.
* **AI-developed, single maintainer.** Every change ships after static review + runtime tests, but
  there is no independent human audit.

### Development

```
npm install
npm test                # unit + integration suites
npm run test:critical   # fast broker/UI subset (~20s)
npm run typecheck       # tsc --noEmit + strip-types import check
npm run lint            # biome (linters only)
npm run format:check    # biome format
npm run ci              # full gate: checks, typecheck, lint, bundle, tests, pack
npm run build:bundle    # rebuild dist/index.mjs
```

Running Pi sessions load the pre-built `dist/index.mjs` bundle — rebuild
(`npm run build:bundle`, or `npm run watch:bundle` while editing) and start a new Pi session to
pick up source changes.

### License

MIT.
