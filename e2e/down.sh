#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UP="${SUBSTRATE_SRC:-$ROOT/.work/substrate}"
if [ -x "$UP/hack/delete-kind-cluster.sh" ]; then
  "$UP/hack/delete-kind-cluster.sh"
else
  kind delete cluster --name "${KIND_CLUSTER_NAME:-kind}"
fi
