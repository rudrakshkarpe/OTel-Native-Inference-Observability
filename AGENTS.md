# Repository guidance

## Project and layout

This is an independent Dash0 inference observability lab built with Python,
OpenTelemetry, vLLM capture data and Perses dashboards. Dash0 is the investigation
UI; do not add a separate frontend unless requested.

Read `README.md` and `CONTRIBUTING.md` first. Keep the verified historical GPU
capture/replay path distinct from the optional simulator and GPU/Kubernetes
deployment examples. An example configuration is not proof of a tested deployment.

- `scripts/replay/`: archive validation, OTLP preparation/export, Dash0 read-back,
  inference statistics, dashboard generation and visual builders.
- `collector/replay.yaml` and `docker-compose.replay.yml`: isolated replay pipeline.
- `dashboards/perses/`: importable dashboard JSON. Update the corresponding Python
  generator when changing a generated dashboard.
- `docs/`: setup, architecture, metrics definitions and investigation walkthroughs.
- `docs/evidence/` and `docs/assets/dash0/`: reviewed summaries, verification results,
  actual UI screenshots and generated walkthroughs.
- `simulator/`, `scripts/loadgen.py`, other Compose files and `k8s/`: separate
  teaching and deployment paths.
- `tests/`: offline replay/metrics tests and a separate simulator suite.

## Development and checks

Use Python 3.12 and the existing pinned requirements. Replay and simulator tools
pin different OpenTelemetry versions; keep their environments separate.

```bash
# Replay environment and tests, from the repository root
python3.12 -m venv .venv
.venv/bin/pip install -r scripts/replay/requirements.txt
.venv/bin/pytest -q tests/test_replay.py tests/test_inference_metrics.py

# Simulator tests in a separate environment
uv run --python 3.12 --no-project --with-requirements tests/requirements.txt \
  pytest -q tests/test_workload.py
```

Run the suite relevant to the changed behavior. For Compose changes, use the
configuration validation commands in `.github/workflows/ci.yml`. Unit tests must
remain offline and require no GPU, Dash0 account or private archive. Do not ingest
telemetry in CI. Documentation-only edits need link/path and diff review, not a
GPU run. Report which checks actually ran and any limitations.

## Telemetry and evidence rules

- Preserve the source archive and verify its checksums before preparing data.
  Replay may remap trace IDs and shift timestamps by a constant offset; preserve
  span IDs, parent relationships, durations, events and original attributes.
- Label historical replay, derived measurements and simulator output accurately.
  Never invent native spans, GPU samples, token usage or successful verification.
- Keep missing usage missing. A client stream closure does not establish when
  the server cancelled generation. An HTTP rejection is not a mid-stream failure.
- Keep client first-content latency distinct from native engine TTFT. Document
  units, sample counts and percentile populations. Recorded gauges are not
  histograms; do not apply histogram quantiles to them. Throughput must account
  for overlapping requests using scenario wall time.
- When changing measurements, update their tests, `docs/inference-metrics.md` or
  `docs/dash0-replay.md`, and affected dashboard generators/JSON together. Keep
  simulator definitions in `docs/metrics-catalog.md` distinct from real captures.
- Collector acceptance alone does not prove hosted ingestion. Use the read-only
  Dash0 verifier before publishing claims about stored records or correlations.

## External operations and private data

Follow `docs/dash0-replay.md` for regional endpoints, credentials and replay steps.
Keep tokens, raw captures, prompts/completions and private response dumps out of
commits, terminal output and screenshots. Use environment variables or ignored
`.secrets/` files; keep generated local payloads under ignored `artifacts/`.

Treat ingestion, dashboard `--apply`, GPU provisioning and Kubernetes deployment
as external operations. Run them only within the user's authorized task scope;
ordinary code or documentation checks do not require them. Keep the replay
Collector bound to loopback. Never delete send journals to bypass retry protection
or resend after an ambiguous failure without checking receipts and hosted data.

## Documentation and visuals

Use actual Dash0 screenshots for product walkthroughs. Crops, zooms and highlights
may guide attention but must not alter displayed telemetry. Preserve screenshot
provenance and review images for private information before committing them.
Follow `docs/assets/dash0/README.md` to rebuild and visually inspect diagrams/GIFs.
Keep static alternatives and relative asset links working on GitHub. Retain Dash0
credit and the independent community project description.

## Change conventions

Inspect the working tree and preserve unrelated changes. Follow existing Python
patterns and conventional commits; keep each commit focused on one logical change.
Do not manufacture commit history. New branches must have concise descriptive
names such as `fix/replay-validation` or `docs/metrics-guide`; never include
`codex` in a new branch name. Do not rename existing branches unless asked.

Keep public documentation, issue comments and PR descriptions concise, specific
and backed by evidence. Avoid em dashes. Post comments or contact maintainers only
when the user authorizes it. Keep these instructions in `AGENTS.md`; `CLAUDE.md`
imports this file and should not duplicate it.
