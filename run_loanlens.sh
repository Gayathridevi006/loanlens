#!/usr/bin/env bash

set -u

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$PROJECT_DIR/frontend"

if [[ -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  PYTHON_BIN="$PROJECT_DIR/.venv/bin/python"
else
  PYTHON_BIN="${PYTHON_BIN:-python3}"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python was not found. Install Python 3 or create .venv first." >&2
  exit 1
fi

if ! "$PYTHON_BIN" -c "import uvicorn, fastapi, sqlalchemy" >/dev/null 2>&1; then
  echo "Backend dependencies are missing." >&2
  echo "Run: $PYTHON_BIN -m pip install -r backend/requirements.txt" >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js and npm first." >&2
  exit 1
fi

if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
  echo "Frontend dependencies are missing." >&2
  echo "Run: cd frontend && npm install" >&2
  exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

stop_services() {
  trap - INT TERM EXIT
  echo
  echo "Stopping LoanLens services..."
  [[ -n "$BACKEND_PID" ]] && kill "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && kill "$FRONTEND_PID" 2>/dev/null || true
  [[ -n "$BACKEND_PID" ]] && wait "$BACKEND_PID" 2>/dev/null || true
  [[ -n "$FRONTEND_PID" ]] && wait "$FRONTEND_PID" 2>/dev/null || true
}

trap stop_services INT TERM EXIT

cd "$PROJECT_DIR" || exit 1
echo "Applying database migrations..."
"$PYTHON_BIN" -m alembic upgrade head || exit 1
echo "Starting backend: http://localhost:8000"
echo "API documentation: http://localhost:8000/docs"
"$PYTHON_BIN" -m uvicorn backend.app:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo "Starting frontend: http://localhost:5173"
(
  cd "$FRONTEND_DIR" || exit 1
  npm run dev -- --host 0.0.0.0 --port 5173
) &
FRONTEND_PID=$!

echo "LoanLens is starting. Press Ctrl+C to stop both services."

while kill -0 "$BACKEND_PID" 2>/dev/null && kill -0 "$FRONTEND_PID" 2>/dev/null; do
  sleep 1
done

echo "One service stopped; shutting down the other service." >&2
exit 1
