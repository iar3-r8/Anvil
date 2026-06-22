# Setup Guide: Connecting Zoo Code to Your Local Backend

This guide walks you through configuring the **Zoo Code** VS Code extension to communicate with your locally hosted inference server. 

By utilizing our unified configuration file, you can bypass manual UI configuration and immediately connect your agentic workspace to your local backend.

---

## Prerequisites

1. **VS Code** installed on your machine.
2. The local inference container running (via your preferred `docker compose` hardware profile).
3. The **Zoo Code** extension installed. 
   > *Note: If you haven't installed it yet, open the Extensions view (`Ctrl+Shift+X` or `Cmd+Shift+X`), search for **Zoo Code**, and click **Install**.*

---

## Automated Configuration (Recommended)

We provide a pre-configured `zoo-code-settings.json` file in the root of this repository. This file automatically sets up the correct API parameters, local endpoints, and context window limits optimized for local execution.

1. Open **VS Code** inside this repository folder.
2. Open the Command Palette using `Ctrl+Shift+P` (Windows/Linux) or `Cmd+Shift+P` (macOS).
3. Type and select: **Zoo Code: Load Settings From File** (or your local equivalent configuration import command).
4. Select the `zoo-code-settings.json` file located in the root directory.

Once loaded, Zoo Code is instantly pointed to `http://localhost:8000/v1` and ready to process requests through your active Docker profile.

---

## Manual Configuration Fallback

If you prefer to configure the extension through the user interface, use the following parameters within the Zoo Code settings panel:

* **API Provider:** `OpenAI Compatible` (or `vLLM` if explicitly listed)
* **Base URL:** `http://localhost:8000/v1`
* **API Key:** `not-needed` *(or leave blank—vLLM handles local requests without authentication by default)*
* **Model ID:** Enter the precise name of the model currently running in your active Docker profile (e.g., `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ`).

---

## Verifying the Connection

1. Open the **Zoo Code** panel from your VS Code activity bar (sidebar).
2. Ensure the connection status icon shows a successful connection to your local endpoint.
3. Submit a quick diagnostic prompt to test the agentic loop:
```text
   Create a basic health check markdown file to verify you can read and write to this workspace.