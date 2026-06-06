FROM python:3.13-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

ENV VENDOR_SERVER_HOST=127.0.0.1
ENV VENDOR_SERVER_PORT=8001
ENV PORT=8080

RUN chmod +x scripts/start.sh

EXPOSE 8080

CMD ["/bin/sh", "/app/scripts/start.sh"]
