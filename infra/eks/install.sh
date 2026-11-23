#!/usr/bin/env bash
# EKS pilot install (experimental: upstream tests kind and GKE, not EKS).
# 1) Substrate from the published v1.0.0 images with S3 snapshots,
# 2) switch the object-store sidecars to S3 (Pod Identity supplies credentials),
# 3) memory agent image to ECR, WorkerPool, atespace, template.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/versions.env"
TF="$ROOT/infra/eks/terraform"
UP="${SUBSTRATE_SRC:-$ROOT/.work/substrate}"
[ -d "$UP/.git" ] || git clone --depth 1 --branch "$SUBSTRATE_VERSION" https://github.com/agent-substrate/substrate.git "$UP"
test "$(git -C "$UP" rev-parse HEAD)" = "$SUBSTRATE_SHA"

REGION="$(terraform -chdir="$TF" output -raw region)"
SNAPSHOT_BUCKET="$(terraform -chdir="$TF" output -raw snapshot_bucket)"
REPO="$(terraform -chdir="$TF" output -raw ecr_repository_url)"
export SUBSTRATE_VERSION SNAPSHOT_BUCKET
envsubst < "$ROOT/infra/eks/substrate-install.yaml.tmpl" > "$ROOT/.work/substrate-install.yaml"

kubectl apply -f - <<'EOF'
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: gp3
  annotations: { storageclass.kubernetes.io/is-default-class: "true" }
provisioner: ebs.csi.aws.com
parameters: { type: gp3, encrypted: "true" }
volumeBindingMode: WaitForFirstConsumer
EOF

(cd "$UP" && ATE_CREDENTIAL_PROVIDER='{"name":"k8s.io"}' go run ./cmd/ate-setup deploy ate-system --config "$ROOT/.work/substrate-install.yaml")
(cd "$UP" && go install ./cmd/kubectl-ate)

# The sidecars, not the main processes, own object storage ("s3" + AWS_* selects S3).
kubectl -n ate-system set env deployment/ate-api-server -c objectstore-plugin ATE_STORAGE_BACKEND=s3 AWS_REGION="$REGION"
kubectl -n ate-system set env daemonset/atelet -c objectstore-plugin ATE_STORAGE_BACKEND=s3 AWS_REGION="$REGION"
kubectl -n ate-system rollout status deployment/ate-api-server --timeout=300s
kubectl -n ate-system rollout status daemonset/atelet --timeout=300s

aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${REPO%%/*}"
TAG="$(git -C "$ROOT" rev-parse --short HEAD)"
docker build -q --platform linux/amd64 -t "$REPO:$TAG" "$ROOT/app/memory-agent"  # EKS nodes are x86_64
docker push -q "$REPO:$TAG"
AGENT_IMAGE="$(docker inspect --format '{{index .RepoDigests 0}}' "$REPO:$TAG")"
# Derive the worker image name from the installed atelet image (same repo and naming).
ATELET_IMG="$(kubectl -n ate-system get daemonset atelet -o jsonpath='{.spec.template.spec.containers[?(@.name=="atelet")].image}')"
WORKER_IMAGE="${ATELET_IMG%@*}"; WORKER_IMAGE="${WORKER_IMAGE%:*}"
WORKER_IMAGE="${WORKER_IMAGE/atelet/ateworker-gvisor}:$SUBSTRATE_VERSION"
echo "worker image: $WORKER_IMAGE"
export WORKER_IMAGE AGENT_IMAGE WORKERS="$SUBLAB_WORKERS"
# shellcheck disable=SC2016
envsubst '${WORKER_IMAGE} ${WORKERS}' < "$ROOT/k8s/workerpool.yaml.tmpl" | kubectl apply -f -
cd "$ROOT"
PYTHONPATH=app python3 -m sublab.cli wait workers --name memory-agent --count "$WORKERS" --timeout 900 || echo "worker count not confirmed; continuing"
kubectl ate create atespace lab-agents 2>/dev/null || true
# shellcheck disable=SC2016
envsubst '${AGENT_IMAGE}' < k8s/actor-template.yaml.tmpl | kubectl ate create actor-template -f -
PYTHONPATH=app python3 -m sublab.cli wait template --name memory-agent --timeout 900
