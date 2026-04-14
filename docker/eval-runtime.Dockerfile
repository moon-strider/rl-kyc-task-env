FROM python:3.12.2-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /opt/runtime

RUN pip install --no-cache-dir uv==0.7.7

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen

ENV PATH="/opt/runtime/.venv/bin:${PATH}"
