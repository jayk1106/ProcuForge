#!/bin/sh
set -e

VENDOR_HOST="${VENDOR_SERVER_HOST:-127.0.0.1}"
VENDOR_PORT="${VENDOR_SERVER_PORT:-8001}"
API_PORT="${PORT:-8080}"
AGENT_CARD_URL="http://${VENDOR_HOST}:${VENDOR_PORT}/.well-known/agent-card.json"

echo "Starting vendor A2A server on ${VENDOR_HOST}:${VENDOR_PORT}..."
uv run uvicorn vendor_server:app --host "$VENDOR_HOST" --port "$VENDOR_PORT" &
VENDOR_PID=$!

echo "Waiting for vendor agent card at ${AGENT_CARD_URL}..."
TRIES=0
MAX_TRIES=30
until curl -sf "$AGENT_CARD_URL" > /dev/null; do
  TRIES=$((TRIES + 1))
  if [ "$TRIES" -ge "$MAX_TRIES" ]; then
    echo "Vendor A2A server did not become ready within ${MAX_TRIES}s" >&2
    kill "$VENDOR_PID" 2>/dev/null || true
    exit 1
  fi
  sleep 1
done
echo "Vendor A2A server ready"

echo "Starting FastAPI on 0.0.0.0:${API_PORT}..."
exec uv run uvicorn api.main:app --host 0.0.0.0 --port "$API_PORT"
