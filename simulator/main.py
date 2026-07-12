"""LLM inference workload simulator.

Impersonates a vLLM server and NVIDIA DCGM exporter closely enough that an
OpenTelemetry Collector pipeline (and any dashboard built on it) is identical
between this demo mode and a real GPU deployment:

  - :8000/metrics  -> vLLM-named Prometheus metrics (vllm:*)
  - :9400/metrics  -> DCGM-named Prometheus metrics (DCGM_FI_*)
  - OTLP/gRPC      -> one span per inference request, following the
                      OpenTelemetry GenAI semantic conventions (gen_ai.*),
                      plus vLLM-style structured logs. Per-request logs carry
                      the request's trace context, so a 429/500 log line links
                      straight to its trace in the backend.

The workload model is a small queueing simulation: Poisson arrivals modulated
by a sped-up diurnal curve, a bounded running batch, queue-driven TTFT, and a
periodic saturation incident (traffic burst -> queue growth -> KV cache
pressure -> P99 TTFT spike -> 429s) so the telemetry tells a story.
"""

import logging
import math
import os
import random
import time

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    disable_created_metrics,
    start_http_server,
)

disable_created_metrics()  # real vLLM/DCGM exporters don't emit *_created series

from opentelemetry import trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import SpanKind, Status, StatusCode

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_NAME = os.getenv("MODEL_NAME", "qwen2.5-7b-instruct")
OTLP_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "vllm-server")

TICK_S = 0.5                 # simulation step
BASE_RPS = float(os.getenv("BASE_RPS", "0.6"))
DIURNAL_PERIOD_S = float(os.getenv("DIURNAL_PERIOD_S", "600"))   # sped-up "day"
INCIDENT_PERIOD_S = float(os.getenv("INCIDENT_PERIOD_S", "420"))
INCIDENT_DURATION_S = float(os.getenv("INCIDENT_DURATION_S", "90"))
INCIDENT_BOOST = float(os.getenv("INCIDENT_BOOST", "3.0"))

MAX_RUNNING = 24             # concurrent decode batch cap
MAX_WAITING = 64             # queue bound; beyond this new requests get 429
KV_CACHE_TOKENS = 64_000     # token capacity across the cache

PREFILL_TOKS_PER_S = 12_000.0
BASE_TPOT_S = 0.013          # per-output-token latency at batch size 1 (~75 tok/s)

GPUS = [
    {"gpu": "0", "UUID": "GPU-8f2a1c34-demo-0000-0000-000000000000"},
    {"gpu": "1", "UUID": "GPU-8f2a1c34-demo-0000-0000-000000000001"},
]
GPU_MODEL = "NVIDIA H100 80GB HBM3"
FB_TOTAL_MIB = 81_559
HOSTNAME = os.getenv("HOSTNAME", "gpu-node-demo")

# prompt/output token distributions per traffic profile: (weight, prompt_mu, out_mu)
PROFILES = [
    ("chat", 0.6, 300, 150),
    ("rag", 0.25, 2500, 300),
    ("longgen", 0.15, 500, 900),
]

# ---------------------------------------------------------------------------
# Prometheus metrics — names/labels mirror vLLM and dcgm-exporter exactly
# ---------------------------------------------------------------------------

vllm_reg = CollectorRegistry()
dcgm_reg = CollectorRegistry()

L = ["model_name"]

NUM_RUNNING = Gauge("vllm:num_requests_running", "Requests currently running", L, registry=vllm_reg)
NUM_WAITING = Gauge("vllm:num_requests_waiting", "Requests waiting in queue", L, registry=vllm_reg)
KV_USAGE = Gauge("vllm:kv_cache_usage_perc", "KV-cache usage. 1 means 100 percent usage", L, registry=vllm_reg)

