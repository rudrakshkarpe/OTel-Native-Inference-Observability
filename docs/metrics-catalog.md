> Scope: this document describes the optional simulator / live scrape configuration. The verified Dash0 replay uses the sources and metric names in [the replay guide](dash0-replay.md). DCGM was not captured in the H100 run.

# Metrics and attributes catalog

Complete inventory of signals emitted by the demo simulator (and expected from
real vLLM + DCGM in GPU mode). All three signals share `service.namespace` and
`deployment.environment.name` after the collector `resource` processor.

## Engine metrics (`vllm:*` on `:8000/metrics`)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `vllm:num_requests_running` | gauge | `model_name` | Concurrent decode-batch size |
| `vllm:num_requests_waiting` | gauge | `model_name` | Queue depth before admission |
| `vllm:kv_cache_usage_perc` | gauge | `model_name` | KV-cache fill fraction (0–1) |
| `vllm:prompt_tokens` | counter | `model_name` | Prefill tokens processed |
| `vllm:generation_tokens` | counter | `model_name` | Decode tokens produced |
| `vllm:request_success` | counter | `model_name`, `finished_reason` | Completed requests (`stop` / `length`) |
| `vllm:prefix_cache_queries` | counter | `model_name` | Prompt tokens queried against prefix cache |
| `vllm:prefix_cache_hits` | counter | `model_name` | Prompt tokens served from prefix cache |
| `vllm:time_to_first_token_seconds` | histogram | `model_name` | Queue + prefill + first decode step |
| `vllm:inter_token_latency_seconds` | histogram | `model_name` | Per-output-token latency (TPOT) |
| `vllm:e2e_request_latency_seconds` | histogram | `model_name` | Arrival to completion |
| `vllm:request_queue_time_seconds` | histogram | `model_name` | Time waiting before admission |
| `vllm:request_prefill_time_seconds` | histogram | `model_name` | Prefill phase duration |
| `vllm:request_decode_time_seconds` | histogram | `model_name` | Decode phase duration |
| `vllm:request_prompt_tokens` | histogram | `model_name` | Prefill tokens per request |
| `vllm:request_generation_tokens` | histogram | `model_name` | Output tokens per request |

Prometheus scrapes expose histogram/counter `_bucket` / `_sum` / `_count` /
`_total` suffixes as usual.

## GPU metrics (`DCGM_*` on `:9400/metrics`)

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `DCGM_FI_DEV_GPU_UTIL` | gauge | `gpu`, `UUID`, `modelName`, `Hostname` | GPU utilization % |
| `DCGM_FI_DEV_FB_USED` | gauge | same | Framebuffer used (MiB) |
| `DCGM_FI_DEV_FB_FREE` | gauge | same | Framebuffer free (MiB) |
| `DCGM_FI_DEV_GPU_TEMP` | gauge | same | Temperature °C |
| `DCGM_FI_DEV_POWER_USAGE` | gauge | same | Power draw W |
| `DCGM_FI_DEV_SM_CLOCK` | gauge | same | SM clock MHz |
| `DCGM_FI_PROF_SM_ACTIVE` | gauge | same | SM active ratio |

## Traces (`gen_ai.*` via OTLP)

One `SERVER` span per request, name `chat {model}`:

| Attribute / event | When | Purpose |
|---|---|---|
| `gen_ai.operation.name` | always | `chat` |
| `gen_ai.provider.name` / `gen_ai.system` | always | `vllm` |
| `gen_ai.request.model` | always | Requested model |
| `gen_ai.request.temperature` | always | Sampling temperature |
| `gen_ai.request.max_tokens` | always | Max generation tokens |
| `http.request.method`, `url.path` | always | `POST` `/v1/chat/completions` |
| `http.response.status_code` | always | `200` / `429` / `500` |
| `workload.profile` | always | `chat` / `rag` / `longgen` |
| `gen_ai.response.model` | 200 | Served model |
| `gen_ai.response.finish_reasons` | 200 | `stop` / `length` |
| `gen_ai.usage.input_tokens` | 200 | Prefill tokens |
| `gen_ai.usage.output_tokens` | 200 | Decode tokens |
| `gen_ai.server.time_to_first_token` | 200 | TTFT seconds |
| `gen_ai.server.request.queue_time` | 200 | Queue wait seconds |
| `gen_ai.first_token` (event) | 200 | Marks TTFT on the timeline |
| `error.type` | 429 / 500 | Status as string |

## Logs (OTLP, trace-correlated)

| Logger | Typical message | Correlation |
|---|---|---|
| `vllm.engine` | Throughput line every ~5s | Resource only |
| `vllm.engine` | Finished request … | Active span `trace_id` |
| `vllm.engine` | Aborted request (queue full) | Active span on 429 |
| `vllm.engine` | Engine error during decode | Active span on 500 |
| `vllm.engine` | Sequence group preempted … | Resource only (KV pressure) |

## Resource attributes (collector)

| Key | Value | Source |
|---|---|---|
| `service.name` | `vllm-server` (default) | Simulator / engine |
| `service.namespace` | `llm-inference` | Collector `resource` processor |
| `deployment.environment.name` | `demo` | Collector `resource` processor |
| `service.version` | simulator build id | Simulator |
