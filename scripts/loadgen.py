#!/usr/bin/env python3
"""OpenAI-compatible load generator for GPU mode.

Hits a vLLM (or any OpenAI-compatible) /v1/chat/completions endpoint to
produce real traffic so the OTel pipeline has something to observe. Demo mode
does not need this — the simulator generates its own workload.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request

PROMPTS = [
    "Summarize the trade-offs of continuous batching in LLM serving.",
    "Explain KV-cache pressure in one paragraph.",
    "What causes time-to-first-token to spike under load?",
    "Compare prefill and decode phases for a transformer LLM.",
    "Why can GPU utilization look healthy while P99 latency is bad?",
]


def chat_once(url: str, model: str, api_key: str, timeout: float) -> tuple[int, float]:
    body = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": random.choice(PROMPTS)}],
            "max_tokens": random.choice([64, 128, 256]),
            "temperature": random.choice([0.0, 0.2, 0.7]),
        }
    ).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            return resp.status, time.perf_counter() - started
    except urllib.error.HTTPError as exc:
        return exc.code, time.perf_counter() - started
    except urllib.error.URLError as exc:
        print(f"request failed: {exc}", file=sys.stderr)
        return 0, time.perf_counter() - started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("VLLM_BASE_URL", "http://localhost:8000"),
        help="OpenAI-compatible base URL (default: %(default)s)",
    )
    parser.add_argument(
        "--model",
        default=os.getenv("MODEL_NAME", "qwen2.5-7b-instruct"),
        help="Model name passed in the request body",
    )
    parser.add_argument("--rps", type=float, default=0.5, help="Target requests per second")
    parser.add_argument("--duration", type=float, default=120.0, help="How long to run (seconds)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Per-request timeout")
    parser.add_argument("--api-key", default=os.getenv("OPENAI_API_KEY", ""), help="Optional bearer token")
    args = parser.parse_args()

    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    interval = 1.0 / args.rps if args.rps > 0 else 1.0
    deadline = time.time() + args.duration
    ok = err = 0

    print(f"loadgen -> {url} model={args.model} rps={args.rps} duration={args.duration}s", flush=True)
    while time.time() < deadline:
        tick = time.time()
        status, latency = chat_once(url, args.model, args.api_key, args.timeout)
        if 200 <= status < 300:
            ok += 1
            print(f"ok  status={status} latency={latency:.2f}s", flush=True)
        else:
            err += 1
            print(f"err status={status} latency={latency:.2f}s", flush=True)
        sleep_for = interval - (time.time() - tick)
        if sleep_for > 0:
            time.sleep(sleep_for)

    print(f"done ok={ok} err={err}", flush=True)
    return 0 if err == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
