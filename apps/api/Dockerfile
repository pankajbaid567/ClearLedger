FROM python:3.13-slim AS runtime-base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv==0.11.25

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/api ./apps/api
COPY db ./db
COPY evaluator ./evaluator
COPY generator ./generator
COPY packages ./packages
COPY policies ./policies
COPY prompts ./prompts
COPY services ./services
COPY alembic.ini ./alembic.ini

RUN useradd --create-home --uid 10001 clearledger \
    && mkdir -p /var/lib/clearledger/uploads \
    && chown -R clearledger:clearledger /var/lib/clearledger

ENV UPLOAD_DIR=/var/lib/clearledger/uploads
USER clearledger
EXPOSE 8000

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000"]

# Only this explicitly selected target contains freshly generated synthetic
# fixtures and their evaluator oracle. It never copies private host files.
FROM runtime-base AS demo
USER root
RUN uv run --no-sync python -m generator.cli --dataset demo --seed 20260827
USER clearledger
ENV APP_MODE=local_demo
CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000"]

# The default image is shared mode and contains neither source fixtures nor truth.
# Authentication must be configured at deployment time; otherwise API access fails closed.
FROM runtime-base AS runtime
ENV APP_MODE=shared
CMD ["uv", "run", "--no-sync", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
