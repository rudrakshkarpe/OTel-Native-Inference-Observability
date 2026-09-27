"""Read back complete traces, correlated outcomes and GPU samples from Dash0."""

import argparse
import base64
import json
from pathlib import Path

from dash0_api import Dash0
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


def hex_id(value):
    if not value:
        return ""
    try:
        return (
            base64.b64decode(value, validate=True).hex()
            if "=" in value
            else bytes.fromhex(value).hex()
        )
    except ValueError:
        raise ValueError("Unrecognized OTLP ID encoding") from None


def main(output):
    manifest = json.loads((output / "manifest.json").read_text())
    api = Dash0()
    expected = ExportTraceServiceRequest.FromString((output / "traces.pb").read_bytes())
    local = {
        (s.trace_id.hex(), s.span_id.hex()): s
        for r in expected.resource_spans
        for sc in r.scope_spans
        for s in sc.spans
    }
    remote = {}
    log_ids = set()
    errors = 0
    window = {"from": manifest["replay_window"][0], "to": manifest["replay_window"][1]}
    for tid in manifest["trace_mapping"].values():
        response = api.call(
            "/api/trace/details",
            {"dataset": api.config["dataset"], "traceId": tid, "timeRange": window},
        )
        (output / f"trace-{tid}.json").write_text(json.dumps(response, indent=2))
        for r in response["resourceSpans"]:
            for sc in r["scopeSpans"]:
                for s in sc["spans"]:
                    key = (hex_id(s["traceId"]), hex_id(s["spanId"]))
                    if key in remote:
                        raise ValueError("Duplicate hosted span ID")
                    remote[key] = s
        for r in response.get("resourceLogs", []):
            for sc in r["scopeLogs"]:
                for log in sc["logRecords"]:
                    log_ids.add((hex_id(log["traceId"]), hex_id(log["spanId"])))
    if set(remote) != set(local):
        raise ValueError(f"Span IDs differ: {len(local)} local, {len(remote)} hosted")
    native = 0
    for key, s in local.items():
        r = remote[key]
        if hex_id(r.get("parentSpanId")) != s.parent_span_id.hex():
            raise ValueError("Parent ID mismatch")
        if (
            int(r["endTimeUnixNano"]) - int(r["startTimeUnixNano"])
            != s.end_time_unix_nano - s.start_time_unix_nano
        ):
            raise ValueError("Duration mismatch")
        if s.name == "llm_request":
            native += 1
        if s.status.code == 2:
            if r.get("status", {}).get("code") not in (2, "STATUS_CODE_ERROR"):
                raise ValueError("Error status missing")
            if not any(e["name"] == "exception" for e in r.get("events", [])):
                raise ValueError("Exception event missing")
            errors += 1
    logs = api.call(
        "/api/logs",
        {
            "dataset": api.config["dataset"],
            "timeRange": window,
            "filter": [
                {
                    "key": "inference.replay.id",
                    "operator": "is",
                    "value": manifest["replay_id"],
                }
            ],
            "pagination": {"limit": 200},
        },
    )
    (output / "hosted-logs.json").write_text(json.dumps(logs, indent=2))
    log_count = 0
    for resource in logs.get("resourceLogs", []):
        for scope in resource["scopeLogs"]:
            for log in scope["logRecords"]:
                log_count += 1
                log_ids.add((hex_id(log["traceId"]), hex_id(log["spanId"])))
    expected_logs = {key for key, span in local.items() if span.name == "chat {model}"}
    if log_ids != expected_logs or log_count != len(expected_logs):
        raise ValueError(
            f"Correlated request outcomes differ: {len(log_ids)} hosted, {len(expected_logs)} expected"
        )
    gpu = api.call(
        "/api/prometheus/api/v1/query_range",
        {
            "dataset": api.config["dataset"],
            "query": f'inference_lab_gpu_utilization_percent{{inference_replay_id="{manifest["replay_id"]}"}}',
            "start": window["from"],
            "end": window["to"],
            "step": "1s",
        },
    )
    (output / "hosted-gpu-query.json").write_text(json.dumps(gpu, indent=2))
    values = [float(v[1]) for r in gpu["data"]["result"] for v in r["values"]]
    if not values:
        raise ValueError("No hosted GPU metrics")
    summary = {
        "replay_id": manifest["replay_id"],
        "traces_verified": len(manifest["trace_mapping"]),
        "span_ids_verified": len(local),
        "parent_ids_verified": len(local),
        "durations_verified": len(local),
        "native_engine_requests": native,
        "correlated_request_logs": len(log_ids),
        "error_spans_with_exception": errors,
        "gpu_query_points": len(values),
        "gpu_peak_utilization_percent": max(values),
        "time_range": window,
        "method": "Public trace/details API for each trace and Prometheus range query; original IDs and durations compared with prepared OTLP payload.",
    }
    (output / "hosted-verification.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    return summary


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("output", type=Path)
    a = p.parse_args()
    print(json.dumps(main(a.output), indent=2))
