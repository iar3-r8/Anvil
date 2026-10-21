# Pi phase 1b — bake-off Docker run recipe

Run this on a **host that has Docker and no sudo**: the entire bake-off —
Pi, the ultrawork extension and the Anvil driver — runs in the
`pi-bakeoff` container on the Compose `llm-network`, so nothing is
installed on the host, nothing needs root, and the host needs no `~/.pi`.
The recipe below is complete: the image and the service are committed
([`docker/Dockerfile.bakeoff`](../../docker/Dockerfile.bakeoff),
[`docker-compose.yml`](../../docker-compose.yml)), and the run is one
command.

The bake-off answers (a) whether a local model can drive Pi unattended,
across the three invocation forms: **print**, **json** and **ultrawork**
(`pi-ultrawork` 1.2.0). The task is deliberately trivial: edit one line of
one file so one existing assertion passes. A run that does not complete on
this task is the finding — it is recorded, not worked around. A NO-GO
verdict is a valid recorded outcome
([`recommendation.md`](recommendation.md)).

## 1. Prerequisites

- **Docker with the Compose v2 plugin** — the host's only runtime
  requirement.
- **A clone of this repository** — the image builds from its
  `anvilkit/`, and the service bind-mounts its root
  [`config.yaml`](../../config.yaml) read-only into the container at
  `/app/config.yaml`; the entry point resolves the coder model id and
  context window from there, so no model id is hand-supplied. The file is
  owned by llama-swap (Anvil only reads it) and already exists in the
  repo root.
- **The llama-swap gateway running**:

  ```sh
  docker compose --profile coder up -d
  ```

  The bake-off container reaches it in-network at `llama-swap:8080`; the
  host-published port is irrelevant to the run.

- **No Node, no npm, no sudo, no `~/.pi` on the host.** The phase-1 recipe
  required all of the first three; the container carries them instead
  (section 8).

## 2. Where the model and gateway values come from

Nothing is hand-supplied at run time; every value has a committed source:

- **Model id and context window**: the entry point reads the read-only
  mounted [`config.yaml`](../../config.yaml) and resolves the coder model
  (`matrix.vars.coder` — `Qwen/Qwen3.8-27B-FP8` in the committed file) and
  its context window (taken from `--max-model-len` in that model's `cmd` —
  `262144`) via `anvilkit.config.read_models`.
- **Gateway host/port**: the in-network address, **not** the host port —
  `127.0.0.1` inside the container is the container itself. The service
  fixes it by environment: `PI_GATEWAY_HOST=llama-swap`,
  `PI_GATEWAY_PORT=8080` ([`docker-compose.yml`](../../docker-compose.yml)
  `pi-bakeoff.environment`), and the entry point reads both from the
  service env.
- **Max tokens**: `BAKEOFF_MAX_TOKENS` (`4096`), a module constant sized
  to the task, not to the window. The models document still carries an
  explicit `contextWindow` and `maxTokens` because Pi defaults to
  `128000`/`16384` and both are wrong for this model
  ([`doc/external/pi-dev/models-configuration.md`](../external/pi-dev/models-configuration.md)).

## 3. The models document, written in-container

The document is `<agent home>/.pi/agent/models.json` — the **agent
directory**, not a project `.pi/` file
([`doc/external/pi-dev/configuration.md`](../external/pi-dev/configuration.md)).
In the bake-off container the agent home is `/home/bakeoff`, and the
driver writes the document to
`/home/bakeoff/.pi/agent/models.json` on every run, into the named volume
`pi-bakeoff-agent` (section 6). It builds it with
[`anvilkit/piargv.py`](../../anvilkit/piargv.py)
`models_document(model_id, port, context_window, max_tokens, host=...)`;
the `host` parameter carries the in-network address (`"llama-swap"`) — its
default `"127.0.0.1"` leaves every host-side caller unchanged. The shape
is exactly

