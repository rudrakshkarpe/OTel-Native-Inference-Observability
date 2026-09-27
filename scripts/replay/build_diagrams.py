"""Build Dash0-focused SVG documentation from the verified capture facts."""

from html import escape
from pathlib import Path

OUT = Path("docs/diagrams")
LOGO = Path("docs/assets/dash0/logo-white.svg").read_text()
LOGO_BODY = LOGO[LOGO.index(">") + 1 : LOGO.rindex("</svg>")]
CORAL = "#f8494d"
ORANGE = "#fd8c66"


def text(x, y, label, size=20, color="#ffffff", weight=400):
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}">{escape(label)}</text>'
    )


def logo(x, y, scale=2):
    return f'<g transform="translate({x} {y}) scale({scale})">{LOGO_BODY}</g>'


def rect(x, y, w, h, fill="#212121", stroke="#424242", radius=16):
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
        f'fill="{fill}" stroke="{stroke}"/>'
    )


def arrow(x1, y1, x2, y2):
    return (
        f'<path d="M{x1} {y1} L{x2} {y2}" fill="none" '
        f'stroke="{ORANGE}" stroke-width="2" marker-end="url(#arrow)"/>'
    )


def shell(title, subtitle, body, filename, height=720):
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="{height}" '
        f'viewBox="0 0 1280 {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(title)}</title><desc id="desc">{escape(subtitle)}</desc>'
        '<defs><linearGradient id="warm"><stop stop-color="#f8494d"/>'
        '<stop offset="1" stop-color="#fd8c66"/></linearGradient>'
        '<marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" '
        'orient="auto"><path d="M0 0 L8 4 L0 8" fill="#fd8c66"/></marker></defs>'
        '<rect width="100%" height="100%" fill="#101010"/>'
        '<rect width="1280" height="6" fill="url(#warm)"/>'
        '<g font-family="Arial, Helvetica, sans-serif">'
        + logo(48, 32, 1.6)
        + text(244, 57, "INFERENCE OBSERVATORY", 15, "#bdbdbd", 600)
        + text(48, 127, title, 38, "#ffffff", 700)
        + text(48, 165, subtitle, 19, "#bdbdbd")
        + body
        + text(
            48,
            height - 27,
            "COMMUNITY PROJECT  /  REAL H100 CAPTURE  /  OTLP INTO DASH0",
            13,
            "#9e9e9e",
        )
        + "</g></svg>\n"
    )
    (OUT / filename).write_text(svg)


def card(x, y, w, h, number, title, lines):
    s = rect(x, y, w, h)
    s += text(x + 24, y + 35, number, 14, ORANGE, 700)
    s += text(x + 24, y + 72, title, 25, "#ffffff", 700)
    for i, line in enumerate(lines):
        s += text(x + 24, y + 112 + i * 29, line, 18, "#bdbdbd")
    return s


hero = text(48, 252, "One workload. Three signals.", 50, "#ffffff", 700)
hero += text(48, 314, "Investigated in Dash0.", 50, ORANGE, 700)
hero += text(
    48,
    363,
    "Gemma 4 12B + vLLM + H100 → OpenTelemetry Collector → Dash0",
    23,
    "#bdbdbd",
)
for x, value, label in [
    (48, "123", "correlated spans"),
    (350, "61", "request outcome logs"),
    (652, "8", "dashboard panels"),
    (954, "158", "GPU observations"),
]:
    hero += rect(x, 415, 278, 128)
    hero += text(x + 24, 469, value, 40, ORANGE, 700)
    hero += text(x + 24, 511, label, 18, "#bdbdbd")
hero += text(
    48,
    592,
    "Recorded on real hardware. Replayed through OTLP. Verified through the Dash0 API.",
    20,
)
shell(
    "GPU inference, explained.",
    "Distributed tracing · Correlated logs · PromQL dashboards · Hosted verification",
    hero,
    "dash0-inference-hero.svg",
    665,
)

body = card(
    48,
    210,
    334,
    305,
    "01 / REAL CAPTURE",
    "H100 + vLLM",
    [
        "61 client requests",
        "W3C trace context propagation",
        "56 native engine request spans",
        "Queue / prefill / decode timings",
        "158 nvidia-smi observations",
    ],
)
body += card(
    420,
    210,
    334,
    305,
    "02 / OPEN TELEMETRY",
    "Archive → Collector",
    [
        "Verify source SHA-256 hashes",
        "Shift timestamps consistently",
        "Preserve span relationships",
        "Derive outcome logs + gauges",
        "Three authenticated OTLP paths",
    ],
)
body += rect(792, 210, 440, 380, "#212121", CORAL)
body += logo(820, 239, 2)
body += text(820, 319, "The investigation workspace", 25, "#ffffff", 700)
for i, line in enumerate(
    [
        "Tracing: client → engine waterfall",
        "Logs: request outcome → failing span",
        "Dashboards: timings + GPU context",
        "Services: discover telemetry resources",
        "API: verify IDs, parents and durations",
    ]
):
    body += text(820, 362 + i * 38, line, 18, "#bdbdbd")
