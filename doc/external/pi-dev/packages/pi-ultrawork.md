# pi-ultrawork · Packages · Pi

Source URL: https://pi.dev/packages/pi-ultrawork
Fetched: 2026-10-20

Why this page is saved: it is a reuse candidate for the orchestration layer — it already
does persistent goal-driven autonomy plus fan-out to **child `pi` processes** whose NDJSON
events the parent parses, which is the same mechanism an external driver would use. Three
facts decide how far it carries us: the steer modal "is skipped in `print`, `json`, and
`rpc` modes so headless sessions pass input through unchanged" (so it is headless-safe);
`ulw_dispatch` takes `{ task, cwd }` with no model parameter (so it does **not** route a
different model per role); and `MAX_DISPATCH_DEPTH = 1` caps nesting. Version 1.2.0,
MIT, 0 dependencies / 4 peers.

---

# pi-ultrawork

Persistent, goal-driven UltraWork mode for pi.dev — auto-continues across turns and fans sub-tasks out to child pi processes.

## Package details

Types: extension, skill

Install `pi-ultrawork` from npm and Pi will load the resources declared by the package manifest.

- npm: https://www.npmjs.com/package/pi-ultrawork
- repo: https://github.com/hu9osaez/pi-ultrawork
- home: https://github.com/hu9osaez/pi-ultrawork#readme

```
$ pi install npm:pi-ultrawork
```

| Field | Value |
|---|---|
| Package | `pi-ultrawork` |
| Version | `1.2.0` |
| Published | Jul 27, 2026 |
| Downloads | not available |
| Author | hu9osaez |
| License | MIT |
| Types | extension, skill |
| Size | 91.2 KB |
| Dependencies | 0 dependencies · 4 peers |

Pi manifest JSON

```json
{
  "extensions": [
    "./src/index.ts"
  ],
  "skills": [
    "./SKILL.md"
  ]
}
```

## Security note

Pi packages can execute code and influence agent behavior. Review the source before installing third-party packages.

## README

# UltraWork

A pi.dev extension. Say a keyword, get a persistent **"running" mode**: a goal that survives across turns, a visible footer status, capped hidden auto-continuation, and background multi-agent fan-out.

The idea in one line: **the goal lives on disk, not in the chat context — so the agent keeps pursuing it even after context compaction.**

### What it does

* **Trigger** — say `ultrawork` or `ulw` (as a whole word) anywhere in a message to start or re-engage the mode. No command needed.
* **Persistent goal** — one run per session, stored as a JSON file on disk (`running` / `complete` / `stopped` / `stuck`). Because it lives outside the LLM context, it survives compaction — and a `session_compact` hook actively re-injects the mode framing on the next turn so the agent never loses the thread.
* **Always-on mode** — `/ulw always on` runs *every* message in UltraWork, no keyword needed; `/ulw always off` reverts.
* **Mid-run steering** — while a run is in progress, typing free text opens a single-keypress modal: `s` steers mid-stream (lands before the next LLM call), `q` queues for the next idle continuation, `d` discards, `e`/Esc returns to the editor. `/ulw-steer <text>` bypasses the modal and steers directly. `/ulw-steer` / `/ulw-steer clear` list and clear the queue.
* **Footer status** — always visible while a run exists:
  + `● UltraWork running — <goal…> (started Nm ago)` (goal truncated so it never floods the bar)
  + `UltraWork complete`
  + `UltraWork stopped (say "ultrawork" to start again)`
  + `UltraWork stuck after 2 idle retries — say "ultrawork" again to restart`
* **Auto-continuation** — while running, pi queues a hidden follow-up once each turn settles, nudging the agent forward. Capped at **2** unproductive attempts (reset by any completed `ulw_dispatch`) before the run is marked stuck instead of looping forever.
* **`ulw_dispatch` tool** — fans independent sub-tasks out to child `pi` processes (parallel with a concurrency cap, or sequential) and folds the results back in. Each child's live activity (thinking / tool calls / web search) streams into the chat as it happens, so a dispatch is no longer a black box. A depth-guard (`MAX_DISPATCH_DEPTH = 1`) stops dispatched children from spawning their own children.
* **`ulw_complete` tool** — the model calls this once the goal is genuinely achieved; it ends the run and disarms auto-continuation. It's the only success exit — the agent can't just declare victory in prose.

### Flow diagrams (ASCII)

These diagrams show the three main runtime paths: the run lifecycle, compaction + steering, and `ulw_dispatch` fan-out.

#### 1) Run lifecycle

```
[user sends a message]
          |
          v
[keyword match? OR always-on?] -- no --> [no UltraWork action]
          |
         yes
          |
          v
[before_agent_start]
          |
          v
[triggerRun updates JSON store]
          |
          v
[fresh run?] -- yes --> [show UltraWork directive in chat]
     |                            |
     no                           v
     |                      [agent works on goal]
     |                            |
     +----------------------------+
                                  |
                                  v
                           [agent_settled]
                                  |
                                  v
                 [run still running + no pending messages?]
                           |                      |
                          no                     yes
                           |                      |
                           v                      v
                 [wait for next event]   [auto-continue cap reached?]
                                                   |            |
                                                  yes          no
                                                   |            |
                                                   v            v
                                         [mark run stuck]   [queue hidden
                                         [notify user]       continuation]
                                                                  |
                                                                  v
                                                       [next turn continues goal]
```

#### 2) Compaction, steering, and control commands