```json
{
  "providers": {
    "llamaswap": {
      "baseUrl": "http://llama-swap:8080/v1",
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

## 4. Run the bake-off

```sh
mkdir -p ./results
chmod 777 ./results
docker compose --profile bakeoff run --rm pi-bakeoff
```

`mkdir -p ./results` first: if the bind source is missing, the Docker
daemon creates it **as root**, and the container's non-root `bakeoff` user
cannot write into a root-owned directory. The `chmod 777` covers the other
mismatch: when your host UID is not the container `bakeoff` user's UID
(1001) and the shell's umask gives the directory a restrictive mode (750
under umask 027), the container user falls into the "other" class, which
that mode gives no permission, and the run dies on its first write to
`/workspace/results`. (Reading the artifacts back is covered in section 5;
this is about the run itself being able to write.)

The service carries the command — `command: ["python3", "-m",
"anvilkit.pibakeoff"]` — so the operator passes nothing after the service
name. The entry point ([`anvilkit/pibakeoff.py`](../../anvilkit/pibakeoff.py)
`main`) reads the gateway host and port from the service env (a missing,
empty or non-numeric value is a `BakeoffError` naming the variable), the
model id and context window from the read-only mounted `config.yaml`
(default path `/app/config.yaml`, overridable with `PI_CONFIG_PATH`; an
unreadable or invalid file is `anvilkit.config.ConfigError`, propagated
unwrapped), and drives `run_all` into `/workspace/results` (overridable
with `PI_RESULTS_DIR`). A run that produces a NO-GO table still exits 0 —
the verdict is data, not a failure to run.

What the image already carries
([`docker/Dockerfile.bakeoff`](../../docker/Dockerfile.bakeoff)):
`node:24-bookworm-slim` + system `python3`, Pi pinned exactly
`@earendil-works/pi-coding-agent@1.3.0` (clear of the four 2026
pi-coding-agent advisories; the worst was patched in 0.79.0) and the
ultrawork extension pinned `pi-ultrawork@1.2.0`, both via
`npm install -g --ignore-scripts`; `anvilkit/` copied to `/app`
(`PYTHONPATH=/app`); a non-root user `bakeoff`; `WORKDIR /workspace`.

The remaining run parameters are module constants in
[`anvilkit/pibakeoff.py`](../../anvilkit/pibakeoff.py) — no operator
input: `BAKEOFF_MAX_TOKENS = 4096` (sized to the task, not to the
window), `BAKEOFF_TIMEOUT_S = 600.0` (the per-run wall-clock budget) and
`BAKEOFF_PROMPT` (the phase-1 trivial task, verbatim below); the
ultrawork extension path resolves from the pinned global npm root.

The driver ([`anvilkit/pibakeoff.py`](../../anvilkit/pibakeoff.py))
composes the rest, unchanged in composition from phase 1. In the container
its process-execution seam is the production `subprocess_runner` (the
`runner` injection remains the test seam): it drains stdout and stderr
continuously so a full pipe buffer cannot stall Pi, and a run still
blocked at the 600 s deadline is killed by **process group** — SIGKILL on
the whole group, so an orphaned child cannot hold a pipe open — and
reported, never raised.

- the **fixture is generated per configuration** —
  `pifixture.write_fixture` into `results/<config>/fixture` — so every run
  starts known-red;
- each invocation runs with **cwd = the fixture directory** (never an argv
  token — [`anvilkit/piargv.py`](../../anvilkit/piargv.py)), **stdin from
  `/dev/null`** so a hung run cannot be mistaken for a working one, and a
  list argv built by `anvilkit.piargv` — no shell, no string;
- **stdout**, **stderr**, the **exit code** and **wall time** are captured
  per run, and stdout is drained to `events.jsonl` for the json
  configuration so Pi cannot stall on a full pipe buffer — stdout carries
  only JSONL; diagnostics go to stderr
  ([`doc/external/pi-dev/json-event-stream.md`](../external/pi-dev/json-event-stream.md));
- a **blocked run** (the 600 s budget exhausted) is not an error: the
  partial stream captured before the kill survives in `stdout`, the
  runner's evidence lands in `evidence.txt`, and the run is recorded with
  `waited_for_input: true` — never an exception;
- the three configurations run in the fixed order print, json,
  ultrawork, and **one configuration failing builds a fallback record and
  never aborts the other two**.

The prompt (the task, verbatim):

> Edit `bakeoff_fixture/adder.py` so that `add(2, 3) == 5` passes. The
> function currently returns `a - b`; change it to `a + b`.

## 5. Read the results

On the host, under `./results/` — one subtree per configuration plus the
table:

```
results/
├── table.md              # one row per config + the verdict line
├── print/
│   ├── fixture/          # the generated fixture after the run
│   └── results/
│       ├── stdout  ├── stderr
│       ├── before.sha256  └── after.sha256
│       ├── record.json
│       └── evidence.txt   # timed-out runs only
├── json/results/         # as print/, plus events.jsonl
└── ultrawork/results/    # as print/
```

- `record.json` per configuration is the closed thirteen-key record
  ([`anvilkit/pirecord.py`](../../anvilkit/pirecord.py) `build`);
  `completed` is exit code 0 **and** the fixture assertion passing — a
  green exit on an un-fixed fixture is not a completed run. The fields
  come from real runs: a blocked run (the 600 s budget exhausted) is
  recorded with `waited_for_input: true`, the partial stream captured
  before the kill, and `evidence.txt`.
- `table.md` renders one row per configuration in run order, plus the
  verdict line: `GO` when all completed, `PARTIAL` when some did,
  `NO-GO` when none did — and a `NO-GO` is a **valid recorded outcome**,
  the answer to the question the bake-off asked
  ([`recommendation.md`](recommendation.md)).
- Artifacts are readable **without sudo** because the bind source is
  created by your shell, not the daemon; the container writes as
  `bakeoff`, so if your host UID does not match that user's UID the files
  land in a directory whose files you may still read but not modify.
  Re-run into a fresh `./results` (delete it first) to start clean.

## 6. Guardrails

- **No sudo.** Pi has no built-in permission system — it runs with the
  launching user's permissions
  ([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md)) —
  so the boundary here is the container: the run executes as the non-root
  `bakeoff` user and touches no host system path.
- **The host `~/.pi/agent` is never bind-mounted.** It holds credentials,
  settings, extensions and sessions
  ([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md)).
  The agent home is the **named volume** `pi-bakeoff-agent` at
  `/home/bakeoff/.pi/agent` — a container-local home that the models
  document is written into, and nothing more. Never a host `.pi` bind.
- **A blocked run is the finding, not an error**, and a NO-GO is a valid
  recorded outcome: the task is not simplified, retried or worked around
  ([`recommendation.md`](recommendation.md)).

## 7. The `-a` / project-trust interaction

Every bake-off argv passes `-a` (`--approve`), which "trusts
project-local configuration and resources for this process"
([`doc/external/pi-dev/cli.md`](../external/pi-dev/cli.md)). Under
advisory **GHSA-mqxh-6gq7-558m**, non-interactive modes ignore
project-local inputs **unless** `-a` is passed — so with the flag, a run
loads the working directory's project-local `.pi` inputs. Here the working
directory is the **freshly generated fixture**, which Anvil itself writes
([`anvilkit/pifixture.py`](../../anvilkit/pifixture.py), fixed byte
strings) — the trusted surface is therefore Anvil's own bytes and nothing
operator-supplied. The advisory's own recommendation for unattended
automation is a container carrying only the needed files
(GHSA-mqxh-6gq7-558m), which is exactly the shape of this recipe.

## 8. What changed from the phase-1 recipe

The phase-1 recipe
([`plans/pi-phase1-bakeoff.md`](../../plans/pi-phase1-bakeoff.md)) ran on a
host with Node and global npm installs. This host has no sudo, so those
steps are **superseded, not an alternative** — a no-sudo host cannot do
them:

| Phase 1 (host) | Phase 1b (container) |
|---|---|
| Node 22.19+ on the host | `node:24-bookworm-slim` in the image |
| `npm install -g @earendil-works/pi-coding-agent` | pinned `@earendil-works/pi-coding-agent@1.3.0` in the image, `--ignore-scripts` |
| local `pi-ultrawork` checkout, path by hand | pinned `pi-ultrawork@1.2.0` in the image; the entry path is the pinned global npm root |
| the repo virtualenv for the harness | `anvilkit/` copied into the image, `PYTHONPATH=/app` |
| the operator assembles and runs the three argvs by hand | one command — the service's `command` is `python3 -m anvilkit.pibakeoff`; the model id comes from the mounted `config.yaml` |
| gateway at `127.0.0.1:<published port>` | gateway at `llama-swap:8080` in-network, from the service env |
| artifacts scattered under `run-<config>/` | everything under the `./results` bind mount |

The host operator's whole job is now: clone, start the gateway,
`mkdir -p ./results`, run the one `docker compose` command in section 4,
and read `./results/table.md`.