PROMPT_TOKENS = Counter("vllm:prompt_tokens", "Number of prefill tokens processed", L, registry=vllm_reg)
GEN_TOKENS = Counter("vllm:generation_tokens", "Number of generation tokens processed", L, registry=vllm_reg)
REQ_SUCCESS = Counter("vllm:request_success", "Count of successfully processed requests", L + ["finished_reason"], registry=vllm_reg)
PREFIX_QUERIES = Counter("vllm:prefix_cache_queries", "Prefix cache queries, in terms of number of queried tokens", L, registry=vllm_reg)
PREFIX_HITS = Counter("vllm:prefix_cache_hits", "Prefix cache hits, in terms of number of cached tokens", L, registry=vllm_reg)

TTFT_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0, 20.0, 40.0, 80.0)
ITL_BUCKETS = (0.01, 0.02, 0.03, 0.04, 0.06, 0.08, 0.1, 0.15, 0.25, 0.5, 1.0)
LAT_BUCKETS = (0.3, 0.5, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0, 15.0, 30.0, 60.0, 120.0)
TOK_BUCKETS = (1, 25, 50, 100, 250, 500, 1000, 2000, 5000, 10000)

TTFT = Histogram("vllm:time_to_first_token_seconds", "Time to first token in seconds", L, buckets=TTFT_BUCKETS, registry=vllm_reg)
ITL = Histogram("vllm:inter_token_latency_seconds", "Inter-token latency (TPOT) in seconds", L, buckets=ITL_BUCKETS, registry=vllm_reg)
E2E = Histogram("vllm:e2e_request_latency_seconds", "End-to-end request latency in seconds", L, buckets=LAT_BUCKETS, registry=vllm_reg)
QUEUE_T = Histogram("vllm:request_queue_time_seconds", "Time spent in the waiting queue", L, buckets=LAT_BUCKETS, registry=vllm_reg)
PREFILL_T = Histogram("vllm:request_prefill_time_seconds", "Time spent in prefill", L, buckets=LAT_BUCKETS, registry=vllm_reg)
DECODE_T = Histogram("vllm:request_decode_time_seconds", "Time spent in decode", L, buckets=LAT_BUCKETS, registry=vllm_reg)
PROMPT_HIST = Histogram("vllm:request_prompt_tokens", "Number of prefill tokens per request", L, buckets=TOK_BUCKETS, registry=vllm_reg)
GEN_HIST = Histogram("vllm:request_generation_tokens", "Number of generation tokens per request", L, buckets=TOK_BUCKETS, registry=vllm_reg)

DL = ["gpu", "UUID", "modelName", "Hostname"]
GPU_UTIL = Gauge("DCGM_FI_DEV_GPU_UTIL", "GPU utilization (in %)", DL, registry=dcgm_reg)
FB_USED = Gauge("DCGM_FI_DEV_FB_USED", "Framebuffer memory used (in MiB)", DL, registry=dcgm_reg)
FB_FREE = Gauge("DCGM_FI_DEV_FB_FREE", "Framebuffer memory free (in MiB)", DL, registry=dcgm_reg)
GPU_TEMP = Gauge("DCGM_FI_DEV_GPU_TEMP", "GPU temperature (in C)", DL, registry=dcgm_reg)
POWER = Gauge("DCGM_FI_DEV_POWER_USAGE", "Power draw (in W)", DL, registry=dcgm_reg)
SM_CLOCK = Gauge("DCGM_FI_DEV_SM_CLOCK", "SM clock frequency (in MHz)", DL, registry=dcgm_reg)
SM_ACTIVE = Gauge("DCGM_FI_PROF_SM_ACTIVE", "Ratio of cycles at least one warp was active", DL, registry=dcgm_reg)

# ---------------------------------------------------------------------------
# Tracing — OTel GenAI semantic conventions
# ---------------------------------------------------------------------------

resource = Resource.create(
    {
        "service.name": SERVICE_NAME,
        "service.version": "0.8.5-sim",
        "service.namespace": "llm-inference",
    }
)
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=OTLP_ENDPOINT, insecure=True)))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer("llm-inference-simulator")

# ---------------------------------------------------------------------------
# Logging — OTLP log records sharing the same resource as traces & metrics.
# The LoggingHandler stamps each record with the currently-active span's
# trace_id/span_id, so per-request logs correlate to their trace.
# ---------------------------------------------------------------------------

