# Dash0 setup and replay

## Prerequisites and credential handling

Use Python 3.12, Docker Compose and an existing Dash0 organization. Copy the **regional** OTLP/gRPC and API endpoints from that organization's integration instructions. Ingestion requires an ingest token. Hosted verification requires telemetry read access; dashboard apply requires dashboard write access. Do not expand permissions merely to ingest traces. If a token cannot write dashboards, generate the JSON without `--apply` and have an authorized user import it.

The commands in the README use environment variables. Alternatively create `.secrets/dash0.json` locally, excluded from Git, with mode 600 and its directory mode 700:

```json
{
  "token": "YOUR_EXISTING_TOKEN",
  "grpc_endpoint": "YOUR_REGIONAL_GRPC_HOST:4317",
  "api_url": "https://YOUR_REGIONAL_API_HOST",
  "dataset": "default"
}
```

Environment values override file values. `collector.py` passes credentials to Docker through its environment and does not put them in shell command arguments. Anyone with access to your Docker daemon can inspect container environment variables; keep this local setup on a trusted machine. No token, receipt response containing account metadata, or raw private archive belongs in a commit.

## Input contract

The replay expects the archive format produced by the [real capture workflow](https://github.com/rudrakshkarpe/logfire-inference-lab/tree/cfcfc210ce790e72a29d634f9c80cbd6b95bf8ad/scripts/gpu):

```text
capture/
  SHA256SUMS.json                 # relative file name -> SHA-256 hex digest
  otlp/*.pb                      # ExportTraceServiceRequest protobuf batches
  workload/manifest.json         # plans, capture_id, started_at, ended_at
  workload/request-index.json    # trace/span IDs, outcomes, measurements, final usage
  workload/<scenario>-requests.jsonl
  remote/gpu-metrics.csv          # timestamped nvidia-smi samples, UTC in this capture
```

The checksum manifest and archive must come from a trusted capture. Checksums detect modifications; they do not authenticate an untrusted third party. Do not use generic protobuf JSON as OTLP/JSON: its base64 ID representation is not the OTLP/JSON wire format. This pipeline uses protobuf for export.

`prepare` verifies every consumed file, validates request/index correspondence and completed-request native token usage, and writes into a fresh output directory. The source archive stays unchanged. The generated `manifest.json` records counts, source/timestamp windows, original-to-replay trace IDs and checksums of the three export payloads.

## Import and verify

Follow the README commands. `collector.py up` starts only the `inference-evidence-replay` Compose project and binds port 24318 on loopback. It does not touch existing simulator or Kubernetes containers.

`send` makes one explicit POST per signal. It validates all three prepared hashes before the first POST. It writes an attempt journal before transmission and accepts only OTLP responses without partial rejection. A timeout may happen after the Collector accepts data, so the tool refuses a second send when a journal exists. Investigate the journal and hosted data before deciding how to recover; do not delete receipts and retry blindly.

`verify_dash0.py` is read-only. It uses the replay's fixed window and IDs, not an unrestricted account-wide search. If it reports missing records shortly after ingestion, allow ingestion to complete and rerun verification. Do not resend. HTTP 200 from a Collector is not evidence that a backend stored every record.

`dashboard.py --apply` upserts a replay dashboard in the configured dataset. Reapplying intentionally changes that dashboard's replay filter; it does not import the data again. Omitting `--apply` only writes the Perses JSON. The dashboard is API-managed and appears read-only in the UI; edit the source and reapply.

Stop the Collector with `collector.py down` after successful verification. The dashboard and ingested data stay in Dash0 according to your account's retention. Keep the source archive, replay manifest and verification output for reproducibility.

## Finding this recorded run

The screenshot replay is `dash0-h100-20260927`. Use a fixed range of **2026-09-27 09:14:00 to 09:17:10 UTC**, or **02:14:00 to 02:17:10 America/Los_Angeles** as shown in the dashboard images. Filter `inference.replay.id` in Logs and Tracing. The six remapped trace IDs are in [the manifest](evidence/dash0-manifest.json).

Use the fixed range when opening saved data later. Built-in views may reset to a relative range, and dashboard data will appear empty once the replay falls outside it or account retention expires. The committed screenshots are the durable visual evidence.

## Metric queries

```promql
max_over_time(inference_lab_engine_queue_seconds{
  inference_replay_id="dash0-h100-20260927"
}[15s])
```

| OTel name | Dash0 Prometheus name | Source |
|---|---|---|
| `inference_lab.request.first_content` | `inference_lab_request_first_content_seconds` | Client clock |
| `inference_lab.request.duration` | `inference_lab_request_duration_seconds` | Client clock |
| `inference_lab.engine.queue` | `inference_lab_engine_queue_seconds` | Native span attribute |
| `inference_lab.engine.prefill` | `inference_lab_engine_prefill_seconds` | Native span attribute |
| `inference_lab.engine.decode` | `inference_lab_engine_decode_seconds` | Native span attribute |
| `inference_lab.gpu.utilization` | `inference_lab_gpu_utilization_percent` | nvidia-smi GPU busy sampling |
| `inference_lab.gpu.memory_utilization` | `inference_lab_gpu_memory_utilization_percent` | Memory controller activity |
| `inference_lab.gpu.memory_used` | `inference_lab_gpu_memory_used_bytes` | Allocated memory |
| `inference_lab.gpu.power` | `inference_lab_gpu_power_watts` | Power draw |
| `inference_lab.gpu.temperature` | `inference_lab_gpu_temperature_celsius` | Temperature |

All are gauges of recorded observations. Missing first-content or final-usage values are not converted to zero. Request attributes include scenario and outcome; resource attributes include replay and source identity. The dashboard uses a bounded rolling maximum, not `histogram_quantile` on invented buckets.

## References

- [Dash0 regional endpoints](https://www.dash0.com/docs/dash0/miscellaneous/glossary/endpoints)
- [Dash0 public OpenAPI specification](https://www.dash0.com/docs/api-reference/openapi.json)
- [Read spans](https://www.dash0.com/docs/api-reference/operations/post/api/spans)
- [Read a full trace](https://www.dash0.com/docs/api-reference/operations/post/api/trace/details)

The implementation uses documented `/api/trace/details`, `/api/logs`, Prometheus query and dashboard endpoints. No private browser API is required for setup or validation.
