.PHONY: up down logs restart validate gpu-up gpu-down k8s-up k8s-down k8s-nuke k8s-status

up: ## Start demo mode (simulator + OTel Collector -> Dash0)
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

gpu-up: ## Start GPU mode (real vLLM + dcgm-exporter; NVIDIA host only)
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d

gpu-down:
	docker compose -f docker-compose.yml -f docker-compose.gpu.yml down

k8s-up: ## Full k8s demo on local k3d: operator + workloads + check rules -> Dash0
	./k8s/setup.sh

k8s-down: ## Remove workloads + operator, keep the k3d cluster
	./k8s/teardown.sh

k8s-nuke: ## Remove everything including the k3d cluster
	./k8s/teardown.sh --all

k8s-status: ## Show demo pods and synced check rules
	kubectl get pods -n llm-inference
	kubectl get pods -n dash0-system
	kubectl get prometheusrule,dash0monitoring -n llm-inference
