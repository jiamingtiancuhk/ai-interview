#!/usr/bin/env bash
# Build the frontend (if sources changed) and serve everything from one
# process at http://localhost:8000. Requires Ollama running with the model.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$PATH"

if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "Ollama is not running. Open the Ollama app first." >&2
  exit 1
fi

if [ ! -d frontend/node_modules ]; then (cd frontend && npm install); fi
if [ ! -f frontend/dist/index.html ] || [ -n "$(find frontend/src frontend/index.html -newer frontend/dist/index.html -print -quit)" ]; then
  (cd frontend && npm run build)
fi

cd backend
uv sync --quiet
echo "Open http://localhost:8000"
exec uv run uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8000}"
