"""Protect statistical populations, concurrent throughput and metrics-only sends."""

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "replay"))
from capture import send
from inference_metrics import distribution, summarize
from scorecard_dashboard import DEFAULT_REPORT, build


def row(request_id, start, end, status="ok", tokens=10, first=0.2):
    return {
        "request_id": request_id,
        "scenario": "test",
        "trace_id": "trace",
        "span_id": request_id,
        "started_at": f"2026-09-27T00:00:{start:02d}+00:00",
        "ended_at": f"2026-09-27T00:00:{end:02d}+00:00",
        "status": status,
        "duration_s": end - start,
        "first_content_s": first,
        "usage": {"prompt_tokens": 20, "completion_tokens": tokens}
        if status == "ok"
        else None,
        "engine_metrics": {"mean_itl_ms": 20, "tokens_per_second": 5}
        if status == "ok"
        else None,
    }


def test_nearest_rank_and_missing_samples():
    d = distribution(list(range(1, 11)))
    assert d == {"n": 10, "p50": 5, "p90": 9, "p95": 10, "p99": 10}
    assert distribution([]) == {
        "n": 0,
        "p50": None,
        "p90": None,
        "p95": None,
        "p99": None,
    }
    for invalid in (float("nan"), float("inf"), -1):
        with pytest.raises(ValueError):
            distribution([invalid])


def test_overlapping_requests_use_wall_time_and_exclude_incomplete_usage():
    rows = [
        row("a", 0, 10),
        row("b", 0, 10),
        row("c", 1, 2, "error", first=None),
        row("d", 1, 3, "intentional_early_close"),
    ]
    s = summarize(rows, {})["test"]
    assert s["wall_seconds"] == 10
    assert s["rates"]["completed_requests_per_second"] == 0.2
    assert s["rates"]["completed_output_tokens_per_second"] == 2
    assert s["completed_tokens"] == {"input": 40, "output": 20}
    assert s["missing_usage"] == 2
    assert s["distributions"]["client_duration"]["n"] == 2
    assert s["distributions"]["request_mean_itl"]["p50"] == 0.020
    assert s["distributions"]["engine_ttft"]["p50"] is None
    assert s["outcomes"] == {"ok": 2, "error": 1, "intentional_early_close": 1}


def test_no_completed_requests_do_not_produce_zero_latency():
    s = summarize([row("bad", 1, 2, "error", first=None)], {})["test"]
    assert s["distributions"]["client_first_content"]["n"] == 0
    assert s["distributions"]["client_first_content"]["p99"] is None
    assert s["rates"]["completed_requests_per_second"] == 0
    assert s["rates"]["attempted_requests_per_second"] == 1


def test_scenario_populations_are_not_mixed():
    a, b = row("a", 0, 2), row("b", 0, 8)
    b["scenario"] = "other"
    s = summarize([a, b], {})
    assert s["test"]["distributions"]["client_duration"]["p90"] == 2
    assert s["other"]["distributions"]["client_duration"]["p90"] == 8
    assert s["all"]["rates"]["completed_requests_per_second"] == 0.25
    with pytest.raises(ValueError):
        summarize([a, a], {})


def test_metric_only_send_is_journaled_without_traces_or_logs(tmp_path):
    import hashlib

    payload = b"valid-protobuf-is-not-needed-before-the-network"
    (tmp_path / "metrics.pb").write_bytes(payload)
    (tmp_path / "manifest.json").write_text(
        json.dumps({"sha256": {"metrics": hashlib.sha256(payload).hexdigest()}})
    )
    with (
        patch("urllib.request.urlopen", side_effect=TimeoutError) as network,
        pytest.raises(TimeoutError),
    ):
        send(tmp_path, "http://127.0.0.1:24318", signals=("metrics",))
    assert network.call_args.args[0].full_url.endswith("/v1/metrics")
    with (
        patch("urllib.request.urlopen") as network,
        pytest.raises(ValueError, match="receipts"),
    ):
        send(tmp_path, "http://127.0.0.1:24318", signals=("metrics",))
    network.assert_not_called()


def test_scorecard_filters_fixed_population_and_uses_scaled_gauges():
    report = json.loads(DEFAULT_REPORT.read_text())
    report["replay_id"] = "test-replay"
    dashboard = build("test-replay", "baseline", report=report)
    assert len(dashboard["spec"]["panels"]) == 12
    for panel in dashboard["spec"]["panels"].values():
        assert panel["spec"]["plugin"]["kind"] == "GaugeChart"
        assert panel["spec"]["plugin"]["spec"]["dash0Extensions"] == {
            "maxTimeSeries": 4,
            "displayMode": "normal",
            "hideSeriesName": False,
        }
        assert panel["spec"]["plugin"]["spec"]["calculation"] == "last-number"
        assert panel["spec"]["plugin"]["spec"]["max"] > 0
        for q in panel["spec"]["queries"]:
            query = q["spec"]["plugin"]["spec"]["query"]
            assert 'inference_scenario="baseline"' in query
            assert 'inference_replay_id="test-replay"' in query
            assert "histogram_quantile" not in query
    for key, quantiles in report["scenarios"]["baseline"]["distributions"].items():
        assert (
            dashboard["spec"]["panels"][key]["spec"]["plugin"]["spec"]["max"]
            > quantiles["p99"]
        )
    with pytest.raises(ValueError, match="Report replay ID"):
        build("different-replay", report=report)
    with pytest.raises(ValueError):
        build("test-replay", 'bad"selector')


def test_supplement_validates_archive_and_keeps_source_payloads_unchanged(tmp_path):
    from capture import prepare as prepare_replay
    from inference_metrics import prepare
    from test_replay import archive

    root, _ = archive(tmp_path)
    replay = tmp_path / "replay"
    prepare_replay(root, replay, "fixture-replay")
    before = (replay / "traces.pb").read_bytes()
    report = prepare(root, replay, tmp_path / "scorecard")
    assert report["scenarios"]["baseline"]["completed_tokens"]["output"] == 3
    assert (
        report["scenarios"]["baseline"]["rates"]["completed_requests_per_second"] == 0.5
    )
    assert (replay / "traces.pb").read_bytes() == before
    assert not (tmp_path / "scorecard" / "traces.pb").exists()
    assert "prompt" not in json.dumps(report)
    with pytest.raises(ValueError, match="empty output"):
        prepare(root, replay, tmp_path / "scorecard")
    (root / "workload/request-index.json").write_text("[]")
    with pytest.raises(ValueError, match="Checksum"):
        prepare(root, replay, tmp_path / "tampered")
    assert not (tmp_path / "tampered").exists()


def test_supplement_does_not_trust_mismatched_index_fields(tmp_path):
    import hashlib

    from capture import prepare as prepare_replay
    from inference_metrics import prepare
    from test_replay import archive

    root, _ = archive(tmp_path)
    replay = tmp_path / "replay"
    prepare_replay(root, replay, "fixture-replay")
    file = root / "workload/request-index.json"
    rows = json.loads(file.read_text())
    rows[0]["duration_s"] = 900
    file.write_text(json.dumps(rows))
    checksums = json.loads((root / "SHA256SUMS.json").read_text())
    checksums["workload/request-index.json"] = hashlib.sha256(
        file.read_bytes()
    ).hexdigest()
    (root / "SHA256SUMS.json").write_text(json.dumps(checksums))
    with pytest.raises(ValueError, match="differs"):
        prepare(root, replay, tmp_path / "mismatch")
