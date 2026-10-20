# pi-ultrawork — source-review verdict

Source review of **pi-ultrawork 1.2.0** (npm, MIT, 16 files, ~93 KB; 0
runtime dependencies, 4 peers: `@earendil-works/pi-ai`,
`pi-coding-agent`, `pi-tui`, `typebox`), performed against the published
tarball. The package is the phase-1 *subject under test* of the Pi
bake-off (`plans/pi-phase1-bakeoff.md`), not a dependency of Anvil —
nothing here is installed in this repository, so the package source is not
vendored; the file:line citations below are recorded from the completed
review, and the interface facts are corroborated by the saved package page
[`doc/external/pi-dev/packages/pi-ultrawork.md`](external/pi-dev/packages/pi-ultrawork.md).

## Verdict: safe to depend on, with caveats

### Safe

- **No dangerous primitives.** No network calls, no `eval`/`Function`, no
  dynamic `require` of untrusted paths. Imports are limited to
  `node:child_process`, `node:fs`, `node:path`, `node:crypto` and the four
  pi runtime peers.
- **No shell.** `spawn` is called with an argument list and
  `shell: false` (`src/ultrawork/dispatch.ts:242`, `runDispatchTask`).
- **Fan-out is bounded.** `MAX_TASKS=12`, `MAX_CONCURRENCY=6` (default 3),
  a 10-minute per-task timeout with SIGTERM→SIGKILL escalation (5 s grace),
  and a 20 KB per-stream output cap.
- **The whole process tree is bounded, not just one call.** Each
  dispatched child inherits `PI_ULTRAWORK_DISPATCH_DEPTH` incremented by
  one; `MAX_DISPATCH_DEPTH=1`, and `runDispatch` refuses to spawn when the
  process is already a dispatched child.
- **The goal is treated as data.** It is wrapped in `<untrusted_goal>` and
  every injected prompt tells the model to treat it as data, not as
  higher-priority instructions (`src/ultrawork/prompt.ts`); the goal text
  is XML-escaped against tag breakout.
- **The store is validated.** Per-session JSON at
  `<sessionDir>/extensions/ultrawork/<threadId>.json`, with a `no-session`
  fallback under the agent directory keyed by `sha256(cwd)`.
  `STORE_VERSION=1`, validated on read: corrupt or version-mismatched store
  → warning + reset to default; missing file → default.
- **Headless-safe.** The steer modal is skipped when
  `ctx.mode !== "tui"` and auto-continuation is skipped when
  `!ctx.hasUI` (`src/index.ts`) — `print`/`json`/`rpc` modes pass input
  through unchanged.

### Caveats (stated, not softened)

1. **A dispatched task is a full child prompt.** The `task` text becomes a
   complete child `pi` prompt with the full tool set. A goal is effectively
   a command in practice, not just data: a malicious or confused goal can
   drive the child's tools.
2. **Children inherit the parent environment wholesale.**
   `env: {...process.env, ...}` — credentials in the parent env (HF token,
   API keys) are visible to every dispatched child.
3. **Auto-continuation does not operate in headless modes.** The
   "persistent autonomy" pitch — the agent keeps pursuing the goal
   unattended — is TUI-only. It does not apply to `--print` /
   `--mode json`.
4. **The keyword trigger is broad.** `\b(?:ultrawork|ulw)\b` (whole-word,
   case-insensitive) fires on any interactive message containing the word;
   always-on mode (`/ulw always on`) turns every prompt into a run. Muted
   with `/ulw off`.

### Layer-thickness interface facts

The facts that decide whether Anvil builds on pi-ultrawork rather than on
bare Pi:

| Fact | Where |
|---|---|
| `ulw_dispatch({ tasks: [{ task, cwd? }], concurrency?, sequential? })` — **no model argument**, so no per-role model routing | [`doc/external/pi-dev/packages/pi-ultrawork.md`](external/pi-dev/packages/pi-ultrawork.md) (Agent tools) |
| `MAX_DISPATCH_DEPTH=1` — a single level of fan-out | this review (Safe, depth guard) |
| The steer modal and auto-continuation are skipped in `print`/`json`/`rpc` | [`doc/external/pi-dev/packages/pi-ultrawork.md`](external/pi-dev/packages/pi-ultrawork.md) (Usage); this review (Safe, headless-safe) |

## Sources

- [`doc/external/pi-dev/packages/pi-ultrawork.md`](external/pi-dev/packages/pi-ultrawork.md)
  — pi.dev package page for `pi-ultrawork` 1.2.0 (MIT), saved in full from
  https://pi.dev/packages/pi-ultrawork
- Completed source review of the npm 1.2.0 tarball (16 files, ~93 KB);
  file-level findings recorded in this document from
  `src/ultrawork/dispatch.ts`, `src/ultrawork/prompt.ts` and `src/index.ts`
