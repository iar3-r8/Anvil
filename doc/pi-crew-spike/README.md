# pi-crew spike — Docker run recipe

Run this on a **host that has Docker and no sudo**: the entire spike — Pi,
the pi-crew extension and the Anvil driver — runs in the `pi-crewspike`
container on the Compose `llm-network`, so nothing is installed on the host,
nothing needs root, and the host needs no `~/.pi`. The recipe below is
complete: the image and the service are committed
([`docker/Dockerfile.crewspike`](../../docker/Dockerfile.crewspike),
[`docker-compose.yml`](../../docker-compose.yml)), and the run is one
command.

The spike answers issue iar3-r8/anvil#84's adopt/reject decision with **one
recorded run**: does pi-crew's `team` tool load and run non-interactively
under Pi `1.3.0` from an `npm install -g` path, via an explicit `-e`
extension load and a `--tools read,edit,write,team` allowlist? The task is
the trivial red fixture the bake-off used, so the crew run is comparable to
the three recorded bake-off configurations. A run where the tool never loads
is the finding — it is recorded, not worked around
([`recommendation.md`](recommendation.md)).

## 1. Prerequisites

- **Docker with the Compose v2 plugin** — the host's only runtime
  requirement.
- **A clone of this repository** — the image builds from its `anvilkit/`,
  and the service bind-mounts its root
  [`config.yaml`](../../config.yaml) read-only into the container at
  `/app/config.yaml`; the entry point resolves the coder model id and
  context window from there, so no model id is hand-supplied. The file is
  owned by llama-swap (Anvil only reads it) and already exists in the
  repo root.
- **The llama-swap gateway running**:

  ```sh
  docker compose --profile coder up -d
  ```

  The spike container reaches it in-network at `llama-swap:8080`; the
  host-published port is irrelevant to the run.

- **No Node, no npm, no sudo, no `~/.pi` on the host.** The container
  carries them instead.

## 2. Where the model and gateway values come from

Nothing is hand-supplied at run time; every value has a committed source:

- **Model id and context window**: the entry point reads the read-only
  mounted [`config.yaml`](../../config.yaml) via `anvilkit.config.read_models`
  (the coder model, `matrix.vars.coder`, and `--max-model-len` in its `cmd`)
  — the same resolution as the bake-off.
- **Gateway host/port**: the in-network address, **not** the host port —
  `127.0.0.1` inside the container is the container itself. The service
  fixes it by environment: `PI_GATEWAY_HOST=llama-swap`,
  `PI_GATEWAY_PORT=8080` ([`docker-compose.yml`](../../docker-compose.yml)
  `pi-crewspike.environment`), and the entry point reads both from the
  service env.
- **Max tokens**: a module constant in
  [`anvilkit/pi/picrew.py`](../../anvilkit/pi/picrew.py)
  (`CREW_SPIKE_MAX_TOKENS = 4096`), sized to the task, not to the window;
  the per-run budget is `CREW_SPIKE_TIMEOUT_S = 1800.0` — larger than the
  bake-off's 600 s because child Pi processes are spawned per crew task.
- **Broker off**: `PI_CREW_BROKER=0` from the service env. The broker is on
  by default over a unix socket
  ([`doc/external/pi-dev/packages/pi-crew.md`](../external/pi-dev/packages/pi-crew.md));
  a single recorded run must not depend on a second socket, so it is pinned
  off, and the driver's env overlay pins it off again for the `pi` process
  itself.

## 3. The agent documents, written in-container

Both live in the agent directory at
`<agent home>/.pi/agent` — the **agent directory**, not a project `.pi/`
file ([`doc/external/pi-dev/configuration.md`](../external/pi-dev/configuration.md)).
In the spike container the agent home is `/home/crewspike`, and the driver
writes both on every run into the named volume `crewspike-agent`:

- **`models.json`** — built by `anvilkit.pi.piargv.models_document` with the
  in-network host (`"llama-swap"`); the `apiKey` is a fixed dummy the local
  gateway ignores.
- **`pi-crew.json`** — the pinned crew user config: `runtime.mode` set to
  `child-process` and `executeWorkers` set to `true` (settable in **user
  config only** — project config silently drops them), the broker disabled,
  one concurrent worker so the run stays comparable
  ([`doc/external/pi-dev/packages/pi-crew.md`](../external/pi-dev/packages/pi-crew.md)).

The operator writes neither file: the driver owns both, and `models.json`
is the driver's own, not a copied host file.

