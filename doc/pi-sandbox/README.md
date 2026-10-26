# Pi sandbox image build and run recipe

A container image and run recipe such that a misbehaving agent loses a
container, not a home directory. The image carries the Pi CLI
alone — no harness, no ultrawork extension, no VCS client
([`docker/Dockerfile.sandbox`](../../docker/Dockerfile.sandbox)) — and the
container rides only an internal network, so a run that goes rogue dies with
the container and touches nothing on the host.

## 1. Prerequisites

- **Docker with the Compose v2 plugin.**
- **The llama-swap gateway running**:

  ```sh
  docker compose --profile coder up -d
  ```

  This starts `llama-swap` — which is attached to **both** `llm-network` and
  `sandbox-internal` ([`docker-compose.yml`](../../docker-compose.yml)) —
  and creates the `sandbox-internal` network itself: it is declared
  `internal: true` with an explicit `name: sandbox-internal`, so the
  out-of-Compose `docker run --network sandbox-internal` below resolves it
  by name.
- **No Node, no npm, no `~/.pi` on the host.** The container carries the
  interpreter and the agent home.

## 2. Build the image

From the repo root:

```sh
docker build -t pi-sandbox -f docker/Dockerfile.sandbox .
```

The context is the repo root (the `.`), never the Dockerfile's directory.
This command — and the run command in section 3 — is exactly the argv the
builders emit: [`anvilkit/pisandbox.py`](../../anvilkit/pisandbox.py)
`build_argv` and `run_argv`. That module is the single place the token order
is decided; the driver `subprocess`es those same vectors rather than
re-deriving them.

What the image carries: `node:24-bookworm-slim` plus `bash`,
`ca-certificates` and `ripgrep`; Pi pinned exactly
`@earendil-works/pi-coding-agent@1.3.0` (clear of the four 2026
pi-coding-agent advisories); a non-root `sandbox` user at uid 1001 (the base
already claims 1000 for `node`); and the agent home
`/home/sandbox/.pi/agent` created **in the image** — without content there,
the named volume's first-mount copy-up never runs and the directory lands
root-owned, unwritable by the container user. `WORKDIR /workspace`.

Deliberately absent: **no VCS client**. The base image installs none, so
absence costs only not adding it; a nested `git push` inside a script finds
no binary, and git is the driver's job, not the agent's.

## 3. Run the container

```sh
docker run --rm \
  -v /path/to/repo:/workspace \
  -v sandbox-agent:/home/sandbox/.pi/agent \
  --network sandbox-internal \
  --user 1001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  -e PI_GATEWAY_HOST=llama-swap \
  -e PI_GATEWAY_PORT=8080 \
  -e PI_CODING_AGENT_DIR=/home/sandbox/.pi/agent \
  pi-sandbox
```

- `-v /path/to/repo:/workspace` — the host repository, bound at the
  container's working directory.
- `-v sandbox-agent:/home/sandbox/.pi/agent` — the agent home is the **named
  volume** `sandbox-agent`, never a host bind. Because it is a named volume,
  the agent home survives between runs; because it is not a host path,
  nothing in the host's `~/.pi` is reachable.
- `--network sandbox-internal` — the internal network: `internal: true`
  means no default route and firewall rules dropping traffic to other
  networks, so the container reaches `llama-swap` (containers on the same
  network still resolve each other by name) and nothing else.
- `--user 1001` — the image's non-root `sandbox` uid.
- `--cap-drop ALL` and `--security-opt no-new-privileges` — no Linux
  capabilities, and no process may gain them.

The three env vars are the only ones the run accepts —
[`anvilkit/pisandbox.py`](../../anvilkit/pisandbox.py) allowlists exactly
these names and refuses anything that looks like a credential, because a
value passed in is readable by every process inside:

- `PI_GATEWAY_HOST=llama-swap` — reaches llama-swap in-network: the
  container name resolves on the user-defined bridge, and `127.0.0.1`
  inside the container would be the container itself.
- `PI_GATEWAY_PORT=8080` — the in-network gateway port; the host-published
  port is irrelevant from inside.
- `PI_CODING_AGENT_DIR=/home/sandbox/.pi/agent` — points Pi at the
  container-local agent home, where Pi's `models.json` and sessions live
  instead of in the default `~/.pi/agent`.

The argv **ends at the image tag**. The `pi` invocation itself (model,
prompt, tools) is added by the driver, which is separate from this recipe.
A bare run just starts the image's default command and exits; section 4
appends a command to the same run to inspect the container's state.

## 4. Verify the host `~/.pi` is unreachable

Run the image with the agent home mounted and list the home directory from
inside:

```sh
docker run --rm \
  -v /path/to/repo:/workspace \
  -v sandbox-agent:/home/sandbox/.pi/agent \
  --network sandbox-internal \
  --user 1001 \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  pi-sandbox ls -la /home/sandbox
```

The home contains the volume-mounted `.pi/agent` and nothing else. The host
`~/.pi` **does not exist** on this filesystem: the host home is not
mounted, so nothing from it can be seen. (The base image's entrypoint runs
a first token that is a resolvable system command as-is, so `ls` runs
without a shell wrapper.) A run that appears to *need* the host agent home
is misconfigured — `run_argv` refuses any host path carrying a `.pi`
component by name.

## 5. What the boundary is — and what it is not

- **Mounting the host `~/.pi/agent` is never the fix.** It exposes Pi's
  credentials, settings, extensions and sessions — Pi's own warning
  ([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md)).
  The fix is the container-local home in the named volume, as in section 3.
- **The binary set is not the exfiltration boundary.** `curl` and `wget`
  ship in the base image (the node base installs them and they survive the
  apt purge), so removing a binary cannot stop a run from sending data out.
  The network is the boundary: `sandbox-internal` is declared
  `internal: true`, so it has no default route and no egress
  ([`doc/external/docker/network-create-internal.md`](../external/docker/network-create-internal.md)).
- **The image has no VCS client**, so the agent cannot push: a nested
  `git push` inside a script finds no binary, and the driver owns git.
