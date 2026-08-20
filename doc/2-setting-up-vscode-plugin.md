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
./anvil setup-repo /path/to/your/target-repo
```

*Follow the interactive prompts to automatically hook up directory paths, copy the `roo_template` folders, configure optional GitHub tokens and Oxylabs documentation access, and optionally bind **architect** and **orchestrator** modes to an Anthropic frontier model (the key is stored in `.env`).*

To run it unattended, supply the answers as flags — for example:

```bash
./anvil setup-repo /path/to/your/target-repo --yes \
    --github-token "$GITHUB_TOKEN" --anthropic-key "$ANTHROPIC_API_KEY" \
    --oxylabs-username "$OXYLABS_USERNAME" --oxylabs-password "$OXYLABS_PASSWORD"
```

Use `--no-github`, `--no-anthropic` and `--no-oxylabs` to skip any integration
explicitly, and `--dry-run` to see exactly which files would be written without
writing any of them. See the [backend guide](1-setting-up-backend.md) for the full
flag list.

### GitHub token

The agent's GitHub personal access token is kept in Anvil's own store, not in
the target repository, so the decision is shared across every provisioned
repository:

* Accepting the prompt stores the token (hidden as you type) in `.env` as
  `GITHUB_TOKEN`, and `setup-repo` injects it into the target's `.roo/mcp.json`
  as `GITHUB_PERSONAL_ACCESS_TOKEN`.
* A `GITHUB_TOKEN` already present in `.env` is reused silently — a second run
  does not re-prompt, and the value itself is never echoed. A blank stored
  value counts as absent and prompts again.
* `--github-token` wins over the store and is persisted the same way, so a
  flag-bearing run leaves flag-less runs on the same machine un-prompted.
* `--no-github` skips the integration entirely without touching `.env`, and a
  `--yes` or non-interactive run with nothing stored skips without blocking.
* Declining the prompt does the same and points you at the same place to fix it
  later: edit `.env` and populate `GITHUB_TOKEN`.

### Documentation grounding with Oxylabs

The agent modes are told that an unknown third-party interface is a **blocking
condition**: rather than guessing at a library's method signatures, the architect
fetches the real documentation with the [Oxylabs](https://dashboard.oxylabs.io/en/overview/scraper)
MCP server, saves the pages that answer the question under `doc/external/<vendor>/`,
and cites them in the plan. Everything adjacent is recorded as a single line in
`doc/external/index.md`. Because that directory is committed, the research is
reviewable in the pull request and is not re-fetched by every developer.

During `setup-repo` you are asked whether to enable it, and the prompt carries the
signup link:

```text
Enable the Oxylabs MCP for documentation fetching?
Sign up at https://dashboard.oxylabs.io/en/overview/scraper
```

* Accepting prompts for a username, then a password (hidden as you type). Both are
  written to `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`, and injected into
  `.roo/mcp.json` — the same path the GitHub token already takes.
* Declining, or passing `--no-oxylabs`, still writes the server entry but marks it
  `"disabled": true` with empty credentials. A configured-but-unauthenticated server
  fails on every call and looks like a bug; disabled is honest, and enabling it later
  is a one-word edit.
* Non-interactive runs (`--yes`) with no credentials available behave the same way.
* Credentials already present in `.env` are reused silently — a second run does not
  re-prompt, and `--yes` does not blank them.

**Upgrading a repository that is already provisioned:** just re-run
`./anvil setup-repo /path/to/your/target-repo`. `.roo/mcp.json`, `.roomodes`
and `.vscode/extensions.json` are all **merged** rather than rewritten:

* **`.roo/mcp.json`** — servers you added by hand are preserved untouched (in
  position), servers Anvil owns — github, git, oxylabs, package-registry — are
  refreshed, and nothing is ever removed. The Oxylabs entry simply appears.
* **`.roomodes`** — a mode whose slug you already have is skipped entirely,
  so your hand edits survive; modes the template defines that you are missing
  are appended.
* **`.vscode/extensions.json`** — `recommendations` are unioned (your entries
  keep their position, missing ones are appended) and other keys such as
  `unwantedRecommendations` survive untouched.

`.env` only ever gains keys — an existing `ANTHROPIC_API_KEY` or `GITHUB_TOKEN`
survives untouched. One exception, in your favour: a credential you have already
filled in is never blanked by an empty incoming value, so a second run after
`.env` loses a credential cannot silently disable the server. A hand edit *to*
an Anvil-owned server (say adding entries to `github.alwaysAllow`) is still
replaced by the template's version on the next run.

A re-run that has nothing to write reports each file as *already up to date*
and leaves it untouched, and a malformed or non-UTF-8 existing file aborts the
run (exit code 5) before anything is written — including under `--dry-run`.

> The `/update_roo_rules` chat command described in section 4 refreshes the rules under
> `.roo/`, but it **cannot** add the Oxylabs server: `.roo/mcp.json` is generated by
> `setup-repo` and lives outside the rules template. Re-run `setup-repo` for the MCP
> entry itself.

### Sensitive file protection

`setup-repo` deploys a `.gitignore` template into the target repository that
protects sensitive files from accidental commits. The merge is **additive** —
existing content is never truncated or reordered. The entries managed are:

| Entry | Reason |
| --- | --- |
| `.env` | secrets and host paths |
| `anvil.local.yaml` | machine-specific overrides |
| `zoo-code-settings.json` | Anthropic API key, gateway URL |
| `.roo/mcp.json` | GitHub personal access token |
| `.venv/.anvil-requirements-stamp` | bootstrap state |

If all entries are already present in the target's `.gitignore`, the file is
left byte-for-byte unchanged (idempotent).

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

---

## 5. Run Zoo Code Inside a Dev Container (Optional)

For a fully sandboxed coding session — isolated filesystem, no access to your
host credentials, and all MCP runtimes pre-installed — open the repo in VS Code
and click **Reopen in Container**.

The container runs with `--network=host` so `localhost` still reaches the gateway
on the host. The Docker socket is **not** mounted, so `./anvil up` and
`./anvil down` must be run from the host. The GitHub token is injected via
`remoteEnv` from the host `${GITHUB_TOKEN}` environment variable.

See [`.devcontainer/devcontainer.json`](../.devcontainer/devcontainer.json) for
details.
