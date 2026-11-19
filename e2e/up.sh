#!/usr/bin/env bash
# POC: kind + Agent Substrate (from the pinned v1.0.0 source, as upstream CI
# does) + the counter demo as a known-good baseline + our memory agent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/versions.env"
UP="${SUBSTRATE_SRC:-$ROOT/.work/substrate}"
log() { printf '\n==> %s\n' "$*"; }
for t in go docker kubectl git; do command -v "$t" >/dev/null || { echo "missing $t" >&2; exit 2; }; done

log "Agent Substrate source at $SUBSTRATE_VERSION ($SUBSTRATE_SHA)"
if [ ! -d "$UP/.git" ]; then
  git clone --depth 1 --branch "$SUBSTRATE_VERSION" https://github.com/agent-substrate/substrate.git "$UP"
fi
test "$(git -C "$UP" rev-parse HEAD)" = "$SUBSTRATE_SHA" || { echo "substrate checkout is not the pinned SHA" >&2; exit 1; }

cd "$UP"
export ATE_CREDENTIAL_PROVIDER='{"name":"k8s.io"}'
export ATE_INGRESS_ALLOWED_SPIFFE_IDS=spiffe://cluster.local/ns/ate-system/sa/atenet-client
log "kind cluster + local registry (localhost:5001)"
hack/create-kind-cluster.sh
log "install Substrate (builds images with ko and pushes to the local registry)"
go run ./cmd/ate-setup --kind deploy ate-system
log "baseline: upstream counter demo"
go run ./cmd/ate-setup --kind deploy demo counter
go install ./cmd/kubectl-ate
cd "$ROOT"

log "memory agent image -> localhost:5001"
docker build -q -t localhost:5001/memory-agent:dev app/memory-agent
docker push -q localhost:5001/memory-agent:dev
AGENT_IMAGE="$(docker inspect --format '{{index .RepoDigests 0}}' localhost:5001/memory-agent:dev)"

log "WorkerPool (worker image copied from the counter pool) + atespace + ActorTemplate"
WORKER_IMAGE="$(kubectl get workerpool counter -n ate-demo-counter -o jsonpath='{.spec.workerImage}')"
test -n "$WORKER_IMAGE"
export WORKER_IMAGE AGENT_IMAGE WORKERS="${SUBLAB_WORKERS}"
# shellcheck disable=SC2016  # envsubst takes the literal variable list
envsubst '${WORKER_IMAGE} ${WORKERS}' < k8s/workerpool.yaml.tmpl | kubectl apply -f -
PYTHONPATH=app python3 -m sublab.cli wait workers --name memory-agent --count "$WORKERS" --timeout 600 || echo "worker count not confirmed; continuing"
kubectl ate create atespace lab-agents 2>/dev/null || true
# shellcheck disable=SC2016
kubectl ate get actor-template memory-agent -a lab-agents >/dev/null 2>&1 \
  || envsubst '${AGENT_IMAGE}' < k8s/actor-template.yaml.tmpl | kubectl ate create actor-template -f -
log "wait for the template's golden snapshot"
PYTHONPATH=app python3 -m sublab.cli wait template --name memory-agent --timeout 900 \
  || { kubectl ate get actor-template memory-agent -a lab-agents -o yaml; exit 1; }
kubectl ate get actor-templates -a lab-agents
log "ready. Next: make e2e"
