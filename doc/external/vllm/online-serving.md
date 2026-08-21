# vLLM — Online Serving

Source URL: https://docs.vllm.ai/en/latest/serving/online_serving/
Fetched: 2026-08-21 (Oxylabs `universal_scraper`, markdown output)

Why this page is saved: it is the authority for which OpenAI-compatible HTTP endpoints a
vLLM worker exposes — specifically that chat generation is `POST /v1/chat/completions` and
that the model registry is `GET /v1/models`. `anvil stress` drives exactly those two paths
through the llama-swap gateway, so the plan cites this page rather than assuming them.

---

vLLM provides an HTTP server that is compatible with many interfaces!

## OpenAI-Compatible Server

We currently support the following OpenAI APIs:

* Completions API (`/v1/completions`)
  * Only applicable to text generation models.
  * *Note: `suffix` parameter is not supported.*
* Chat Completions API (`/v1/chat/completions`)
  * Only applicable to text generation models with a chat template.
  * *Note: `user` parameter is ignored.*
  * *Note:* Setting the `parallel_tool_calls` parameter to `false` ensures vLLM only returns
    zero or one tool call per request. Setting it to `true` (the default) allows returning
    more than one tool call per request. There is no guarantee more than one tool call will
    be returned if this is set to `true`, as that behavior is model dependent and not all
    models are designed to support parallel tool calls.
* Chat Completions batch API (`/v1/chat/completions/batch`)
* Responses API (`/v1/responses`, `/v1/responses/{response_id}`, `/v1/responses/{response_id}/cancel`)
  * Only applicable to text generation models.
* Embeddings API (`/v1/embeddings`)
  * Only applicable to embedding models.
* Transcriptions API (`/v1/audio/transcriptions`)
  * Only applicable to Automatic Speech Recognition (ASR) models.
* Translation API (`/v1/audio/translations`)
  * Only applicable to Automatic Speech Recognition (ASR) models.

## Anthropic APIs

* Anthropic messages API (`/v1/messages`, `/v1/messages/count_tokens`)

## Cohere APIs

* Cohere Embed API (`/v2/embed`)
  * Compatible with Cohere's Embed API
  * Works with any embedding model, including multimodal models.
* Cohere Rerank API (`/rerank`, `/v1/rerank`, `/v2/rerank`)
  * Implements Jina AI's v1 rerank API
  * compatible with Cohere's v1 & v2 rerank APIs

## Pooling APIs

For further details on pooling models, please refer to the pooling models page.

* Classification Usages
  * Classification API (`/classify`)
  * Only applicable to classification models.
* Embedding Usages
  * Cohere Embed API (`/v2/embed`)
  * OpenAI-compatible Embeddings API (`/v1/embeddings`)
  * Only applicable to embedding models.
* Scoring Usages
  * Score API (`/score`, `/v1/score`)
  * Cohere Rerank API (`/rerank`, `/v1/rerank`, `/v2/rerank`)
  * Applicable to score models (cross-encoder, bi-encoder, late-interaction).
* Pooling API (`/pooling`)
  * Applicable to all pooling models.

## Speech to Text APIs

For further details on speech to text, please refer to the speech-to-text page.

* Transcriptions API (`/v1/audio/transcriptions`)
  * Only applicable to Automatic Speech Recognition (ASR) models.
* Translation API (`/v1/audio/translations`)
  * Only applicable to Automatic Speech Recognition (ASR) models.
* Realtime API (`/v1/realtime`)
  * Only applicable to Automatic Speech Recognition (ASR) models.

## Custom APIs

* Classification API (`/classify`)
  * Only applicable to classification models.
* Score API (`/score`, `/v1/score`)
  * Applicable to score models (cross-encoder, bi-encoder, late-interaction).
* Pooling API (`/pooling`)
  * Applicable to all pooling models.
* Generative Scoring API (`/generative_scoring`)
  * Applicable to CausalLM models (task `"generate"`).
  * Computes next-token probabilities for specified `label_token_ids`.

## Instrumentator APIs

### Basic APIs

* `/version` - Version information
* `/load` - Server load metrics
* `/v1/models` - List available models
* `/health` - Health check

### Metrics APIs

For further details on metrics, please refer to the metrics design page.

* `/metrics` - Prometheus-compatible metrics HTTP endpoint

### Offline API Documentation

The FastAPI `/docs` endpoint requires an internet connection by default. To enable offline
access in air-gapped environments, use the `--enable-offline-docs` flag:

```
vllm serve NousResearch/Meta-Llama-3-8B-Instruct --enable-offline-docs
```

### LoRA dynamic loading

LoRA dynamic loading & unloading is enabled in the API server. This should ONLY be used for
local development!

* `/v1/load_lora_adapter` - LoRA dynamic loading
* `/v1/unload_lora_adapter` - LoRA dynamic unloading

### Profiling APIs

* `/start_profile` - Start PyTorch profiler
* `/stop_profile` - Stop PyTorch profiler

### SageMaker APIs

* `/ping` - SageMaker health check
* `/invocations` - SageMaker-compatible endpoint (routes to the same inference functions as
  `/v1` endpoints)

