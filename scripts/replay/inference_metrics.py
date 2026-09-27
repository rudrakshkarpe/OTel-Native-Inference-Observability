"""Prepare exact inference scorecards from a verified archive and an existing replay.

This metrics-only supplement does not resend traces or logs. Percentiles describe
completed requests; throughput uses observed scenario wall time, not summed latency.
"""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from capture import attrs, iso, ns, put, send, verified_bytes
from dash0_api import Dash0
from opentelemetry.proto.collector.metrics.v1.metrics_service_pb2 import (
    ExportMetricsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

PERCENTILES = (50, 90, 95, 99)
# key: display name, OTLP unit, observation source, field, multiplier
DEFINITIONS = {
    "client_first_content": (
        "Client first-content latency",
        "s",
        "client",
        "first_content_s",
        1,
    ),
    "client_duration": ("Client request duration", "s", "client", "duration_s", 1),
    "engine_ttft": ("Native engine TTFT", "s", "span", "time_to_first_token", 1),
    "queue": ("Native queue wait", "s", "span", "time_in_queue", 1),
    "prefill": ("Native prefill", "s", "span", "time_in_model_prefill", 1),
    "decode": ("Native decode", "s", "span", "time_in_model_decode", 1),
    "request_mean_itl": ("Per-request mean ITL", "s", "response", "mean_itl_ms", 0.001),
    "request_output_tps": (
        "Per-request engine output tokens/s",
        "1",
        "response",
        "tokens_per_second",
        1,
    ),
}


def distribution(values):
    if not values:
        return {"n": 0, **{f"p{q}": None for q in PERCENTILES}}
    if any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError("Measurements must be finite and non-negative")
    values = sorted(values)
    return {
        "n": len(values),
        **{f"p{q}": values[math.ceil(q / 100 * len(values)) - 1] for q in PERCENTILES},
    }


def summarize(rows, native):
    """Report only aggregates: no prompts, completions or private request metadata."""
    if not rows or len({r["request_id"] for r in rows}) != len(rows):
        raise ValueError("Requests must be nonempty and unique")
    scenarios = {}
    for scenario in [*dict.fromkeys(r["scenario"] for r in rows), "all"]:
        group = (
            rows
            if scenario == "all"
            else [r for r in rows if r["scenario"] == scenario]
        )
        start = min(ns(r["started_at"]) for r in group)
        end = max(ns(r["ended_at"]) for r in group)
        seconds = (end - start) / 1e9
        if seconds <= 0:
            raise ValueError("Scenario wall time must be positive")
        completed = [r for r in group if r["status"] == "ok"]
        if any(r.get("usage") is None for r in completed):
            raise ValueError("Completed requests require recorded usage")
        measurements = {}
        for key, (_, _, source, field, multiplier) in DEFINITIONS.items():
            values = []
            for r in completed:
                if source == "client":
                    value = r.get(field)
                elif source == "response":
                    value = (r.get("engine_metrics") or {}).get(field)
                else:
                    value = native.get((r["trace_id"], r["span_id"]), {}).get(
                        "gen_ai.latency." + field
                    )
                if value is not None:
                    values.append(value * multiplier)
            measurements[key] = distribution(values)
        counts = Counter(r["status"] for r in group)
        tokens = {
            kind: sum(r["usage"][field] for r in completed)
            for kind, field in [
                ("input", "prompt_tokens"),
                ("output", "completion_tokens"),
            ]
        }
        scenarios[scenario] = {
            "window": [iso(start), iso(end)],
            "wall_seconds": seconds,
            "attempted": len(group),
            "completed": len(completed),
            "outcomes": dict(counts),
            "missing_usage": sum(r.get("usage") is None for r in group),
            "completed_tokens": tokens,
            "rates": {
                "attempted_requests_per_second": len(group) / seconds,
                "completed_requests_per_second": len(completed) / seconds,
                "completed_input_tokens_per_second": tokens["input"] / seconds,
                "completed_output_tokens_per_second": tokens["output"] / seconds,
            },
            "distributions": measurements,
        }
    return scenarios


def prepare(archive, replay, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Use an empty output directory; previous supplements are preserved"
        )
    checksums = json.loads((archive / "SHA256SUMS.json").read_text())
    source = json.loads(verified_bytes(archive, "workload/manifest.json", checksums))
    index = json.loads(
        verified_bytes(archive, "workload/request-index.json", checksums)
    )
    rows = []
    for scenario, *_ in source["plans"]:
        rows.extend(
            json.loads(line)
            for line in verified_bytes(
                archive, f"workload/{scenario}-requests.jsonl", checksums
            )
            .decode()
            .splitlines()
        )
    keyed = {r["request_id"]: r for r in rows}
    if len(rows) != len(index) or len(keyed) != len(rows):
        raise ValueError("Request index does not match source records")
    for row in index:
        if row["request_id"] not in keyed or any(
            keyed[row["request_id"]].get(k) != v for k, v in row.items()
        ):
            raise ValueError("Request index differs from source record")
    manifest = json.loads((replay / "manifest.json").read_text())
    if source["capture_id"] != manifest["source_capture"] or {
        r["trace_id"] for r in rows
    } != set(manifest["trace_mapping"]):
        raise ValueError("Archive does not match selected replay")
    payload = (replay / "traces.pb").read_bytes()
    if hashlib.sha256(payload).hexdigest() != manifest["sha256"]["traces"]:
        raise ValueError("Replay trace checksum mismatch")
    # Read original native values, not hosted backend aggregations.
    native = {}
    for p in sorted((archive / "otlp").glob("*.pb")):
        traces = ExportTraceServiceRequest.FromString(
            verified_bytes(archive, "otlp/" + p.name, checksums)
        )
        for resource in traces.resource_spans:
            for scope in resource.scope_spans:
                for span in scope.spans:
                    if (
                        span.name == "llm_request"
                        and span.trace_id.hex() in manifest["trace_mapping"]
                    ):
                        key = (span.trace_id.hex(), span.parent_span_id.hex())
                        if key in native:
                            raise ValueError("Duplicate native request span")
                        native[key] = attrs(span.attributes)
    for r in rows:
        if r["status"] == "ok":
            a = native[(r["trace_id"], r["span_id"])]
            for response_key, span_key in [
                ("prompt_tokens", "prompt_tokens"),
                ("completion_tokens", "completion_tokens"),
            ]:
                if r["usage"][response_key] != a["gen_ai.usage." + span_key]:
                    raise ValueError("Native and response token counts differ")
    report = {
        "source_capture": source["capture_id"],
        "replay_id": manifest["replay_id"],
        "method": "Nearest-rank percentiles of completed requests; scenario rates use earliest client start to latest client end. Missing observations stay missing.",
        "scenarios": summarize(rows, native),
    }
    timestamp = ns(source["ended_at"]) + manifest["timestamp_shift_ns"]
    report["sample_time"] = iso(timestamp)
    report["summary_id"] = "inference-scorecard-v1"
    metrics = ExportMetricsServiceRequest()
    rm = metrics.resource_metrics.add()
    for k, v in {
        "service.name": "inference-capture-scorecard",
        "service.namespace": "inference-lab",
        "inference.replay.id": report["replay_id"],
        "inference.summary.id": report["summary_id"],
        "inference.capture.id": report["source_capture"],
        "observatory.replayed": True,
        "inference.metric.source": "verified-archive-aggregates",
    }.items():
        put(rm.resource.attributes, k, v)
    scope = rm.scope_metrics.add()
    scope.scope.name = "inference-scorecard"
    cache = {}

    def point(key, unit, value, labels):
        if key not in cache:
            m = scope.metrics.add()
            m.name = "inference_lab.summary." + key
            m.unit = unit
            m.description = (
                "Fixed capture statistic at run end, not a live rolling measurement"
            )
            cache[key] = m
        p = cache[key].gauge.data_points.add()
        p.as_double = value
        p.time_unix_nano = timestamp
        for k, v in labels.items():
            put(p.attributes, k, v)

    for scenario, summary in report["scenarios"].items():
        labels = {"inference.scenario": scenario}
        for key, dist in summary["distributions"].items():
            for q in PERCENTILES:
                if dist[f"p{q}"] is not None:
                    point(
                        key,
                        DEFINITIONS[key][1],
                        dist[f"p{q}"],
                        {
                            **labels,
                            "percentile": str(q),
                            "sample_count": str(dist["n"]),
                        },
                    )
        for key, value in summary["rates"].items():
            point(key, "1", value, labels)
        for key in ("attempted", "completed", "missing_usage", "wall_seconds"):
            point(key, "s" if key == "wall_seconds" else "1", summary[key], labels)
        for outcome in ("ok", "error", "intentional_early_close"):
            point(
                "outcome_count",
                "1",
                summary["outcomes"].get(outcome, 0),
                {**labels, "inference.outcome": outcome},
            )
        for kind, count in summary["completed_tokens"].items():
            point("token_count", "1", count, {**labels, "token_type": kind})
    body = metrics.SerializeToString()
    output.mkdir(parents=True, exist_ok=True)
    (output / "metrics.pb").write_bytes(body)
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "replay_id": report["replay_id"],
                "summary_id": report["summary_id"],
                "sample_time": report["sample_time"],
                "sha256": {
                    "metrics": hashlib.sha256(body).hexdigest(),
                    "report": hashlib.sha256(
                        (output / "report.json").read_bytes()
                    ).hexdigest(),
                },
                "metric_points": sum(len(m.gauge.data_points) for m in scope.metrics),
            },
            indent=2,
        )
        + "\n"
    )
    return report


