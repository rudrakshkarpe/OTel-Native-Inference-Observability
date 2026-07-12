# Contributing

## Local setup

```bash
cp .env.example .env   # optional OTLP backend credentials
make up                # demo mode: simulator + collector
make validate
```

## Tests

```bash
pip install -r tests/requirements.txt
pytest -q
```

Tests import the simulator without opening OTLP connections. Keep pure
workload helpers free of side effects at import time.

## Commit style

Use conventional commits: `feat|fix|docs|test|ci|chore|refactor(scope): summary`.

Keep each commit one logical change. Prefer updating the metrics catalog and
Perses dashboards in the same PR when you add or rename a signal.

## Demo vs GPU mode

Collector config, dashboards, and the data model are identical in both modes.
Only scrape targets change. Document any new metric in `docs/metrics-catalog.md`.
