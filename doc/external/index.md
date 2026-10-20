# External documentation manifest

Third-party documentation gathered while planning, so a plan's claims about an external
library, API or service can be checked rather than trusted.

The agent modes treat an unknown third-party interface as a blocking condition: rather
than guessing at a method signature, the architect fetches the real documentation with
the Oxylabs MCP server, records it here, and cites it in the plan.

## Format

**One line per entry**, in the table below:

```text
| URL | Title | Description |
```

* **URL** — the canonical source, linked so a reader can open it.
* **Title** — the page's own title, not a paraphrase.
* **Description** — one sentence on what the page covers. One sentence, not a summary.

## What gets saved in full, and what does not

| Case | Action |
| --- | --- |
| The page answers the question being planned | Save it in full at `doc/external/<vendor>/<page-slug>.md`, link it from the entry below |
| The page is adjacent, but not needed right now | Record the link and the one-sentence description only |

`<vendor>` is the owner of the documentation, lowercase (`oxylabs`, `stripe`, `vllm`).
`<page-slug>` is a kebab-case slug derived from the page title. One page per file, with
the source URL recorded at the top of the file, so an entry can cite a single path.

Saving a vendor's whole site is not the goal: it buries the page that mattered and makes
the diff unreviewable. Saving a fragment is not either, because the next reader re-fetches
it. Save what answers the question, in full.

## Why this is committed

The research is a team asset and is reviewable in the pull request that relies on it. A
gitignored cache would be re-scraped by every developer and would silently rot.

Two rules follow from that:

* Update this manifest in the same change that saves a page — a saved page absent from
  the manifest is unfindable.
* Never commit credentials, tokens or private endpoints into `doc/external/`.

## Entries