body += arrow(383, 365, 414, 365) + arrow(755, 365, 786, 365)
body += text(48, 557, "Capture provenance is retained.", 22, ORANGE, 700)
body += text(
    48,
    594,
    "Historical GPU records; no live endpoint or invented engine-stage spans.",
    19,
    "#bdbdbd",
)
body += text(
    48,
    627,
    "Dash0 ingestion is checked by reading the hosted telemetry back.",
    19,
    "#bdbdbd",
)
shell(
    "From inference serving to Dash0",
    "The tested integration carries traces, logs and metrics through the same Collector.",
    body,
    "dash0-evidence-architecture.svg",
)

body = ""
for y, number, title, lines in [
    (
        211,
        "TRACES",
        "Request context",
        ["6 traces / 123 spans", "Client → native vLLM request"],
    ),
    (
        350,
        "LOGS",
        "Request outcomes",
        ["61 correlated log records", "Trace ID + span ID retained"],
    ),
    (
        489,
        "METRICS",
        "Timings + GPU",
        ["1,079 prepared data points", "Derived from archived observations"],
    ),
]:
    body += rect(48, y, 360, 120)
    body += text(70, y + 29, number, 13, ORANGE, 700)
    body += text(70, y + 59, title, 23, "#ffffff", 700)
    body += text(70, y + 88, lines[0], 18, "#bdbdbd")
    body += arrow(409, y + 60, 461, y + 60)
body += card(
    468,
    211,
    306,
    398,
    "TRANSPORT",
    "OTel Collector",
    [
        "Loopback OTLP/HTTP",
        "Memory limiter + batch",
        "OTLP/gRPC over TLS",
        "Bearer authentication",
        "Dataset selection",
        "Separate signal pipelines",
    ],
)
body += arrow(775, 410, 829, 410)
body += card(
    836,
    211,
    396,
    398,
    "DASH0",
    "Explore + verify",
    [
        "Distributed trace investigation",
        "Log-to-trace navigation",
        "PromQL metric queries",
        "Eight-panel Perses dashboard",
        "Services resource inventory",
        "Public API readback checks",
    ],
)
shell(
    "Three signals. One Dash0 integration.",
    "OpenTelemetry is the transport; Dash0 is where the captured workload is investigated.",
    body,
    "reference-architecture.svg",
)

body = ""
for x, n, title, lines in [
    (
        48,
        "01 / TRACING",
        "Where did time go?",
        [
            "Inspect the native request.",
            "23.046 s queued",
            "0.053 s prefill",
            "6.108 s decode",
        ],
    ),
    (
        450,
        "02 / LOGS → TRACE",
        "Why did it fail?",
        [
            "Follow the request outcome.",
            "9,000 output tokens requested",
            "8,192 configured limit",
            "HTTP 400 before generation",
        ],
    ),
    (
        852,
        "03 / DASHBOARDS",
        "What did GPU do?",
        [
            "Use the same time window.",
            "158 recorded observations",
            "100% utilization peak",
            "Context, not proof of cause",
        ],
    ),
]:
    body += card(x, 225, 380, 306, n, title, lines)
body += text(
    48,
    588,
    "Dash0 connects the investigation to the underlying evidence.",
    27,
    ORANGE,
    700,
)
body += text(
    48,
    631,
    "A slow request, a rejected request and GPU activity answer different questions.",
    21,
    "#bdbdbd",
)
shell(
    "Turn inference symptoms into questions",
    "Actual captured cases, explored through Dash0 traces, logs and dashboards.",
    body,
    "problem.svg",
)

body = card(
    48,
    226,
    360,
    300,
    "01 / FIND IN DASH0 LOGS",
    "Locate the outcome",
    [
        "Filter by inference.replay.id",
        "Select the error log",
        "Read BadRequestError",
        "Keep its trace + span context",
    ],
)
body += card(
    460,
    226,
    360,
    300,
    "02 / OPEN THE TRACE",
    "Follow the same request",
    [
        "Open the linked client span",
        "Inspect the exception event",
        "Confirm HTTP 400",
        "No engine generation child",
    ],
)
body += card(
    872,
    226,
    360,
    300,
    "03 / EXPLAIN THE FAILURE",
    "Validate the boundary",
    [
        "9,000 requested output tokens",
        "8,192 configured limit",
        "Rejected before generation",
        "One intentional invalid request",
    ],
)
body += arrow(409, 380, 454, 380) + arrow(821, 380, 866, 380)
body += text(
    48, 586, "Correlation is verified, not inferred from timing.", 28, ORANGE, 700
)
body += text(
    48,
    631,
    "Dash0 API readback confirms all 61 log-to-span pairs and the captured exception event.",
    21,
    "#bdbdbd",
)
shell(
    "From a Dash0 log to an explained error",
    "A real validation failure with preserved request context.",
    body,
    "incident-correlation.svg",
)

print("Built five Dash0 documentation SVGs.")
