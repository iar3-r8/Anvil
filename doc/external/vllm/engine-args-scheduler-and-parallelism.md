# vLLM — Engine Arguments (scheduler, cache, parallelism and identity flags)

Source URL: https://docs.vllm.ai/en/latest/configuration/engine_args.html
Fetched: 2026-08-24 (Oxylabs `universal_scraper`, `render: html`, `output_format: md`)
Page date footer: August 24, 2026

Why this page is saved: the Anvil `config.yaml` passes vLLM engine arguments verbatim inside
each llama-swap model's `cmd`. The diagnosis of the Qwen3.8 concurrency symptom rests on what
`--max-num-seqs` actually means, and the replacement block's flags must be grounded in the
argument reference rather than recalled.

The full page documents every engine argument across ~20 config classes. Only the sections
bearing on scheduling, KV cache, parallelism and served identity are reproduced below, in
full and verbatim. The multi-modal, LoRA, speculative-decoding, offload, Mamba, observability
and compilation sections are omitted deliberately — Anvil's models use none of them.

---

## SchedulerConfig

Scheduler configuration.

#### `--max-num-batched-tokens`

> Maximum number of tokens that can be processed in a single iteration.
>
> The default value here is mainly for convenience when testing. In real usage, this should be
> set in `EngineArgs.create_engine_config`.
>
> Parse human-readable integers like '1k', '2M', etc. Including decimal values with decimal
> multipliers.
>
> ```
> Examples:
> - '1k' -> 1,000
> - '1K' -> 1,024
> - '25.6k' -> 25,600
> ```

#### `--max-num-scheduled-tokens`

> Maximum number of tokens that the scheduler may issue in a single iteration.
>
> This is usually equal to max_num_batched_tokens, but can be smaller in cases when the model
> might append tokens into the batch (such as speculative decoding). Defaults to
> max_num_batched_tokens.

#### `--max-num-seqs`

> Maximum number of sequences to be processed in a single iteration.
>
> The default value here is mainly for convenience when testing. In real usage, this should be
> set in `EngineArgs.create_engine_config`.

**Note on the absent default:** this page does *not* publish a numeric default for
`--max-num-seqs`; it defers to `EngineArgs.create_engine_config`. Any plan that needs a
specific value must therefore set it explicitly rather than rely on a documented default.

#### `--long-prefill-token-threshold`

> For chunked prefill, a request is considered long if the prompt is longer than this number of
> tokens. 0 disables the cap (default).
>
> Default: `0`

#### `--scheduling-policy`

> Possible choices: `fcfs`, `priority`
>
> The scheduling policy to use:
>
> * "fcfs" means first come first served, i.e. requests are handled in order of arrival.
> * "priority" means requests are handled based on given priority (lower value means earlier
>   handling) and time of arrival deciding any ties).
>
> Default: `fcfs`

#### `--enable-chunked-prefill`, `--no-enable-chunked-prefill`

> If True, prefill requests can be chunked based on the remaining `max_num_batched_tokens`.
>
> The default value here is mainly for convenience when testing. In real usage, this should be
> set in `EngineArgs.create_engine_config`.

#### `--scheduler-reserve-full-isl`, `--no-scheduler-reserve-full-isl`

> If True, the scheduler checks whether the full input sequence length fits in the KV cache
> before admitting a new request, rather than only checking the first chunk. Prevents
> over-admission and KV cache thrashing with chunked prefill.
>
> Default: `True`

#### `--watermark`

> Fraction of total KV cache blocks to keep free (the watermark) when admitting waiting or
> preempted requests into the running queue. This headroom helps avoid frequent KV cache
> eviction and the resulting repeated preemption of requests when GPU memory is scarce. Must be
> in the range [0.0, 1.0); 0.0 (the default) disables the watermark.
>
> Default: `0.0`

#### `--async-scheduling`, `--no-async-scheduling`

> If set to False, disable async scheduling. Async scheduling helps to avoid gaps in GPU
> utilization, leading to better latency and throughput.

#### `--stream-interval`

> The interval (or buffer size) for streaming in terms of token length. A smaller value (1)
> makes streaming smoother by sending each token immediately, while a larger value (e.g., 10)
> reduces host overhead and may increase throughput by batching multiple tokens before sending.
>
> Default: `1`

---

## CacheConfig

Configuration for the KV cache.

#### `--block-size`

> Size of a contiguous cache block in number of tokens. Accepts None (meaning "use default").
> After construction, always int.

#### `--gpu-memory-utilization`

> The fraction of GPU memory to be used for the model executor, which can range from 0 to 1. For
> example, a value of 0.5 would imply 50% GPU memory utilization. If unspecified, will use the
> default value of 0.92. This is a per-instance limit, and only applies to the current vLLM
> instance. It does not matter if you have another vLLM instance running on the same GPU. For
> example, if you have two vLLM instances running on the same GPU, you can set the GPU memory
> utilization to 0.5 for each instance.
>
> Default: `0.92`

#### `--kv-cache-memory-bytes`

> Size of KV Cache per GPU in bytes. By default, this is set to None and vllm can automatically
> infer the kv cache size based on gpu_memory_utilization. However, users may want to manually
> specify the kv cache memory size. kv_cache_memory_bytes allows more fine-grain control of how
> much memory gets used when compared with using gpu_memory_utilization. Note that
> kv_cache_memory_bytes (when not-None) ignores gpu_memory_utilization

#### `--kv-cache-dtype`

