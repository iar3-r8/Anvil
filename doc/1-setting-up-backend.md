# Setup Guide: Running Anvil's Backend

This guide details how to launch and configure the local backend stack powered by [llama-swap](https://github.com/mostlygeek/llama-swap) for dynamic model routing.

## Architecture Overview

Anvil uses **llama-swap** as a central routing gateway that manages multiple vLLM model containers dynamically. Instead of running all models simultaneously, llama-swap uses TTL-based swapping to efficiently share GPU resources:

- **`llama-swap-service`** — The central gateway (port configurable via `LLM_PORT`, default `8000`). This is the only port you need to configure the LLM service.
- **On-demand vLLM containers** — Spun up automatically when a model is requested, stopped after the TTL expires (default 30 minutes).
- **`coder_qdrant`** — Persistent vector database for workspace RAG (runs continuously under the `coder` profile).

This setup uses **Docker Compose Profiles** under the `coder` profile to orchestrate the llama-swap gateway, on-demand model containers, and the local vector database.

---

## 1. Requirements

Before running the stack, ensure your host hardware meets the requirements for your target allocation. llama-swap dynamically manages model containers, so models only consume GPU resources when actively being used.

### Software Prerequisites
* **Python 3.8+:** Used by the `./anvil` command itself. Anvil locates a suitable interpreter and provisions its own virtual environment in `.venv/` on first run, refreshing it automatically whenever `requirements.txt` changes. **There is no manual `pip install` step**, and `.venv/` is disposable — delete it and it will be rebuilt. If your default `python3` is older than 3.8, Anvil will find a newer one if it is installed.
* **Docker & Docker Compose:** Required to orchestrate the multi-container infrastructure. Make sure you are running a modern version of Docker Compose (v2.x).
* **NVIDIA Container Toolkit:** Required on Linux host machines to expose your physical graphics hardware to the underlying Docker containers. Install it following the official [guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

Run `./anvil doctor` to verify all of the above at once.

### Hardware Prerequisites

#### Mid Tier (Default Configuration)
* **GPU for Main LLM (`Qwen/Qwen3.8-27B-FP8`):** Minimum $2 \times 24\text{GB}$ GPUs (e.g., $2 \times \text{RTX 3090/4090}$ or enterprise equivalents like A10/A100) to run the 27B model with `--tensor-parallel-size 2`.
* **GPU for Embedding Indexer (`nomic-ai/nomic-embed-text-v1.5`):** Minimum $1 \times$ dedicated GPU with at least $1\text{GB}$ available VRAM (can be a low-end card or integrated GPU).
* **Storage:** $\sim 50\text{GB}$ of (ideally) fast SSD storage allocated to the Hugging Face cache directory (`HF_HOME`) to store model weights for all configured models.
* **RAM:** $64\text{GB}$ system RAM recommended when running with speculative decoding.

---

## 2. Using the Anvil Workspace Script (`./anvil`)

The `anvil` script helps you manage the llama-swap backend stack. Make sure it's executable:

```bash
chmod +x anvil
```

### Main commands

| Command | Action | Description |
| :--- | :--- | :--- |
| `./anvil init` | Configure | Creates the `.env` file interactively (storage paths, gateway port, GPU device ids). Runs automatically the first time you use a command that needs it. Refuses to overwrite an existing `.env` unless you pass `--force`. |
| `./anvil doctor` | Diagnose | Reports the Python interpreter and venv, Docker, Compose v2, NVIDIA tooling, and whether your configuration files parse. Writes nothing and never fails on what it is diagnosing. |
| `./anvil up` | Start Stack | Starts the llama-swap gateway and Qdrant vector database in the background. |
| `./anvil build` | Rebuild | Force rebuild of custom Docker configurations. |
| `./anvil status` | View Status | Shows llama-swap gateway health and which models are actively loaded vs cold/swapped out. Add `--json` for machine-readable output. |
| `./anvil logs` | View Logs | Streams llama-swap orchestration logs and on-demand model outputs. Add `--no-follow` for a one-shot dump. |
| `./anvil restart` | Restart | Restarts the llama-swap gateway container. |
| `./anvil down` | Stop Stack | Stops all containers and cleans up any orphaned on-demand vLLM model containers. Add `--keep-orphans` to skip the sweep. |
| `./anvil setup-repo PATH` | Provision | Injects Zoo Code settings, the `.roo` framework and VS Code recommendations into a target repository. See the [VS Code guide](2-setting-up-vscode-plugin.md) — and [how the agents work](how-the-agents-work.md) for what the provisioned agent pipeline actually does. |

Any arguments Anvil does not recognise are passed straight through to Docker
Compose, so `./anvil up --force-recreate` and `./anvil logs llama-swap` work as
you would expect.

### Running without prompts

Every interactive question has a corresponding flag, so Anvil can run in CI or a
provisioning script. `--yes` accepts all defaults and never reads stdin; Anvil
also detects a non-interactive stdin automatically and falls back to defaults
rather than hanging.

| Flag | Applies to | Purpose |
| :--- | :--- | :--- |
| `--yes`, `-y` | all | Accept every default; never prompt. |
| `--llm-port N` | `init`, `status`, `setup-repo` | Gateway port. |
| `--hf-home PATH` | `init` | Hugging Face cache directory. |
| `--data-dir PATH` | `init` | Local data storage directory. |
| `--gpu-generic ID` | `init` | Generic LLM GPU device id. |
| `--gpu-coder ID[,ID]` | `init` | Coder GPU device ids; a single id is used for both slots. |
| `--gpu-embedder ID` | `init` | Indexer GPU device id. |
| `--force` | `init` | Regenerate `.env` even though it already exists. |
| `--github-token TOKEN` / `--no-github` | `setup-repo` | Supply or explicitly skip the GitHub token. |
| `--anthropic-key KEY` / `--no-anthropic` | `setup-repo` | Supply or explicitly skip the Anthropic key. `--anthropic` reuses a key already in `.env`. |
| `--anthropic-model ID` | `setup-repo` | Any model id, including one not on the menu. |
| `--profile NAME` | lifecycle commands | Compose profile (default `coder`). |

Global flags: `--dry-run` prints everything that would be written or executed
without doing any of it, `--verbose` explains each step, and `--no-color`
suppresses ANSI colour.

A note on secrets: an API key is persisted to `.env` and never echoed back to the
terminal. Because Anvil builds JSON with a real serialiser, keys containing
characters like `\`, `&` or `|` are stored intact.

### Exit codes

Each failure class has its own code, so scripts can react to what went wrong:

| Code | Meaning |
| :--- | :--- |
| `0` | Success |
| `1` | Unexpected internal error |
| `2` | Usage error (unknown command, bad flag) |
| `3` | Configuration error (`anvil.yaml`, `config.yaml`, invalid `LLM_PORT`) |
| `4` | Docker or Compose unavailable |
| `5` | Provisioning failure (missing target directory or template) |
| `6` | A required value was missing while running non-interactively |

When Docker itself fails, its own exit code is passed through unchanged.

### Understanding Model Status

When you run `./anvil status`, you'll see models listed as:

- **🟢 ACTIVE & HOT** — The model is currently loaded and serving requests.
- **🟡 COLD / SWAPPED OUT** — The model is configured but not loaded. It will lazy-load on first request.

llama-swap automatically evicts cold models based on the TTL (default 30 minutes) and eviction cost priorities defined in [`config.yaml`](../config.yaml).

---
