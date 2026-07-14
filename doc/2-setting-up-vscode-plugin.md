# Setup Guide: VS Code Extension & Agent Configuration

This guide outlines how to configure your workspace repository to connect with the local Anvil AI infrastructure using the **Zoo Code** VS Code extension.

### Prerequisites
* Ensure the local Anvil inference backend and embedding indexer services are up and running (`./anvil up`).
* You can check the status to see when it is done warming up (`./anvil status`)
* You can also look at the compose logs for any error (`./anvil logs`)

---

## 1. Provision Your Target Repository

Run the initialization command from your Anvil root directory to generate the required environment profiles, MCP structures, VS Code extensions, and workspace configuration templates inside your project repository (Note that some files will be copied to your repositories):

```bash
./anvil setup_repo /path/to/your/target-repo
```

*Follow the interactive prompts to automatically hook up directory paths, copy the `roo_template` folders, and configure optional GitHub tokens.*

---

## 2. Open VS Code & Install the Extension

1. Open your target repository directory inside VS Code.
2. If prompted, accept the workspace recommendation to install the **Zoo Code** extension (pre-configured via `.vscode/extensions.json`). 
3. *Alternative:* If it does not install automatically, open the Extensions marketplace (`Ctrl+Shift+X` or `Cmd+Shift+X`), search for **Zoo Code**, and click install manually. Refresh or reload your IDE window if required.

---

## 3. Import Zoo Code Configuration

To link the extension directly to your local Docker containers and active `.env` network ports, import the dynamically generated settings file:

1. Click on the **Zoo Code** icon in the VS Code Activity Bar (left-hand sidebar).
2. Click the **Settings** (gear icon) inside the Zoo Code interface panel.
3. Scroll down or navigate to the **"About Zoo Code"** section block.
4. Click the **Import** button.
5. Select or paste the path to the `zoo-code-settings.json` file located at the **root** of your current workspace repository.

---

## 4. Initialize Agent Persona & Rules

Once your profile is active, initialize the system prompts, custom tools, and behavioral guidelines for the agent layer:

1. Open a new chat window inside the **Zoo Code** sidebar interface.
2. Execute the custom directive command directly in the chat window with the LLM:
```text
   /update_roo_rules
   ```
3. The LLM will automatically parse your `.roo/commands/update_roo_rules.md` directives to orchestrate, align, and save your specific development rules and behaviors. 

Your local environment is now fully configured and ready for sovereign agentic execution!