def verify(output):
    manifest = json.loads((output / "manifest.json").read_text())
    body = (output / "metrics.pb").read_bytes()
    if hashlib.sha256(body).hexdigest() != manifest["sha256"]["metrics"]:
        raise ValueError("Metric payload checksum mismatch")
    metrics = ExportMetricsServiceRequest.FromString(body)
    api = Dash0()
    results = []
    for rm in metrics.resource_metrics:
        for scope in rm.scope_metrics:
            for m in scope.metrics:
                query = (
                    '{otel_metric_name="'
                    + m.name
                    + '",inference_replay_id="'
                    + manifest["replay_id"]
                    + '",inference_summary_id="'
                    + manifest["summary_id"]
                    + '"}'
                )
                response = api.call(
                    "/api/prometheus/api/v1/query",
                    {
                        "dataset": api.config["dataset"],
                        "query": query,
                        "time": iso(ns(manifest["sample_time"]) + 1_000_000_000),
                    },
                )
                results.extend(response["data"]["result"])
    verified = 0
    for rm in metrics.resource_metrics:
        for scope in rm.scope_metrics:
            for m in scope.metrics:
                for p in m.gauge.data_points:
                    labels = {
                        k.replace(".", "_"): str(v)
                        for k, v in attrs(p.attributes).items()
                    }
                    matching = [
                        r
                        for r in results
                        if r["metric"].get("otel_metric_name") == m.name
                        and all(r["metric"].get(k) == v for k, v in labels.items())
                    ]
                    if len(matching) != 1 or not math.isclose(
                        float(matching[0]["value"][1]),
                        p.as_double,
                        rel_tol=1e-9,
                        abs_tol=1e-12,
                    ):
                        raise ValueError(
                            f"Hosted statistic mismatch: {m.name} {labels}"
                        )
                    verified += 1
    if len(results) != verified:
        raise ValueError("Unexpected extra hosted statistic series")
    result = {
        "replay_id": manifest["replay_id"],
        "summary_id": manifest["summary_id"],
        "statistics_verified": verified,
        "sample_time": manifest["sample_time"],
        "method": "Compare every hosted metric name, scenario, percentile, sample count and value against the OTLP payload using the Dash0 Prometheus API.",
    }
    (output / "hosted-verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument("--archive", type=Path, required=True)
    prep.add_argument("--replay", type=Path, required=True)
    prep.add_argument("--output", type=Path, required=True)
    export = sub.add_parser("send")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--endpoint", default="http://127.0.0.1:24318")
    check = sub.add_parser("verify")
    check.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if a.command == "prepare":
        r = prepare(a.archive, a.replay, a.output)
        print(
            json.dumps(
                {"scenarios": list(r["scenarios"]), "sample_time": r["sample_time"]}
            )
        )
    elif a.command == "send":
        print(json.dumps(send(a.output, a.endpoint, signals=("metrics",))))
    else:
        print(json.dumps(verify(a.output), indent=2))