logger_provider = LoggerProvider(resource=resource)
logger_provider.add_log_record_processor(
    BatchLogRecordProcessor(OTLPLogExporter(endpoint=OTLP_ENDPOINT, insecure=True))
)
set_logger_provider(logger_provider)

engine_log = logging.getLogger("vllm.engine")
engine_log.setLevel(logging.INFO)
engine_log.addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))
engine_log.propagate = False

NS = 1_000_000_000


def emit_request_span(req, status_code, finish_reason=None):
    """Emit one SERVER span for a finished (or rejected) inference request."""
    attrs = {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "vllm",
        "gen_ai.system": "vllm",
        "gen_ai.request.model": MODEL_NAME,
        "gen_ai.request.temperature": req["temperature"],
        "gen_ai.request.max_tokens": req["max_tokens"],
        "http.request.method": "POST",
        "url.path": "/v1/chat/completions",
        "http.response.status_code": status_code,
        "workload.profile": req["profile"],
    }
    if status_code == 200:
        attrs.update(
            {
                "gen_ai.response.model": MODEL_NAME,
                "gen_ai.response.finish_reasons": [finish_reason],
                "gen_ai.usage.input_tokens": req["prompt_tokens"],
                "gen_ai.usage.output_tokens": req["output_tokens"],
                "gen_ai.server.time_to_first_token": round(req["ttft"], 4),
                "gen_ai.server.request.queue_time": round(req["queue_time"], 4),
            }
        )

    start_ns = int(req["arrival"] * NS)
    span = tracer.start_span(
        f"chat {MODEL_NAME}",
        kind=SpanKind.SERVER,
        attributes=attrs,
        start_time=start_ns,
    )
    if status_code == 200:
        span.add_event("gen_ai.first_token", timestamp=int((req["arrival"] + req["ttft"]) * NS))
        span.set_status(Status(StatusCode.OK))
        end_ns = int((req["arrival"] + req["e2e"]) * NS)
    else:
        reason = "queue full: too many pending requests" if status_code == 429 else "engine failure during decode"
        span.set_attribute("error.type", str(status_code))
        span.set_status(Status(StatusCode.ERROR, reason))
        end_ns = int((req["arrival"] + req.get("e2e", 0.005)) * NS)

    # Log the request outcome inside the span's context so the record carries
    # this trace_id/span_id — the log-to-trace correlation demo.
    with trace.use_span(span, end_on_exit=False):
        if status_code == 200:
            engine_log.info(
                "Finished request: %s prompt=%d gen=%d ttft=%.3fs e2e=%.2fs finish=%s",
                req["profile"], req["prompt_tokens"], req["output_tokens"],
                req["ttft"], req["e2e"], finish_reason,
            )
        elif status_code == 429:
            engine_log.warning(
                "Aborted request (queue full): %d requests waiting exceeds max %d",
                MAX_WAITING, MAX_WAITING,
            )
        else:
            engine_log.error(
                "Engine error during decode for %s request (prompt=%d tokens): CUDA error",
                req["profile"], req["prompt_tokens"],
            )
    span.end(end_time=end_ns)


# ---------------------------------------------------------------------------
# Workload simulation
# ---------------------------------------------------------------------------


def sample_profile():
    r = random.random()
    acc = 0.0
    for name, weight, prompt_mu, out_mu in PROFILES:
        acc += weight
        if r <= acc:
            prompt = max(8, int(random.lognormvariate(math.log(prompt_mu), 0.5)))
            out = max(4, int(random.lognormvariate(math.log(out_mu), 0.6)))
            return name, prompt, out
    name, _, prompt_mu, out_mu = PROFILES[-1]
    return name, prompt_mu, out_mu


