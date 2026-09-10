# vLLM — Optimization and Tuning

Source URL: https://docs.vllm.ai/en/latest/configuration/optimization/
Fetched: 2026-08-24 (Oxylabs `universal_scraper`, `render: html`, `output_format: md`)
Page date footer: August 20, 2026

Why this page is saved: it is vLLM's own account of *why* batching settings change behaviour
under concurrent load. Three claims in the Anvil diagnosis are cited from here — that
decreasing `max_num_seqs` reduces the number of concurrent requests in a batch, that chunked
prefill is enabled by default in V1 (so its absence from a `cmd` is not a defect), and that
tensor parallelism shards one model across GPUs rather than serving users in parallel.

Reproduced in full apart from the multi-modal caching, `fastokens`, NUMA-binding and CPU
backend sections, which bear on no Anvil model.

---

This guide covers optimization strategies and performance tuning for vLLM V1.

## Optimization Levels

vLLM provides 4 optimization levels (`-O0`, `-O1`, `-O2`, `-O3`) that allow users to trade off
startup time for performance:

* `-O0`: No optimizations. Fastest startup time, but lowest performance.
* `-O1`: Fast optimization. Simple compilation and fast fusions, and PIECEWISE cudagraphs.
* `-O2`: Default optimization. Additional compilation ranges, additional fusions,
  FULL_AND_PIECEWISE cudagraphs.
* `-O3`: Aggressive optimization. Currently equal to `-O2`, but may include additional
  time-consuming or experimental optimizations in the future.

## Faster Startup

Beyond the optimization levels, three mechanisms reduce time-to-first-token on repeated boots of
the same (model, config, hardware) combination:

* **Reuse the compile cache.** vLLM persists `torch.compile` artifacts under `VLLM_CACHE_ROOT`
  (default `~/.cache/vllm`), and the cache directory can be copied between machines or baked
  into a container image. Set `VLLM_FORCE_AOT_LOAD=1` to fail loudly instead of silently
  recompiling when the cache misses (any change to the model, config, relevant `VLLM_*`
  environment variables, torch build, or GPU model invalidates it).
* **Skip memory profiling with `--kv-cache-memory`.** On startup, vLLM logs the exact
  `--kv-cache-memory` value that reproduces the current allocation. Passing it back on the next
  boot skips the memory-profiling measurement and the CUDA-graph memory estimation pass. Note
  that this has performance implications: the KV cache is sized to exactly the given value
  instead of being measured, so a conservative value caps batch concurrency (and therefore
  throughput), while an optimistic one fails at allocation time. The value is only valid on the
  same GPU with the same initial free memory; if a boot OOMs after hardware or co-tenant
  changes, remove the flag to re-profile.
* **Serve without CUDA graphs using `--enforce-eager`.** Skips both compilation and CUDA-graph
  capture for the fastest possible startup, at the cost of steady-state decode performance.

## Preemption

Due to the autoregressive nature of transformer architecture, there are times when KV cache
space is insufficient to handle all batched requests. In such cases, vLLM can preempt requests
to free up KV cache space for other requests. Preempted requests are recomputed when sufficient
KV cache space becomes available again. When this occurs, you may see the following warning:

```
WARNING 05-09 00:49:33 scheduler.py:1057 Sequence group 0 is preempted by
PreemptionMode.RECOMPUTE mode because there is not enough KV cache space. This can affect the
end-to-end performance. Increase gpu_memory_utilization or tensor_parallel_size to provide more
KV cache memory. total_cumulative_preemption_cnt=1
```

While this mechanism ensures system robustness, preemption and recomputation can adversely
affect end-to-end latency. If you frequently encounter preemptions, consider the following
actions:

* Increase `gpu_memory_utilization`. vLLM pre-allocates GPU cache using this percentage of
  memory. By increasing utilization, you can provide more KV cache space.
* **Decrease `max_num_seqs` or `max_num_batched_tokens`. This reduces the number of concurrent
  requests in a batch, thereby requiring less KV cache space.**
* Increase `tensor_parallel_size`. This shards model weights across GPUs, allowing each GPU to
  have more memory available for KV cache. However, increasing this value may cause excessive
  synchronization overhead.
* Increase `pipeline_parallel_size`. This distributes model layers across GPUs, reducing the
  memory needed for model weights on each GPU, indirectly leaving more memory available for KV
  cache. However, increasing this value may cause latency penalties.

You can monitor the number of preemption requests through Prometheus metrics exposed by vLLM.
Additionally, you can log the cumulative number of preemption requests by setting
`disable_log_stats=False`.

In vLLM V1, the default preemption mode is `RECOMPUTE` rather than `SWAP`, as recomputation has
lower overhead in the V1 architecture.

## Chunked Prefill

Chunked prefill allows vLLM to process large prefills in smaller chunks and batch them together
with decode requests. This feature helps improve both throughput and latency by better balancing
compute-bound (prefill) and memory-bound (decode) operations.

**In V1, chunked prefill is enabled by default whenever possible.** With chunked prefill
enabled, the scheduling policy prioritizes decode requests. It batches all pending decode
requests before scheduling any prefill operations. When there are available tokens in the
`max_num_batched_tokens` budget, it schedules pending prefills. If a pending prefill request
cannot fit into `max_num_batched_tokens`, it automatically chunks it.

This policy has two benefits:

* It improves inter-token latency (ITL) and generation decode because decode requests are
  prioritized.
* It helps achieve better GPU utilization by locating compute-bound (prefill) and memory-bound
  (decode) requests to the same batch.