## 4. Run the spike

```sh
mkdir -p ./results && chmod 777 ./results
docker compose --profile crewspike run --rm pi-crewspike
```

`mkdir -p ./results && chmod 777 ./results` first: if the bind source is
missing, the Docker daemon creates it **as root**, and the container's
non-root `crewspike` user cannot write into a root-owned directory; the
`chmod 777` covers the case where your host UID does not match the
container user's UID and the directory's mode gives the container user no
write permission.

The service carries the command — `command: ["python3", "-m",
"anvilkit.pi.picrew"]` — so the operator passes nothing after the service
name. The entry point ([`anvilkit/pi/picrew.py`](../../anvilkit/pi/picrew.py)
`main`) reads the gateway host and port from the service env (a missing,
empty or non-numeric value is a `CrewSpikeError` naming the variable), the
model id and context window from the read-only mounted `config.yaml`, and
drives exactly one `pi` invocation with:

- the extension loaded explicitly — `-e /usr/local/lib/node_modules/pi-crew/index.ts` —
  because Pi's skill discovery expects the `pi install npm:` layout, not the
  `npm install -g` layout this image uses
  ([`doc/external/pi-crew/postinstall-mjs.md`](../external/pi-crew/postinstall-mjs.md));
- the tools allowlisted with `--tools read,edit,write,team`;
- the bake-off's trivial red prompt, verbatim, so the crew run is
  comparable to the three recorded bake-off configurations;
- cwd the fixture directory, stdin from `/dev/null` (a hung run cannot be
  mistaken for a working one), and the env overlay `PI_CREW_BROKER=0`,
  `PI_CODING_AGENT_DIR` pointing at the agent directory the agent-home
  volume targets.

What the image already carries
([`docker/Dockerfile.crewspike`](../../docker/Dockerfile.crewspike)):
`node:24-bookworm-slim` + the bake-off's apt set, Pi pinned exactly
`@earendil-works/pi-coding-agent@1.3.0` and pi-crew pinned exactly
`pi-crew@0.11.57`, both via `npm install -g --ignore-scripts` (the verdict
for that flag is in [`recommendation.md`](recommendation.md));
`anvilkit/` copied to `/app` (`PYTHONPATH=/app`); a non-root user
`crewspike`; `WORKDIR /workspace`.

A run where the `team` tool never loads, an absent `.crew/` tree, or a
budget-exhausted run are **recorded outcomes** in the record — never an
exception; `main` returns 0 whenever the run was measured.

## 5. Read the results

On the host, under `./results/`:

```
results/
├── fixture/                # the generated fixture after the run
│   └── .crew/              # crew project state (manifest, tasks, events, artifacts)
├── results/
│   ├── stdout              # the JSON event stream
│   ├── stderr
│   └── events.jsonl        # stdout, drained as-is
└── record.json
```

- **`record.json`** — the flat run record
  ([`anvilkit/pi/picrew.py`](../../anvilkit/pi/picrew.py) `run_spike`):
  `config`, `completed` (exit 0 **and** the fixture assertion passing),
  `exit_code`, `wall_time_s`, `waited_for_input`, `team_tool_seen`,
  `crew_tree`, `artifacts`, `assertion` and `timestamp`. `team_tool_seen`
  is the unknown-1 evidence: true only if the captured stream carries a
  `tool_execution` record naming `team`.
- **The `.crew/` tree** under `./results/fixture/.crew/` — the crew
  project state the extension writes when it actually runs its state
  machine; its absence is the recorded finding, not an error.
- The artifacts are readable **without sudo** because the bind source is
  created by your shell, not the daemon. Re-run into a fresh `./results`
  (delete it first) to start clean.

## 6. Guardrails

- **No sudo.** Pi runs with the launching user's permissions
  ([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md))
  — the boundary is the container: the run executes as the non-root
  `crewspike` user and touches no host system path.
- **The host `~/.pi/agent` is never bind-mounted.** It holds credentials,
  settings, extensions and sessions. The agent home is the **named volume**
  `crewspike-agent` at `/home/crewspike/.pi/agent` — a container-local home
  the agent documents are written into, and nothing more. Never a host `.pi`
  bind.
- **A failed run is the finding, not an error**: the task is not
  simplified, retried or worked around
  ([`recommendation.md`](recommendation.md)).

---

Back-link: issue iar3-r8/anvil#84 (the `pi-crew` adopt/reject decision).
