# Kubernetes deployment (production-shaped)

The docker-compose demo is the 10-minute quickstart. This path runs the same
OpenTelemetry pipeline on a real Kubernetes cluster so infrastructure
monitoring (Deployments/Pods) and alerting (check rules) light up alongside
Services/Tracing — the way a customer actually runs GPU inference.

This demo ships with the [Dash0](https://www.dash0.com) Kubernetes operator as
the reference OTLP-native backend for those tiles.

## What it deploys

| Piece | Role |
|---|---|
| **Dash0 operator** (Helm, `dash0-system`) | Collects Kubernetes infrastructure metrics + pod logs, and syncs `PrometheusRule` resources into check rules |
| **vllm-simulator** Deployment | The same vLLM/DCGM-faithful simulator, now a first-class k8s workload |
| **otel-collector** Deployment | Our collector, scraping both metric ports and receiving OTLP traces/logs — identical config to the compose demo (`collector/config.yaml`) |
| **Dash0Monitoring** CR | Enables operator monitoring + rule sync for the `llm-inference` namespace |
| **PrometheusRule** (`40-check-rules.yaml`) | Four PromQL check rules (TTFT SLO, KV-cache saturation, queue backlog, GPU temp) as code |

## Prerequisites

`docker`, `k3d`, `kubectl`, `helm`, and a populated `.env` in the repo root
(`DASH0_ENDPOINT`, `DASH0_AUTH_TOKEN`, `DASH0_DATASET`). Override the Dash0 API
endpoint for your region with `DASH0_API_ENDPOINT` (default:
`https://api.europe-west4.gcp.dash0.com`).

## Run

```bash
make k8s-up       # create cluster, install operator, deploy, sync rules
make k8s-status   # pods + synced check rules
make k8s-down     # remove workloads + operator (keep cluster)
make k8s-nuke     # also delete the k3d cluster
```

## How the three tiles get populated

- **Services / Tracing** — our in-cluster collector exports the simulator's
  traces, `vllm:*`/`DCGM_*` metrics, and logs.
- **Kubernetes Monitoring** — the operator's cluster-metrics collector
  (`k8s_cluster` + kubeletstats receivers) reports every Deployment/Pod/Node.
- **Alerting / Failed checks** — the operator syncs the `PrometheusRule` into
  Dash0 check rules. They evaluate PromQL and flip to Degraded/Critical during
  the simulator's periodic saturation incident.

## Check rules as code

Each rule compares against Dash0's `$__threshold` token, with two severity
levels supplied via annotations:

```yaml
- alert: HighTimeToFirstTokenP99
  expr: histogram_quantile(0.99, sum by (le) (rate(vllm:time_to_first_token_seconds_bucket[5m]))) > $__threshold
  for: 1m
  annotations:
    dash0-threshold-degraded: "1"
    dash0-threshold-critical: "2.5"
```

Notes learned the hard way, baked into the manifests/script:
- Dash0 requires an evaluation `interval` of **at least 1 minute**.
- The operator only syncs rules in a namespace that already has an **active
  `Dash0Monitoring`** resource, so `setup.sh` applies monitoring and waits for
  it before applying the rules.

## GPU nodes without hardware (optional)

To make the cluster advertise GPU nodes for scheduling demos, add the
[fake GPU operator](https://github.com/run-ai/fake-gpu-operator). It provides
GPU node topology (and a fake DCGM exporter); this simulator still supplies the
vLLM engine metrics and `gen_ai.*` traces the operator does not model.
