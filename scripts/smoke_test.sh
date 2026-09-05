#!/usr/bin/env sh
set -eu

uv run pytest
docker compose config --quiet
