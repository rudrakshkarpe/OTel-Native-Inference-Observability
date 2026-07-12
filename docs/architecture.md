# Reference Architecture: OTel-Native LLM Inference Observability

## Design goals

1. **One standard, every signal.** All telemetry — engine metrics, GPU metrics,
   request traces — leaves the host as OpenTelemetry data through a single
   collector. No proprietary agents, no vendor formats.
2. **Identical pipeline in demo and production.** The simulator exposes the
   *exact* metric names and trace semantics of vLLM and NVIDIA DCGM, so the
   collector config, dashboards, and alert rules transfer unchanged to a real
   GPU deployment. A sales engineer can run the full demo on a laptop; a
   customer platform team can point the same config at their cluster.
3. **Tell a story, not just numbers.** The workload model injects a periodic
   saturation incident so the data supports a realistic troubleshooting
   narrative end-to-end: traffic burst → queue growth → KV-cache pressure →
   P99 TTFT spike → 429 rejections.

## Topology

```
┌──────────────────────────┐      ┌─────────────────────────┐
│  Workload simulator      │      │  OTel Collector (contrib)│
│  (or vLLM + DCGM in      │      │                         │
│   GPU mode)              │      │  receivers:             │──┐
│                          │      │   • prometheus (scrape) │  │ OTLP/gRPC
│  :8000/metrics  vllm:*   │◄─────│   • otlp (gRPC/HTTP)    │  │ (+ Bearer)
│  :9400/metrics  DCGM_*   │      │  processors:            │  ▼
│  OTLP traces  gen_ai.*   │─────►│   memory_limiter,       │  any OTLP
│                          │      │   resource, attributes, │  backend
└──────────────────────────┘      │   batch                 │  (e.g. Dash0)
                                  └─────────────────────────┘
```

## Telemetry data model

### Traces — OTel GenAI semantic conventions

One `SERVER` span per inference request, named `chat {model}`:

| Attribute | Purpose |
|---|---|
| `gen_ai.operation.name`, `gen_ai.provider.name` (+ legacy `gen_ai.system`) | Operation and engine identity |
| `gen_ai.request.model`, `gen_ai.response.model` | Requested vs. served model |
| `gen_ai.request.temperature`, `gen_ai.request.max_tokens` | Sampling parameters |
| `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens` | Per-request token accounting (cost attribution) |
| `gen_ai.response.finish_reasons` | `stop` vs `length` — truncation monitoring |
| `gen_ai.server.time_to_first_token`, `gen_ai.server.request.queue_time` | Latency decomposition on the span itself |
| `gen_ai.first_token` (span event) | Marks TTFT visually on the trace timeline |
| `http.response.status_code`, `error.type` | 200 / 429 (queue full) / 500 (engine failure) |

Why spans *and* histograms for latency: histograms give cheap percentiles for
dashboards and alerts; spans let you pivot from "P99 spiked" to the exact
outlier requests — which profile, which prompt size, queued behind what.

### Metrics — engine (vLLM names)

- Latency histograms: `vllm:time_to_first_token_seconds`,
  `vllm:inter_token_latency_seconds`, `vllm:e2e_request_latency_seconds`, and
  the phase breakdown `request_queue_time` / `request_prefill_time` /
  `request_decode_time`.
- Scheduler gauges: `vllm:num_requests_running`, `vllm:num_requests_waiting`,
  `vllm:kv_cache_usage_perc` — the leading indicators of saturation.
- Throughput counters: `vllm:prompt_tokens`, `vllm:generation_tokens`,
  `vllm:request_success`, prefix-cache hit counters.

See [metrics-catalog.md](metrics-catalog.md) for the full inventory.

### Metrics — GPU fleet (DCGM names)

`DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED/FREE`, `DCGM_FI_DEV_GPU_TEMP`,
`DCGM_FI_DEV_POWER_USAGE`, `DCGM_FI_DEV_SM_CLOCK`, `DCGM_FI_PROF_SM_ACTIVE`
labelled by `gpu`, `UUID`, `modelName`, `Hostname`.

### Resource attributes

The collector's `resource` processor stamps every signal with
`service.namespace=llm-inference`, `deployment.environment.name=demo`, and
`observability.pipeline=otel-native-llm-inference`, so one org can hold demo
and production datasets side by side and every signal is filterable by
environment.

## Collector design notes

- **`prometheus` receiver instead of per-engine OTel plugins**: vLLM and DCGM
  already expose battle-tested Prometheus endpoints; scraping them at the
  collector keeps the engines untouched and the migration path incremental.
- **`memory_limiter` first, enrichment next, `batch` last** — standard contrib
  ordering; the pipeline degrades gracefully under load instead of OOM-ing
  next to the inference engine it observes.
- **Auth via `bearertokenauth` extension** for OTLP backends that expect a
  Bearer token (Dash0's reference config uses this pattern).
- **`debug` exporter kept in every pipeline** so the telemetry stream is
  inspectable locally (`make logs`) with or without a backend account.

## The incident narrative

Every 7 minutes the simulator triggers a 90-second, 3× traffic burst
(`SCENARIO=burst`). Watch the causal chain across the dashboard:

1. `num_requests_waiting` climbs as arrivals outpace the decode batch.
2. `kv_cache_usage_perc` approaches 95%+.
3. Queue-time P95 and TTFT P99 spike together (latency decomposition shows the
   spike lives in *queueing*, not prefill/decode).
4. Once the queue bound is hit, 429-status error spans appear.
5. The burst ends; the queue drains; every signal recovers.

Ask: *"Why did P99 time-to-first-token spike at 14:32?"* — the answer is
written across correlated metrics, traces, and logs from a single OTel
pipeline. Backend UIs (including Dash0's Agent0/MCP path) can query the same
correlated data humans see on the dashboards.