```
[existing running run]
          |
          v
     [what happened?]
      /      |       \
     /       |        \
    v        v         v
[session_  [/ulw-    [/ulw stop
 compact]   steer]    / off /
    |        |        always on]
    |        |              |
    v        v              v
[set       [idle?]     [update run /
 pending      |         trigger state]
 reinject]  yes/no
    |      /      \
    |     /        \
    v    v          v
[next  [consume   [store steer in
 before_ steer      pendingSteers]
 agent_ now]              |
 start]   |               v
    |      v      [consume on next continuation]
    v   [queue visible
[inject  continuation]
 reinject
 directive once]

Extra command paths:
- /ulw-steer         -> list pending steers
- /ulw-steer clear   -> clear steer queue
```

#### 3) `ulw_dispatch` fan-out

```
[active UltraWork turn]
          |
          v
   [call ulw_dispatch]
          |
          v
 [spawn child pi processes]
          |
          v
 [each child handles one task]
          |
          +-----------------------------+
          |                             |
          v                             v
 [child emits NDJSON events]     [child finishes with
          |                       structured result]
          v                             |
 [parent parses activity]              |
 [thinking/tool/message]               |
          |                             |
          v                             v
 [live progress streams into   [parent folds results back
  the main chat]               into the current turn]
                                          |
                                          v
                           [dispatch made forward progress?]
                                   |                   |
                                  yes                 no
                                   |                   |
                                   v                   v
                        [reset auto-continue]   [normal continuation
                        [attempt counter]        rules still apply]
```

### Install

UltraWork is published on npm as `pi-ultrawork`. Install it in pi with the npm package locator:

```
pi install npm:pi-ultrawork
```

Then restart / `reload` pi. That's the whole install — pi resolves and loads the published package the same way it loads its built-ins. No build step: pi transpiles the TypeScript entry on load.

Point the extension at a local checkout instead of the published package:

```
// ~/.pi/agent/settings.json
{ "extensions": ["/abs/path/to/pi-ultrawork"] }
```

Or load it once without touching settings:

```
pi -e ./src/index.ts
```

`reload` pi after editing `settings.json`.

### Usage

```
ultrawork implement dark mode across the settings screens
```

That's it — no command. The mode starts, works autonomously across turns (fanning out independent sub-tasks via `ulw_dispatch` when useful), and ends when the model calls `ulw_complete`, the stuck cap is hit, or you run `/ulw stop`.

### Commands

```
/ulw               # show the current run (same as /ulw status)
/ulw status        # show the current run
/ulw stop          # stop the run; auto-continuation stops too
/ulw off           # mute the keyword trigger — "ultrawork"/"ulw" stop activating the mode
/ulw on            # re-arm the keyword trigger
/ulw always on     # run EVERY message in UltraWork, no keyword needed
/ulw always off    # revert to keyword-only triggering

/ulw-steer <text>  # steer mid-stream now (bypasses the modal, shown in chat)
/ulw-steer         # list pending steers
/ulw-steer clear   # empty the steer queue
```

While a run is active, typing any free text in the editor (instead of a slash command) opens a single-keypress modal:

| Key | Action |
| --- | --- |
| `s` | Steer mid-stream — delivered before the next LLM call (uses pi's native `deliverAs: "steer"`) |
| `q` | Queue — rides the next idle continuation via `/ulw-steer`'s disk queue |
| `d` | Discard the message |
| `e` / `Esc` | Return to the editor to keep typing |

`/ulw off` is what you want while **developing this extension** (or any repo where you type "ulw" a lot): it lets you say the trigger words freely without starting a run. `off` and `always on` are mutually exclusive — each clears the other. `/ulw always off` reverts triggering but never stops an in-flight run (that's `/ulw stop`). The steer modal and `/ulw-steer` need a running run; the modal only appears in TUI mode (it is skipped in `print`, `json`, and `rpc` modes so headless sessions pass input through unchanged).

### Agent tools

* `ulw_dispatch({ tasks: [{ task, cwd? }], concurrency?, sequential? })` — fan sub-tasks out to background `pi` processes.
* `ulw_complete({ summary? })` — signal the goal is achieved and end the run.

See SKILL.md for the full model-facing usage guide.

### Publishing

UltraWork ships as an npm package of **TypeScript source** — no build, no `dist/`. pi transpiles `src/index.ts` on load, so the published tarball just needs the source, the docs, and `package.json`.

The `package.json` declares what pi and npm need:

```json
{
  "pi":    { "extensions": ["./src/index.ts"], "skills": ["./SKILL.md"] },
  "files": ["src", "README.md", "SKILL.md", "LICENSE"]
}
```

Steps (use **`pnpm`** — `devEngines` pins the package manager, so `npm publish` fails):

```
pnpm test && pnpm typecheck        # 1. green bar before shipping
npm version patch                  # 2. bump (patch | minor | major)
pnpm pack --pack-destination /tmp  # 3. dry-run: inspect the tarball contents
pnpm publish --access public       # 4. publish
```

> Note: `npm login` also trips over `devEngines` inside the repo — run it from your home dir (`cd ~ && npm login`); the token is global.

Then anyone installs it with pi:

```
pi install npm:pi-ultrawork
```

That `pi install npm:<package-name>` form is exactly how pi resolves published extensions — the same mechanism as the built-ins.

### Inspiration

UltraWork is inspired by:

* **[lazyclaudecode](https://github.com/code-yeongyu/lazyclaudecode)**
* **[lazycodex](https://github.com/code-yeongyu/lazycodex)**

### Development

```
pnpm install
pnpm test        # vitest
pnpm typecheck   # tsc --noEmit
```
