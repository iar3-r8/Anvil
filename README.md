

# <img  src="./assets/logo.png" style="vertical-align: bottom;" width="80" height="80"> <img  src="./assets/anvil.png" style="vertical-align: bottom;" height="80">

**Anvil** provides everything teams need to self-host their own agentic coding environment. Eliminate commercial API expenses and secure your code intellectual property and data behind an air-gapped, high-throughput local backend stack powered by [llama-swap](https://github.com/mostlygeek/llama-swap), [Docker Compose](https://docs.docker.com/compose/), and [Zoo Code](https://www.zoocode.dev/).

---

## Why Anvil?

Commercial AI coding assistants are powerful, but they come with two massive drawbacks for engineering teams: **unpredictable monthly token bills** and **data privacy compliance risks** associated with sending proprietary codebases and sometimes even data to external APIs. 

Anvil gives you a turnkey, production-grade alternative that runs completely on your own metal. 

### What's Under the Hood?
* **Dynamic Model Routing:** Powered by [llama-swap](https://github.com/mostlygeek/llama-swap), a smart gateway that manages model lifecycles with TTL-based swapping, allowing multiple models to share limited GPU resources efficiently.
* **High-Throughput Inference:** Child containers run [`vllm`](https://vllm.ai/) hosting optimized `Qwen2.5-Coder-7B` and `Qwen3.8-27B-FP8` reasoning models on-demand.
* **Local Workspace RAG:** A dedicated text-embedding container paired with a [`Qdrant`](https://qdrant.tech/) vector database to provide deep codebase context to your agent.
* **Frictionless UI Integration:** Pre-configured settings to tie the entire infrastructure directly into the [**Zoo Code**](https://www.zoocode.dev/) (formerly Roo Code) VS Code extension.
* **Documentation-Grounded Planning:** The agent modes treat an unknown third-party interface as a blocking condition rather than something to guess at. Real vendor documentation is fetched through the [Oxylabs](https://dashboard.oxylabs.io/en/overview/scraper) MCP server, saved under `doc/external/` and cited in the plan, so tests are never written against an invented API.

---

## Getting Started

### Prerequisites
* **Python 3.8 or newer**, used by the `./anvil` command itself. Anvil provisions its own virtual environment on first run, so there is **no manual `pip install`** — just clone and run. `.venv/` is disposable and safe to delete; it will be rebuilt.
* **Docker with Compose v2**, and the **NVIDIA Container Toolkit** on Linux hosts. See the backend guide for versions and hardware sizing.

Run `./anvil doctor` at any point to check what Anvil found on your machine.

To keep the setup process straightforward and clean, the documentation is split into two distinct layers: bringing up your infrastructure and configuring your editor.

### Step 1: Spin Up Your Infrastructure
Learn how to use the interactive `./anvil` helper script to generate your environment file, configure your GPU device allocations, and launch the multi-container backend stack.

👉 **[Read the Backend Setup Guide](doc/1-setting-up-backend.md)**

### Step 2: Configure Your VS Code Extension
Once your local backend engines are online, learn how to install the recommended extension workspace and configure your agentic setup in your own repository.

`./anvil setup-repo` provisions the target repository and prompts for the optional
integrations. Supply them as flags to run unattended — `--github-token`,
`--anthropic-key`, `--oxylabs-username` and `--oxylabs-password` — or skip any of them
with `--no-github`, `--no-anthropic` and `--no-oxylabs`. Re-running `setup-repo` is also
the upgrade path for an already-provisioned repository: existing `.env` credentials are
reused rather than re-prompted.

👉 **[Read the VS Code Plugin Setup Guide](doc/2-setting-up-vscode-plugin.md)**

---

## Contribute

Check open issues and vote on features you want. Your feedback helps prioritise what gets built next.
