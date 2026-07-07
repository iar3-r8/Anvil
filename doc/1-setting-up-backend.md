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
* **Docker & Docker Compose:** Required to orchestrate the multi-container infrastructure. Make sure you are running a modern version of Docker Compose (v2.x).
* **NVIDIA Container Toolkit:** Required on Linux host machines to expose your physical graphics hardware to the underlying Docker containers. Install it following the official [guide](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).

### Hardware Prerequisites

#### Low Tier Configuration
coming up

#### Mid Tier (Default Configuration)
* **GPU for Main LLM (`Qwen/Qwen3.6-35B-A3B-FP8`):** Minimum $2 \times 24\text{GB}$ GPUs (e.g., $2 \times \text{RTX 3090/4090}$ or enterprise equivalents like A10/A100) to run the 35B model with `--tensor-parallel-size 2`.
* **GPU for Embedding Indexer (`nomic-ai/nomic-embed-text-v1.5`):** Minimum $1 \times$ dedicated GPU with at least $1\text{GB}$ available VRAM (can be a low-end card or integrated GPU).
* **Storage:** $\sim 50\text{GB}$ of (ideally) fast SSD storage allocated to the Hugging Face cache directory (`HF_HOME`) to store model weights for all configured models.
* **RAM:** $64\text{GB}$ system RAM recommended when running the 35B model with speculative decoding.

#### High Tier Configuration
coming up


---

## 2. Using the Anvil Workspace Script (`./anvil`)

The `anvil` script helps you manage the llama-swap backend stack. Make sure it's executable:

```bash
chmod +x anvil
```

### Main commands

| Command | Action | Description |
| :--- | :--- | :--- |
| `./anvil up` | Start Stack | Starts the llama-swap gateway and Qdrant vector database in the background. |
| `./anvil build` | Rebuild | Force rebuild of custom Docker configurations. |
| `./anvil status` | View Status | Shows llama-swap gateway health and which models are actively loaded vs cold/swapped out. |
| `./anvil logs` | View Logs | Streams llama-swap orchestration logs and on-demand model outputs. |
| `./anvil restart` | Restart | Restarts the llama-swap gateway container. |
| `./anvil down` | Stop Stack | Stops all containers and cleans up any orphaned on-demand vLLM model containers. |

### Understanding Model Status

When you run `./anvil status`, you'll see models listed as:

- **🟢 ACTIVE & HOT** — The model is currently loaded and serving requests.
- **🟡 COLD / SWAPPED OUT** — The model is configured but not loaded. It will lazy-load on first request.

llama-swap automatically evicts cold models based on the TTL (default 30 minutes) and eviction cost priorities defined in [`config.yaml`](../config.yaml).

---
