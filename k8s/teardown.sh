#!/usr/bin/env bash
# Tear down the Kubernetes demo. Pass --all to also delete the k3d cluster.
set -euo pipefail
cd "$(dirname "$0")/.."

kubectl delete -k k8s/ --ignore-not-found 2>/dev/null || true
kubectl delete configmap otel-collector-config secret dash0-secret -n llm-inference --ignore-not-found 2>/dev/null || true
helm uninstall dash0-operator -n dash0-system 2>/dev/null || true

if [ "${1:-}" = "--all" ]; then
  k3d cluster delete llm-obs
  echo "cluster deleted."
else
  echo "workloads removed; k3d cluster kept (use --all to delete it)."
fi