| URL | Title | Description |
| --- | --- | --- |
| [https://dashboard.oxylabs.io/en/overview/scraper](https://dashboard.oxylabs.io/en/overview/scraper) | Oxylabs Web Scraper API dashboard | Where Anvil users create the credentials that `setup-repo` writes to `.env` as `OXYLABS_USERNAME` and `OXYLABS_PASSWORD`. |
| [https://docs.vllm.ai/en/latest/serving/online_serving/](https://docs.vllm.ai/en/latest/serving/online_serving/) | Online Serving — vLLM | The OpenAI-compatible endpoints a vLLM worker exposes, establishing that chat generation is `POST /v1/chat/completions` and the registry is `GET /v1/models` — saved in full at [`doc/external/vllm/online-serving.md`](vllm/online-serving.md). |
| [https://docs.vllm.ai/en/latest/usage/troubleshooting/](https://docs.vllm.ai/en/latest/usage/troubleshooting/) | Troubleshooting — vLLM | vLLM's own account of out-of-memory and engine-death failures, and the evidence that no stable machine-readable OOM error code is published — saved in full at [`doc/external/vllm/troubleshooting.md`](vllm/troubleshooting.md). |
| [https://github.com/mostlygeek/llama-swap/blob/main/README.md](https://github.com/mostlygeek/llama-swap/blob/main/README.md) | llama-swap README | The gateway's supported endpoints and its on-demand swap behaviour, which is why a cold model's first request can take minutes — saved in full at [`doc/external/llama-swap/readme-endpoints.md`](llama-swap/readme-endpoints.md). |
| [https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md](https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md) | llama-swap configuration reference | How a model key becomes the API model ID, plus `useModelName`, `concurrencyLimit`, `unlisted` and the `matrix` solver rule that a model in no set runs alone — saved in full at [`doc/external/llama-swap/configuration-reference.md`](llama-swap/configuration-reference.md). |
| [https://docs.vllm.ai/en/latest/configuration/engine_args.html](https://docs.vllm.ai/en/latest/configuration/engine_args.html) | Engine Arguments — vLLM | The authoritative meaning of `--max-num-seqs`, `--max-num-batched-tokens`, `--served-model-name` and the parallelism flags that Anvil's `config.yaml` passes verbatim to vLLM — saved in full at [`doc/external/vllm/engine-args-scheduler-and-parallelism.md`](vllm/engine-args-scheduler-and-parallelism.md). |
| [https://docs.vllm.ai/en/latest/configuration/optimization/](https://docs.vllm.ai/en/latest/configuration/optimization/) | Optimization and Tuning — vLLM | Why batching settings govern behaviour under concurrent load: `max_num_seqs` bounds requests per batch, chunked prefill is on by default in V1, and tensor parallelism shards one model rather than serving users in parallel — saved in full at [`doc/external/vllm/optimization-and-tuning.md`](vllm/optimization-and-tuning.md). |
| [https://pypi.org/project/guidellm/](https://pypi.org/project/guidellm/) | GuideLLM on PyPI | vLLM-project LLM benchmarking tool for OpenAI-compatible servers; rejected for Anvil because it requires Python 3.10+ and pulls torch, transformers, datasets and pydantic. |
| [https://pypi.org/project/locust/](https://pypi.org/project/locust/) | Locust on PyPI | General-purpose load-testing framework; rejected for Anvil because it requires Python 3.11+ and pulls gevent, flask and pyzmq. |
| [https://docs.python.org/3/library/concurrent.futures.html](https://docs.python.org/3/library/concurrent.futures.html) | concurrent.futures — Python 3 standard library | The stdlib `ThreadPoolExecutor` used to drive concurrent requests, available since Python 3.2 and therefore inside Anvil's 3.8 floor. |
| [https://docs.python.org/3/library/statistics.html](https://docs.python.org/3/library/statistics.html) | statistics — Python 3 standard library | Provides `mean` and `median`; note `quantiles()` is 3.8+ but the plan computes percentiles by index to keep p95/p99 exact and testable. |
| [https://pypi.org/project/oxylabs-mcp/](https://pypi.org/project/oxylabs-mcp/) | Oxylabs MCP Server on PyPI | Why `uvx oxylabs-mcp` dies in Anvil's Python 3.11 devcontainer (`requires-python <4,>=3.12`) and the hosted alternative at `https://mcp.oxylabs.io/mcp`, which accepts `X-Oxylabs-Username` and `X-Oxylabs-Password` headers — saved in full at [`doc/external/oxylabs/mcp-server-hosted-and-local.md`](oxylabs/mcp-server-hosted-and-local.md). |
| [https://github.com/RooCodeInc/Roo-Code-Docs/blob/main/docs/features/mcp/using-mcp-in-roo.mdx](https://github.com/RooCodeInc/Roo-Code-Docs/blob/main/docs/features/mcp/using-mcp-in-roo.mdx) | Using MCP in Roo Code | The authoritative key set for a `.roo/mcp.json` entry, establishing that a remote server takes `type: streamable-http`, `url` and `headers` — and that `type` is mandatory for any URL-based config — saved in full at [`doc/external/roo-code/mcp-transport-configuration.md`](roo-code/mcp-transport-configuration.md). |
| [https://pypi.org/project/mcp-server-git/](https://pypi.org/project/mcp-server-git/) | mcp-server-git on PyPI | Current releases require `mcp>=2.3,<3`, which is why the `--with mcp<1.10` pin Anvil ships in `mcp.json.template` is unsatisfiable and the git server fails to start. |
| [https://github.com/earendil-works/pi](https://github.com/earendil-works/pi) | Pi README | The terminal coding agent under review in the Pi spike: a minimal, extensible agent harness (npm `@earendil-works/pi-coding-agent`, Node.js ≥ 22.19) that deliberately ships without sub-agents or plan mode — saved in full at [`doc/external/pi-dev/readme.md`](pi-dev/readme.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/configuration.md) | Pi coding-agent: Configuration | Where Pi reads its configuration — the user-level agent directory (`~/.pi/agent`) and the project-level `.pi/` directory — saved in full at [`doc/external/pi-dev/configuration.md`](pi-dev/configuration.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models.md) | Pi coding-agent: Choose a Model | How an OpenAI-compatible endpoint becomes a usable model (a dummy key is fine) and that model selection is one model per session with no per-mode routing — saved in full at [`doc/external/pi-dev/models.md`](pi-dev/models.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models-configuration.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/models-configuration.md) | Pi coding-agent: Models Configuration | The `models.json` reference, including the `maxTokens` default of 16384 that long-context local models must override — saved in full at [`doc/external/pi-dev/models-configuration.md`](pi-dev/models-configuration.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/mcp.md) | Pi coding-agent: MCP Servers | The `.pi/mcp.json` format — the standard `mcpServers` map with stdio or streamable-HTTP entries and `${NAME}` env interpolation — saved in full at [`doc/external/pi-dev/mcp.md`](pi-dev/mcp.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/settings.md) | Pi coding-agent: Settings Reference | The `settings.json` reference, including `defaultProvider`/`defaultModel` selection and the built-in tool list (`read`, `bash`, `edit`, `write`, `grep`, `find`, `ls`) — saved in full at [`doc/external/pi-dev/settings.md`](pi-dev/settings.md). |
| [https://github.com/Zetaphor/pi-vscode-extension](https://github.com/Zetaphor/pi-vscode-extension) | Pi coding agent, as a VSCode extension | Community wrapper providing VS Code integration for Pi, which ships no first-party extension. |
| [https://github.com/frostime/pi-vscode-ui](https://github.com/frostime/pi-vscode-ui) | Pi VSCode UI | Non-intrusive community wrapper offering a GUI over the Pi Coding Agent's terminal UI. |
| [https://pi.dev/packages/pi-multiagent](https://pi.dev/packages/pi-multiagent) | pi-multiagent · Packages · Pi | pi.dev package page for the `agent_team` delegation package: adds the `agent_team` tool (parent stays in charge; child sessions are isolated and their output is evidence) plus bundled specialist agents and graph examples — saved in full at [`doc/external/pi-dev/packages/pi-multiagent.md`](pi-dev/packages/pi-multiagent.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/cli.md) | Pi coding-agent: Command Line | The non-interactive contract a scripted pipeline runs on — `--print`, `--mode json`, `--mode rpc`, `--session-id`/`--session-dir`/`--fork`, tool allowlisting via `--tools`, `--append-system-prompt`, and the `-a`/`--approve` project-trust flag an unattended run needs — saved in full at [`doc/external/pi-dev/cli.md`](pi-dev/cli.md). |
| [https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/containerization.md](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/containerization.md) | Pi coding-agent: Run Pi in an isolated environment | Pi has no built-in permission system and runs with the launching user's permissions, so a sandbox is the only boundary; gives the plain-Docker recipe (`/workspace` bind mount, named `pi-agent-home` volume) and three other isolation methods — saved in full at [`doc/external/pi-dev/containerization.md`](pi-dev/containerization.md). |
| [https://pi.dev/docs/latest/json](https://pi.dev/docs/latest/json) | Pi coding-agent: JSON Event Stream | The measurement surface for a dev-cycle benchmark: strict JSONL on stdout carrying per-tool `durationMs`, cumulative token `usage` with `cost`, `auto_retry_*`, `compaction_*` and `agent_settled.aborted` — plus the LF-only framing rule and the warning that a stalled reader blocks Pi — saved in full at [`doc/external/pi-dev/json-event-stream.md`](pi-dev/json-event-stream.md). |
| [https://pi.dev/packages/pi-ultrawork](https://pi.dev/packages/pi-ultrawork) | pi-ultrawork · Packages · Pi | Reuse candidate for autonomy and fan-out: a goal persisted on disk that survives compaction, capped auto-continuation, and `ulw_dispatch` spawning child `pi` processes whose NDJSON it parses — but its dispatch takes no model argument, so it does not route a model per role — saved in full at [`doc/external/pi-dev/packages/pi-ultrawork.md`](pi-dev/packages/pi-ultrawork.md). |

<!-- Append new entries above this line, one per row, newest last. -->
