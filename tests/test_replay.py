"""Replay integrity tests: no backend, credentials or private capture required."""

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "replay"))
from capture import attrs, prepare, put, send, verified_bytes
from dashboard import build
from verify_dash0 import hex_id


def archive(tmp_path):
    root = tmp_path / "archive"
    (root / "workload").mkdir(parents=True)
    (root / "otlp").mkdir()
    (root / "remote").mkdir()
    tid = "01" * 16
    parent = "02" * 8
    client = "03" * 8
    row = {
        "request_id": "r1",
        "trace_id": tid,
        "span_id": client,
        "scenario": "baseline",
        "status": "ok",
        "usage": {"prompt_tokens": 7, "completion_tokens": 3},
        "duration_s": 2.0,
        "first_content_s": 0.3,
        "ended_at": "2026-09-27T08:00:02+00:00",
    }
    (root / "workload/request-index.json").write_text(json.dumps([row]))
    (root / "workload/baseline-requests.jsonl").write_text(json.dumps(row) + "\n")
    (root / "workload/manifest.json").write_text(
        json.dumps(
            {
                "plans": [["baseline"]],
                "started_at": "2026-09-27T08:00:00+00:00",
                "ended_at": row["ended_at"],
                "capture_id": "fixture",
            }
        )
    )
    msg = ExportTraceServiceRequest()
    resource = msg.resource_spans.add()
    put(resource.resource.attributes, "service.name", "fixture")
    scope = resource.scope_spans.add()
    for sid, pid, name in [
        (parent, "", "gpu.workload {scenario}"),
        (client, parent, "chat {model}"),
        ("04" * 8, client, "llm_request"),
    ]:
        s = scope.spans.add()
        s.trace_id = bytes.fromhex(tid)
        s.span_id = bytes.fromhex(sid)
        s.parent_span_id = bytes.fromhex(pid)
        s.name = name
        s.start_time_unix_nano = 1790496000000000000
        s.end_time_unix_nano = s.start_time_unix_nano + 2000000000
        e = s.events.add()
        e.name = "recorded"
        e.time_unix_nano = s.start_time_unix_nano + 1000
        if name == "llm_request":
            for key, val in {
                "gen_ai.usage.prompt_tokens": 7,
                "gen_ai.usage.completion_tokens": 3,
                "gen_ai.latency.time_in_queue": 0.1,
                "gen_ai.latency.time_in_model_prefill": 0.2,
                "gen_ai.latency.time_in_model_decode": 1.7,
            }.items():
                put(s.attributes, key, val)
    (root / "otlp/one.pb").write_bytes(msg.SerializeToString())
    (root / "remote/gpu-metrics.csv").write_text(
        "timestamp, name, utilization.gpu [%], utilization.memory [%], memory.used [MiB], power.draw [W], temperature.gpu\n2026/09/27 08:00:01.000, H100, 99 %, 40 %, 1024 MiB, 200 W, 42\n"
    )
    checksums = {
        str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in root.rglob("*")
        if p.is_file()
    }
    (root / "SHA256SUMS.json").write_text(json.dumps(checksums))
    return root, msg


def test_replay_preserves_parent_links_durations_and_events(tmp_path):
    root, original = archive(tmp_path)
    out = tmp_path / "out"
    summary = prepare(root, out, "test-replay", now_ns=1790500000000000000)
    replay = ExportTraceServiceRequest.FromString((out / "traces.pb").read_bytes())
    before = original.resource_spans[0].scope_spans[0].spans
    after = replay.resource_spans[0].scope_spans[0].spans
    for a, b in zip(before, after, strict=True):
        assert a.trace_id != b.trace_id
        assert a.span_id == b.span_id and a.parent_span_id == b.parent_span_id
        assert (
            b.end_time_unix_nano - b.start_time_unix_nano
            == a.end_time_unix_nano - a.start_time_unix_nano
        )
        assert (
            b.events[0].time_unix_nano - a.events[0].time_unix_nano
            == summary["timestamp_shift_ns"]
        )
    assert (
        summary["metric_points"] == 10
    )  # two client, three native and five GPU measurements
    assert summary["logs"] == 1
    assert attrs(after[-1].attributes)["gen_ai.latency.time_in_queue"] == 0.1
    with pytest.raises(ValueError, match="empty output"):
        prepare(root, out, "test-replay")


def test_tampered_archive_rejected_before_output(tmp_path):
    root, _ = archive(tmp_path)
    (root / "otlp/one.pb").write_bytes(b"changed")
    with pytest.raises(ValueError, match="Checksum"):
        prepare(root, tmp_path / "out", "test-replay")
    assert not (tmp_path / "out").exists()


def test_payload_tampering_and_ambiguous_send_do_not_retry(tmp_path):
    root, _ = archive(tmp_path)
    out = tmp_path / "out"
    prepare(root, out, "test-replay")
    # A timeout might occur after the backend accepted the request. Preserve the attempt.
    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError),
        pytest.raises(TimeoutError),
    ):
        send(out, "http://127.0.0.1:24318")
    assert (
        json.loads((out / "send-receipts.json").read_text())[0]["status"]
        == "attempting"
    )
    with pytest.raises(ValueError, match="already has send receipts"):
        send(out, "http://127.0.0.1:24318")


def test_checksum_validation(tmp_path):
    (tmp_path / "sample").write_bytes(b"a")
    with pytest.raises(ValueError, match="Checksum"):
        verified_bytes(tmp_path, "sample", {})


def test_dashboard_scoped_queries_expire_stale_observations():
    dashboard = build("test-replay")
    assert len(dashboard["spec"]["panels"]) == 8
    for panel in dashboard["spec"]["panels"].values():
        for query in panel["spec"]["queries"]:
            expression = query["spec"]["plugin"]["spec"]["query"]
            assert 'inference_replay_id="test-replay"' in expression
            assert expression.endswith("[15s])")
    with pytest.raises(ValueError):
        build('bad"id')


def test_dash0_otlp_id_encodings():
    assert hex_id("AQEBAQEBAQE=") == "01" * 8
    assert hex_id("01" * 8) == "01" * 8
    assert hex_id(None) == ""


def test_prepared_payload_tampering_fails_before_network(tmp_path):
    root, _ = archive(tmp_path)
    out = tmp_path / "out"
    prepare(root, out, "test-replay")
    (out / "metrics.pb").write_bytes(b"tampered")
    with patch("urllib.request.urlopen") as network:
        with pytest.raises(ValueError, match="checksum mismatch"):
            send(out, "http://127.0.0.1:24318")
        network.assert_not_called()
    assert not (out / "send-receipts.json").exists()