def new_request(now):
    profile, prompt_tokens, output_tokens = sample_profile()
    return {
        "arrival": now,
        "profile": profile,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "max_tokens": max(output_tokens, 2 ** math.ceil(math.log2(max(output_tokens, 16)))),
        "temperature": round(random.choice([0.0, 0.2, 0.7, 1.0]), 2),
        "generated": 0,
        "queue_time": 0.0,
        "prefill_left": None,   # seconds of prefill remaining once running
        "ttft": None,
        "start_run": None,
    }


def arrival_rate(now, incident_active):
    diurnal = 1.0 + 0.6 * math.sin(2 * math.pi * now / DIURNAL_PERIOD_S)
    rate = BASE_RPS * max(0.15, diurnal)
    if incident_active:
        rate *= INCIDENT_BOOST
    return rate


def main():
    start_http_server(8000, registry=vllm_reg)
    start_http_server(9400, registry=dcgm_reg)
    print(f"simulator up: vLLM metrics :8000, DCGM metrics :9400, traces -> {OTLP_ENDPOINT}", flush=True)

    engine_log.info("Started vLLM engine (model=%s, max_num_seqs=%d)", MODEL_NAME, MAX_RUNNING)

    waiting, running = [], []
    sim_start = time.time()
    temp = {g["gpu"]: 42.0 for g in GPUS}
    incident_was_active = False
    tick_count = 0
    window_prompt_toks = 0
    window_gen_toks = 0

    while True:
        tick_begin = time.time()
        now = tick_begin
        elapsed = now - sim_start

        # incident sits at the end of each period, so the first minutes are calm
        incident_active = (elapsed % INCIDENT_PERIOD_S) > (INCIDENT_PERIOD_S - INCIDENT_DURATION_S)
        if incident_active and not incident_was_active:
            print(f"[incident] saturation burst started at {time.strftime('%H:%M:%S')}", flush=True)
        if incident_was_active and not incident_active:
            print(f"[incident] burst ended at {time.strftime('%H:%M:%S')}", flush=True)
        incident_was_active = incident_active

        # --- arrivals ------------------------------------------------------
        lam = arrival_rate(elapsed, incident_active) * TICK_S
        for _ in range(int(random.gauss(lam, math.sqrt(lam)) + 0.5) if lam > 0 else 0):
            req = new_request(now)
            if len(waiting) >= MAX_WAITING:
                emit_request_span(req, 429)
                continue
            if random.random() < 0.005:
                req["e2e"] = random.uniform(0.05, 0.4)
                emit_request_span(req, 500)
                continue
            waiting.append(req)

        # --- admit from queue into the running batch -----------------------
        while waiting and len(running) < MAX_RUNNING:
            req = waiting.pop(0)
            req["queue_time"] = now - req["arrival"]
            req["start_run"] = now
            load_penalty = 1.0 + 0.5 * (len(running) / MAX_RUNNING)
            req["prefill_total"] = (req["prompt_tokens"] / PREFILL_TOKS_PER_S) * load_penalty
            req["prefill_left"] = req["prefill_total"]
            running.append(req)

        # --- advance running requests --------------------------------------
        batch = len(running)
        tpot = BASE_TPOT_S * (1.0 + 0.02 * batch) * (1.25 if incident_active else 1.0)
        finished = []
        for req in running:
            if req["prefill_left"] > 0:
                req["prefill_left"] -= TICK_S
                if req["prefill_left"] <= 0 and req["ttft"] is None:
                    req["ttft"] = req["queue_time"] + req["prefill_total"] + tpot
                continue
            req["generated"] += max(1, int(TICK_S / tpot))
            if req["generated"] >= req["output_tokens"]:
                req["generated"] = req["output_tokens"]
                finished.append(req)
        for req in finished:
            running.remove(req)
            req["e2e"] = now - req["arrival"]
            prefill_time = req["prompt_tokens"] / PREFILL_TOKS_PER_S
            decode_time = max(req["e2e"] - req["queue_time"] - prefill_time, req["output_tokens"] * tpot * 0.5)
            if req["ttft"] is None:
                req["ttft"] = req["queue_time"] + req["prefill_total"] + tpot
            finish_reason = "length" if random.random() < 0.08 else "stop"

            m = MODEL_NAME
            TTFT.labels(m).observe(req["ttft"])
            E2E.labels(m).observe(req["e2e"])
            QUEUE_T.labels(m).observe(req["queue_time"])
            PREFILL_T.labels(m).observe(prefill_time)
            DECODE_T.labels(m).observe(decode_time)
            PROMPT_HIST.labels(m).observe(req["prompt_tokens"])
            GEN_HIST.labels(m).observe(req["output_tokens"])
            for _ in range(min(req["output_tokens"] - 1, 40)):  # sampled, keeps scrape cheap
                ITL.labels(m).observe(max(0.005, random.gauss(tpot, tpot * 0.25)))
            PROMPT_TOKENS.labels(m).inc(req["prompt_tokens"])
            GEN_TOKENS.labels(m).inc(req["output_tokens"])
            PREFIX_QUERIES.labels(m).inc(req["prompt_tokens"])
            PREFIX_HITS.labels(m).inc(int(req["prompt_tokens"] * random.uniform(0.45, 0.75)))
            REQ_SUCCESS.labels(m, finish_reason).inc()
            window_prompt_toks += req["prompt_tokens"]
            window_gen_toks += req["output_tokens"]
            emit_request_span(req, 200, finish_reason)

        # --- gauges: engine state ------------------------------------------
        kv_tokens = sum(r["prompt_tokens"] + r["generated"] for r in running)
        kv_frac = min(kv_tokens / KV_CACHE_TOKENS + (0.35 if incident_active else 0.0), 0.985)
        NUM_RUNNING.labels(MODEL_NAME).set(len(running))
        NUM_WAITING.labels(MODEL_NAME).set(len(waiting))
        KV_USAGE.labels(MODEL_NAME).set(round(kv_frac, 4))

        # --- gauges: GPU telemetry -----------------------------------------
        load = min(1.0, (batch / MAX_RUNNING) * 0.85 + (0.1 if waiting else 0.0))
        for g in GPUS:
            gid = g["gpu"]
            util = max(0.0, min(99.0, load * 92 + random.gauss(0, 4)))
            fb_used = 62_000 + kv_frac * 17_000 + random.gauss(0, 150)  # weights + KV cache
            target_temp = 38 + util * 0.42
            temp[gid] += (target_temp - temp[gid]) * 0.15  # thermal inertia
            labels = (gid, g["UUID"], GPU_MODEL, HOSTNAME)
            GPU_UTIL.labels(*labels).set(round(util, 1))
            FB_USED.labels(*labels).set(int(fb_used))
            FB_FREE.labels(*labels).set(int(FB_TOTAL_MIB - fb_used))
            GPU_TEMP.labels(*labels).set(round(temp[gid], 1))
            POWER.labels(*labels).set(round(90 + load * 580 + random.gauss(0, 12), 1))
            SM_CLOCK.labels(*labels).set(1980 if load > 0.05 else 345)
            SM_ACTIVE.labels(*labels).set(round(min(0.99, load * 0.9 + random.gauss(0, 0.03)), 3))

        # --- periodic engine logs (vLLM emits a throughput line ~every 5s) --
        tick_count += 1
        if tick_count % 10 == 0:
            window_s = 10 * TICK_S
            engine_log.info(
                "Avg prompt throughput: %.1f tokens/s, Avg generation throughput: %.1f tokens/s, "
                "Running: %d reqs, Waiting: %d reqs, GPU KV cache usage: %.1f%%",
                window_prompt_toks / window_s, window_gen_toks / window_s,
                len(running), len(waiting), kv_frac * 100,
            )
            window_prompt_toks = 0
            window_gen_toks = 0
            if kv_frac > 0.9 and running:
                engine_log.warning(
                    "Sequence group preempted by PreemptionMode.RECOMPUTE: "
                    "not enough KV cache space (usage %.1f%%). Consider raising gpu_memory_utilization.",
                    kv_frac * 100,
                )

        time.sleep(max(0.0, TICK_S - (time.time() - tick_begin)))


if __name__ == "__main__":
    main()
