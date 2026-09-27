"""Build zoomed GIF walkthroughs from captured Dash0 UI, without altering values."""

from pathlib import Path

from animate import ASSETS, CORAL, ORANGE, RED, Detail, Scene, build

FOOTER = (
    "REAL H100 CAPTURE REPLAYED INTO DASH0  /  ACTUAL UI EXCERPTS  /  SEPT 27, 2026"
)
latency = [
    Scene(
        "dashboard-request",
        "Detect",
        "Spot the slow response window",
        "Queue pressure moves first-content latency.",
        "Compare the client measurement with native engine queue time.",
        ORANGE,
        (
            Detail(
                (630, 235, 2900, 865), (36, 217, 1244, 552), "15-SECOND ROLLING MAXIMA"
            ),
        ),
    ),
    Scene(
        "trace-graph",
        "Trace",
        "Follow the request across services",
        "Client context reaches the vLLM serving layer.",
        "The replay preserves the original span IDs and parent relationships.",
        CORAL,
        (
            Detail((510, 450, 1370, 1225), (36, 202, 471, 594), "DISTRIBUTED TRACE"),
            Detail(
                (1940, 820, 2890, 1065),
                (500, 262, 1244, 454),
                "NATIVE REQUEST TIMINGS",
                (((1940, 945, 2890, 1065), ORANGE),),
            ),
        ),
    ),
    Scene(
        "queue-attributes",
        "Queue",
        "Find where this request spent its time",
        "23.05 s queue. 53 ms prefill. 6.11 s decode.",
        "Queue wait accounts for most of this 29.22-second engine request.",
        ORANGE,
        (
            Detail(
                (1940, 565, 2890, 1065),
                (240, 185, 1040, 606),
                "SECONDS, RECORDED BY VLLM",
                (((1940, 945, 2890, 1065), ORANGE), ((1940, 820, 2890, 939), CORAL)),
            ),
        ),
    ),
    Scene(
        "prefill-attributes",
        "Prefill",
        "Contrast with a long input prompt",
        "3.44 s prefill. Only 56 microseconds queued.",
        "The bottleneck changes; first-content latency alone cannot explain it.",
        CORAL,
        (
            Detail(
                (1940, 820, 2890, 1185),
                (95, 198, 1185, 617),
                "A DIFFERENT NATIVE REQUEST",
                (((1940, 820, 2890, 939), CORAL), ((1940, 945, 2890, 1065), ORANGE)),
            ),
        ),
    ),
]
failure = [
    Scene(
        "error-log",
        "Find",
        "Find the rejected request in Logs",
        "61 outcome logs. One deliberate rejection.",
        "The logs come from preserved request records and carry trace context.",
        RED,
        (
            Detail((0, 12, 2050, 92), (36, 215, 1244, 262), "INGESTED OUTCOMES"),
            Detail(
                (0, 955, 1900, 1265),
                (36, 310, 1244, 507),
                "SELECT THE ERROR RECORD",
                (((0, 1170, 1900, 1230), RED),),
            ),
        ),
    ),
    Scene(
        "log-trace-pivot",
        "Correlate",
        "Pivot from the log into its request",
        "The error log links to the failing client span.",
        "The same trace ID and span ID connect the archived outcome to the trace.",
        CORAL,
        (
            Detail(
                (1940, 1085, 2890, 1450),
                (165, 190, 1115, 555),
                "SPAN CONTEXT IN THE LOG DETAIL",
                (((2600, 1090, 2865, 1158), CORAL), ((1950, 1340, 2850, 1415), RED)),
            ),
        ),
    ),
    Scene(
        "error-trace",
        "Explain",
        "Read why the request was rejected",
        "9,000 requested output tokens; 8,192 limit.",
        "Validation failed before generation. This is not a mid-stream failure.",
        RED,
        (
            Detail(
                (0, 192, 1890, 386), (36, 198, 1244, 322), "THE FAILED CLIENT REQUEST"
            ),
            Detail(
                (1940, 920, 2890, 1215),
                (230, 354, 1050, 608),
                "RECORDED BADREQUESTERROR",
            ),
        ),
    ),
]
resources = [
    Scene(
        "services",
        "Discover",
        "Discover the telemetry resources",
        "Two traced services and an H100 metric source.",
        "Service request totals use entry spans; the workload contains 61 calls.",
        CORAL,
        (
            Detail(
                (620, 290, 2900, 725),
                (36, 230, 1244, 461),
                "SERVICES OBSERVED BY DASH0",
            ),
        ),
    ),
    Scene(
        "dashboard-gpu",
        "Correlate",
        "Inspect the GPU on the same time axis",
        "100% utilization appears in the preserved samples.",
        "GPU utilization and allocated memory come from recorded nvidia-smi data.",
        ORANGE,
        (
            Detail(
                (635, 645, 2900, 1390),
                (36, 187, 1244, 584),
                "15-SECOND ROLLING MAXIMA OF ACTUAL GPU SAMPLES",
            ),
        ),
    ),
]
if __name__ == "__main__":
    for name, scenes in [
        ("latency", latency),
        ("failure", failure),
        ("resources", resources),
    ]:
        build(
            scenes,
            ASSETS / f"{name}-walkthrough.gif",
            Path("artifacts/animation-preview") / name,
            FOOTER,
        )
