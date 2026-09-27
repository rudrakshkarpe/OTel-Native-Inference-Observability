# Inference metrics in Dash0: TTFT, percentiles and throughput

The original eight-panel dashboard shows individual captured observations using rolling maxima. The **inference scorecard** adds exact p50, p90, p95 and p99 across completed requests, with sample counts and whole-scenario throughput. Both use the same real H100 capture. The scorecard is a metrics-only supplement: it never resends traces or logs.

## 1. Choose the measurement boundary

| Measurement | Source used here | What it tells you |
|---|---|---|
| Client first-content latency | `first_content_s` in the archived request index | Time until the client receives non-empty content. Includes client, network and SSH transport; an empty first SSE chunk does not count. This is the user-facing TTFT proxy. |
| Native engine TTFT | `gen_ai.latency.time_to_first_token` on the linked vLLM request span | Engine-reported first-token delay. Separate from the client's transport boundary and from response-side scheduled-to-first-token timing. |
| Client end-to-end duration | `duration_s` | Complete client request duration. The percentile population includes completed calls only. |
| Queue / prefill / decode | Native `gen_ai.latency.*` span attributes | Engine phase measurements, preserved without inventing child spans. |
| Per-request mean ITL | Response `engine_metrics.mean_itl_ms`, converted to seconds | Each request's average decode interval. Its p95 is a percentile across request means, **not** p95 of every individual token interval. |
| Per-request output speed | Response `engine_metrics.tokens_per_second` | The engine-reported rate for each request. This differs from aggregate throughput under concurrency. |
| Aggregate request throughput | Attempted or completed requests / scenario wall seconds | Arrival/completion counts over the observed scenario interval. |
| Aggregate token throughput | Completed-request input or output tokens / scenario wall seconds | Tokens accounted for in final usage over the same interval. Early-close output is unknown and excluded. |

The native span TTFT and response `time_to_first_token_ms` are distinct measurements. In this capture, the latter excludes queue admission time and must not silently replace the span value. vLLM's [per-request metrics documentation](https://docs.vllm.ai/en/v0.30.0/features/per_request_metrics/) explains the response fields and streaming usage requirement.

## 2. Rebuild and publish the recorded scorecard

First follow [Dash0 setup and replay](dash0-replay.md). Keep the generated replay directory; its manifest identifies the existing traces and timestamp shift. Use a new, empty supplement directory:

```bash
python scripts/replay/inference_metrics.py prepare \
  --archive /path/to/h100-capture \
  --replay artifacts/my-replay \
  --output artifacts/my-scorecard

python scripts/replay/collector.py up
python scripts/replay/inference_metrics.py send --output artifacts/my-scorecard
python scripts/replay/inference_metrics.py verify --output artifacts/my-scorecard
python scripts/replay/scorecard_dashboard.py \
  --replay-id my-replay --scenario queue-pressure --apply
python scripts/replay/collector.py down
```

`prepare` checks source hashes, request-index correspondence, native token usage, replay identity and the prepared trace payload hash. It writes `report.json`, `metrics.pb` and a manifest with checksums. The report contains aggregate statistics without prompt or completion content.

`send` exports only metrics and writes a journal before transmission. A timeout or partial failure must be investigated before any retry. To check eventual ingestion, rerun the read-only `verify` command; do not resend the payload. `verify` compares every expected metric name, scenario, percentile, sample count and value with Dash0's Prometheus API. The published run verified [251 statistics](evidence/inference-scorecard-verification.json).

The dashboard generator supports `baseline`, `queue-pressure`, `long-context`, `recovery`, `invalid-request`, `client-early-close` or `all` from this capture. Run it again with a different `--scenario` to create that scenario's dashboard. Without `--apply`, it only writes importable Perses JSON.

Open **Dash0 inference scorecard: queue-pressure** and set the fixed range to **2026-09-27 09:14:00–09:17:10 UTC** for the committed example. All summary points are stamped at the capture's shifted end, **09:16:46.477864 UTC**. Stat panels show the last non-missing value inside the selected window. These are fixed scenario scorecards, not a new time series of live p95 estimates. The 15-second selector limits stale sample lookback; keep the time-picker resolution fine enough to include that interval.

