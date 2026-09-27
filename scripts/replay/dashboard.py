"""Create a replay-scoped Perses dashboard using real, documented measurement sources."""

import argparse
import json
import re
from pathlib import Path

from dash0_api import Dash0


def build(replay_id):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", replay_id):
        raise ValueError("Invalid replay ID")
    selector = '{inference_replay_id="' + replay_id + '"}'
    panels = {}
    definitions = [
        (
            "first-content",
            "Client: first content",
            "Recorded per-request client timings. Includes SSH/network transport.",
            "seconds",
            [("inference_lab_request_first_content_seconds", "{{inference_scenario}}")],
        ),
        (
            "queue",
            "Engine: queue wait",
            "Derived from native vLLM span attributes, in seconds.",
            "seconds",
            [("inference_lab_engine_queue_seconds", "{{inference_scenario}}")],
        ),
        (
            "execution",
            "Engine: prefill and decode",
            "Native engine request statistics. These are not GPU kernel profiles.",
            "seconds",
            [
                (
                    "inference_lab_engine_prefill_seconds",
                    "prefill / {{inference_scenario}}",
                ),
                (
                    "inference_lab_engine_decode_seconds",
                    "decode / {{inference_scenario}}",
                ),
            ],
        ),
        (
            "duration",
            "Client: full request duration",
            "Includes completed, rejected and intentionally closed requests; consult outcome logs.",
            "seconds",
            [("inference_lab_request_duration_seconds", "{{inference_scenario}}")],
        ),
        (
            "gpu-utilization",
            "H100: GPU utilization",
            "Recorded nvidia-smi samples with the same replay timestamp shift. No DCGM data is claimed.",
            "percent",
            [
                ("inference_lab_gpu_utilization_percent", "H100 GPU"),
                ("inference_lab_gpu_memory_utilization_percent", "memory controller"),
            ],
        ),
        (
            "gpu-memory",
            "H100: allocated GPU memory",
            "nvidia-smi used memory, converted from MiB to bytes. Includes model and KV-cache reservation.",
            "bytes",
            [("inference_lab_gpu_memory_used_bytes", "GPU memory")],
        ),
        (
            "gpu-power",
            "H100: power draw",
            "Actual nvidia-smi power samples.",
            "watts",
            [("inference_lab_gpu_power_watts", "power")],
        ),
        (
            "gpu-temperature",
            "H100: temperature",
            "Actual nvidia-smi temperature samples.",
            "celsius",
            [("inference_lab_gpu_temperature_celsius", "temperature")],
        ),
    ]
    for key, title, description, unit, queries in definitions:
        panels[key] = {
            "kind": "Panel",
            "spec": {
                "display": {
                    "name": title,
                    "description": description
                    + " Chart shows a 15-second rolling maximum of recorded observations.",
                },
                "plugin": {
                    "kind": "TimeSeriesChart",
                    "spec": {"yAxis": {"format": {"unit": unit}}},
                },
                "queries": [
                    {
                        "kind": "TimeSeriesQuery",
                        "spec": {
                            "plugin": {
                                "kind": "PrometheusTimeSeriesQuery",
                                "spec": {
                                    "query": "max_over_time("
                                    + name
                                    + selector
                                    + "[15s])",
                                    "seriesNameFormat": legend,
                                },
                            }
                        },
                    }
                    for name, legend in queries
                ],
            },
        }
    return {
        "kind": "Dashboard",
        "metadata": {"name": "h100-real-inference", "project": "default"},
        "spec": {
            "display": {
                "name": "H100 inference: queue, execution and GPU",
                "description": f"Real Gemma 4 12B capture, replay {replay_id}. Time-shifted evidence, not live inference. Request outcomes are in Logs; request parent links are in Tracing.",
            },
            "duration": "1h",
            "panels": panels,
            "layouts": [
                {
                    "kind": "Grid",
                    "spec": {
                        "display": {
                            "title": "Request and engine timings",
                            "collapse": {"open": True},
                        },
                        "items": [
                            {
                                "x": (i % 2) * 12,
                                "y": (i // 2) * 8,
                                "width": 12,
                                "height": 8,
                                "content": {"$ref": "#/spec/panels/" + key},
                            }
                            for i, key in enumerate(list(panels)[:4])
                        ],
                    },
                },
                {
                    "kind": "Grid",
                    "spec": {
                        "display": {
                            "title": "GPU samples: nvidia-smi",
                            "collapse": {"open": True},
                        },
                        "items": [
                            {
                                "x": (i % 2) * 12,
                                "y": (i // 2) * 8,
                                "width": 12,
                                "height": 8,
                                "content": {"$ref": "#/spec/panels/" + key},
                            }
                            for i, key in enumerate(list(panels)[4:])
                        ],
                    },
                },
            ],
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replay-id", required=True)
    p.add_argument("--apply", action="store_true")
    a = p.parse_args()
    body = build(a.replay_id)
    dest = Path("dashboards/perses/h100-real-inference.json")
    dest.write_text(json.dumps(body, indent=2) + "\n")
    if a.apply:
        api = Dash0()
        from urllib.parse import quote

        dataset = api.config["dataset"]
        body["metadata"]["project"] = dataset
        response = api.call(
            "/api/dashboards/h100-real-inference-"
            + quote(dataset, safe="")
            + "?dataset="
            + quote(dataset, safe=""),
            body,
            method="PUT",
        )
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/dashboard-response.json").write_text(
            json.dumps(response, indent=2)
        )
        print(json.dumps({"dashboard": response["metadata"]}))
    else:
        print(dest)
