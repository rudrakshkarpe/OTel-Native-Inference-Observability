# LLM Inference Observatory — OpenTelemetry-native, on Dash0

**A reference architecture and reusable POC template for observing GPU LLM
inference workloads (vLLM + NVIDIA DCGM) with a single OpenTelemetry
pipeline, shipping to [Dash0](https://www.dash0.com).**

One standard, every signal: engine metrics, GPU fleet metrics, and per-request
traces following the [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
flow through one OpenTelemetry Collector into Dash0 — no proprietary agents,
no vendor formats, dashboards as code.

<p align="center">
  <img src="docs/diagrams/reference-architecture.svg" alt="Reference architecture: vLLM + DCGM → one OpenTelemetry Collector → Dash0" width="960">
</p>

## The problem

GPU inference is the fastest-growing telemetry source in most platform estates,
and its failure modes are unusual: saturation shows up as queue growth and
KV-cache pressure long before GPU utilization looks alarming, and the
user-facing SLI (time to first token) is a *composition* of queueing, prefill,
and decode. In practice that telemetry ends up scattered across tools with no
shared data model — so when latency spikes, there's no way to pivot from the
symptom to the request that caused it.

<p align="center">
  <img src="docs/diagrams/problem.svg" alt="The problem: GPU inference telemetry lives in silos" width="960">
</p>

This repo models all of it in OpenTelemetry natively — one pipeline, one data
model, every signal correlated — and doubles as a demo environment that runs on
any laptop, because the telemetry sources are simulated with full fidelity.

<p align="center">
  <img src="docs/diagrams/incident-correlation.svg" alt="The payoff: one incident across metrics, traces and logs, correlated by trace_id" width="960">
</p>

## Quickstart (10 minutes, no GPU required)

```bash
git clone <this-repo> && cd llm-inference-observatory-dash0

# 1. Connect your Dash0 org (free trial works):
#    app.dash0.com → Settings → Endpoints (OTLP/gRPC) + Auth Tokens
cp .env.example .env   # paste DASH0_ENDPOINT and DASH0_AUTH_TOKEN

# 2. Launch
make up                # docker compose up -d --build

# 3. Watch data arrive in Dash0 (traces + metrics within ~30s),
#    or inspect the stream locally without any account:
make logs              # collector debug exporter
make validate          # compose check + sample scraped metrics
```

No Dash0 token yet? Everything still runs — the collector's `debug` exporter
prints the full telemetry stream locally while the Dash0 exporter retries.

Then import [`dashboards/perses/llm-inference-overview.json`](dashboards/perses/llm-inference-overview.json)
— a [Perses](https://perses.dev)-format dashboard kept in git, deployable
through a release pipeline rather than built by hand in a UI.

## What you'll see

The simulated workload is a small queueing model, not random noise:

- **Poisson arrivals** over a sped-up diurnal curve, with a realistic traffic
  mix (short chat / long-prompt RAG / long generations → distinct token
  distributions).
- **A bounded decode batch**, so queue depth drives time-to-first-token
  exactly as it does in a real engine; inter-token latency degrades with
  batch size.
- **A saturation incident every ~7 minutes**: a 90-second 3× burst. Queue
  climbs → KV-cache hits ~95% → P99 TTFT spikes → 429-status error spans
  appear — then it drains and recovers.

That last part is the demo script: open Dash0 and ask *"why did P99
time-to-first-token spike five minutes ago?"* The answer is written across
correlated metrics and traces from one pipeline — queue-time histograms, KV
cache pressure, and the individual rejected requests as `gen_ai.*` spans.

## Telemetry data model

| Signal | Convention | Examples |
|---|---|---|
| Request traces | OTel GenAI semconv | `gen_ai.usage.input_tokens`, `gen_ai.server.time_to_first_token`, `gen_ai.response.finish_reasons`, TTFT span event |
| Engine metrics | vLLM Prometheus names | `vllm:time_to_first_token_seconds`, `vllm:num_requests_waiting`, `vllm:kv_cache_usage_perc` |
| GPU metrics | DCGM exporter names | `DCGM_FI_DEV_GPU_UTIL`, `DCGM_FI_DEV_FB_USED`, `DCGM_FI_DEV_POWER_USAGE` |
| Logs | OTLP logs, trace-correlated | vLLM-style engine throughput lines, per-request outcomes, preemption warnings; each request log carries its `trace_id` for log→trace pivot |
| Resources | OTel resource semconv | `service.namespace=llm-inference`, `deployment.environment.name=demo` |

All three signals share one resource and one collector pipeline, so a 429
log line links straight to its trace, which links to the metrics for the same
window — the full "one standard, every signal" story.

Full rationale in [docs/architecture.md](docs/architecture.md).

## Demo mode vs GPU mode

The collector config, data model, and dashboards are **identical** in both
modes — only the scrape targets change.

| | Demo mode (`make up`) | GPU mode (`make gpu-up`) |
|---|---|---|
| Engine metrics | simulator, vLLM-exact names | real `vllm/vllm-openai` |
| GPU metrics | simulator, DCGM-exact names | real `dcgm-exporter` |
| Traces | simulator, GenAI semconv | vLLM `--otlp-traces-endpoint` |
| Hardware | any laptop | NVIDIA host |

GPU mode details: [docs/gpu-mode.md](docs/gpu-mode.md).

## Production-shaped Kubernetes deployment

`docker compose up` is the quickstart. For the full picture — where Dash0's
**Kubernetes Monitoring** (Deployments/Pods) and **Alerting** (check rules)
light up next to Services/Tracing — deploy onto a local k3d cluster with the
Dash0 operator:

```bash
make k8s-up      # k3d cluster + Dash0 operator + workloads + check rules
make k8s-status
make k8s-nuke    # tear it all down
```

This installs the Dash0 Kubernetes operator (infrastructure monitoring + pod
logs), runs the simulator and collector as k8s workloads, and ships four
**check rules as code** (`PrometheusRule` → Dash0 check rules) that trip during
the saturation incident. Full details: [k8s/README.md](k8s/README.md).

## Repo layout

```
collector/config.yaml        one collector pipeline for both modes
simulator/                   vLLM+DCGM-faithful workload simulator
docker-compose.yml           demo mode
docker-compose.gpu.yml       GPU overlay (real vLLM + dcgm-exporter)
k8s/                         production-shaped k3d deployment + check rules
dashboards/perses/           dashboards as code (Perses spec)
docs/                        architecture & GPU-mode guides
```

## Roadmap

- Query the incident through Dash0's MCP server from an AI agent
  ("agents query the same data as humans")
- Add the [fake GPU operator](https://github.com/run-ai/fake-gpu-operator) to
  the k8s deployment for simulated GPU node topology (scheduling demos); this
  simulator still supplies the vLLM engine metrics and `gen_ai.*` traces the
  operator does not model.
- Manage check rules and dashboards via the Dash0 Terraform provider as an
  alternative to the operator
