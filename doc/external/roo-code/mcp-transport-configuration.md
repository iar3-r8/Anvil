# Using MCP in Roo Code — transport configuration

Source: https://github.com/RooCodeInc/Roo-Code-Docs/blob/main/docs/features/mcp/using-mcp-in-roo.mdx
Also: https://github.com/RooCodeInc/Roo-Code-Docs/blob/main/docs/features/mcp/server-transports.md
Retrieved: 2026-10-19 (via the github MCP server; oxylabs was unavailable in that session)

Captured because Anvil renders `.roo/mcp.json` and needed the authoritative key set for a
remote MCP server — specifically whether Roo Code can pass custom HTTP headers, which the
hosted Oxylabs server requires for authentication.

## Where the file lives, and precedence

MCP server configurations are managed at two levels:

1. **Global configuration** — `mcp_settings.json`, applying across all workspaces unless
   overridden.
2. **Project-level configuration** — `.roo/mcp.json` in the project root. Roo Code
   automatically detects and loads this file if it exists.

**Precedence**: if a server name exists in both global and project configurations, the
**project-level configuration takes precedence**.

Both files use a JSON format with an `mcpServers` object containing named server
configurations.

## Understanding transport types

> MCP supports three transport types for server communication: STDIO for local servers,
> Streamable HTTP (recommended for new remote servers), and SSE (for legacy remote servers).

### STDIO transport

Used for local servers running on your machine. Runs as a child process on your machine.

STDIO configuration parameters:

* `command` (required): The executable to run (e.g. `node`, `python`, `npx`, or an absolute
  path).
* `args` (optional): An array of string arguments to pass to the command. You can reference
  system environment variables using `${env:VARIABLE_NAME}` syntax.
* `cwd` (optional): The working directory from which to launch the server process. If
  omitted, defaults to the first workspace folder path or the main process's working
  directory.
* `env` (optional): An object containing environment variables to set for the server process.
* `alwaysAllow` (optional): An array of tool names from this server to automatically approve.
* `disabled` (optional): Set to `true` to disable this server configuration.
* `timeout` (optional): Per-server timeout override in seconds (1-3600). If not specified,
  uses the default of 60 seconds.
* `watchPaths` (optional): An array of file paths to watch. When any of these files change,
  the server will automatically restart.
* `disabledTools` (optional): An array of tool names to disable from this server.

STDIO configuration example:

```json
{
  "mcpServers": {
    "local-server": {
      "command": "node",
      "args": ["server.js"],
      "cwd": "/path/to/project/root",
      "env": {
        "API_KEY": "your_api_key"
      },
      "alwaysAllow": ["tool1", "tool2"],
      "disabled": false
    }
  }
}
```

### Using system environment variables in arguments

You can reference system-level environment variables within the `args` array using the
`${env:VARIABLE_NAME}` syntax. This allows you to pass sensitive information like API keys or
tokens from your system environment without hardcoding them in your configuration.

```json
{
  "mcpServers": {
    "github": {
      "command": "docker",
      "args": [
        "run", "-i", "--rm",
        "-e", "GITHUB_PERSONAL_ACCESS_TOKEN=${env:GITHUB_PERSONAL_ACCESS_TOKEN}",
        "ghcr.io/github/github-mcp-server"
      ],
      "alwaysAllow": ["get_pull_request"]
    }
  }
}
```

> **Note:** The environment variable must exist in your system environment for this to work.

This is documented for the `args` array. The documentation does not state that the same
`${env:...}` syntax is expanded inside `headers`.

### Streamable HTTP transport

> This is the **modern standard** for remote servers accessed over HTTP/HTTPS, offering more
> flexibility and replacing the legacy SSE transport for new implementations.

* Communicates via HTTP POST/GET to a single MCP endpoint
* Optionally uses Server-Sent Events (SSE) for streaming
* Can be hosted on a different machine
* Supports multiple client connections
* Requires network access

Streamable HTTP configuration parameters:

* `type` (required): Must be set to `"streamable-http"`.
* `url` (required): The full URL of the remote MCP server's single endpoint (e.g.
  `https://your-server.com/mcp`).
* `headers` (optional): An object containing custom HTTP headers to send with requests (e.g.
  for authentication tokens).
* `alwaysAllow` (optional): An array of tool names from this server to automatically approve.
* `disabled` (optional): Set to `true` to disable this server configuration.
* `timeout` (optional): Per-server timeout override in seconds (1-3600). If not specified,
  uses the default of 60 seconds.
* `disabledTools` (optional): An array of tool names to disable from this server.

Streamable HTTP configuration example:

```json
{
  "mcpServers": {
    "modern-remote-server": {
      "type": "streamable-http",
      "url": "https://your-modern-server.com/api/mcp-endpoint",
      "headers": {
        "X-API-Key": "your-secure-api-key"
      },
      "alwaysAllow": ["newToolA", "newToolB"],
      "disabled": false
    }
  }
}
```

Note that the parameter list for Streamable HTTP contains **no `command`, `args` or `env`
key**. A remote server is configured by `url` and `headers` alone.

### SSE transport (legacy)

Used for older remote servers. **For new remote server implementations, Streamable HTTP
transport is recommended.**

SSE (legacy) configuration parameters:

* `type` (required for URL-based configs): Must be set to `"sse"` when using a `url` for an
  SSE server. For stdio configs (those using `command`), `type` defaults to `"stdio"` and can
  be omitted. **For any URL-based config, omitting `type` will cause an immediate error — Roo
  Code cannot infer the transport type from a `url` alone.**
* `url` (required): The base URL for the remote MCP server.
* `headers` (optional): An object containing custom HTTP headers to send with requests.
* `alwaysAllow`, `disabled`, `timeout`, `disabledTools` — as above.

```json
{
  "mcpServers": {
    "legacy-remote-server": {
      "type": "sse",
      "url": "https://your-legacy-server-url.com/mcp-base",
      "headers": {
        "Authorization": "Bearer your-legacy-token"
      },
      "alwaysAllow": ["oldToolX"],
      "disabled": false
    }
  }
}
```

## Network timeout

> To set the maximum time to wait for a response after a tool call to the MCP server: click
> the `Network Timeout` pulldown at the bottom of the individual MCP server's config box and
> change the time. Default is 60 seconds (1 minute) but it can be set between 1 second and
> 3600 seconds (1 hour).

## Troubleshooting (verbatim)

> * **Server Not Responding:** Check if the server process is running and verify network
>   connectivity
> * **Permission Errors:** Ensure proper API keys and credentials are configured in your
>   `mcp_settings.json` (for global settings) or `.roo/mcp.json` (for project settings).
> * **Tool Not Available:** Confirm the server is properly implementing the tool and it's not
>   disabled in settings
> * **Slow Performance:** Try adjusting the network timeout value for the specific MCP server

## Transport comparison (from server-transports.md)

| Consideration | STDIO | Streamable HTTP | SSE (Legacy) |
|---|---|---|---|
| **Location** | Local machine only | Local or remote | Local or remote |
| **Setup Complexity** | Simpler | More complex (requires HTTP server) | More complex |
| **Network Access** | Not needed | Required | Required |
| **Dependencies** | Client-side dependencies | Server-side dependencies | Server-side dependencies |
| **Recommendation** | Ideal for local, secure, single-client tools | **Modern standard for all new remote servers** | Legacy, for existing older servers |

The row that decides Anvil's case: STDIO carries **client-side dependencies** — the
interpreter and package must resolve on the user's machine — while Streamable HTTP carries
**server-side dependencies** only.
