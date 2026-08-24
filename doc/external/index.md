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
| [https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md](https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md) | llama-swap configuration reference | Full reference for `config.yaml` keys including `ttl`, `unloadTimeout` and `matrix`; adjacent to Anvil's read-only parse of that file, not needed for the stress command. |
| [https://pypi.org/project/guidellm/](https://pypi.org/project/guidellm/) | GuideLLM on PyPI | vLLM-project LLM benchmarking tool for OpenAI-compatible servers; rejected for Anvil because it requires Python 3.10+ and pulls torch, transformers, datasets and pydantic. |
| [https://pypi.org/project/locust/](https://pypi.org/project/locust/) | Locust on PyPI | General-purpose load-testing framework; rejected for Anvil because it requires Python 3.11+ and pulls gevent, flask and pyzmq. |
| [https://docs.python.org/3/library/concurrent.futures.html](https://docs.python.org/3/library/concurrent.futures.html) | concurrent.futures — Python 3 standard library | The stdlib `ThreadPoolExecutor` used to drive concurrent requests, available since Python 3.2 and therefore inside Anvil's 3.8 floor. |
| [https://docs.python.org/3/library/statistics.html](https://docs.python.org/3/library/statistics.html) | statistics — Python 3 standard library | Provides `mean` and `median`; note `quantiles()` is 3.8+ but the plan computes percentiles by index to keep p95/p99 exact and testable. |

<!-- Append new entries above this line, one per row, newest last. -->
