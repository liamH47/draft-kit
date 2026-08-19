# Stage 1: build the frontend
FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: python runtime
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_NO_DEV=1
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-install-project
COPY backend/src ./src
RUN uv sync --frozen
COPY --from=frontend /build/dist ./static

ENV DRAFTKIT_DATA_DIR=/data \
    DRAFTKIT_STATIC_DIR=/app/static
VOLUME /data
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "draftkit.main:app", "--host", "0.0.0.0", "--port", "8000"]