### Performance Tuning with Chunked Prefill

You can tune the performance by adjusting `max_num_batched_tokens`:

* Smaller values (e.g., 2048) achieve better ITL because there are fewer prefills slowing down
  decodes.
* Higher values achieve better time to first token (TTFT) as you can process more prefill tokens
  in a batch.
* **For optimal throughput, we recommend setting `max_num_batched_tokens > 8192` especially for
  smaller models on large GPUs.**
* If `max_num_batched_tokens` is the same as `max_model_len`, that's almost the equivalent to
  the V0 default scheduling policy (except that it still prioritizes decodes).

> **Warning**
>
> When chunked prefill is disabled, `max_num_batched_tokens` must be greater than
> `max_model_len`.
> In that case, if `max_num_batched_tokens < max_model_len`, vLLM may crash at server start-up.

```python
from vllm import LLM

# Set max_num_batched_tokens to tune performance
llm = LLM(model="meta-llama/Llama-3.1-8B-Instruct", max_num_batched_tokens=16384)
```

See related papers for more details (https://arxiv.org/pdf/2401.08671 or
https://arxiv.org/pdf/2308.16369).

## Parallelism Strategies

vLLM supports multiple parallelism strategies that can be combined to optimize performance
across different hardware configurations.

### Tensor Parallelism (TP)

**Tensor parallelism shards model parameters across multiple GPUs within each model layer.**
This is the most common strategy for large model inference within a single node.

**When to use:**

* When the model is too large to fit on a single GPU
* When you need to reduce memory pressure per GPU to allow more KV cache space for higher
  throughput

```python
from vllm import LLM

# Split model across 4 GPUs
llm = LLM(model="meta-llama/Llama-3.3-70B-Instruct", tensor_parallel_size=4)
```

For models that are too large to fit on a single GPU (like 70B parameter models), tensor
parallelism is essential.

### Pipeline Parallelism (PP)

Pipeline parallelism distributes model layers across multiple GPUs. Each GPU processes different
parts of the model in sequence.

**When to use:**

* When you've already maxed out efficient tensor parallelism but need to distribute the model
  further, or across nodes
* For very deep and narrow models where layer distribution is more efficient than tensor
  sharding

### Expert Parallelism (EP)

Expert parallelism is a specialized form of parallelism for Mixture of Experts (MoE) models,
where different expert networks are distributed across GPUs.

**When to use:**

* Specifically for MoE models (like DeepSeekV3, Qwen3MoE, Llama-4)
* When you want to balance the expert computation load across GPUs

Expert parallelism is enabled by setting `enable_expert_parallel=True`, which will use expert
parallelism instead of tensor parallelism for MoE layers. It will use the same degree of
parallelism as what you have set for tensor parallelism.

### Data Parallelism (DP)

**Data parallelism replicates the entire model across multiple GPU sets and processes different
batches of requests in parallel.**

**When to use:**

* When you have enough GPUs to replicate the entire model
* When you need to scale throughput rather than model size
* In multi-user environments where isolation between request batches is beneficial

Data parallelism can be combined with the other parallelism strategies and is set by
`data_parallel_size=N`. Note that MoE layers will be sharded according to the product of the
tensor parallel size and data parallel size.

## CPU Resources for GPU Deployments

vLLM V1 uses a multi-process architecture where each process requires CPU resources.
Underprovisioning CPU cores is a common source of performance degradation, especially in
virtualized environments.

### Minimum CPU Requirements

For a deployment with `N` GPUs, there are at minimum:

* **1 API server process** — handles HTTP requests, tokenization, and input processing
* **1 engine core process** — runs the scheduler and coordinates GPU workers
* **N GPU worker processes** — one per GPU, executes model forward passes

This means there are always at least **`2 + N` processes** competing for CPU time.

> **Warning**
>
> Using fewer physical CPU cores than processes will cause contention and significantly degrade
> throughput and latency. The engine core process runs a busy loop and is particularly sensitive
> to CPU starvation.

The minimum is `2 + N` physical cores (1 for the API server, 1 for the engine core, and 1 per
GPU worker). In practice, allocating more cores improves performance because the OS, PyTorch
background threads, and other system processes also need CPU time.

> **Important**
>
> Please note we are referring to **physical CPU cores** here. If your system has hyperthreading
> enabled, then 1 vCPU = 1 hyperthread = 1/2 physical CPU core, so you need `2 x (2 + N)` minimum
> vCPUs.

### Performance Impact

CPU underprovisioning particularly impacts:

* **Input processing throughput** — tokenization, chat template rendering, and multi-modal data
  loading all run on CPU
* **Scheduling latency** — the engine core scheduler runs on CPU and directly affects how
  quickly new tokens are dispatched to the GPU workers
* **Output processing** — detokenization, networking, and especially streaming token responses
  use CPU cycles

If you observe that GPU utilization is lower than expected, CPU contention may be the
bottleneck. Increasing the number of available CPU cores and even the clock speed can
significantly improve end-to-end performance.

## Input Processing — Parallel Processing

You can run input processing in parallel via API server scale-out. This is useful when input
processing (which is run inside the API server) becomes a bottleneck compared to model execution
(which is run inside engine core) and you have excess CPU capacity.

```
# Run 4 API processes and 1 engine core process
vllm serve Qwen/Qwen2.5-VL-3B-Instruct --api-server-count 4

# Run 4 API processes and 2 engine core processes
vllm serve Qwen/Qwen2.5-VL-3B-Instruct --api-server-count 4 -dp 2
```

> **Note**
>
> API server scale-out is only available for online inference.
