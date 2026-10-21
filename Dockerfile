FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.19 AS uv
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
WORKDIR /app
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-editable \
    && mkdir /data && chown 1000:1000 /data
COPY scripts/fetch_woob_modules.py /tmp/fetch_woob_modules.py
RUN python /tmp/fetch_woob_modules.py --destination /app/bank_modules
COPY --from=frontend /frontend/dist /app/frontend/dist
USER 1000:1000
EXPOSE 8000
CMD ["uvicorn", "budgetward.api:app_factory", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
