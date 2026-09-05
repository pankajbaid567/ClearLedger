UV := $(shell command -v uv 2>/dev/null)
ifeq ($(UV),)
UV := $(HOME)/.local/bin/uv
endif
UV_CACHE_DIR ?= /tmp/clearledger-uv-cache

.PHONY: doctor install db-up db-down migrate generate-demo generate-stress reconcile dev-api dev-web dev test test-unit test-python test-web test-api evaluate ablation stress-test verify-claims demo-backup secret-scan security-scan reset-demo lint typecheck-core test-adversarial

doctor:
	@echo "Checking ClearLedger environment..."
	@command -v uv >/dev/null && echo "✅ uv: $$(uv --version)" || echo "❌ uv: missing"
	@command -v node >/dev/null && echo "✅ node: $$(node --version)" || echo "❌ node: missing"
	@command -v pnpm >/dev/null && echo "✅ pnpm: $$(pnpm --version)" || echo "❌ pnpm: missing"
	@command -v docker >/dev/null && echo "✅ docker: installed" || echo "❌ docker: missing"
	@if docker info >/dev/null 2>&1; then \
		echo "✅ Docker daemon: running"; \
	else \
		echo "⚠️  Docker daemon: not running (PostgreSQL container requires Docker: 'make db-up')"; \
	fi
	@echo "Ready. To run pure offline tests: 'make test-unit'"

install:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) sync --frozen
	pnpm --dir apps/web install --frozen-lockfile

db-up:
	docker compose up -d db

db-down:
	docker compose down

migrate:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run alembic upgrade head

generate-demo:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m generator.cli --dataset demo --seed 20260827

generate-stress:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m generator.cli --dataset stress --seed 99999 --count 1000 --output-dir data/stress

reconcile:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m services.reconciliation.cli

dev-api:
	APP_MODE=$${APP_MODE:-local_demo} UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen uvicorn apps.api.app.main:app --reload --host 127.0.0.1 --port 8000

dev-web:
	pnpm --dir apps/web dev

dev:
	$(MAKE) -j2 dev-api dev-web

test: test-python test-web

lint:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen ruff check .

# Deliberate strict gate for money, policy, evaluator and authentication contracts.
# The remaining service layer is not yet covered by a clean whole-project mypy run.
typecheck-core:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen mypy --follow-imports=silent packages/domain apps/api/app/auth.py apps/api/app/config.py apps/api/app/routes/auth.py evaluator/schemas.py evaluator/metrics.py evaluator/validation.py services/normalization/dates.py services/normalization/policy.py

test-adversarial:
	AI_ENABLED=false UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run --frozen pytest evaluator/tests/test_prediction_integrity.py tests/unit/test_control_package.py tests/unit/test_auth.py

test-unit:
	AI_ENABLED=false UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run pytest tests/unit tests/property evaluator/tests generator/tests

test-python:
	AI_ENABLED=false UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run pytest

test-web:
	pnpm --dir apps/web lint
	pnpm --dir apps/web typecheck
	pnpm --dir apps/web test:e2e

test-api:
	AI_ENABLED=false UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run pytest apps/api/tests/ -v

evaluate:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m services.reconciliation.cli
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m evaluator.cli

ablation:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m scripts.ablation_study

stress-test: generate-stress
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m scripts.stress_test

verify-claims:
	./scripts/verify_claims.sh

demo-backup:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m scripts.build_demo_backup

secret-scan:
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m scripts.scan_secrets

security-scan: secret-scan
	pnpm --dir apps/web audit --audit-level=high
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) export --no-dev --no-hashes --format requirements-txt --output-file /tmp/clearledger-requirements.txt
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) tool run pip-audit -r /tmp/clearledger-requirements.txt --no-deps --disable-pip

reset-demo:
	docker compose down -v
	docker compose up -d db
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run alembic upgrade head
	UV_CACHE_DIR=$(UV_CACHE_DIR) $(UV) run python -m generator.cli --dataset demo --seed 20260827
