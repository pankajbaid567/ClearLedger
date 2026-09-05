#!/usr/bin/env sh
set -eu

uv sync
pnpm --dir apps/web install
