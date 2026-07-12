"""Unit tests for the simulator queueing model and metric naming."""

import importlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "simulator"))

main = importlib.import_module("main")


def test_arrival_rate_boosts_during_incident():
    calm = main.arrival_rate(10.0, incident_active=False)
    hot = main.arrival_rate(10.0, incident_active=True)
    assert hot == pytest.approx(calm * main.INCIDENT_BOOST)


def test_arrival_rate_stays_positive():
    for t in (0.0, 150.0, 300.0, 599.0):
        assert main.arrival_rate(t, False) > 0


def test_incident_active_at_trailing_window():
    period = main.INCIDENT_PERIOD_S
    duration = main.INCIDENT_DURATION_S
    # calm for most of the period
    assert main.incident_active_at(period - duration - 1) is False
    # trailing burst window
    assert main.incident_active_at(period - duration + 1) is True
    assert main.incident_active_at(period - 1) is True


def test_steady_scenario_never_incidents():
    assert main.incident_active_at(100.0, period=86_400.0, duration=0.0) is False
    assert main.incident_active_at(86_399.0, period=86_400.0, duration=0.0) is False


def test_resolve_incident_knobs_presets(monkeypatch):
    monkeypatch.delenv("INCIDENT_PERIOD_S", raising=False)
    monkeypatch.delenv("INCIDENT_DURATION_S", raising=False)
    monkeypatch.delenv("INCIDENT_BOOST", raising=False)
    period, duration, boost = main._resolve_incident_knobs("steady")
    assert duration == 0.0
    assert boost == 1.0
    period, duration, boost = main._resolve_incident_knobs("recovery")
    assert period == 180.0
    assert duration == 45.0
    assert boost == 2.5


def test_new_request_has_required_fields():
    req = main.new_request(1_700_000_000.0)
    assert req["arrival"] == 1_700_000_000.0
    assert req["profile"] in {p[0] for p in main.PROFILES}
    assert req["prompt_tokens"] >= 8
    assert req["output_tokens"] >= 4
    assert req["generated"] == 0
    assert req["ttft"] is None


def test_sample_profile_returns_known_profile():
    name, prompt, out = main.sample_profile()
    assert name in {p[0] for p in main.PROFILES}
    assert prompt >= 8
    assert out >= 4


def test_vllm_metric_names_use_colon_prefix():
    names = {c.name for c in main.vllm_reg.collect()}
    assert "vllm:time_to_first_token_seconds" in names
    assert "vllm:num_requests_waiting" in names
    assert "vllm:kv_cache_usage_perc" in names


def test_dcgm_metric_names_match_exporter():
    names = {c.name for c in main.dcgm_reg.collect()}
    assert "DCGM_FI_DEV_GPU_UTIL" in names
    assert "DCGM_FI_DEV_FB_USED" in names
    assert "DCGM_FI_DEV_POWER_USAGE" in names
