

# <img  src="./assets/logo.png" style="vertical-align: bottom;" width="80" height="80"> <img  src="./assets/anvil.png" style="vertical-align: bottom;" height="80">

**Anvil** provides everything teams need to self-host their own agentic coding environment. Eliminate commercial API expenses and secure your code intellectual property and data behind an air-gapped, high-throughput local backend stack powered by [llama-swap](https://github.com/mostlygeek/llama-swap), [Docker Compose](https://docs.docker.com/compose/), and [Zoo Code](https://www.zoocode.dev/).

---

## Why Anvil?

Commercial AI coding assistants are powerful, but they come with two massive drawbacks for engineering teams: **unpredictable monthly token bills** and **data privacy compliance risks** associated with sending proprietary codebases and sometimes even data to external APIs. 

Anvil gives you a turnkey, production-grade alternative that runs completely on your own hardware. 

### What's Under the Hood?
* **Dynamic Model Routing:** Powered by [llama-swap](https://github.com/mostlygeek/llama-swap), a smart gateway that manages model lifecycles with TTL-based swapping, allowing multiple models to share limited GPU resources efficiently.
* **High-Throughput Inference:** Child containers run [`vllm`](https://vllm.ai/) hosting optimized `Qwen2.5-Coder-7B` and `Qwen3.6-35B-A3B-FP8` reasoning models on-demand.
* **Local Workspace RAG:** A dedicated text-embedding container paired with a [`Qdrant`](https://qdrant.tech/) vector database to provide deep codebase context to your agent.
* **Frictionless UI Integration:** Pre-configured settings to tie the entire infrastructure directly into the [**Zoo Code**](https://www.zoocode.dev/) (formerly Roo Code) VS Code extension.

---

## Getting Started

To keep the setup process straightforward and clean, the documentation is split into two distinct layers: bringing up your infrastructure and configuring your editor.

### Step 1: Spin Up Your Infrastructure
Learn how to use the interactive `./anvil` helper script to generate your environment file, configure your GPU device allocations, and launch the multi-container backend stack.

👉 **[Read the Backend Setup Guide](doc/1-setting-up-backend.md)**

### Step 2: Configure Your VS Code Extension
Once your local backend engines are online, learn how to install the recommended extension workspace and configure your agentic setup in your own repository.

👉 **[Read the VS Code Plugin Setup Guide](doc/2-setting-up-vscode-plugin.md)**

---

## Coming up
- See issues. Vote on whatever feels important to you.
                                                                      
                                                                      
