# Setup Guide: Running Anvil's backend

This guide details how to launch and configure the local dual-service backend (Inference LLM + Embedding Indexer) 

This setup uses **Docker Compose Profiles** under the `coder` profile to spin up both a high-throughput reasoning model and a local vector database for workspace indexing.

---

## 1. Requirements

Before running the stack, ensure your host hardware meets the requirements for your target allocation. Because the default configuration utilizes tensor parallelism across two GPUs for the main LLM and a third dedicated GPU for the indexer, the requirements are split below:

### Software Prerequisites
* **Docker & Docker Compose:** Required to orchestrate the multi-container infrastructure. Make sure you are running a modern version of Docker Compose.
* **NVIDIA Container Toolkit:** Required on Linux host machines to expose your physical graphics hardware to the underlying Docker containers.

### Hardware Prerequisites

#### Low Tier Configuration
Coming up

#### Mid Tier (Default Configuration)
* **GPU VRAM:** 
  * **Main LLM (`vllm-coder-mid`):** Minimum $2 \times 24\text{GB}$ GPUs (e.g., $2 \times \text{RTX 3090/4090}$ or enterprise equivalents) to split the model weight overhead via `--tensor-parallel-size 2`.
  * **Indexer (`vllm-coder-indexer`):** Minimum $1 \times \text{Dedicated GPU}$ with at least $1\text{GB}$ available VRAM.
* **Storage:** $\sim 50\text{GB}$ of (ideally) fast SSD storage allocated to the Hugging Face cache directory (`HF_HOME`) to store model weights.
* **Drivers:** NVIDIA Container Toolkit installed on the host with CUDA-capable drivers.

#### High Tier Configuration
Coming up


---

## 2. Using the Anvil Workspace Script (`./anvil`)

The anvil script is here to help you manage the project backend. Make sure that it can be executable with the command `chmod +x anvil`

### Available Commands

| Command | Action | Description |
| :--- | :--- | :--- |
| `./anvil up` | Start Stack | Builds and starts the LLM, Indexer, and Qdrant database in the background. |
| `./anvil down` | Stop Stack | Safely stops and tears down all running containers. |
| `./anvil logs` | View Logs | Streams the real-time engine and model outputs to your terminal. |
| `./anvil restart` | Restart Stack | Quickly restarts the container processes to clear the engine's memory. |