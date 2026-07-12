#!/usr/bin/env bash
# Stand up the full Kubernetes demo on a local k3d cluster:
#   - Dash0 operator (Kubernetes monitoring + check-rule sync)
#   - the vLLM/DCGM simulator + our OTel collector
#   - PromQL check rules as code
# Idempotent: safe to re-run. Requires docker, k3d, kubectl, helm, and a
# populated .env (DASH0_ENDPOINT, DASH0_AUTH_TOKEN, DASH0_DATASET).
set -euo pipefail
cd "$(dirname "$0")/.."

CLUSTER=llm-obs
IMAGE=llm-inference-observatory-dash0-simulator:latest
API_ENDPOINT="${DASH0_API_ENDPOINT:-https://api.europe-west4.gcp.dash0.com}"

set -a; . ./.env; set +a
: "${DASH0_ENDPOINT:?set DASH0_ENDPOINT in .env}"
: "${DASH0_AUTH_TOKEN:?set DASH0_AUTH_TOKEN in .env}"

echo "==> cluster"
k3d cluster list 2>/dev/null | grep -q "^${CLUSTER} " || k3d cluster create "$CLUSTER" --agents 1 --wait

echo "==> simulator image -> cluster"
docker build -t "$IMAGE" ./simulator
k3d image import "$IMAGE" -c "$CLUSTER"

echo "==> PrometheusRule CRD"
kubectl apply --server-side -f https://raw.githubusercontent.com/prometheus-operator/prometheus-operator/main/example/prometheus-operator-crd/monitoring.coreos.com_prometheusrules.yaml

echo "==> Dash0 operator"
helm repo add dash0-operator https://dash0hq.github.io/dash0-operator >/dev/null 2>&1 || true
helm repo update dash0-operator >/dev/null
helm upgrade --install --namespace dash0-system --create-namespace \
  --set operator.dash0Export.enabled=true \
  --set operator.dash0Export.endpoint="$DASH0_ENDPOINT" \
  --set operator.dash0Export.apiEndpoint="$API_ENDPOINT" \
  --set operator.dash0Export.token="$DASH0_AUTH_TOKEN" \
  dash0-operator dash0-operator/dash0-operator

echo "==> namespace, secret (from .env), collector config"
kubectl create namespace llm-inference --dry-run=client -o yaml | kubectl apply -f -
kubectl create secret generic dash0-secret --from-env-file=.env -n llm-inference \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap otel-collector-config --from-file=config.yaml=collector/config.yaml \
  -n llm-inference --dry-run=client -o yaml | kubectl apply -f -

# Apply the Dash0Monitoring resource FIRST and wait for it to become active, so
# the operator will accept the PrometheusRule (rules in an unmonitored namespace
# are skipped).
echo "==> enable Dash0 monitoring for the namespace"
kubectl apply -f k8s/00-namespace.yaml -f k8s/30-dash0-monitoring.yaml
kubectl wait --for=condition=Available dash0monitoring/dash0-monitoring -n llm-inference --timeout=90s

echo "==> workloads + check rules"
kubectl apply -k k8s/

echo "==> waiting for app pods"
kubectl rollout status deploy/otel-collector -n llm-inference --timeout=120s
kubectl rollout status deploy/vllm-simulator -n llm-inference --timeout=120s

echo
echo "Done. Data flowing to Dash0 ($DASH0_ENDPOINT):"
echo "  - Services / Tracing : vllm-server (traces, metrics, logs)"
echo "  - Kubernetes         : deployments & pods via the operator"
echo "  - Alerting           : 4 check rules (trip during the saturation incident)"
echo "Inspect:  kubectl get pods -A | grep -E 'llm-inference|dash0'"
