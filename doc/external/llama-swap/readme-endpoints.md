# llama-swap — README (supported endpoints and swap behaviour)

Source URL: https://github.com/mostlygeek/llama-swap/blob/main/README.md
Fetched: 2026-08-21 (GitHub MCP `get_file_contents`, `mostlygeek/llama-swap`, branch `main`)

Why this page is saved: `anvil stress` talks to the llama-swap gateway, not directly to vLLM.
Two facts from this README are load-bearing for the plan and are cited from here:

1. The gateway exposes `v1/chat/completions`, `v1/models` and `/running` — the three paths the
   stress command uses (generation, registry lookup, hot/cold reporting).
2. **Swap semantics**: "When a request is made to an OpenAI compatible endpoint, llama-swap will
   extract the `model` value and load the appropriate server configuration to serve it. If the
   wrong upstream server is running, it will be replaced with the correct one." This is why the
   warm-up phase exists: the first request to a cold model triggers a load that can take
   minutes, and measuring that load as if it were request latency would poison every number in
   the report.

Only the sections bearing on those facts are reproduced; the install and Docker sections are
omitted deliberately.

---

# llama-swap

Run multiple generative AI models on your machine and hot-swap between them on demand.
llama-swap works with any OpenAI and Anthropic API compatible server and is used by thousands
of people to power their local AI workflows.

Built in Go for performance and simplicity, llama-swap has zero dependencies and is incredibly
easy to set up. Get started in minutes - just one binary and one configuration file.

## Features:

- ✅ Easy to deploy and configure: one binary, one configuration file. no external dependencies
- ✅ On-demand model switching for many local AI servers (llama.cpp + forks, vllm,
  stable-diffusion.cpp, audio.cpp, ComfyUI, etc.)
  - future proof, upgrade your inference servers at any time.
- ✅ OpenAI API supported endpoints:
  - `v1/completions`
  - `v1/chat/completions`
  - `v1/responses`
  - `v1/embeddings`
  - `v1/models` - list available models
  - `v1/audio/speech` (#36)
  - `v1/audio/transcriptions`
  - `v1/audio/voices`
  - `v1/images/generations`
  - `v1/images/edits`
- ✅ Anthropic API supported endpoints:
  - `v1/messages`
  - `v1/messages/count_tokens`
- ✅ llama-server (llama.cpp) supported endpoints
  - `v1/rerank`, `v1/reranking`, `/rerank`
  - `/infill` - for code infilling
  - `/completion` - for completion endpoint
  - `/models` - list available models. same behavior as `v1/models`
  - `/props` - requires `?model={model_id}` query parameter to be provided. The autoload
    parameter is not supported and will be ignored.
- ✅ SDAPI via stable-diffusion.cpp's server
  - `/sdapi/v1/txt2img`
  - `/sdapi/v1/img2img`
  - `/sdapi/v1/loras` - requires `model` in request body to fetch the correct loras
- ✅ audio.cpp supported extra endpoints
  - `/audioapi/v1/tasks/run`
- ✅ `/comfyui/` - ComfyUI custom endpoint (#1001) for more reliable swapping
- ✅ llama-swap API
  - `/ui` - web UI
  - `/upstream/:model_id` - direct access to upstream server
  - `/running` - list currently running models (#61)
  - `POST /api/models/unload` - manually unload all running models (#58)
  - `POST /api/models/unload/:model_id` - unload a specific model
  - `GET /api/profiles` - list configured profiles and the active selection
  - `PUT /api/profiles/active` - activate a profile or select none
  - `/logs` - remote log monitoring
    - `GET /logs` returns buffered plain text logs.
      - If `Accept: text/html` is sent, `/logs` redirects to `/ui/`.
    - `GET /logs/stream` keeps the connection open for live log streaming.
      - Stream endpoints send buffered history first by default; add `?no-history` to stream
        only new lines.
    - `GET /logs/stream/proxy` streams proxy logs only.
    - `GET /logs/stream/upstream` streams upstream process logs only.
    - `GET /logs/stream/{model_id}` streams logs for one model (including IDs with slashes,
      like `author/model`).
  - `/health` - just returns "OK"
  - `/metrics` - system and GPU metrics for prometheus
- ✅ API Key support - define keys to restrict access to API endpoints
- ✅ Customization
  - Switch model ID routing at runtime with profiles
  - Run concurrent models with a custom DSL swap matrix (#643)
  - Automatic unloading of models after timeout by setting a `ttl`
  - Docker and Podman support using `cmd` and `cmdStop` together
  - Preload models on startup with `hooks` (#235)
  - Apply filters to requests to control inference with `stripParams`, `setParams` and
    `setParamsByID`

## Configuration

```yaml
# minimum viable config.yaml

models:
  model1:
    cmd: llama-server --port ${PORT} --model /path/to/model.gguf
```

That's all you need to get started:

1. `models` - holds all model configurations
2. `model1` - the ID used in API calls
3. `cmd` - the command to run to start the server.
4. `${PORT}` - an automatically assigned port number

Almost all configuration settings are optional and can be added one step at a time:

- Advanced features
  - `matrix` to run concurrent models with a custom swap logic DSL
  - `hooks` to run things on startup
  - `macros` reusable snippets
- Model customization
  - `ttl` to automatically unload models
  - `unloadTimeout` to tune graceful unloads (manual, API and `ttl` expiry)
  - `aliases` to use familiar model names (e.g., "gpt-4o-mini")
  - `env` to pass custom environment variables to inference servers
  - `cmdStop` gracefully stop Docker/Podman containers
  - `useModelName` to override model names sent to upstream servers
  - `${PORT}` automatic port variables for dynamic port assignment
  - `filters` rewrite parts of requests before sending to the upstream server

## How does llama-swap work?

When a request is made to an OpenAI compatible endpoint, llama-swap will extract the `model`
value and load the appropriate server configuration to serve it. If the wrong upstream server
is running, it will be replaced with the correct one. This is where the "swap" part comes in.
The upstream server is automatically swapped to handle the request correctly.

In the most basic configuration llama-swap handles one model at a time. For more advanced use
cases, using a `matrix` allows multiple models to be loaded at the same time. You have complete
control over how your system resources are used.

## Do I need to use llama.cpp's server (llama-server)?

Any OpenAI compatible server would work. llama-swap was originally designed for llama-server
and it is the best supported.

For Python based inference servers like vllm or tabbyAPI it is recommended to run them via
podman or docker. This provides clean environment isolation as well as responding correctly to
`SIGTERM` signals for proper shutdown.
