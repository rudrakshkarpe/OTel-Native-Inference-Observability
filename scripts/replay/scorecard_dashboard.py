"""Create a Dash0 inference scorecard from exact recorded scenario statistics."""

import argparse
import json
import re
from pathlib import Path
from urllib.parse import quote

from dash0_api import Dash0
from inference_metrics import DEFINITIONS


def build(replay_id, scenario="queue-pressure"):
    for value in (replay_id, scenario):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", value):
            raise ValueError("Invalid replay ID or scenario")
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
        panels[key] = {
            "kind": "Panel",
            "spec": {
                "display": {
                    "name": title,
                    "description": f"Fixed whole-scenario statistic for {scenario}. Percentiles: nearest-rank over completed requests, with n shown. Rates: counts divided by earliest start to latest end. Missing usage is excluded from token totals. Values are recorded at capture end; not rolling live estimates.",
                },
                "plugin": {
                    "kind": "StatChart",
                    "spec": {
                        "calculation": "last-number",
                        "format": {"unit": unit},
                        "dash0Extensions": {"maxTimeSeries": 4},
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
                                "y": i // 2 * 4,
                                "width": 12,
                                "height": 4,
                                "content": {"$ref": "#/spec/panels/" + key},
                            }
                            for i, key in enumerate(keys)
                        ],
                    },
                }
                for title, keys in [
                    ("Completed-request distributions", list(panels)[:8]),
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
    a = p.parse_args()
    body = build(a.replay_id, a.scenario)
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
