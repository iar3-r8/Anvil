# pi-crew spike — recommendation

Issue iar3-r8/anvil#84 asks for an adopt/reject decision on `pi-crew`.
This page records the three unknowns that decision turns on. Two of them
can only be answered by a recorded run — the run recipe is in
[`README.md`](README.md) — so those sections carry a marker line instead
of a verdict until the run exists. The third is answerable from the saved
source alone, and it is answered here.

## 1. Headless `team` tool load

**The question.** Does pi-crew's `team` tool load and run
non-interactively under pi 1.3.0 — the spike's single invocation, one `pi`
process in JSON mode with the crew extension loaded via `-e` and the tools
allowlisted to `read,edit,write,team`? The `team` tool is the extension's
only tool: the multi-worker orchestration (explore, execute, verify) that
spawns a child Pi process per crew task. "Load" means the extension
registers when Pi starts; "run" means the model actually calls it on the
trivial red fixture task, and the crew state machine writes its project
state under `.crew/`.

For a non-expert: the operator runs one command (the recipe in
[`README.md`](README.md)) and then reads data, not an impression —
`record.json` carries a `team_tool_seen` field that is true only if the
captured event stream shows the tool executing, and the `.crew/` tree
under `./results/fixture/.crew/` is present only if the crew state machine
actually ran.

**GO**.
The recorded run 2 (driven by the harder delegation goal,
`CREW_SPIKE_PROMPT` — run 1, driven by the trivial goal, solved the task
directly without calling `team`, which is why the goal was hardened) shows
the tool loaded and ran: the top-level model's only executed tools were the
two `team` actions — `run` and `summary` — no direct read or edit, so the
work was delegated to the crew, not done by the parent. Model routing hit the
local gateway throughout, every model call addressing
`llamaswap/Qwen/Qwen3.8-27B-FP8`. The crew executed the full 3-task
`fast-fix` workflow headless — `01_explore` (explorer), `02_execute`
(executor), `03_verify` (verifier), all completed — and wrote a live `.crew/`
state tree; `record.json` carries `team_tool_seen: true`, `completed: true`,
exit 0 and a wall time of 298.2 s, with the populated `crew_tree`
(`README.md`, `state/metrics/2026-11-02.jsonl`, …).

## 2. Postinstall and `--ignore-scripts`

**Answered: keep `--ignore-scripts`.**

Every Anvil npm global install runs with `--ignore-scripts`, so before the
spike could adopt pi-crew it had to decide whether that flag is safe for
this package. The decision rests on the saved source
([`doc/external/pi-crew/postinstall-mjs.md`](../external/pi-crew/postinstall-mjs.md),
fetched in full from the package's repository), and it has no unknowns:

- **Step 1 — rebuild the ESM bundle — is a no-op in a published install.**
  The published package does not ship the build script in its `files`
  array; it ships the already-built bundle, so the step does nothing and
  the install does not need it.
- **Step 2 — install the crew-vibes font — is cosmetic.** It makes the
  package's special speed/capacity glyphs render in a terminal. It has
  nothing to do with whether the `team` tool works.
- **Step 3 — clean up stale skill copies — is an upgrade migration.** On a
  fresh container it returns immediately, having nothing to clean.
- **The whole script is wrapped in a try/catch that cannot fail the
  install** — the script's own comment is "Postinstall must NEVER fail the
  install".

So nothing the postinstall does is a precondition for the `team` tool, and
keeping the flag changes nothing the spike measures. The one real
difference between the two install layouts is elsewhere: Pi's skill
discovery expects the `pi install npm:` layout under the agent directory,
not the `npm install -g` layout the spike image uses. That gap is bridged
by the driver loading the extension explicitly with `-e`
([`anvilkit/pi/picrew.py`](../../anvilkit/pi/picrew.py)), and whether that
bridge is enough is exactly what the headless run in section 1 measures —
an invocation fact, not a postinstall one.

## 3. Per-run record shape

**The question.** Does pi-crew's per-run terminal record match #59's prior
art shape — `{ runId, status, team, goal, durationMs, cost, tokens, at }`
— the same eight keys, populated for a single recorded run?

The package page documents the per-run record and a per-run resource
sampler plus an auto-generated performance report and cost breakdown
([`doc/external/pi-dev/packages/pi-crew.md`](../external/pi-dev/packages/pi-crew.md)).
Whether the documented shape is what a single `team run` actually writes,
and what each field contains, is measured by the recorded run — not
assumed here.

**GO**, with a finding on the shape.
The prior-art shape is largely met. The `team` tool result's `details.metrics`
carries `runId`, `timestamp` (not the prior art's `at`), `taskCount`,
`completedCount`, `failedCount`, `totalCost`, `durationMs` and
`consistencyScore`. The record is not a single flat file: it lives embedded
in the event-stream tool result, and the crew state machine appends a
Prometheus-style metrics JSONL under `.crew/state/metrics/` — while
`.crew/state/runs/` was empty in the recorded run.

The finding is the orchestration overhead on a task this small: the 3-task
run consumed 33,789 tokens in 253,086 ms, and the package's preflight
advised that the sequential chain was 5.7× slower and 1.9× costlier than
three raw Agent calls. `totalCost` is 0 — the local model reports no price,
so the cost figure is unavailable rather than free
([`doc/external/pi-dev/packages/pi-crew.md`](../external/pi-dev/packages/pi-crew.md)).

---

Back-link: issue iar3-r8/anvil#84 (the `pi-crew` adopt/reject decision).
