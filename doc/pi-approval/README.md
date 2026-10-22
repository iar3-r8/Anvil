# Pi phase 2 — unattended approval: can a project-local `.pi/` be applied without a TTY?

This is the phase-2 spike ([`plans/pi-phase2-approval.md`](../../plans/pi-phase2-approval.md),
issue iar3-r8/Anvil#49). The question it answers: can a **generated**
project-local `.pi/` — settings, a trust-gated system-prompt append, and one
MCP entry — be applied by pi **unattended** (no TTY, no hang, stdin
`/dev/null`) with `-a` / `-na`, and does the difference between the two show?
The deliverable is recorded evidence plus a reproducible recipe — not a
general-purpose feature.

The probe is deliberately one-sided. The project fixture carries a marker
token only in its trust-gated `APPEND_SYSTEM.md`, and the model prompt names
**no** marker — so the marker appearing in the model's reply is evidence the
trusted project append was loaded, and its absence under `-na` is the
difference. (The prompt must name no token because JSON mode echoes the user
message verbatim into stdout — a prompt naming the marker would put it there
whether or not the model ever emitted it,
[`json-event-stream.md`](../external/pi-dev/json-event-stream.md).) The MCP
entry is one stdio server whose `command` is a single executable that does
not exist on PATH — it can never connect, so whether pi *reads* the project
`mcp.json` at all is the measurement.

## 1. Prerequisites

- **The Anvil devcontainer** (`.devcontainer/`), with the repo checked out
  and its `.venv` provisioned (`./anvil init` or any Anvil command creates
  it on first use).
- **Pi 1.3.0**, installed into a throwaway prefix — the recorded measurement
  was made against 1.3.0, and a `--prefix` install keeps the devcontainer
  image clean:

  ```sh
  npm install --prefix /tmp/pi-prefix @earendil-works/pi-coding-agent@1.3.0
  ```

- **The llama-swap gateway running on the host**:

  ```sh
  docker compose --profile coder up -d
  ```

  From inside the devcontainer the gateway is not in-network; it is reached
  as a host process at `host.docker.internal:8080` (the devcontainer carries
  `--add-host=host.docker.internal:host-gateway`
  ([`.devcontainer/devcontainer.json`](../../.devcontainer/devcontainer.json));
  `127.0.0.1` inside the container is the container itself).

## 2. Run it

From the repo root inside the devcontainer:

```sh
PATH="/tmp/pi-prefix/node_modules/.bin:$PATH" \
  PI_GATEWAY_HOST=host.docker.internal \
  PI_GATEWAY_PORT=8080 \
  PI_RESULTS_DIR=./results/phase2-pass4 \
  .venv/bin/python -m anvilkit.piapproval
```

- **`PATH=…`** puts the prefix install's `pi` binary first; nothing else
  needs npm.
- **`PI_GATEWAY_HOST` / `PI_GATEWAY_PORT`** — both required; a missing,
  empty or non-numeric value is an `ApprovalError` naming the variable,
  before any run happens
  ([`anvilkit/piapproval.py`](../../anvilkit/piapproval.py) `main`).
- **`PI_RESULTS_DIR`** — where the four run subtrees and `table.md` land
  (default `./results`).
- **Model id and context window are not hand-supplied**: the entry point
  reads the read-only [`config.yaml`](../../config.yaml)
  (`PI_CONFIG_PATH` defaults to the repo-root file) via
  `anvilkit.config.read_models` — the coder model id and its
  `--max-model-len`, the same values the rest of Anvil uses.
- The run drives the four configurations in the fixed order `approve`,
  `no-approve`, `mcp-list-approve`, `mcp-list-no-approve`, and **exits 0
  whenever the four runs were measured** — a negative finding is a
  successful measurement. One configuration raising builds a fallback
  record and never aborts the other three.

## 3. The four configurations

Each configuration is one `pi` invocation, built by
[`anvilkit/piargv.py`](../../anvilkit/piargv.py), driven against a **fresh
project directory** carrying the generated `.pi/` fixture
([`anvilkit/pitrust.py`](../../anvilkit/pitrust.py)) and a **fresh, isolated
agent directory** (section 5). The model runs use `-nt` (all tools
disabled), so the model cannot reach the marker file with the `read` tool —
the trust-gated `APPEND_SYSTEM.md` append is the only path to the marker.

| config | invocation | what varies |
|---|---|---|
| `approve` | `pi --mode json --model <id> -nt -a --no-session -- <prompt>` | `-a` — "trusts project-local configuration and resources for this process" |
| `no-approve` | same, with `-na` | `-na` — ignores trust-gated project-local inputs |
| `mcp-list-approve` | `pi mcp list --json` | the agent dir is **seeded** with a `trust.json` mapping the resolved project dir to `true` |
| `mcp-list-no-approve` | `pi mcp list --json` | **no** `trust.json` — the project is untrusted |

The two model pairs differ by the `-a` / `-na` **flag**. The two mcp-list
pairs differ by the **trust store**, not a flag: `pi mcp list` accepts no
trust flag — its usage is `pi mcp list [--json]` only, and passing `-a` or
`-na` exits 1 with a usage error (live pi 1.3.0, verified against the
installed source; see section 7).

## 4. Where the artifacts land

Under `$PI_RESULTS_DIR` — one subtree per configuration, in run order, plus
the table:

```
results/phase2-pass4/
├── table.md                    # one row per config + the verdict line
├── approve/
│   ├── agent/                  # the isolated per-run agent directory
│   │   ├── models.json         # the models document, pointing at the gateway
│   │   └── …                   # state pi writes during the run (auth, model store)
│   ├── project/                # the fresh project dir; the runner's cwd
│   │   └── .pi/
│   │       ├── settings.json   # valid, inert
│   │       ├── APPEND_SYSTEM.md# instructs the model to echo the marker
│   │       └── mcp.json        # one stdio entry; command not on PATH
│   └── results/
│       ├── record.json         # the closed thirteen-key run record
│       ├── stdout              # captured stdout (JSONL for the model configs)
│       ├── stderr
│       ├── events.jsonl        # the model configs only (stdout drained)
│       ├── before.sha256       # project fixture digest before the run
│       ├── after.sha256        # project fixture digest after the run
│       └── evidence.txt        # timed-out runs only
├── no-approve/                 # as approve/
├── mcp-list-approve/           # as approve/, plus agent/trust.json ({"<project dir>": true}); no events.jsonl
└── mcp-list-no-approve/        # as approve/, no events.jsonl
```

- `record.json` is the closed thirteen-key record
  ([`anvilkit/pirecord.py`](../../anvilkit/pirecord.py) `build`);
  `completed` is exit code 0 **and** the assertion passing. For the
  mcp-list runs that is a stricter bar than the finding: `mcp-list-approve`
  exits 1 because pi exits 1 when an enabled server is not connected
  (section 5), and `mcp-list-no-approve` fails its own assertion by design —
  both are correctly recorded findings, not failures to run.
- `table.md` renders one row per configuration in run order plus the verdict
  line. A `PARTIAL` / `NO-GO` verdict is a **valid recorded outcome**.

## 5. The recorded result

The measurement of record is the fourth four-run pass (pi 1.3.0, gateway
up), the run ledger in
[`plans/pi-phase2-approval.md`](../../plans/pi-phase2-approval.md); the tree
in section 4 is its output. All four runs bounded, recorded, and
`waited_for_input: false`.

`results/phase2-pass4/table.md`:

| config | Completed | Tool calls | Wall time | Tokens | Waited for input |
| --- | --- | --- | --- | --- | --- |
| approve | yes | 0 attempted / 0 ok / 0 failed / 0 unfinished | 5.119796088896692s | 898 | no |
| no-approve | no | 0 attempted / 0 ok / 0 failed / 0 unfinished | 2.917081560008228s | 672 | no |
| mcp-list-approve | no | 0 attempted / 0 ok / 0 failed / 0 unfinished | 0.2637190960813314s | 0 | no |
| mcp-list-no-approve | no | 0 attempted / 0 ok / 0 failed / 0 unfinished | 0.26369714294560254s | 0 | no |
| **PARTIAL (1 of 4 completed)** |

Answers to the definition of done:

- **Config was applied, not merely exited.** `mcp-list-approve` read the
  project `.pi/mcp.json`: `anvil-trust-probe` is listed with
  `state: "failed"` and `error: "spawn anvil-nonexistent-mcp-server ENOENT"`
  (exit 1 — pi exits 1 when an enabled server is not connected).
  `mcp-list-no-approve` did not read it: `servers: []` plus the note
  "`.pi/mcp.json` is ignored because the project is not trusted" (exit 0).
  The difference is trust-store **seeded vs not seeded**, not a flag.
- **The `-a` / `-na` difference is recorded for both pairs.** Model pair:
  `approve`'s system prompt carries the trust-gated addendum and the
  marker is present in the model's reply (assertion passed); `no-approve`
  lacks the addendum and the marker is nowhere in the output — the model's
  thinking block shows it looking for an addendum it cannot read (assertion
  recorded `passed: False`, not raised). mcp-list pair: see the previous
  bullet.
- **No input wait occurred.** `waited_for_input: false` on all four
  records — stdin `/dev/null`, no TTY, no hang.

## 6. Guardrails

- **stdin `/dev/null`, stdout redirected, no TTY** — a run that blocks on
  input cannot be mistaken for a working one.
- **An isolated agent directory per run** (`<base>/<config>/agent`), passed
  as `PI_CODING_AGENT_DIR` — never the invoking user's `~/.pi`, which holds
  credentials and sessions
  ([`doc/external/pi-dev/containerization.md`](../external/pi-dev/containerization.md)).
- **A bounded wall-clock budget per run**: 300 s for the two model runs,
  60 s for the two mcp-list runs. Both are far above pi's documented 10 s
  wait for MCP servers with direct tools
  ([`mcp.md`](../external/pi-dev/mcp.md)), so an exhausted budget means a
  real wait, not a slow connect.
- **A timed-out run is recorded, not raised.** The runner
  ([`anvilkit/pibakeoff.py`](../../anvilkit/pibakeoff.py)
  `subprocess_runner`) drains both pipes continuously, kills the whole
  process group at the deadline, and reports `timed_out`; the run is
  recorded with `waited_for_input: true`, the partial stream still in the
  `stdout` artifact and the runner's evidence in `evidence.txt`.
- **A failed assertion is a recorded finding.** `results/table.md` prints
  the verdict and the run exits 0 even when runs "fail" their assertion —
  the negative finding **is** the answer to the spike's question.

## 7. Interface facts worth knowing

Three things a future developer would otherwise rediscover the hard way.
Full citations — including the live-1.3.0 source-level facts the saved
vendor docs under-pin — are in the run ledger and interface-facts table of
[`plans/pi-phase2-approval.md`](../../plans/pi-phase2-approval.md), with the
saved vendor pages under
[`doc/external/pi-dev/`](../external/pi-dev/readme.md).

1. **`models.json` lives flat in `<agent-dir>/`** — the models document is
   `<agent-dir>/models.json`, **not** `<agent-dir>/.pi/agent/models.json`.
   `PI_CODING_AGENT_DIR` names the agent directory *itself* (whose default
   is `~/.pi/agent`), and the agent directory's files sit directly under it
   ([`configuration.md`](../external/pi-dev/configuration.md)). The driver
   writes it flat accordingly
   ([`anvilkit/piapproval.py`](../../anvilkit/piapproval.py) `run_one`).
2. **`pi mcp list` accepts no trust flag.** Its usage is
   `pi mcp list [--json]` only; passing `-a` or `-na` exits 1 with a usage
   error. The subcommand works outside a session and resolves project trust
   **only** via `ProjectTrustStore(agentDir)` — `<agent-dir>/trust.json`, a
   JSON map of canonicalized cwd → bool, walked to the nearest ancestor
   entry; `defaultProjectTrust` in settings does not affect it. That is why
   the mcp-list pair's difference is materialised by seeding (or not
   seeding) that file, not by a flag
   ([`anvilkit/pitrust.py`](../../anvilkit/pitrust.py) — fixture side;
   [`anvilkit/piapproval.py`](../../anvilkit/piapproval.py) `run_one` —
   trust-store side; the vendor docs only say project `mcp.json` "is only
   read for projects that are already trusted" without stating how a shell
   command decides that, [`cli.md`](../external/pi-dev/cli.md)).
3. **`PI_CODING_AGENT_DIR` must be a resolved absolute path.** The runner's
   cwd is the *project* directory, so a relative agent-dir value would
   resolve against the project dir (`<project dir>/agent`) and pi would read
   the wrong, empty agent directory — with the models document and the
   seeded trust file both correctly on disk. The driver passes
   `str(agent_dir.resolve())`
   ([`anvilkit/piapproval.py`](../../anvilkit/piapproval.py) `run_one`);
   the failure mode this prevents — flat `models.json` and seeded
   `trust.json` present, yet every model run "Model not found" and every
   mcp-list run reporting the project untrusted — is recorded in the plan's
   run ledger.
