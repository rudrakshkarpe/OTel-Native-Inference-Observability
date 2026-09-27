"""Create a Dash0 inference scorecard from exact recorded scenario statistics."""

import argparse
import json
import math
import re
from pathlib import Path
from urllib.parse import quote

from dash0_api import Dash0
from inference_metrics import DEFINITIONS

DEFAULT_REPORT = (
    Path(__file__).resolve().parents[2] / "docs/evidence/inference-scorecard.json"
)


def build(replay_id, scenario="queue-pressure", *, report=None):
    for value in (replay_id, scenario):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
            raise ValueError("Invalid replay ID or scenario")
    if report is None:
        report = json.loads(DEFAULT_REPORT.read_text())
    if report["replay_id"] != replay_id:
        raise ValueError("Report replay ID must match dashboard replay ID")
    summary = report["scenarios"][scenario]
    base = f'inference_replay_id="{replay_id}",inference_summary_id="inference-scorecard-v1",inference_scenario="{scenario}"'
    panels = {}
    definitions = [
        (
            key,
            title,
            "seconds" if unit == "s" else "decimal",
            [(key, "p{{percentile}} / n={{sample_count}}")],
        )
        for key, (title, unit, *_) in DEFINITIONS.items()
    ]
    definitions.extend(
        [
            (
                "request-rate",
                "Scenario throughput: requests/s",
                "decimal",
                [
                    ("attempted_requests_per_second", "attempted requests/s"),
                    ("completed_requests_per_second", "completed requests/s"),
                ],
            ),
            (
                "token-rate",
                "Scenario throughput: tokens/s",
                "decimal",
                [
                    ("completed_input_tokens_per_second", "input tokens/s"),
                    ("completed_output_tokens_per_second", "output tokens/s"),
                ],
            ),
            (
                "outcomes",
                "Request outcomes and missing usage",
                "decimal",
                [
                    ("outcome_count", "{{inference_outcome}}"),
                    ("missing_usage", "missing final usage"),
                ],
            ),
            (
                "token-count",
                "Completed-request token counts",
                "decimal",
                [("token_count", "{{token_type}} tokens")],
            ),
        ]
    )
    for key, title, unit, queries in definitions:
        if key in DEFINITIONS:
            values = [summary["distributions"][key][f"p{p}"] for p in (50, 90, 95, 99)]
        elif key in ("request-rate", "token-rate"):
            values = [summary["rates"][name] for name, _ in queries]
        elif key == "outcomes":
            values = [*summary["outcomes"].values(), summary["missing_usage"]]
        else:
            values = list(summary["completed_tokens"].values())
        largest = max((value for value in values if value is not None), default=0)
        # One common zero-based scale per panel, rounded up with visible headroom.
        step = 10 ** math.floor(math.log10(largest)) if largest > 0 else 1
        maximum = math.ceil(largest * 1.1 / step) * step if largest > 0 else 1
        scale_unit = "s" if unit == "seconds" else ""
        description = (
            f"Completed requests: nearest-rank percentiles for {scenario}."
            if key in DEFINITIONS
            else f"Whole-scenario totals and wall-time rates for {scenario}."
        ) + f" Scale: 0 to {maximum:g}{scale_unit}."
        panels[key] = {
            "kind": "Panel",
            "spec": {
                "display": {
                    "name": title,
                    "description": description,
                },
                "plugin": {
                    "kind": "GaugeChart",
                    "spec": {
                        "calculation": "last-number",
                        "format": {"unit": unit},
                        "max": maximum,
                        "visual": {"palette": {"mode": "categorical"}},
                        "dash0Extensions": {
                            "maxTimeSeries": 4,
                            "displayMode": "normal",
                            "hideSeriesName": False,
                        },
                    },
                },
                "queries": [
                    {
                        "kind": "TimeSeriesQuery",
                        "spec": {
                            "plugin": {
                                "kind": "PrometheusTimeSeriesQuery",
                                "spec": {
                                    "query": 'max_over_time({otel_metric_name="inference_lab.summary.'
                                    + name
                                    + '",'
                                    + base
                                    + "}[15s])",
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
        "metadata": {"name": "inference-scorecard-" + scenario, "project": "default"},
        "spec": {
            "display": {
                "name": f"Dash0 inference scorecard: {scenario}",
                "description": f"Exact fixed-capture statistics, replay {replay_id}. Completed-request percentiles and scenario wall-time throughput. Select the replay window; no live GPU is running.",
            },
            "duration": "1h",
            "panels": panels,
            "layouts": [
                {
                    "kind": "Grid",
                    "spec": {
                        "display": {"title": title, "collapse": {"open": True}},
                        "items": [
                            {
                                "x": i % 2 * 12,
                                "y": i // 2 * 7,
                                "width": 12,
                                "height": 7,
                                "content": {"$ref": "#/spec/panels/" + key},
                            }
                            for i, key in enumerate(keys)
                        ],
                    },
                }
                for title, keys in [
                    ("Completed-request percentile comparisons", list(panels)[:8]),
                    ("Whole-scenario throughput and outcomes", list(panels)[8:]),
                ]
            ],
        },
    }


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--replay-id", required=True)
    p.add_argument("--scenario", default="queue-pressure")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    a = p.parse_args()
    body = build(a.replay_id, a.scenario, report=json.loads(a.report.read_text()))
    dest = Path("dashboards/perses/inference-scorecard-" + a.scenario + ".json")
    dest.write_text(json.dumps(body, indent=2) + "\n")
    if a.apply:
        api = Dash0()
        dataset = api.config["dataset"]
        body["metadata"]["project"] = dataset
        response = api.call(
            "/api/dashboards/inference-scorecard-"
            + a.scenario
            + "-"
            + quote(dataset, safe="")
            + "?dataset="
            + quote(dataset, safe=""),
            body,
            method="PUT",
        )
        Path("artifacts").mkdir(exist_ok=True)
        Path("artifacts/scorecard-dashboard-response.json").write_text(
            json.dumps(response, indent=2)
        )
        print(json.dumps({"dashboard": response["metadata"]}))
    else:
        print(dest)
