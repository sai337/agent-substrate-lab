#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck disable=SC1091
source "$ROOT/versions.env"
TARGET="${TARGET:-kind}"
OUT="${SUBLAB_OUT:-$ROOT/evals/results/$(date -u +%Y-%m-%d)-$TARGET}"
cd "$ROOT"
export SUBLAB_WORKERS
PYTHONPATH=app python3 -m sublab.cli run --actors "${SUBLAB_ACTORS}" --target "$TARGET" --out "$OUT" "$@"
