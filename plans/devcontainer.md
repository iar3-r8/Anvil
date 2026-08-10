# Decision: Dev container for Zoo Code sandbox

## Context

Anvil provides a GPU workstation environment (llama-swap, Qdrant) and provisions
target repositories with Zoo Code configuration. Developers running the Zoo Code
agent inside the same repo need a safe, reproducible workspace that has all
MCP runtime dependencies (Node.js for the GitHub server, uv for the Git server)
and a Python venv provisioned on first attach.

The existing project runs Python 3.8+ and uses a project-local `.venv` managed
by `scripts/bootstrap.sh`. Docker Compose is the only mechanism for running
llama-swap and Qdrant, and the host network namespace is the only way for the
generated settings (which hardcode `localhost`) to resolve the gateway and
Qdrant without modifying Anvil itself.

## Decision

- **`--network=host`** on the dev container. Every hardcoded `localhost` in
  [`render.zoo_code_settings()`](../anvilkit/render.py:51),
  [`health._url()`](../anvilkit/health.py:426) and the Qdrant URL in
  [`zoo-code-settings.json.template`](../templates/zoo-code-settings.json.template:245)
  resolves to the host gateway unchanged. No Anvil code changes.

- **No Docker socket.** The container cannot access `docker.sock`. Docker-driving
  commands (`up`, `down`) are run from the host. `doctor` reports docker as
  unavailable-by-design when `ANVIL_IN_CONTAINER` is set.

- **Non-root `vscode` user.** The Dockerfile creates a user matching the
  convention so file ownership stays correct after `postCreateCommand`.

- **Workspace-only bind mount.** `$HOME`, `.ssh`, `.gitconfig`, cloud credentials
  and any other host state is **not** mounted into the container. The workspace
  volume is the only bind mount.


- **`ANVIL_IN_CONTAINER=1`** in `containerEnv`. Drives the two Python-level
  behaviours above: `doctor` changes the docker report, `up`/`down` emit a
  clear message.

- **Secrets via `remoteEnv`** from `${localEnv:GITHUB_TOKEN}`. The token never
  lands in a file inside the container.

- **Promoted to `templates/devcontainer/`** only after the Anvil-native instance
  is validated. Provisioning skips when the target already has a `.devcontainer/`.

## Consequences

### What this buys

- The agent operates in a filesystem sandbox: it can only see the workspace and
  the caches. It cannot reach `$HOME`, `.ssh`, or cloud credentials.
- Without the Docker socket the agent cannot escalate to the host daemon.
- Secrets are injected by the VS Code client, not committed or baked into the
  image.

### What this does not protect against

- **Network.** `--network=host` means the container shares the host network
  namespace. The agent can reach anything on loopback (and beyond). The sandbox
  here is a **filesystem and process** boundary, not a network one. This is an
  intentional trade-off to avoid modifying Anvil's hardcoded URLs.

- **Host environment variables.** `remoteEnv` values from the host are passed
  into the container environment, but any other process on the host can read
  those same variables.

## Defects found while validating

0. **The git MCP server had no version pin — the most important finding.**
   `uvx mcp-server-git` resolved the `mcp` SDK afresh, and a newer SDK moved the
   attribute the server calls, so it died at startup with
   `AttributeError: 'Server' object has no attribute 'list_tools'`, surfaced to
   the user only as `MCP error -32000: Connection closed`. This was **not**
   caused by the container: a warm `uv` cache on the host held an older,
   compatible pair, so the latent fault was invisible until a clean environment
   resolved dependencies from scratch. Any new contributor would have hit it.
   Fixed with `uvx --with "mcp<1.10"` in `templates/mcp.json.template`, so the
   constraint travels in the generated config rather than living in someone's
   cache. Regression tests: `TestMcpGoldenParity.test_git_server_constrains_the_mcp_sdk`
   and `..._precedes_the_package_name`.

Recorded so they are not reintroduced:

1. **`mcp.json` carried an absolute host path.** The git MCP server was invoked
   with `--repository /home/mgaron/Repositories/anvil`, which does not exist
   inside the container — the workspace is at `/workspaces/anvil`. The server
   exited immediately, reported only as `Connection closed`. The generated
   `.roo/mcp.json` now uses `${workspaceFolder}`, matching the template.
2. **`RUN` uses `dash`, which has no brace expansion.** `mkdir -p
   .vscode-server/{bin,data,extensions}` created a single directory literally
   named `{bin,data,extensions}`. Every path is now listed explicitly.
3. **Root-owned named volumes**, as described above.
4. **An invented schema key.** `customizations.vscode.experimental
   .extensionsInstallBypassListing` is not part of the dev container
   specification and did nothing; it was removed.

## Alternatives considered

- **Configurable gateway host in Anvil.** `--network=host` is the simplest
  Linux-only solution. A future enhancement could make the gateway host
  configurable via `anvil.yaml` and `.env`, which would allow bridged networking
  and isolate the agent further.

- **Docker Compose service for the dev container.** Would couple the editor to
  the inference stack. The current `docker-compose.yml` is GPU-specific and
  adding a dev environment there would entangle the two concerns.

- **Socat sidecar.** A socat process forwarding localhost to
  `host.docker.internal` would work on non-Linux, but adds another process and
  maintenance burden. Linux-only matches the GPU workstation profile.
