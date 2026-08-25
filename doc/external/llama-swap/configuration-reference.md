# llama-swap — configuration reference (model identity, concurrency, matrix routing)

Source URLs:
- https://github.com/mostlygeek/llama-swap/blob/main/docs/configuration.md
- https://github.com/mostlygeek/llama-swap/blob/main/config.example.yaml

Fetched: 2026-08-24 (GitHub MCP `get_file_contents`, `mostlygeek/llama-swap`, branch `main`)

Why this page is saved: Anvil's `config.yaml` *is* a llama-swap configuration file. Adding a
second model block for an already-served model raises three questions that must be answered
from the vendor's own reference rather than assumed:

1. **What the model key means** — it is the ID used in API requests, so a second block needs a
   second, distinct key, and that key is what `anvil stress <model-id>` must name.
2. **How a gateway ID that differs from the upstream model name is handled** — llama-swap's own
   vLLM example passes `--served-model-name` matching the gateway key, and `useModelName`
   exists for the reverse case. This is the fact that makes a distinct gateway ID safe for a
   model whose Hugging Face path is unchanged.
3. **How concurrent requests to one model are limited at the gateway** — `concurrencyLimit`
   caps in-flight requests per model and returns HTTP 429 beyond it. A stress test that sees
   429s must be able to tell a gateway cap from a vLLM scheduler queue.

Also reproduced: `matrix` solver semantics (a model in no set runs alone) and the `hooks`
`preload` contract, both of which bear on whether the new block must join `matrix.sets` and
`hooks.on_startup.preload`.

---

## From `docs/configuration.md`

### minimal viable config

```yaml
models:
  model1:
    cmd: llama-server --port ${PORT} --model /path/to/model.gguf
```

This is enough to launch `llama-server` to serve `model1`. Of course, llama-swap is about making
it possible to serve many models:

```yaml
models:
  model1:
    cmd: llama-server --port ${PORT} -m /path/to/model.gguf
  model2:
    cmd: llama-server --port ${PORT} -m /path/to/another_model.gguf
  model3:
    cmd: llama-server --port ${PORT} -m /path/to/third_model.gguf
```

With this configuration models will be hot swapped and loaded on demand. The special `${PORT}`
macro provides a unique port per model which is useful if you want to run multiple models at the
same time with the `matrix` feature.

### Support for any OpenAI API compatible server

llama-swap supports any OpenAI API compatible server. If you can run it on the CLI llama-swap
will be able to manage it. Even if it's run in Docker or Podman containers.

```yaml
models:
  "Q3-30B-CODER-VLLM":
    name: "Qwen3 30B Coder vllm AWQ (Q3-30B-CODER-VLLM)"
    # cmdStop provides a reliable way to stop containers
    cmdStop: docker stop vllm-coder
    cmd: |
      docker run --init --rm --name vllm-coder
        --runtime=nvidia --gpus '"device=2,3"'
        --shm-size=16g
        -v /mnt/nvme/vllm-cache:/root/.cache
        -v /mnt/ssd-extra/models:/models -p ${PORT}:8000
        vllm/vllm-openai:v0.10.0
        --model "/models/cpatonn/Qwen3-Coder-30B-A3B-Instruct-AWQ"
        --served-model-name "Q3-30B-CODER-VLLM"
        --enable-expert-parallel
        --swap-space 16
        --max-num-seqs 512
        --max-model-len 65536
        --max-seq-len-to-capture 65536
        --gpu-memory-utilization 0.9
        --tensor-parallel-size 2
        --trust-remote-code
```

**Note:** in the vendor's own vLLM example the gateway model key (`Q3-30B-CODER-VLLM`) differs
from the Hugging Face path, and the example passes `--served-model-name` set to the gateway key.
The same example uses `--max-num-seqs 512`.

---

## From `config.example.yaml`

### models

