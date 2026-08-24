# <img  src="./assets/logo.png" style="vertical-align: bottom;" width="80" height="80"> <img  src="./assets/anvil.png" style="vertical-align: bottom;" height="80">

Anvil does two things: it runs local model inference behind the [llama-swap](https://github.com/mostlygeek/llama-swap) gateway, and it turns a repository into an agentic [Zoo Code](https://www.zoocode.dev/) pipeline that takes a task from intake to pull request under test-driven development.

---

## What Anvil does

**Run models locally.** `./anvil up` brings up the llama-swap gateway, which starts vLLM containers for your configured models on demand, plus a [Qdrant](https://qdrant.tech/) stack that gives your agent retrieval-augmented context over your codebase. Commands, flags and hardware sizing: [backend setup guide](doc/1-setting-up-backend.md).

**Turn a repo into an agentic pipeline.** `./anvil setup-repo PATH` installs Zoo Code settings, a team of agent modes, the MCP servers that fetch documentation and check package registries, and an optional devcontainer. What the provisioned agents do: [how the agents work](doc/how-the-agents-work.md); installation steps: [VS Code plugin setup guide](doc/2-setting-up-vscode-plugin.md).

## Quick start

* **Python 3.8+** — Anvil provisions its own virtual environment on first run; there is no manual `pip install`.
* **Docker with Compose v2**, and the **NVIDIA Container Toolkit** on Linux hosts.

```bash
./anvil init                 # create .env (storage paths, gateway port, GPUs)
./anvil up                   # start the llama-swap gateway and Qdrant
./anvil status               # gateway health and model state
./anvil stress MODEL         # measure latency and failures at increasing concurrency
./anvil setup-repo PATH      # provision your coding repository
```

`./anvil doctor` reports what Anvil found on your machine — run it whenever something looks wrong.

## The pipeline

Anvil takes one task from intake to pull request: `intake (issue or description) → architect plans → red → green → docs → pull request`. Each stage is one mode:

| Mode | Owns |
| --- | --- |
| **tdd-manager** | Intake, delegation, the red/green loop, and all git — it is the sole git actor in the pipeline. |
| **architect** | The plan: a numbered list of independently testable behaviours, grounded in real documentation. |
| **qna-tester** | The red step: tests that fail now, for the right reason. |
| **code** | The green step: making exactly those tests pass, without touching the tests. |
| **docs-manager** | Documentation, once the tests pass. |

How each stage works, and why it is shaped this way: [how the agents work](doc/how-the-agents-work.md).

## Why it is different

* **Small context by design** — every behaviour is delegated to a fresh specialist mode, one behaviour at a time, so no agent's context window fills up ([how the agents work](doc/how-the-agents-work.md)).
* **Nothing is guessed** — an unknown third-party interface is a blocking condition: the real documentation is fetched, saved under `doc/external/` and cited, so tests are never written against an invented API ([how the agents work](doc/how-the-agents-work.md)).
* **The repo sets itself up** — re-running `setup-repo` upgrades a provisioned repo, merging rather than overwriting your hand edits ([VS Code plugin setup guide](doc/2-setting-up-vscode-plugin.md)).

## Why self-host

Commercial AI coding assistants bring two drawbacks to engineering teams: unpredictable monthly token bills, and the compliance risk of sending proprietary code to external APIs. Anvil removes both — the backend runs entirely on your own hardware, and the agents run against it.

## Documentation

* [Backend setup guide](doc/1-setting-up-backend.md) — running the local stack: commands, flags, exit codes, hardware sizing.
* [VS Code plugin setup guide](doc/2-setting-up-vscode-plugin.md) — provisioning a repository with `setup-repo`.
* [How the agents work](doc/how-the-agents-work.md) — the agentic pipeline in depth: stages, loop mechanics, grounded planning.
* [Testing](doc/3-testing.md) — dev-facing: how to run Anvil's own test suite.
