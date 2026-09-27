"""Replay verified H100 evidence through OTLP without rerunning or inventing inference."""

import argparse
import csv
import hashlib
import json
import re
import time
import urllib.request
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
    ExportLogsServiceResponse,
)
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
    ExportMetricsServiceResponse,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
    ExportTraceServiceResponse,
)


def ns(iso):
    return int(datetime.fromisoformat(iso).timestamp() * 1e9)


def iso(nanos):
    return datetime.fromtimestamp(nanos / 1e9, timezone.utc).isoformat()


def attrs(items):
    return {
        a.key: getattr(a.value, a.value.WhichOneof("value"))
        for a in items
        if a.value.WhichOneof("value")
        in ("string_value", "bool_value", "int_value", "double_value")
    }


def put(items, key, value):
    a = next((a for a in items if a.key == key), None)
    if a is None:
        a = items.add()
        a.key = key
    a.value.Clear()
    if isinstance(value, bool):
        a.value.bool_value = value
    elif isinstance(value, int):
        a.value.int_value = value
    elif isinstance(value, float):
        a.value.double_value = value
    else:
        a.value.string_value = str(value)


def verified_bytes(root, relative, manifest):
    body = (root / relative).read_bytes()
    if hashlib.sha256(body).hexdigest() != manifest.get(relative):
        raise ValueError(f"Checksum mismatch or missing manifest entry: {relative}")
    return body


