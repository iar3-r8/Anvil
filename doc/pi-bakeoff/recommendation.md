# Pi phase 1 — bake-off recommendation

The phase-1 bake-off
([`plans/pi-phase1-bakeoff.md`](../../plans/pi-phase1-bakeoff.md), issue
iar3-r8/anvil#48) records a verdict on two independent questions:

- **(a) Local-model viability** — can a local model drive Pi unattended on
  the trivial fixture task?
- **(b) Layer thickness** — does `pi-ultrawork` replace machinery Anvil
  would otherwise write, or should the driver use bare Pi?

**(b) is answerable now and is answered here. (a) is pending the host run**
— the three run records (`run-print/`, `run-json/`, `run-ultrawork/`) do
not exist yet, and this document does not invent them.

## Verdict: (b) lean bare Pi; (a) pending

**(b) Layer thickness — lean bare Pi.** The driver should be built on
bare `pi` invocation forms (`-p` and `--mode json`) without
`pi-ultrawork`. `pi-ultrawork` is recorded as *safe to depend on, with
caveats*
([`doc/pi-ultrawork-review.md`](../pi-ultrawork-review.md)) — but nothing
it provides is something the driver needs, and one of its two pitches is
a no-op in the only modes a driver can use.

**(a) Local-model viability — PENDING the host run.** The three run
records do not exist yet. When they are produced per
[the host run recipe](README.md):

- any record with `completed` `true` (exit code 0 **and** the fixture
  assertion passing — the closed rule in
  [`anvilkit/pirecord.py`](../../anvilkit/pirecord.py) `build`) is GO
  evidence for the configuration it came from;
- **if no configuration completes, this is a recorded NO-GO** — the
  verdict line `render_table` emits, the failure mode and the model named
  in this document, and the roadmap pauses pending a model or prompt fix.
  A negative result is a success for issue #48: the question asked was
  "can a local model drive Pi unattended?", and an honest NO-GO with the
  evidence is the answer. It is not a reason to work around the task or
  retry with a simpler one.

## Evidence for (b): layer thickness

All claims below are cited to the source-review verdict page or a saved
page. No run record is cited, because none exists yet.

| Claim | Citation |
|---|---|
| `ulw_dispatch({ tasks: [{ task, cwd? }], concurrency?, sequential? })` takes **no model argument** — fan-out children run on the parent's session model, so pi-ultrawork provides no per-role model routing. Anvil's two-tier design (frontier plans, local codes) needs exactly that routing, and it is not in the package. | [`doc/external/pi-dev/packages/pi-ultrawork.md`](../external/pi-dev/packages/pi-ultrawork.md) (Agent tools); the gap on the bare-Pi side is unchanged since the spike ([`doc/pi-code-spike-recommendation.md`](../pi-code-spike-recommendation.md), verdict: switch, reason 1) |
| **Headless auto-continuation is a no-op.** The "keeps pursuing the goal unattended" mechanism is TUI-only: the steer modal is skipped when `ctx.mode !== "tui"` and auto-continuation when `!ctx.hasUI`. A driver runs Pi in `print`/`json` mode, where neither operates — so the package's central value proposition does not apply to the driver's harness form. | [`doc/pi-ultrawork-review.md`](../pi-ultrawork-review.md) (Safe, headless-safe; Caveat 3) |
| What remains for a headless driver is the fan-out tool itself — and that is exactly the machinery Anvil would otherwise write: spawning bounded child `pi` processes and folding results back. `MAX_DISPATCH_DEPTH=1` and the bounded concurrency are real, but they describe the package's discipline, not a capability Anvil lacks: a driver that spawns its own children with a list argv and no shell has the same bounds by construction. | [`doc/pi-ultrawork-review.md`](../pi-ultrawork-review.md) (Safe, fan-out bounded; depth guard) |
| The caveats cut against adoption, not for it. A dispatched task is a full child prompt with the full tool set; children inherit the parent environment wholesale (credentials visible to every child); the keyword trigger fires on any message containing the word. For an unattended driver the first two are standing risks, not edge cases. | [`doc/pi-ultrawork-review.md`](../pi-ultrawork-review.md) (Caveats 1–4) |

The ultrawork run configuration in the bake-off exists to **measure**
pi-ultrawork's overhead (does the model call `ulw_dispatch` at all on a
single-file task? what do the `tool_calls` counters and `wall_time_s`
record?), not to pre-commit to it. The record field to read when the
`run-ultrawork/` record lands is `tool_calls` — a run where
`ulw_dispatch` is never called is evidence that the model does not reach
for the layer on small tasks, recorded verbatim, not a failure to retry.

## What the pending host run will add

| Question | Evidence source | Status |
|---|---|---|
| (a) Does any configuration complete? | `completed` in each run record | **PENDING** — host run ([`README.md`](README.md), steps 5–7) |
| (a) Does the model stall on input? | `waited_for_input` + evidence string in each record | PENDING |
| (a) How much does the task cost? | `tokens`, `cost_total`, `wall_time_s` per record | PENDING |
| (b) Does the model use `ulw_dispatch` on a trivial task? | `tool_calls` in the ultrawork record | PENDING — reinforces the lean, does not overturn the (b) verdict, which rests on the interface facts above |

## Sources

- [`plans/pi-phase1-bakeoff.md`](../../plans/pi-phase1-bakeoff.md) — the plan: scope, interface facts, behaviours 13–18
- [`doc/pi-ultrawork-review.md`](../pi-ultrawork-review.md) — behaviour 16: the source-review verdict on pi-ultrawork 1.2.0
- [`doc/pi-bakeoff/README.md`](README.md) — behaviour 18: the host run recipe producing the three run records
- [`anvilkit/pirecord.py`](../../anvilkit/pirecord.py) — `build` (closed thirteen-key record; `completed` = exit 0 and assertion passed), `render_table` (GO / PARTIAL / NO-GO verdict line)
- [`anvilkit/piargv.py`](../../anvilkit/piargv.py) — the three invocation argvs and the models document
- [`anvilkit/pifixture.py`](../../anvilkit/pifixture.py) — the generated trivial red task
- [`doc/external/pi-dev/packages/pi-ultrawork.md`](../external/pi-dev/packages/pi-ultrawork.md) — pi-ultrawork package page (saved in full)
- [`doc/pi-code-spike-recommendation.md`](../pi-code-spike-recommendation.md) — the prior spike: bare Pi has no per-mode model routing, unchanged by this phase
