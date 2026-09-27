# Contributing

## Tests

Use separate environments for the replay tools and the optional simulator, which pin different OpenTelemetry versions:

```bash
# Replay environment
python3.12 -m venv .venv
.venv/bin/pip install -r scripts/replay/requirements.txt
.venv/bin/pytest -q tests/test_replay.py

# Simulator in an isolated uv environment
uv run --python 3.12 --no-project --with-requirements tests/requirements.txt \
  pytest -q tests/test_workload.py
```

Unit tests do not contact a backend. Do not run ingestion in CI. See [the replay guide](docs/dash0-replay.md) for explicit authenticated ingestion and read-back checks.

## Evidence and documentation

Preserve missing usage, original statuses and timing units. Never present replayed records as new inference, generate fake GPU samples or infer cancellation latency from a client closure. Keep raw captures and credentials outside public commits. Store summary evidence and reviewed screenshots alongside documentation.

For a new measurement, update the replay metric table and Perses dashboard together. Validate backend name/unit normalization. The optional simulator metric family is documented separately in `docs/metrics-catalog.md`; compatibility with a live engine must be checked per version.

## Commit style

Use conventional commits: `feat|fix|docs|test|ci|chore|refactor(scope): summary`.
Keep each commit one logical change. Use concise descriptive branches such as `feat/dash0-real-inference`.
