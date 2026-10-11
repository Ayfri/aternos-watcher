FROM ghcr.io/astral-sh/uv:python3.14-alpine AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/venv
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

FROM python:3.14-alpine
COPY --from=builder /venv /venv
COPY main.py /app/
USER nobody
CMD ["/venv/bin/python", "/app/main.py"]
