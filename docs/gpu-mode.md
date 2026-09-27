> Scope: this document describes the optional simulator / live scrape configuration. The verified Dash0 replay uses the sources and metric names in [the replay guide](dash0-replay.md). DCGM was not captured in the H100 run.

# GPU Mode: Real vLLM + DCGM

Demo mode simulates the telemetry sources. GPU mode replaces the simulator
with the real engines while keeping the collector pipeline, OTLP export, and
dashboards after validating metric names and units against the chosen engine and DCGM versions.

## Requirements

- Linux host with NVIDIA GPU(s) (≥16 GB VRAM for the default Qwen2.5-7B in fp16)
- NVIDIA driver + [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- Optionally a `HUGGING_FACE_HUB_TOKEN` in `.env` for gated models

## Run

```bash
make gpu-up
# equivalent to:
# docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

What the overlay changes:

| Concern | Demo mode | GPU mode |
|---|---|---|
| Engine metrics (`vllm:*`) | simulator `:8000` | `vllm/vllm-openai` `:8000` |
| GPU metrics (`DCGM_*`) | simulator `:9400` | `dcgm-exporter` `:9400` |
| Request traces | simulator via OTLP | vLLM `--otlp-traces-endpoint=grpc://otel-collector:4317` |
| Collector, processors, OTLP exporter | identical | identical |
| Dashboards / alerts | simulator metric family | validate against engine and exporter versions |

The scrape targets are switched purely via the `VLLM_METRICS_TARGET` and
`DCGM_METRICS_TARGET` environment variables consumed by
[collector/config.yaml](../collector/config.yaml).

## Generating traffic

Any OpenAI-compatible client works against `http://<host>:8000/v1`:

```bash
make loadgen
# or:
curl http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "qwen2.5-7b-instruct",
    "messages": [{"role": "user", "content": "Explain KV-cache paging in two sentences."}]
  }'
```

For sustained load, point any load generator (`vllm bench serve`, `k6`, or
`scripts/loadgen.py`) at the same endpoint; every request shows up as a
`gen_ai.*` trace and moves the engine histograms.

## Notes

- vLLM's OTLP tracing requires the server to be started with
  `--otlp-traces-endpoint` (already set in the overlay). Depending on your
  vLLM version/image you may also need `pip install vllm[otlp]` extras baked
  into the image.
- `dcgm-exporter` needs `--cap-add SYS_ADMIN` (set in the overlay) to read
  profiling counters like `DCGM_FI_PROF_SM_ACTIVE`.
- The overlay was validated with `docker compose config`; it requires an
  NVIDIA host to actually run (the demo machine for this repo is a Mac).