[Recorded results](evidence/inference-scorecard.md) · [Machine-readable report](evidence/inference-scorecard.json) · [Importable dashboard](../dashboards/perses/inference-scorecard-queue-pressure.json)

## 3. Understand p50, p90, p95 and p99

For each scenario and measurement, sort the available completed-request observations and select element `ceil(percentile / 100 × n)`, using one-based indexing. Missing values are excluded and `n` is shown. A scenario with no completed requests has no latency quantiles; it does not get a zero-latency result.

For eight requests, p90, p95 and p99 all select the largest observation. For 32 requests, p99 still selects the maximum. These are diagnostic samples, not production tail-latency guarantees. Percentiles from different metrics can belong to different requests and must not be added. Do not average scenario p95s; `all` recomputes from the underlying combined observations, and still mixes distinct workload profiles.

The scorecard uses gauges containing already-calculated percentiles. Do not apply `histogram_quantile`, `rate`, or `quantile_over_time` to those gauges. In Dash0 Query Builder, for example:

```promql
max_over_time({
  otel_metric_name="inference_lab.summary.engine_ttft",
  inference_replay_id="dash0-h100-20260927",
  inference_summary_id="inference-scorecard-v1",
  inference_scenario="queue-pressure",
  percentile="90"
}[15s])
```

