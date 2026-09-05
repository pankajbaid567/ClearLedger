#!/usr/bin/env sh
set -eu

uv run python -m generator.cli --dataset demo --seed 20260827
