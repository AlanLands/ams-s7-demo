#!/usr/bin/env bash
# Launch the S7 Admin panel — the operator surface over the product
# configuration plane (prompt sets, LLM settings, roles, users, runs, audit).
#
# Binds to 127.0.0.1 deliberately, like the Control Centre. Open by default;
# set S7_ADMIN_TOKEN to require `X-Admin-Token` on every /api/admin request.
# Everything it changes lands under config/ (gitignored) and is audited.
set -euo pipefail

cd "$(dirname "$0")/.."

PORT="${PORT:-8730}"

if [ -x .venv/bin/uvicorn ]; then
  UV=.venv/bin/uvicorn
elif [ -x .venv/Scripts/uvicorn.exe ]; then
  UV=.venv/Scripts/uvicorn.exe
elif command -v uvicorn >/dev/null 2>&1; then
  UV=uvicorn
else
  echo "uvicorn not found. Create the venv first:" >&2
  echo "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
  exit 1
fi

echo "S7 Admin -> http://127.0.0.1:${PORT}"
echo "Ctrl-C to stop."
exec "$UV" apps.admin.server:app --host 127.0.0.1 --port "$PORT" "$@"
