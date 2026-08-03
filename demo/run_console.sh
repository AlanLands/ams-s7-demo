#!/usr/bin/env bash
# Launch the S7 delivery console.
#
# Binds to 127.0.0.1 deliberately: this is a presenter's local demo, not a
# service. Nothing here needs an API key — artifacts are staged (Sprint 0) and
# will be replayed from committed recordings (Sprint 3), so it runs offline.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${PORT:-8700}"

if [ -x .venv/bin/uvicorn ]; then
  PY=.venv/bin/uvicorn
elif command -v uvicorn >/dev/null 2>&1; then
  PY=uvicorn
else
  echo "uvicorn not found. Create the venv first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "S7 delivery console -> http://127.0.0.1:${PORT}"
echo "Ctrl-C to stop."
exec "$PY" apps.console.server:app --host 127.0.0.1 --port "$PORT" "$@"