## Scale-Out APIs

### Tokens IN <> Tokens OUT APIs

* `/inference/v1/generate` - Generate completions
* `/abort_requests` - Abort in-flight requests (only when `--tokens-only` is also set)

### Renderer APIs

* Completions Render API (`/v1/completions/render`) - Render completion requests
* Chat Completions Render API (`/v1/chat/completions/render`) - Render chat completions

### Derenderer APIs

* Chat Completions Derender API (`/v1/chat/completions/derender`)
* Completions Derender API (`/v1/completions/derender`)

## Tokenize APIs

* `/tokenize` - Tokenize text
* `/detokenize` - Detokenize tokens
* `/tokenizer_info` - Get comprehensive tokenizer information including chat templates and
  configuration

## Elastic Expert Parallelism (EEP)

* `/scale_elastic_ep` - Trigger scaling operations
* `/is_scaling_elastic_ep` - Check if scaling is in progress

## Server in development mode

When using the flag `VLLM_SERVER_DEV_MODE=1`, you enable development endpoints.

**SECURITY WARNING: These endpoints should NOT be used in production!**

### Cache Management APIs

* `/reset_prefix_cache` - Reset prefix cache (can disrupt service)
* `/reset_mm_cache` - Reset multimodal cache (can disrupt service)
* `/reset_encoder_cache` - Reset encoder cache (can disrupt service)

### Weight Transfer APIs (RL Training)

* `/pause` - Pause generation (causes denial of service)
* `/resume` - Resume generation
* `/is_paused` - Check if generation is paused
* `/abort_requests` - Abort in-flight requests (all in-flight, or the given `request_ids`)
  without pausing the scheduler
* `/init_weight_transfer_engine` - Initialize weight transfer engine for RLHF
* `/start_weight_update` - Prepares the inference engine for a weight update.
* `/update_weights` - Update model weights (can alter model behavior)
* `/finish_weight_update` - Finalizes the weight update
* `/update_weight_version` - Set the weight version without updating model weights
* `/weight_info` - Get the latest committed weight version
* `/get_world_size` - Get distributed world size

### Collective RPC

* `/collective_rpc` - Execute arbitrary RPC methods on the engine (extremely dangerous)

### Server info

* `/server_info` - Get detailed server configuration

### Sleep Mode APIs

* `/sleep` - Put engine to sleep (causes denial of service)
* `/wake_up` - Wake engine from sleep
* `/is_sleeping` - Check if engine is sleeping

## Chat Template

In order for the language model to support chat protocol, vLLM requires the model to include
a chat template in its tokenizer configuration. The chat template is a Jinja2 template that
specifies how roles, messages, and other chat-specific tokens are encoded in the input.

An example chat template for `NousResearch/Meta-Llama-3-8B-Instruct` can be found in the
Meta Llama 3 prompt-format documentation.

Some models do not provide a chat template even though they are instruction/chat fine-tuned.
For those models, you can manually specify their chat template in the `--chat-template`
parameter with the file path to the chat template, or the template in string form. Without a
chat template, the server will not be able to process chat and all chat requests will error.

```
vllm serve <model> --chat-template ./path-to-chat-template.jinja
```

vLLM community provides a set of chat templates for popular models, under the `examples`
directory of the vLLM repository.

With the inclusion of multi-modal chat APIs, the OpenAI spec now accepts chat messages in a
new format which specifies both a `type` and a `text` field. An example is provided below:

```python
completion = client.chat.completions.create(
    model="NousResearch/Meta-Llama-3-8B-Instruct",
    messages=[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Classify this sentiment: vLLM is wonderful!"},
            ],
        },
    ],
)
```

Most chat templates for LLMs expect the `content` field to be a string, but there are some
newer models like `meta-llama/Llama-Guard-3-1B` that expect the content to be formatted
according to the OpenAI schema in the request. vLLM provides best-effort support to detect
this automatically, which is logged as a string like *"Detected the chat template content
format to be..."*, and internally converts incoming requests to match the detected format,
which can be one of:

* `"string"`: A string. Example: `"Hello world"`
* `"openai"`: A list of dictionaries, similar to OpenAI schema.
  Example: `[{"type": "text", "text": "Hello world!"}]`

If the result is not what you expect, you can set the `--chat-template-content-format` CLI
argument to override which format to use.

## Ray Serve LLM

Ray Serve LLM enables scalable, production-grade serving of the vLLM engine. It integrates
tightly with vLLM and extends it with features such as auto-scaling, load balancing, and
back-pressure.

Key capabilities:

* Exposes an OpenAI-compatible HTTP API as well as a Pythonic API.
* Scales from a single GPU to a multi-node cluster without code changes.
* Provides observability and autoscaling policies through Ray dashboards and metrics.

The following example shows how to deploy a large model like DeepSeek R1 with Ray Serve LLM:
`examples/ray_serving/ray_serve_deepseek.py`.

Learn more about Ray Serve LLM with the official Ray Serve LLM documentation.

*(Page footer date: July 28, 2026)*
