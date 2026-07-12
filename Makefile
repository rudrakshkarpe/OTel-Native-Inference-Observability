.PHONY: up down logs restart validate gpu-up gpu-down k8s-up k8s-down k8s-nuke k8s-status scenario-burst scenario-steady scenario-recovery demo-script test

up: ## Start demo mode (simulator + OTel Collector -> OTLP backend)
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f otel-collector

restart:
	docker compose restart

validate: ## Check both compose files and print scraped metric samples
	docker compose config -q
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml config -q
	@echo "--- vLLM-shaped metrics ---"
	@curl -s localhost:8000/metrics | grep -E '^vllm:' | head -20
	@echo "--- DCGM-shaped metrics ---"
	@curl -s localhost:9400/metrics | grep -E '^DCGM_' | head -10
	@echo "--- health ---"
	@curl -sf localhost:8000/healthz && echo " vllm ok"
	@curl -sf localhost:9400/readyz && echo " dcgm ok"

gpu-up: ## Start GPU mode (real vLLM + dcgm-exporter; NVIDIA host only)
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

gpu-down:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml down

k8s-up: ## Full k8s demo on local k3d: operator + workloads + check rules
	./k8s/setup.sh

k8s-down: ## Remove workloads + operator, keep the k3d cluster
	./k8s/teardown.sh

k8s-nuke: ## Remove everything including the k3d cluster
	./k8s/teardown.sh --all

k8s-status: ## Show demo pods and synced check rules
	kubectl get pods -n llm-inference
	kubectl get pods -n dash0-system
	kubectl get prometheusrule,dash0monitoring -n llm-inference

scenario-burst: ## Restart simulator with periodic saturation bursts (default)
	SCENARIO=burst docker compose up -d --build --force-recreate simulator

scenario-steady: ## Restart simulator with no saturation bursts
	SCENARIO=steady docker compose up -d --build --force-recreate simulator

scenario-recovery: ## Restart simulator with a faster burst/recovery cycle
	SCENARIO=recovery docker compose up -d --build --force-recreate simulator

demo-script: ## Print the TTFT investigation narrative for live demos
	@printf '%s\n' \
		'=== LLM Inference Observatory demo script ===' \
		'' \
		'1. make up            # wait ~30s for first scrapes' \
		'2. make scenario-burst  # ensure saturation cycle is on' \
		'3. Watch for ~7 minutes (or use scenario-recovery for ~3m cycles)' \
		'4. Ask: why did P99 time-to-first-token spike five minutes ago?' \
		'' \
		'Causal chain written into the telemetry:' \
		'  queue depth waiting  ->  KV-cache ~95%  ->  P99 TTFT spike  ->  429 spans/logs' \
		'  Pivot: metric window -> gen_ai.* spans -> trace-correlated engine logs' \
		'' \
		'Import dashboards/perses/*.json into your OTLP backend (e.g. Dash0).'

test: ## Run simulator unit tests
	pytest -q
