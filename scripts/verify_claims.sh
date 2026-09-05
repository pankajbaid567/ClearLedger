#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
UV_BIN="${UV_BIN:-$(command -v uv || true)}"
if [[ -z "$UV_BIN" ]]; then
  UV_BIN="$HOME/.local/bin/uv"
fi

echo "=== Generating demo data ==="
make generate-demo

echo "=== Running reconciliation and evaluation ==="
make evaluate

echo "=== Running ablation study ==="
make ablation

echo "=== Running stress test ==="
make stress-test

echo "=== Verifying claims and reproducibility ==="
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/clearledger-uv-cache}" "$UV_BIN" run python -m scripts.verify_claims

echo "=== Building final metrics and demo backup ==="
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/clearledger-uv-cache}" "$UV_BIN" run python -m scripts.final_metrics
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/clearledger-uv-cache}" "$UV_BIN" run python -m scripts.build_demo_backup

echo "=== All claims verified ==="
