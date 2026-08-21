# vLLM — Troubleshooting

Source URL: https://docs.vllm.ai/en/latest/usage/troubleshooting/
Fetched: 2026-08-21 (Oxylabs `universal_scraper`, markdown output)

Why this page is saved: it is the closest vendor statement to the issue's "report any fails
(e.g. OOMs)" requirement. Note what it does and does **not** say. It documents that a model
too large for the GPU produces an out-of-memory (OOM) error, and it names
`EngineDeadError` / `EngineCore encountered an issue` as the shape of an engine-level
failure surfaced to the client. It does **not** publish a stable machine-readable error
code, `error.type` value or HTTP status for a per-request OOM. The plan therefore treats OOM
detection as a best-effort textual classification of whatever the gateway returns, and
records that limitation explicitly rather than asserting a schema this page does not define.

---

This document outlines some troubleshooting strategies you can consider. If you think you've
discovered a bug, please search existing issues first to see if it has already been reported.
If not, please file a new issue, providing as much relevant information as possible.

> Note: Once you've debugged a problem, remember to turn off any debugging environment
> variables defined, or simply start a new shell to avoid being affected by lingering
> debugging settings. Otherwise, the system might be slow with debugging functionalities left
> activated.

## Hangs downloading a model

If the model isn't already downloaded to disk, vLLM will download it from the internet which
can take time and depend on your internet connection. It's recommended to download the model
first using the `huggingface-cli` and passing the local path to the model to vLLM. This way,
you can isolate the issue.

## Hangs loading a model from disk

If the model is large, it can take a long time to load it from disk. Pay attention to where
you store the model. Some clusters have shared filesystems across nodes, e.g. a distributed
filesystem or a network filesystem, which can be slow. It'd be better to store the model in a
local disk. Additionally, have a look at the CPU memory usage, when the model is too large it
might take a lot of CPU memory, slowing down the operating system because it needs to
frequently swap between disk and memory.

> Note: To isolate the model downloading and loading issue, you can use the
> `--load-format dummy` argument to skip loading the model weights. This way, you can check
> if the model downloading and loading is the bottleneck.

## Out of memory

If the model is too large to fit in a single GPU, you will get an out-of-memory (OOM) error.
Consider adopting the memory-conserving options to reduce the memory consumption.

## Generation quality changed

In v0.8.0, the source of default sampling parameters was changed in Pull Request #12622.
Prior to v0.8.0, the default sampling parameters came from vLLM's set of neutral defaults.
From v0.8.0 onwards, the default sampling parameters come from the `generation_config.json`
provided by the model creator.

In most cases, this should lead to higher quality responses, because the model creator is
likely to know which sampling parameters are best for their model. However, in some cases the
defaults provided by the model creator can lead to degraded performance.

You can check if this is happening by trying the old defaults with `--generation-config vllm`
for online and `generation_config="vllm"` for offline. If, after trying this, your generation
quality improves we would recommend continuing to use the vLLM defaults and petition the model
creator on https://huggingface.co to update their default `generation_config.json` so that it
produces better quality generations.

## Enable more logging

If other strategies don't solve the problem, it's likely that the vLLM instance is stuck
somewhere. You can use the following environment variables to help debug the issue:

* `export VLLM_LOGGING_LEVEL=DEBUG` to turn on more logging.
* `export VLLM_LOG_STATS_INTERVAL=1.` to get log statistics more frequently for tracking
  running queue, waiting queue and cache hit states.
* `export CUDA_LAUNCH_BLOCKING=1` to identify which CUDA kernel is causing the problem.
* `export NCCL_DEBUG=TRACE` to turn on more logging for NCCL.
* `export VLLM_TRACE_FUNCTION=1` to record all function calls for inspection in the log files
  to tell which function crashes or hangs. (WARNING: This flag will slow down the token
  generation by **over 100x**. Do not use unless absolutely needed.)

## Breakpoints

Setting normal `pdb` breakpoints may not work in vLLM's codebase if they are executed in a
subprocess. You will experience something like:

```
  File ".../bdb.py", line 100, in trace_dispatch
    return self.dispatch_line(frame)
  File ".../bdb.py", line 125, in dispatch_line
    if self.quitting: raise BdbQuit
bdb.BdbQuit
```

One solution is using forked-pdb. Install with `pip install fpdb` and set a breakpoint with
something like:

```python
__import__('fpdb').ForkedPdb().set_trace()
```

Another option is to disable multiprocessing entirely, with the
`VLLM_ENABLE_V1_MULTIPROCESSING` environment variable. This keeps the scheduler in the same
process, so you can use stock `pdb` breakpoints:

```python
import os
os.environ["VLLM_ENABLE_V1_MULTIPROCESSING"] = "0"
```

## Incorrect network setup

The vLLM instance cannot get the correct IP address if you have a complicated network config.
You can find a log such as
`DEBUG 06-10 21:32:17 parallel_state.py:88] world_size=8 rank=0 local_rank=0 distributed_init_method=tcp://xxx.xxx.xxx.xxx:54641 backend=nccl`
and the IP address should be the correct one. If it's not, override the IP address using the
environment variable `export VLLM_HOST_IP=<your_ip_address>`.

You might also need to set `export NCCL_SOCKET_IFNAME=<your_network_interface>` and
`export GLOO_SOCKET_IFNAME=<your_network_interface>` to specify the network interface for the
IP address.

## Error near `self.graph.replay()`