> models: a dictionary of model configurations
> - required
> - **each key is the model's ID, used in API requests**
> - model settings have default values that are used if they are not defined here
> - the model's ID is available in the `${MODEL_ID}` macro, also available in macros defined above

### `cmd`

> cmd: the command to run to start the inference server.
> - required
> - it is just a string, similar to what you would run on the CLI
> - using `|` allows for comments in the command, these will be parsed out
> - macros can be used within cmd

### `proxy`

> proxy: the URL where llama-swap routes API requests
> - optional, default: `http://localhost:${PORT}`
> - if you used `${PORT}` in cmd this can be omitted
> - if you use a custom port in cmd this *must* be set

### `checkEndpoint`

> checkEndpoint: URL path to check if the server is ready
> - optional, default: `/health`
> - endpoint is expected to return an HTTP 200 response
> - all requests wait until the endpoint is ready or fails
> - use "none" to skip endpoint health checking

### `useModelName`

> useModelName: override the model name that is sent to upstream server
> - optional, default: ""
> - **useful for when the upstream server expects a specific model name that is different from
>   the model's ID**

### `unlisted`

> unlisted: boolean, true or false
> - optional, default: false
> - **unlisted models do not show up in `/v1/models` api requests**
> - can be requested as normal through all apis

### `concurrencyLimit`

> concurrencyLimit: overrides the allowed number of active parallel requests to a model
> - optional, default: 0
> - useful for limiting the number of active parallel requests a model can process
> - must be set per model
> - **any number greater than 0 will override the internal default value of 10**
> - **any requests that exceeds the limit will receive an HTTP 429 Too Many Requests response**
> - recommended to be omitted and the default used

### `ttl`

> ttl: automatically unload the model after ttl seconds
> - optional, default: -1 (use global default)
> - ttl values must be a value greater than or equal to 0
> - a ttl of -1 will use the global TTL value as the default
> - a ttl of 0 will mean never unload

### `aliases`

> aliases: alternative model names that this model configuration is used for
> - optional, default: empty array
> - aliases must be unique globally
> - useful for impersonating a specific model

### `env`

> env: define an array of environment variables to inject into cmd's environment
> - optional, default: empty array
> - each value is a single string
> - in the format: `ENV_NAME=value`
>
> ```yaml
> env:
>   - "CUDA_VISIBLE_DEVICES=0,1,2"
> ```

### hooks / preload

> hooks: a dictionary of event triggers and actions
> - optional, default: empty dictionary
> - the only supported hook is `on_startup`
>
> on_startup:
> - preload: a list of model ids to load on startup
>   - optional, default: empty list
>   - **model names must match keys in the models sections**
>   - when preloading multiple models at once, define a group otherwise models will be loaded and
>     swapped out

### matrix routing

> The matrix lists the model combinations that are allowed to run concurrently. When a model is
> requested, the solver makes room for it by evicting as few running models as possible,
> preferring to keep the costliest ones loaded.
>
> Solver behaviour:
>   1. A request arrives for model X.
>   2. If X is already running, forward the request. Done.
>   3. Collect every set that contains X.
>   4. For each set, add up the `evict_costs` of the running models that are NOT in that set —
>      that is the set's cost.
>   5. Choose the lowest-cost set. Break ties by definition order.
>   6. Evict the models outside that set, start X, forward the request.
>
> Subset semantics: a set `[a, b, c]` also permits any subset of itself. Only the requested model
> is started; the others are not preloaded.
>
> **A model that appears in no set can only run on its own.**

> vars: optional aliases for model IDs
> - names may contain alphanumeric, "-", or "." characters (1-32 chars)
> - **map each short name to a real model ID (not a model alias)**
> - keeps the set expressions short and readable
> - sets and evict_costs may mix vars with real model IDs
> - a var takes precedence when its name is also a real model ID

> evict_costs: relative cost of losing a running model (default: 1)

### scheduler

> scheduler: how queued requests are ordered.
> The default and only valid scheduler is "fifo"
