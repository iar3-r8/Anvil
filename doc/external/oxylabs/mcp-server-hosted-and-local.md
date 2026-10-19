# Oxylabs MCP Server — hosted endpoint, local run, and credentials

Source: https://pypi.org/project/oxylabs-mcp/ (package metadata and long description, v0.10.0)
Upstream repository: https://github.com/oxylabs/oxylabs-mcp
Retrieved: 2026-10-19 (via the package-registry MCP server; oxylabs itself was down — this
page is what explains why)

Captured because Anvil ships an `oxylabs` entry in `.roo/mcp.json` that launches the server
locally with `uvx`, and that launch fails in Anvil's devcontainer. The two facts that decide
the fix are the **Python floor** and the **hosted endpoint's header authentication**.

## Packaging facts (PyPI metadata, v0.10.0)

| Field | Value |
|---|---|
| Latest version | `0.10.0` |
| `requires-python` | `<4,>=3.12` |
| Classifiers | Python 3.12, Python 3.13 |
| Dependencies | `fastmcp>=3.2.4`, `httpx>=0.28.1`, `lxml>=6.1.0`, `lxml-html-clean>=0.4.4`, `markdownify==1.2.2`, `oxylabs-ai-studio>=0.2.20`, `pydantic>=2.13.3`, `pydantic-settings>=2.14.0` |
| Known vulnerabilities | none reported |
| Licence | MIT |

**`requires-python = "<4,>=3.12"` is the load-bearing fact.** A host or container whose
Python is older cannot run `uvx oxylabs-mcp` without `uv` first downloading a managed
CPython ≥ 3.12.

## Two ways to use the server

> There are two ways to use the server: connect to the **hosted instance** (no installation)
> or **run it locally** with credentials in environment variables.

### Option 1: hosted server (no installation)

> Oxylabs runs a hosted MCP server at:
>
> ```
> https://mcp.oxylabs.io/mcp
> ```
>
> Credentials are passed with request headers:

| Credential | Header |
|---|---|
| Web Scraper API token (recommended) | `Authorization: Bearer <token>` |
| Web Scraper API token (alternative) | `X-Oxylabs-Api-Token` |
| Web Scraper API username and password | `Authorization: Basic <base64(username:password)>` |
| Web Scraper API username and password (alt.) | `X-Oxylabs-Username` and `X-Oxylabs-Password` |
| AI Studio | `X-Oxylabs-AI-Studio-Api-Key` |

> If both an API token and a username and password are passed, the token is used.

Client configuration for "Cursor or any client that supports remote MCP servers with custom
headers":

```json
{
  "mcpServers": {
    "oxylabs": {
      "url": "https://mcp.oxylabs.io/mcp",
      "headers": {
        "Authorization": "Bearer YOUR_API_TOKEN",
        "X-Oxylabs-AI-Studio-Api-Key": "YOUR_API_KEY"
      }
    }
  }
}
```

> **Note:** clients that only support OAuth for remote servers (for example, adding a custom
> connector in the claude.ai web UI) cannot pass headers yet — OAuth sign-in is on our
> roadmap. Use the local setup below with those clients in the meantime.

The `X-Oxylabs-Username` / `X-Oxylabs-Password` row matters for Anvil: the hosted endpoint
accepts the **same username and password pair** Anvil already prompts for and stores in
`.env`, so switching transport does not force a change of credential type.

### Option 2: run locally

Environment variables the server supports:

| Name | Description | Default |
|---|---|---|
| `OXYLABS_API_TOKEN` | Your Oxylabs Web Scraper API token | |
| `OXYLABS_USERNAME` | Your Oxylabs Web Scraper API username | |
| `OXYLABS_PASSWORD` | Your Oxylabs Web Scraper API password | |
| `OXYLABS_AI_STUDIO_API_KEY` | Your Oxylabs AI Studio API key | |
| `LOG_LEVEL` | Log level for the logs returned to the client | `INFO` |

> For the Web Scraper API tools, set either `OXYLABS_API_TOKEN` or both `OXYLABS_USERNAME`
> and `OXYLABS_PASSWORD`. If both are set, the token is used.

> ❗ **Important: only set the environment variables you have real credentials for.
> Placeholder values make tool calls fail.**

This is the configuration Anvil currently ships:

```json
{
  "mcpServers": {
    "oxylabs": {
      "command": "uvx",
      "args": ["oxylabs-mcp"],
      "env": {
        "OXYLABS_API_TOKEN": "YOUR_API_TOKEN",
        "OXYLABS_AI_STUDIO_API_KEY": "YOUR_API_KEY"
      }
    }
  }
}
```

To run the server locally the documentation also requires the `uv` package manager.

### Prerequisites

> Before you begin, make sure you have **at least one** of the following:
>
> * **Oxylabs Web Scraper API account**: obtain an API token (or your username and password)
>   from the [Oxylabs dashboard](https://dashboard.oxylabs.io/) (1-week free trial
>   available);
> * **Oxylabs AI Studio API key**: obtain your API key from
>   [Oxylabs AI Studio](https://aistudio.oxylabs.io/settings/api-key) (1000 credits free).

## Tools provided

Web Scraper API tools: `universal_scraper`, `google_search_scraper`,
`amazon_search_scraper`, `amazon_product_scraper`.

AI Studio tools: `ai_scraper`, `ai_crawler`, `ai_browser_agent`, `ai_search`, `ai_map`,
`generate_schema`.

> All tools are always listed; calling a tool without the credentials it needs returns an
> error message explaining what to configure.

`universal_scraper` is the tool Anvil's architect mode relies on for fetching third-party
documentation pages.

## Self-hosting over HTTP

The server also supports the MCP streamable-HTTP transport:

```bash
MCP_TRANSPORT=streamable-http MCP_HOST=0.0.0.0 MCP_PORT=8000 uvx oxylabs-mcp
```

With the HTTP transport, credentials are passed per request as headers instead of
environment variables — the same header table as the hosted instance.