> Possible choices: `auto`, `bfloat16`, `float16`, `fp8`, `fp8_ds_mla`, `fp8_e4m3`, `fp8_e5m2`,
> `fp8_inc`, `fp8_per_token_head`, `int4_per_token_head`, `int8_per_token_head`, `nvfp4`,
> `nvfp4_4over6`, `turboquant_3bit_nc`, `turboquant_4bit_nc`, `turboquant_k3v4_nc`,
> `turboquant_k8v4`
>
> Data type for kv cache storage. If "auto", will use model data type. CUDA 11.8+ supports fp8
> (=fp8_e4m3) and fp8_e5m2. ROCm (AMD GPU) supports fp8 (=fp8_e4m3). Intel Gaudi (HPU) supports
> fp8 (using fp8_inc). Some models (namely DeepSeekV3.2) default to fp8, set to bfloat16 to use
> bfloat16 instead, this is an invalid option for models that do not default to fp8.
>
> Default: `auto`

#### `--num-gpu-blocks-override`

> Number of GPU blocks to use. This overrides the profiled `num_gpu_blocks` if specified. Does
> nothing if `None`. Used for testing preemption.

#### `--enable-prefix-caching`, `--no-enable-prefix-caching`

> Whether to enable prefix caching.

---

## ParallelConfig

Configuration for the distributed execution.

#### `--distributed-executor-backend`

> Possible choices: `external_launcher`, `mp`, `ray`, `uni`
>
> Backend to use for distributed model workers, either "ray" or "mp" (multiprocessing). If the
> product of pipeline_parallel_size and tensor_parallel_size is less than or equal to the number
> of GPUs available, "mp" will be used to keep processing on a single host. Otherwise, an error
> will be raised.

#### `--pipeline-parallel-size`, `-pp`

> Number of pipeline parallel groups.
>
> Default: `1`

#### `--tensor-parallel-size`, `-tp`

> Number of tensor parallel groups.
>
> Default: `1`

#### `--device-ids`

> Comma-separated physical GPU device IDs or UUIDs to use (e.g. --device-ids "2,3,5,7"). Avoids
> setting CUDA_VISIBLE_DEVICES, preserving full GPU topology visibility for GPU-NIC affinity and
> DeepGEMM. Note: has no effect with Ray executors; use Ray placement groups for GPU selection
> instead.

#### `--data-parallel-size`, `-dp`

> Number of data parallel groups. MoE layers will be sharded according to the product of the
> tensor, prefill-context, and data parallel sizes.
>
> Default: `1`

#### `--data-parallel-rank`, `-dpn`

> Data parallel rank of this instance. When set, enables external load balancer mode for MoE
> data-parallel deployments. **Unsupported for non-MoE models; launch independent vLLM instances
> instead.**

#### `--enable-expert-parallel`, `--no-enable-expert-parallel`, `-ep`

> Use expert parallelism instead of tensor parallelism for MoE layers.
>
> Default: `False`

#### `--disable-custom-all-reduce`, `--no-disable-custom-all-reduce`

> Disable the custom all-reduce kernel and fall back to NCCL.
>
> Default: `False`

#### `--max-parallel-loading-workers`

> Maximum number of parallel loading workers when loading model sequentially in multiple
> batches. To avoid RAM OOM when using tensor parallel and large models.

---

## ModelConfig (identity and context flags)

#### `--model`

> Name or path of the Hugging Face model to use. It is also used as the content for `model_name`
> tag in metrics output when `served_model_name` is not specified.
>
> Default: `Qwen/Qwen3-0.6B`

#### `--served-model-name`

> The model name(s) used in the API. If multiple names are provided, the server will respond to
> any of the provided names. The model name in the model field of a response will be the first
> name in this list. If not specified, the model name will be the same as the `--model`
> argument. Noted that this name(s) will also be used in `model_name` tag content of prometheus
> metrics, if multiple names provided, metrics tag will take the first one.

#### `--max-model-len`

> Model context length (prompt and output). If unspecified, will be automatically derived from
> the model config.
>
> When passing via `--max-model-len`, supports k/m/g/K/M/G in human-readable format. Examples:
>
> * 1k -> 1000
> * 1K -> 1024
> * 25.6k -> 25,600
> * -1 or 'auto' -> Automatically choose the maximum model length that fits in GPU memory. This
>   will use the model's maximum context length if it fits, otherwise it will find the largest
>   length that can be accommodated.

#### `--enforce-eager`, `--no-enforce-eager`

> Whether to always use eager-mode PyTorch. If True, we will disable CUDA graph and always
> execute the model in eager mode. If False, we will use CUDA graph and eager execution in
> hybrid for maximal performance and flexibility.
>
> Default: `False`

---

## VllmConfig (runtime performance mode)

#### `--performance-mode`

> Possible choices: `balanced`, `interactivity`, `throughput`
>
> Performance mode for runtime behavior, 'balanced' is the default. 'interactivity' favors low
> end-to-end per-request latency at small batch sizes (fine-grained CUDA graphs, latency-oriented
> kernels). 'throughput' favors aggregate tokens/sec at high concurrency (larger CUDA graphs,
> more aggressive batching, throughput-oriented kernels).
>
> Default: `balanced`

#### `--optimization-level`

> The optimization level. These levels trade startup time cost for performance, with -O0 having
> the best startup time and -O3 having the best performance. -O2 is used by default.
>
> Default: `2`

---

## StructuredOutputsConfig

#### `--reasoning-parser`

> Select the reasoning parser depending on the model that you're using. This is used to parse the
> reasoning content into OpenAI API format.
>
> Default: `""`