Change `percentile` to `50`, `95` or `99`. The [generator](../scripts/replay/scorecard_dashboard.py) includes the exact queries for every panel. Dash0 recommends querying original OTel names through `otel_metric_name` to avoid name-normalization mistakes. [Query guidance](https://www.dash0.com/docs/dash0/telemetry/metrics/common-metric-query-issues)

## 4. Calculate throughput with the correct denominator

For each scenario:

```text
wall seconds = latest client ended_at - earliest client started_at
completed requests/s = completed request count / wall seconds
output tokens/s = sum(completed-request output tokens) / wall seconds
input tokens/s = sum(completed-request input tokens) / wall seconds
```

Do not divide aggregate tokens by the sum of request durations: overlapping requests would double-count elapsed time. Do not sum per-request engine token speeds and label the result aggregate throughput. Attempted requests/s includes rejections and early closures; completed requests/s does not.

Queue pressure completed 32 calls and 8,192 output tokens in 62.594338048 seconds: **0.5112 completed requests/s and 130.8745 output tokens/s**. Baseline completed eight calls and 1,024 output tokens in 26.109636096 seconds: **39.2192 output tokens/s**. Those scenarios differ in concurrency and output length. This is workload accounting, not a controlled hardware comparison or sustainable capacity estimate.

The `all` denominator spans the first client start through the last client end, including gaps between scenarios. Four early closures have unknown final token usage. Therefore its token throughput is the rate of **accounted completed-request tokens**, not all GPU-generated tokens.

## 5. Collect live inference metrics on the next GPU run

This path needs a running engine. It was not exercised by the replay, and no GPU is started by these instructions.

1. Use the engine version's `/metrics` endpoint. vLLM 0.30.0 exposes cumulative histograms and counters; keep a continuous scrape history from before load until after completion. [vLLM production metrics](https://docs.vllm.ai/en/v0.30.0/usage/metrics/)
2. For response-side diagnostic fields, start vLLM with `--enable-per-request-metrics` and retain the final usage chunk with `stream_options={"include_usage": True}`. Keep a monotonic client timer for first non-empty content and total duration. The original capture tools are linked from the [replay guide](dash0-replay.md#input-contract).
3. Use the Prometheus receiver in [`collector/config.yaml`](../collector/config.yaml), setting `VLLM_METRICS_TARGET` to an engine endpoint reachable **from the Collector**, and configure the Dash0 TLS endpoint/token/dataset. It currently scrapes every 15 seconds. The file also contains an optional DCGM target; if you have no DCGM exporter, remove that scrape job instead of treating it as GPU evidence.
4. In Dash0 Metrics Explorer, confirm the actual `otel_metric_name`, type, unit and `model_name` labels. The Prometheus receiver may remove `_total` from counter names while converting them to OTel sums. Adapt the selectors below to the observed names. Scope the model and serving deployment before comparing replicas.
5. In Query Builder, use histogram quantiles for live distributions and counter rates for throughput. Save successful queries to a new live dashboard. Use at least several scrape intervals per rate window; these examples use five minutes. [Dash0 PromQL guidance](https://www.dash0.com/docs/dash0/telemetry/metrics/write-effective-promql-queries)

Example native-histogram query in Dash0, once the original OTel name is confirmed:

```promql
histogram_quantile(0.90,
  sum by (model_name) (
    rate({otel_metric_name="vllm:time_to_first_token_seconds",
          otel_metric_type="histogram",
          model_name="google/gemma-4-12B-it"}[5m])
  )
)
```

Use `0.50`, `0.95` and `0.99` for the other percentiles. Change the metric to `vllm:e2e_request_latency_seconds`, `vllm:request_queue_time_seconds`, `vllm:request_prefill_time_seconds`, `vllm:request_decode_time_seconds` or `vllm:inter_token_latency_seconds` for other distributions. The last histogram measures token intervals; it has a different population from the replay's per-request mean ITL.

When selecting the original OTel histogram name, Dash0 exposes a native histogram. For a classic Prometheus `_bucket` query instead, retain `le` during aggregation:

```promql
histogram_quantile(0.90,
  sum by (le, model_name) (
    rate(vllm:time_to_first_token_seconds_bucket{
      model_name="google/gemma-4-12B-it"
    }[5m])
  )
)
```

The classic spelling above is the **engine endpoint name**. If the Collector/backend translates it, use the name shown in Dash0. Never drop `le` from classic buckets. Histogram quantiles are bucket-based estimates, unlike the exact nearest-rank calculation over our archived requests.

Counter-rate examples, assuming the confirmed OTel names have their Prometheus `_total` suffix removed:

```promql
# Completed requests/s. Inspect finished_reason before treating this as success.
sum by (model_name) (
  rate({otel_metric_name="vllm:request_success",
        otel_metric_type="sum", model_name="google/gemma-4-12B-it"}[5m])
)

# Generated output tokens/s across serving replicas.
sum by (model_name) (
  rate({otel_metric_name="vllm:generation_tokens",
        otel_metric_type="sum", model_name="google/gemma-4-12B-it"}[5m])
)

# Processed input tokens/s.
sum by (model_name) (
  rate({otel_metric_name="vllm:prompt_tokens",
        otel_metric_type="sum", model_name="google/gemma-4-12B-it"}[5m])
)
```

Take `rate` before summing across replicas so counter resets are handled per series. Add running/waiting request gauges, KV-cache occupancy and preemption counters to explain saturation, but verify their names and semantics against the running version. GPU allocated memory from `nvidia-smi` does not substitute for KV-cache occupancy.

Do not reconstruct live histograms, token-interval tails or continuous queue depth from the few archived Prometheus snapshots. This project preserves that boundary explicitly.

## Dashboard access and public evidence

[Open the hosted Dash0 scorecard](https://app.dash0.com/dashboards?org=9554a420-a7db-45da-99a8-ca786f8fa8c0&s=eJxljjGuwjAQRO-ydfzZGBIU1_8EiIpu492AJceOYpsmyt0xDRKinTczehscwGzAlClJBgMsExWfoYEp2pKEr26WC4W7gAnF-0_-X1bKLoZvtsa5nmjUvcJB6fMVB9OeDOIfIt7qa46__GzaD080L96Fe20R05LdU2Bv4MCUHmOkldPb17tUZTeIiwQweS3SgOO66bRo5pZUf-wmdaJRK7L2qMTSIL3tRrQt7Pv-Ane1S6M%3D) with the captured time range. It requires access to this Dash0 organization. On September 27, 2026, the dashboard's access panel listed Admin/Edit and Member/Read, with no anonymous public-sharing option visible. Dash0's [sharing documentation](https://www.dash0.com/docs/dash0/dashboards/control-sharing-and-access) describes grants to users, roles and teams; this project does not advertise the organization URL as public.

For reviewers without an account, the [actual dashboard screenshot](assets/dash0/inference-scorecard.png), [complete statistics](evidence/inference-scorecard.md) and [dashboard JSON](../dashboards/perses/inference-scorecard-queue-pressure.json) are public. Importing the JSON requires ingesting compatible data and adjusting the replay ID; the definition does not carry telemetry or credentials. Retention can expire the hosted data while these committed artifacts remain available.
