FROM python:3.13-slim

WORKDIR /app

# Node 20 + Mailgun MCP server pre-installed so the escalation_notifier subagent
# can launch `@mailgun/mcp-server` over stdio without a first-run npx fetch.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g @mailgun/mcp-server@latest \
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
