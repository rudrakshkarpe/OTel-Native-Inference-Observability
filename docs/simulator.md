# Optional simulator

The simulator is a separate teaching workload. It did not produce the H100 results in the main README. Its queue, GPU and error signals are synthetic and do not establish compatibility with every vLLM or DCGM version.

## Run

From the repository root:

```bash
cp .env.example .env
# Configure the selected OTLP destination in .env before starting.
make up
make logs
make validate
make scenario-burst
make scenario-recovery
make down
```

The simulator exposes vLLM-shaped metrics on port 8000, DCGM-shaped metrics on port 9400 and sends synthetic request traces to the Collector. The `steady`, `burst` and `recovery` scenarios model queue growth and changing token workloads. They are useful for testing a demonstration pipeline without a GPU, but are not real scheduler or GPU measurements.

The older Perses overview and saturation dashboards, and the Kubernetes check rules, target this metric family. The real archive replay has its own dashboard, resource namespace and Collector Compose project. Avoid mixing simulator traffic into a dataset while recording evidence of the real workload.

## Development

Install `tests/requirements.txt` in a separate virtual environment and run `pytest -q tests/test_workload.py`. The simulator dependency pins are independent from the replay tools. `docker-compose.gpu.yml` is an optional Linux/NVIDIA deployment example; review the [GPU guide](gpu-mode.md) and validate the selected engine version before using it.
