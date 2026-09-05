FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY apps ./apps
COPY db ./db
COPY evaluator ./evaluator
COPY generator ./generator
COPY packages ./packages
COPY policies ./policies
COPY prompts ./prompts
COPY services ./services
COPY data/demo ./data/demo
COPY evaluator_private ./evaluator_private
COPY alembic.ini ./alembic.ini

EXPOSE 8000

CMD ["sh", "-c", "uv run --no-sync alembic upgrade head && exec uv run --no-sync uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000"]