If vLLM crashes and the error trace captures it somewhere around `self.graph.replay()` in
`vllm/worker/model_runner.py`, it is a CUDA error inside CUDAGraph. To identify the particular
CUDA operation that causes the error, you can add `--enforce-eager` to the command line, or
`enforce_eager=True` to the `LLM` class to disable the CUDAGraph optimization and isolate the
exact CUDA operation that causes the error.

## Incorrect hardware/driver

If GPU/CPU communication cannot be established, vLLM documents a PyTorch NCCL/GLOO sanity
script to confirm whether the GPU/CPU communication is working correctly, run under
`torchrun` with `NCCL_DEBUG=TRACE`. If the test script hangs or crashes, usually it means the
hardware/drivers are broken in some sense. As a common workaround, you can try to tune some
NCCL environment variables, such as `export NCCL_P2P_DISABLE=1`.

## Python multiprocessing

### `RuntimeError` Exception

If you have seen a warning in your logs like this:

```
WARNING 12-11 14:50:37 multiproc_worker_utils.py:281] CUDA was previously
    initialized. We must use the `spawn` multiprocessing start method. Setting
    VLLM_WORKER_MULTIPROC_METHOD to 'spawn'.
```

then you must update your Python code to guard usage of `vllm` behind an
`if __name__ == '__main__':` block.

## `torch.compile` Error

vLLM heavily depends on `torch.compile` to optimize the model for better performance, which
introduces the dependency on the `torch.compile` functionality and the `triton` library. If it
raises errors from the `torch/_inductor` directory, usually it means you have a custom
`triton` library that is not compatible with the version of PyTorch you are using.

## Model failed to be inspected

If you see an error like:

```
  File "vllm/model_executor/models/registry.py", line xxx, in _raise_for_unsupported
    raise ValueError(
ValueError: Model architectures ['<arch>'] failed to be inspected. Please check the logs for more details.
```

It means that vLLM failed to import the model file. Usually, it is related to missing
dependencies or outdated binaries in the vLLM build.

## Model not supported

If you see an error like:

```
TypeError: 'NoneType' object is not iterable
```

or:

```
ValueError: Model architectures ['<arch>'] are not supported for now. Supported architectures: [...]
```

But you are sure that the model is in the list of supported models, there may be some issue
with vLLM's model resolution.

## Failed to infer device type

If you see an error like `RuntimeError: Failed to infer device type`, it means that vLLM failed
to infer the device type of the runtime environment.

## NCCL error: unhandled system error during `ncclCommInitRank`

If your serving workload uses GPUDirect RDMA for distributed serving across multiple nodes and
encounters an error during `ncclCommInitRank`, with no clear error message even with
`NCCL_DEBUG=INFO` set, it might look like this:

```
Error executing method 'init_device'. This might cause deadlock in distributed execution.
...
 RuntimeError: NCCL error: unhandled system error (run with NCCL_DEBUG=INFO for details)
```

This indicates vLLM failed to initialize the NCCL communicator, possibly due to a missing
`IPC_LOCK` linux capability or an unmounted `/dev/shm`.

## CUDA error: the provided PTX was compiled with an unsupported toolchain

If you see an error like
`RuntimeError: CUDA error: the provided PTX was compiled with an unsupported toolchain`, it
means that the CUDA PTX in vLLM's wheels was compiled with a toolchain unsupported by your
system. This section also applies if you get the error
`RuntimeError: The NVIDIA driver on your system is too old`.

If you are using the vLLM official Docker image, you can solve this by adding
`-e VLLM_ENABLE_CUDA_COMPATIBILITY=1` to your `docker run` command.

## ptxas fatal: Value 'sm_110a' is not defined for option 'gpu-name'

If you use triton kernels with cuda 13, you might see an error like
`ptxas fatal: Value 'sm_110a' is not defined for option 'gpu-name'`:

```
(EngineCore_0 pid=9492) triton.runtime.errors.PTXASError: PTXAS error: Internal Triton PTX codegen error
(EngineCore_0 pid=9492) `ptxas` stderr:
(EngineCore_0 pid=9492) ptxas fatal   : Value 'sm_110a' is not defined for option 'gpu-name'
...
  File ".../vllm/v1/engine/core_client.py", line 668, in get_output
    raise self._format_exception(outputs) from None
vllm.v1.engine.exceptions.EngineDeadError: EngineCore encountered an issue. See stack trace (above) for the root cause.
```

It means that the ptxas in the triton bundle is not compatible with your device. You need to
set the `TRITON_PTXAS_PATH` environment variable to use the cuda toolkit's ptxas manually.

## Known Issues

* In `v0.5.2`, `v0.5.3`, and `v0.5.3.post1`, there is a bug caused by zmq, which can
  occasionally cause vLLM to hang depending on the machine configuration. The solution is to
  upgrade to the latest version of `vllm`.
* To address a memory overhead issue in older NCCL versions, vLLM versions
  `>= 0.4.3, <= 0.10.1.1` would set the environment variable `NCCL_CUMEM_ENABLE=0`. External
  processes connecting to vLLM also needed to set this variable to prevent hangs or crashes.
  Since the underlying NCCL bug was fixed in NCCL 2.22.3, this override was removed in newer
  vLLM versions.
* In some PCIe machines (e.g. machines without NVLink), if you see an error like
  `transport/shm.cc:590 NCCL WARN Cuda failure 217 'peer access is not supported between these two devices'`,
  it's likely caused by a driver bug. In that case, you can try to set
  `NCCL_CUMEM_HOST_ENABLE=0` to disable the feature, or upgrade your driver.

*(Page footer date: March 12, 2026)*
