# Pi phase 1 — bake-off host run recipe

Run this on the **GPU host**: the workspace that produced this document has
no GPU, no container runtime and no reachable llama-swap endpoint. The
recipe below is complete — everything needed to run the bake-off and
produce the three run records is here or in the cited files.

The bake-off answers (a) whether a local model can drive Pi unattended,
across the three invocation forms: **print**, **json** and **ultrawork**
(`pi-ultrawork` 1.2.0). The task is deliberately trivial: edit one line of
one file so one existing assertion passes. A run that does not complete on
this task is the finding — it is recorded, not worked around.

## 1. Prerequisites

- **Node 22.19+** (Pi's minimum;
  [`doc/external/pi-dev/readme.md`](../external/pi-dev/readme.md)).
- Pi installed globally:

  ```sh
  npm install -g --ignore-scripts @earendil-works/pi-coding-agent
  ```

- For the ultrawork run only: **pi-ultrawork 1.2.0** available locally as
  an extension path `<ext-path>` — the `src/index.ts` entry (or package
  directory) of a local checkout of
  [pi-ultrawork](https://github.com/hu9osaez/pi-ultrawork) at version 1.2.0
  (MIT; see
  [`doc/external/pi-dev/packages/pi-ultrawork.md`](../external/pi-dev/packages/pi-ultrawork.md)
  for the local-load form).
- The llama-swap gateway running, serving the coder model on its resolved
  port (below).
- This repository's virtualenv (the `anvil` entrypoint provisions it):
  the recipe calls `anvilkit.pifixture`, `anvilkit.piargv`,
  `anvilkit.pievents` and `anvilkit.pirecord` — stdlib-only modules, no new
  dependencies.

## 2. Resolve the model id and port

- **Model id**: `matrix.vars.coder` in [`config.yaml`](../../config.yaml) —
  `Qwen/Qwen3.8-27B-FP8`. Read it, do not assume it:
  `anvilkit.config.read_models` is what resolves it (with the coder's
  context window, taken from `--max-model-len` in that model's `cmd`).
- **Port**: the usual precedence — CLI flag `--llm-port` > `LLM_PORT` in
  `.env` > `anvil.local.yaml` > [`anvil.yaml`](../../anvil.yaml)
  `gateway.default_port` (8000) — see
  [`anvilkit/config.py`](../../anvilkit/config.py) `resolve_port`.
- **Context window / max tokens**: explicit in the models document (Pi
  defaults to `contextWindow` 128000 and `maxTokens` 16384 and both are
  wrong for this model —
  [`doc/external/pi-dev/models-configuration.md`](../external/pi-dev/models-configuration.md)).
  Use the coder's `--max-model-len` for `contextWindow` and a `maxTokens`
  appropriate to the task.

## 3. Write the models document

The document is `~/.pi/agent/models.json` — the **agent directory**, not a
project `.pi/` file
([`doc/external/pi-dev/configuration.md`](../external/pi-dev/configuration.md)).
Build it with [`anvilkit/piargv.py`](../../anvilkit/piargv.py)
`models_document(model_id, port, context_window, max_tokens)` and write it
with `json.dumps`; the shape is exactly

```json
{
  "providers": {
    "llamaswap": {
      "baseUrl": "http://127.0.0.1:<port>/v1",
      "api": "openai-completions",
      "apiKey": "llamaswap-local",
      "models": [
      { "id": "<coder-id>", "contextWindow": <cw>, "maxTokens": <mt> }
      ]
    }
  }
}
```

The `apiKey` is a fixed dummy — the local gateway ignores it
([`doc/external/pi-dev/models.md`](../external/pi-dev/models.md)).

## 4. Generate the fixture and take the before-digest

For each of the three configurations, start from a **fresh** destination
(e.g. `./run-print/fixture`) — the fixture is generated, never committed,
so a run always starts known-red:

```python
from pathlib import Path
import anvilkit.pifixture as pifixture

dest = Path("./run-print/fixture")
pifixture.write_fixture(dest)          # bakes adder.py (a - b), tests/, TASK.md
before = pifixture.digest_fixture(dest)  # relative path -> sha256
```

`write_fixture` refuses a destination that already contains
`bakeoff_fixture/` ([`anvilkit/pifixture.py`](../../anvilkit/pifixture.py)).

## 5. Run the three configurations

The prompt (the task, verbatim):

> Edit `bakeoff_fixture/adder.py` so that `add(2, 3) == 5` passes. The
> function currently returns `a - b`; change it to `a + b`.

For every run:

- **cwd = the fixture destination** (never an argv token —
  [`anvilkit/piargv.py`](../../anvilkit/piargv.py));
- **stdin from `/dev/null`** (`< /dev/null`) so a hung run cannot be
  mistaken for a working one;
- capture **stdout**, **stderr**, the **exit code** and **wall time**;
- build the argv with `anvilkit.piargv` and pass the list to
  `subprocess` — no shell, no string.

**print** — `anvilkit.piargv.print_argv(model_id, prompt)`:

```
["pi", "-p", "--model", <id>, "--tools", "read,edit,write",
 "-a", "--no-session", "--", <prompt>]
```

**json** — `anvilkit.piargv.json_argv(model_id, prompt)`; identical except
`-p` → `--mode json` ([`doc/external/pi-dev/cli.md`](../external/pi-dev/cli.md)):

```
["pi", "--mode", "json", "--model", <id>, "--tools", "read,edit,write",
 "-a", "--no-session", "--", <prompt>]
```

**Read stdout continuously** (line by line, appending to
`events.jsonl`) so Pi cannot stall on a full pipe buffer. Stdout carries
only JSONL; diagnostics go to stderr
([`doc/external/pi-dev/json-event-stream.md`](../external/pi-dev/json-event-stream.md)).

**ultrawork** — `anvilkit.piargv.ultrawork_argv(model_id, prompt, extension_path)`:

```
["pi", "-p", "-e", <ext-path>, "--model", <id>,
 "--tools", "read,edit,write,ulw_dispatch,ulw_complete",
 "-a", "--no-session", "--", <prompt>]
```

The builder emits the prompt prefixed with the whole word `ultrawork`
(never twice) so the extension's trigger fires
([`doc/external/pi-dev/packages/pi-ultrawork.md`](../external/pi-dev/packages/pi-ultrawork.md)).

**A blocked run** (no output until your timeout) is not an error: record it
with `waited_for_input: true` and the evidence (last lines seen, elapsed
time at kill). A non-completing run is the finding, not a reason to
simplify the task.

## 6. Collect the artifacts

After each run, take the after-digest and diff:

```python
after = pifixture.digest_fixture(dest)
changed = pifixture.changed_files(before, dest)
assertion = pifixture.assertion_passes(dest)
```

Lay the artifacts down under the run directory
(`run-print/`, `run-json/`, `run-ultrawork/`), one set of **five** per
configuration, matching the record's `artifacts` key set
([`anvilkit/pirecord.py`](../../anvilkit/pirecord.py)):

| key | file |
|---|---|
| `stdout` | captured stdout |
| `stderr` | captured stderr |
| `jsonl` | `events.jsonl` for the json run; `null` for print and ultrawork (they produce no JSONL stream) |
| `before_digest` | the step-4 before-digest, serialised |
| `after_digest` | the after-digest, serialised |

## 7. Build the records and render the table

For each configuration, build one record with
[`anvilkit/pirecord.py`](../../anvilkit/pirecord.py) `build` — all
dimensions keyword-only, and a missing one raises `RecordError` naming the
field, so a half-recorded run cannot become a verdict:

```python
import anvilkit.pirecord as pirecord
import anvilkit.pievents as pievents

stream = open("run-json/events.jsonl", encoding="utf-8").read()
events = pievents.parse(stream)["events"]

record = pirecord.build(
    "json",
    model=model_id,
    exit_code=exit_code,
    wall_time_s=wall_time_s,
    waited_for_input=False,
    artifacts={"stdout": ..., "stderr": ..., "jsonl": "run-json/events.jsonl",
               "before_digest": ..., "after_digest": ...},
    tool_calls=pievents.tool_calls(events),
    outcome=pievents.outcome(events),
    assertion=assertion,
    changed_files=changed,
    timestamp=timestamp_iso_utc,
)
```

For the **print** and **ultrawork** runs, which produce no JSONL stream,
pass the empty-stream values: `pievents.tool_calls([])` (all five counters
at 0) and `pievents.outcome([])` (`settled` `False`, `aborted` `None`,
zeros, `usage_reported` `False`), with `artifacts["jsonl"] = None`.
`build` computes `completed` as exit code 0 **and** the assertion passing —
a green exit on an un-fixed fixture is not a completed run.

Finally, render the go/no-go table:

```python
print(pirecord.render_table([print_record, json_record, uw_record]))
```

One row per configuration in run order, plus the verdict line: `GO` when
all completed, `PARTIAL` when some did, `NO-GO` when none did.

## 8. Guardrail: never mount the host agent directory

If any part of the run happens in a container, **the host
`~/.pi/agent` must NOT be bind-mounted in** — it holds credentials,
settings, extensions and sessions
([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md)).
Use a container-local agent home (a named volume or fresh directory) and
write the step-3 models document into it.
