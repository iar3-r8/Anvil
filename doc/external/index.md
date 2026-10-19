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
| [https://www.rtk-ai.app/docs/](https://www.rtk-ai.app/docs/) | Overview — RTK | What RTK is and how its PreToolUse hook rewrites a command into `rtk <cmd>`, plus what "savings" measure (bash output bytes only) and the two optional layers, the engine and the RTK Proxy — saved in full at [`doc/external/rtk-ai/overview.md`](rtk-ai/overview.md). |
| [https://www.rtk-ai.app/docs/resources/editions/](https://www.rtk-ai.app/docs/resources/editions/) | Editions and licensing — RTK | The three RTK downloads and their licences: full `rtk` is Apache-2.0 + BUSL-1.1 (the engine), `rtk-oss` is Apache-2.0 and drops the engine's PostToolUse Read/MCP compression, and the BUSL Additional Use Grant permits free production use — saved in full at [`doc/external/rtk-ai/editions-and-licensing.md`](rtk-ai/editions-and-licensing.md). |
| [https://www.rtk-ai.app/docs/getting-started/supported-agents/](https://www.rtk-ai.app/docs/getting-started/supported-agents/) | Supported agents — RTK | The integration tiers per agent, establishing that Cline / Roo Code is the rules-file (prompt-level) tier with no transparent rewrite — the agent must prefix `rtk` itself, and `rtk init --agent cline` writes `.clinerules` — saved in full at [`doc/external/rtk-ai/supported-agents.md`](rtk-ai/supported-agents.md). |
| [https://www.rtk-ai.app/docs/resources/what-rtk-covers/](https://www.rtk-ai.app/docs/resources/what-rtk-covers/) | What RTK optimizes — RTK | The per-ecosystem list of filtered commands; the Python filters are `pytest`, `ruff check`, `mypy` and `pip install`, with no `python -m unittest` filter, so uncovered commands pass through unchanged — saved in full at [`doc/external/rtk-ai/what-rtk-optimizes.md`](rtk-ai/what-rtk-optimizes.md). |
| [https://www.rtk-ai.app/docs/resources/savings-explained/](https://www.rtk-ai.app/docs/resources/savings-explained/) | Savings explained — RTK | Why RTK's "up to 90%" is measured only on the bytes a shell command sends back, how the reduction dilutes from bytes to input tokens to cost, and what RTK does not reduce — saved in full at [`doc/external/rtk-ai/savings-explained.md`](rtk-ai/savings-explained.md). |
| [https://roocodeinc.github.io/Roo-Code/features/custom-instructions](https://roocodeinc.github.io/Roo-Code/features/custom-instructions) | Custom instructions — Roo Code | Roo Code's rule loading order, establishing that the legacy files `.roorules` and `.clinerules` are used only if no generic rules directory content was loaded, so a `.clinerules` is inert wherever `.roo/rules/` has files — saved in full at [`doc/external/roo-code/custom-instructions.md`](roo-code/custom-instructions.md). |

<!-- Append new entries above this line, one per row, newest last. -->
