# Host smoke test for the single-role stack

One command that proves, per layer, that the real single-role stack — docker,
gateway, agent volume, role prompt, one real coder run, the two failure paths —
is actually working on this host. The report is a list of per-layer verdicts,
never a single pass/fail, so a failure names *which* layer broke and prints the
exact command to fix it ([`anvilkit/smoke.py`](../../anvilkit/smoke.py)).

Run it **occasionally** — after an upgrade, when the stack starts misbehaving,
or before trusting an unattended run. CI **never** runs the smoke test: the
real run layer needs Docker and a serving local model, so the test is
deliberately excluded from the unit suite
([`tests/test_smoke.py`](../../tests/test_smoke.py)).

## 1. Prerequisites

- **Docker with the Compose v2 plugin**, on PATH.
- **The llama-swap gateway running** (for layer 2 and up):

  ```sh
  docker compose --profile coder up -d
  ```

- **The sandbox image built** (for layers 1, 3, 5): see
  [`doc/pi-sandbox/README.md`](../pi-sandbox/README.md).
- **The local model actually serving** — only layers 2 (hot check) and 5 (the
  real run) need a model; layers 1, 3, 4, 6 do not.

## 2. Run it

```sh
anvil smoke-test
```

- **`--repo`** — the target repository directory; defaults to the current
  working directory. A path that is not an existing directory is a usage
  error (exit 2) before any layer runs.
- **`--llm-port`** — override the gateway port the layer-2 model check
  probes; without it, port resolution follows the usual precedence
  (CLI flag > `.env` > `anvil.local.yaml` > `anvil.yaml` > built-in default).
- **`--fix`** — on a `models.json` permission failure, chown the agent volume
  once and retry the read once. This is the only repair the command ever
  performs; see section 4.
- **`--dry-run`** — print what each layer would check; spawn no process and
  make no HTTP call.

## 3. The six layers

The report prints one line per layer, in this order, named exactly as the
report prints it:

| # | report name | what it proves |
| --- | --- | --- |
| 1 | `docker-daemon` | the docker daemon is reachable, the `pi-sandbox` image is present, and the `sandbox-internal` network exists |
| 2 | `gateway` | the `llama-swap-service` container is running, and the coder model from `config.yaml` is registered on the gateway and hot |
| 3 | `sandbox-agent-volume` | the `sandbox-agent` named volume exists, its `models.json` is readable by the image uid, and that `models.json` seeds the coder id |
| 4 | `role-prompt` | `<repo>/.pi/roles/coder.md` exists and is non-empty |
| 5 | `coder-run` | one real coder run completes: exit 0, no timeout, and a non-empty event stream |
| 6 | `failure-paths` | the two cheap failure paths still fire: a tag no image matches raises `DriverError`, and a missing prompt raises `RoleError` before any container starts |

The layers are driven in order and fail-fast: a failing layer makes the
following layers *skipped*, and a skipped layer never counts toward the exit
code. Layer 6 runs exactly when an earlier layer is failing — the moment a
diagnosis is wanted — and is skipped on a fully healthy stack, where there is
nothing left to diagnose. Layer 5 is the one layer that needs the local model
serving; layer 6 does not (its sub-checks never reach a model), so it can run
on a GPU-less host.

## 4. Exit codes and the diagnose-and-print rule

| exit | meaning |
| --- | --- |
| 0 | every layer passed (or was skipped) |
| 4 | a docker-class layer (1–4) failed |
| 1 | only the run-class layers (5–6) failed |
| 2 | usage error (e.g. `--repo` names no directory) |
| 3 | configuration error (e.g. `config.yaml` unreadable) |

When a layer fails, the command prints what to fix — a
`docker compose --profile coder up -d` for a missing network or gateway, a
root `chown` one-liner for a root-owned agent volume, the minimal content to
write for a missing prompt — and **never applies it**. The one exception is
`--fix`, which repairs exactly one thing: on a `models.json` permission
failure it chowns the `sandbox-agent` volume once (as root, in a throwaway
container) and retries the read once. Nothing else — no image build, no
network create, no seeding, no gateway start — is ever performed.

## 5. Five things that look broken and are not

Each of these has a specific look; do not "fix" any of them.

1. **Root-owned `models.json` → `EACCES`.** If the volume was seeded or touched
   as root, the in-container read of `models.json` fails with `EACCES` when it
   runs as the image uid. That is a real failure — but the repair is the one
   the report already prints (a root `chown -R 1001:1001` one-liner against the
   `sandbox-agent` volume), or simply rerun with `--fix`, which performs that
   chown once and retries.
2. **In-network port 8080 vs the host `LLM_PORT`.** The gateway container
   always serves on 8080 inside `sandbox-internal`, regardless of the host
   port; the host side is published as `${LLM_PORT}:8080`. The report's port
   fact is 8080 on purpose — do not "fix" the 8080, and `--llm-port` only
   changes which host port the model check probes.
3. **The `sandbox-agent` volume is pre-existing but empty.** The volume can
   exist and still be empty — created before any container first ran. An
   empty volume is expected on first run, not corruption; the layer that
   actually fails is the `models.json`-readability check, with the seed
   instruction printed.
4. **The coder model id carries a slash: `Qwen/Qwen3.8-27B-FP8`.** That id
   comes from `matrix.vars.coder` in `config.yaml` and is mirrored verbatim
   into the seeded `models.json`. The slash is correct and must not be
   "fixed" — do not quote-escape, strip, or rename `Qwen/Qwen3.8-27B-FP8` to
   make a failure go away; the layer 2 and layer 3 checks compare the ids
   exactly as written.
5. **First-run stderr noise: `No project session found`.** Every smoke run
   mints a fresh `smoke-...` session id, so on a fresh session you will see a
   stderr line like `No project session found`. That is expected first-run
   noise — harmless and ignorable, never a failure; the run layer is judged on
   the event stream, never on stderr.
