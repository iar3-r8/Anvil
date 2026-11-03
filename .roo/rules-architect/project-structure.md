# Project Structure — module ownership table

One concern per module, so each module's docstring says so. Job descriptions
below are the first-paragraph job of each module, relative to `anvilkit/`.

| Module | Job (one line) |
| --- | --- |
| `yamlio.py` | safe YAML loading — the only module permitted to import `yaml` |
| `env.py` | safe `.env` reading and writing |
| `config.py` | reading `config.yaml` (llama-swap's, read-only) and `anvil.yaml` (Anvil's own) |
| `render.py` | generating the agent artifacts — Zoo Code's `zoo-code-settings.json` and `.roo/mcp.json`, Pi's `models.json`, `.pi/mcp.json` and `.pi/extensions/guardrails.json`; the only module that writes them |
| `compose.py` | driving `docker compose` and the container runtime |
| `health.py` | health checks against the llama-swap gateway |
| `stress.py` | stress testing against the llama-swap gateway |
| `prompts.py` | interactive prompts, every one of which can be bypassed |
| `provision.py` | provisioning a target repository — the `setup-repo` orchestration |
| `cli.py` | the Anvil command line: subcommand dispatch, flags and exit codes |
| `pi/` | the Pi package: the bake-off, approval, sandbox and single-role pipeline (see below) |
| `pi/piapproval.py` | phase-2 approval run driver — one job: drive the approval configurations |
| `pi/piargv.py` | bake-off invocation argv builders — one job: turn inputs into `pi` command lines |
| `pi/pibakeoff.py` | bake-off run driver — one job: drive bake-off configurations end to end |
| `pi/pievents.py` | JSONL event-stream reader for `pi --mode json` streams |
| `pi/pifixture.py` | generated bake-off fixture — the trivial red task for the Pi phase-1 bake-off |
| `pi/piguard.py` | checks over GitHub branch rules, returning findings |
| `pi/piguardrails.py` | guardrails document builder and validator — one job: build and validate the `.pi/extensions/guardrails.json` document for the `@aliou/pi-guardrails` package (one exception type: `GuardrailsError`); the write seam is `render.guardrails_settings` |
| `pi/pirecord.py` | bake-off run-record builder (closed thirteen-key record, table rendering) |
| `pi/piruleset.py` | GitHub ruleset builder — the importable main-branch guard ruleset |
| `pi/pisandbox.py` | sandbox image argv builders — one job: turn inputs into `docker` command lines |
| `pi/pirole.py` | single-role role table and role argv builder — one job: resolve a role name to its model id, tier, prompt path and tools, and build the per-role `pi` invocation |
| `pi/pidriver.py` | single-role run driver — one job: compose the sandbox container argv with the role argv and invoke the injected runner once |
| `pi/piverdict.py` | red/green classification — one job: turn one suite result into green, red, wrong-kind-of-red or reason-mismatch |
| `pi/picommit.py` | red and green commit messages and the `git` argv — builds them, never executes |
| `pi/picycle.py` | the red/green loop driver — the only module that invokes a git mutation |
| `pi/pitrust.py` | write the project-local `.pi/` fixture for the phase-2 trust probe |