def prepare(root, output, replay_id, now_ns=None):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", replay_id):
        raise ValueError(
            "Replay ID must use 1-80 letters, digits, hyphens or underscores"
        )
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Use an empty output directory; previous replays are preserved"
        )
    checksums = json.loads((root / "SHA256SUMS.json").read_text())
    index = json.loads(verified_bytes(root, "workload/request-index.json", checksums))
    manifest = json.loads(verified_bytes(root, "workload/manifest.json", checksums))
    requests = []
    for scenario, *_ in manifest["plans"]:
        requests.extend(
            json.loads(line)
            for line in verified_bytes(
                root, f"workload/{scenario}-requests.jsonl", checksums
            )
            .decode()
            .splitlines()
        )
    if len(requests) != len(index) or {r["request_id"] for r in requests} != {
        r["request_id"] for r in index
    }:
        raise ValueError("Request index does not match recorded requests")
    ids = {r["trace_id"] for r in index}
    scenarios = {r["trace_id"]: r["scenario"] for r in index}
    mapping = {tid: uuid.uuid4().hex for tid in ids}
    # Leave 30s after the final GPU sample; no timestamp lies in the future.
    shift = (now_ns or time.time_ns()) - ns(manifest["ended_at"]) - 40_000_000_000
    common = {
        "inference.replay.id": replay_id,
        "observatory.replayed": True,
        "inference.capture.id": manifest["capture_id"],
        "inference.replay.shift_ns": shift,
        "service.namespace": "inference-lab",
        "inference.source": "real-h100-capture",
    }
    traces = ExportTraceServiceRequest()
    native = {}
    span_lookup = {}
    for path in sorted((root / "otlp").glob("*.pb")):
        msg = ExportTraceServiceRequest.FromString(
            verified_bytes(root, "otlp/" + path.name, checksums)
        )
        for resource in msg.resource_spans:
            selected = []
            for scope in resource.scope_spans:
                keep = [
                    s
                    for s in scope.spans
                    if s.trace_id.hex() in ids
                    and attrs(s.attributes).get("logfire.span_type") != "pending_span"
                ]
                if keep:
                    selected.append((scope, keep))
            if not selected:
                continue
            dest = traces.resource_spans.add()
            dest.resource.CopyFrom(resource.resource)
            for k, v in common.items():
                put(dest.resource.attributes, k, v)
            for scope, keep in selected:
                target = dest.scope_spans.add()
                target.scope.CopyFrom(scope.scope)
                for source in keep:
                    key = (source.trace_id.hex(), source.span_id.hex())
                    if key in span_lookup:
                        raise ValueError("Duplicate final span in capture")
                    s = target.spans.add()
                    s.CopyFrom(source)
                    original = s.trace_id.hex()
                    span_lookup[key] = s
                    if s.name == "llm_request":
                        native[(original, s.parent_span_id.hex())] = s
                    put(s.attributes, "inference.original.trace_id", original)
                    put(s.attributes, "inference.scenario", scenarios[original])
                    s.trace_id = bytes.fromhex(mapping[original])
                    s.start_time_unix_nano += shift
                    s.end_time_unix_nano += shift
                    for event in s.events:
                        event.time_unix_nano += shift
                    for link in s.links:
                        if link.trace_id.hex() in mapping:
                            link.trace_id = bytes.fromhex(mapping[link.trace_id.hex()])
    for row in index:
        if (row["trace_id"], row["span_id"]) not in span_lookup:
            raise ValueError("Client span missing")
        if row["status"] == "ok":
            a = attrs(native[(row["trace_id"], row["span_id"])].attributes)
            if (
                a["gen_ai.usage.prompt_tokens"] != row["usage"]["prompt_tokens"]
                or a["gen_ai.usage.completion_tokens"]
                != row["usage"]["completion_tokens"]
            ):
                raise ValueError("Engine usage does not match response")

    logs = ExportLogsServiceRequest()
    rl = logs.resource_logs.add()
    for k, v in {
        **common,
        "service.name": "inference-h100-client",
        "inference.log.source": "archived-request-outcomes",
    }.items():
        put(rl.resource.attributes, k, v)
    sl = rl.scope_logs.add()
    sl.scope.name = "inference-evidence-replay"
    for row in requests:
        log = sl.log_records.add()
        log.time_unix_nano = ns(row["ended_at"]) + shift
        log.observed_time_unix_nano = log.time_unix_nano
        log.trace_id = bytes.fromhex(mapping[row["trace_id"]])
        log.span_id = bytes.fromhex(row["span_id"])
        log.severity_number = 17 if row["status"] == "error" else 9
        log.severity_text = "ERROR" if row["status"] == "error" else "INFO"
        log.body.string_value = (
            f"Archived request outcome: {row['scenario']} / {row['status']}"
        )
        for k, v in {
            "inference.request.id": row["request_id"],
            "inference.scenario": row["scenario"],
            "inference.outcome": row["status"],
            "inference.duration_s": row["duration_s"],
            "inference.usage_available": row["usage"] is not None,
        }.items():
            put(log.attributes, k, v)
        if row.get("error_type"):
            put(log.attributes, "exception.type", row["error_type"])
            put(log.attributes, "exception.message", row["error_message"])

    metrics = ExportMetricsServiceRequest()
    metric_cache = {}

    def point(name, unit, value, timestamp, service, source, labels=None, row=None):
        key = (service, source, name)
        if key not in metric_cache:
            rm = metrics.resource_metrics.add()
            for k, v in {
                **common,
                "service.name": service,
                "inference.metric.source": source,
            }.items():
                put(rm.resource.attributes, k, v)
            scope = rm.scope_metrics.add()
            scope.scope.name = "inference-evidence-replay"
            metric = scope.metrics.add()
            metric.name = name
            metric.unit = unit
            metric.description = (
                f"Recorded measurement from {source}; timestamps shifted for replay"
            )
            metric_cache[key] = metric
        dp = metric_cache[key].gauge.data_points.add()
        dp.time_unix_nano = timestamp + shift
        dp.as_double = value
        for k, v in (labels or {}).items():
            put(dp.attributes, k, v)
        if row:
            ex = dp.exemplars.add()
            ex.time_unix_nano = dp.time_unix_nano
            ex.as_double = value
            ex.trace_id = bytes.fromhex(mapping[row["trace_id"]])
            ex.span_id = bytes.fromhex(row["span_id"])

    for row in index:
        timestamp = ns(row["ended_at"])
        labels = {
            "inference.scenario": row["scenario"],
            "inference.outcome": row["status"],
        }
        for field, name in [
            ("duration_s", "inference_lab.request.duration"),
            ("first_content_s", "inference_lab.request.first_content"),
        ]:
            if row.get(field) is not None:
                point(
                    name,
                    "s",
                    row[field],
                    timestamp,
                    "inference-h100-client",
                    "archived-client-measurements",
                    labels,
                    row,
                )
        engine = native.get((row["trace_id"], row["span_id"]))
        if engine:
            a = attrs(engine.attributes)
            for field, name in [
                ("time_in_queue", "queue"),
                ("time_in_model_prefill", "prefill"),
                ("time_in_model_decode", "decode"),
            ]:
                point(
                    f"inference_lab.engine.{name}",
                    "s",
                    a["gen_ai.latency." + field],
                    timestamp,
                    "vllm-h100-serving",
                    "native-vllm-span-attributes",
                    labels,
                    row,
                )
    gpu_rows = csv.DictReader(
        verified_bytes(root, "remote/gpu-metrics.csv", checksums).decode().splitlines(),
        skipinitialspace=True,
    )
    gpu_count = 0
    for row in gpu_rows:
        timestamp = int(
            datetime.strptime(row["timestamp"], "%Y/%m/%d %H:%M:%S.%f")
            .replace(tzinfo=timezone.utc)
            .timestamp()
            * 1e9
        )
        if (
            not ns(manifest["started_at"]) - 10_000_000_000
            <= timestamp
            <= ns(manifest["ended_at"]) + 10_000_000_000
        ):
            continue
        gpu_count += 1
        for field, name, unit, multiplier in [
            ("utilization.gpu [%]", "utilization", "%", 1),
            ("utilization.memory [%]", "memory_utilization", "%", 1),
            ("memory.used [MiB]", "memory_used", "By", 1048576),
            ("power.draw [W]", "power", "W", 1),
            ("temperature.gpu", "temperature", "Cel", 1),
        ]:
            point(
                "inference_lab.gpu." + name,
                unit,
                float(row[field].split()[0]) * multiplier,
                timestamp,
                "h100-gpu",
                "nvidia-smi-csv",
                {"gpu.model": row["name"]},
            )
    output.mkdir(parents=True, exist_ok=True)
    payloads = {"traces": traces, "logs": logs, "metrics": metrics}
    hashes = {}
    for signal, msg in payloads.items():
        body = msg.SerializeToString()
        (output / f"{signal}.pb").write_bytes(body)
        hashes[signal] = hashlib.sha256(body).hexdigest()
    summary = {
        "replay_id": replay_id,
        "source_capture": manifest["capture_id"],
        "original_window": [manifest["started_at"], manifest["ended_at"]],
        "replay_window": [
            iso(ns(manifest["started_at"]) + shift - 10_000_000_000),
            iso(ns(manifest["ended_at"]) + shift + 10_000_000_000),
        ],
        "timestamp_shift_ns": shift,
        "trace_mapping": mapping,
        "spans": len(span_lookup),
        "requests": len(index),
        "outcomes": dict(Counter(r["status"] for r in index)),
        "engine_parent_links": len(native),
        "logs": len(requests),
        "gpu_samples": gpu_count,
        "metric_points": sum(
            len(m.gauge.data_points)
            for rm in metrics.resource_metrics
            for sc in rm.scope_metrics
            for m in sc.metrics
        ),
        "sha256": hashes,
        "notes": [
            "Only the six main-workload traces are replayed; startup attempts and smoke are excluded.",
            "Request outcome logs are derived from archived client records, not original vLLM console logs.",
            "GPU metrics come from recorded nvidia-smi CSV, not DCGM.",
            "Engine timing gauges are derived from native span attributes; no stage spans were fabricated.",
            "Original Prometheus snapshots remain in the archive; no continuous scrape history is invented.",
        ],
    }
    (output / "manifest.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def send(output, endpoint):
    manifest = json.loads((output / "manifest.json").read_text())
    if (output / "send-receipts.json").exists():
        raise ValueError(
            "This replay already has send receipts; inspect before repeating ingestion"
        )
    payloads = {}
    for signal in ("traces", "logs", "metrics"):
        body = (output / f"{signal}.pb").read_bytes()
        if hashlib.sha256(body).hexdigest() != manifest["sha256"][signal]:
            raise ValueError("Prepared payload checksum mismatch")
        payloads[signal] = body
    receipts = []
    response_types = {
        "traces": ExportTraceServiceResponse,
        "logs": ExportLogsServiceResponse,
        "metrics": ExportMetricsServiceResponse,
    }
    for signal, body in payloads.items():
        receipts.append(
            {
                "signal": signal,
                "status": "attempting",
                "sha256": manifest["sha256"][signal],
            }
        )
        (output / "send-receipts.json").write_text(
            json.dumps(receipts, indent=2) + "\n"
        )
        req = urllib.request.Request(
            endpoint.rstrip("/") + "/v1/" + signal,
            data=body,
            headers={"Content-Type": "application/x-protobuf"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            reply = response_types[signal].FromString(response.read())
            if reply.partial_success.ListFields():
                raise RuntimeError(
                    f"Collector reported partial success for {signal}: {reply.partial_success}"
                )
            receipts[-1].update({"status": "accepted", "http_status": response.status})
        (output / "send-receipts.json").write_text(
            json.dumps(receipts, indent=2) + "\n"
        )
    return receipts


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--archive", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--replay-id", required=True)
    p = sub.add_parser("send")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--endpoint", default="http://127.0.0.1:24318")
    args = parser.parse_args()
    result = (
        prepare(args.archive, args.output, args.replay_id)
        if args.command == "prepare"
        else send(args.output, args.endpoint)
    )
    print(json.dumps(result, indent=2))
