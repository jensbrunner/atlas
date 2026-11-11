#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it with: brew install uv" >&2
  exit 1
fi

uv python install 3.12
uv sync --group dev
mkdir -p data
uv run alembic upgrade head

echo
echo "ATLAS M0 is ready. Try:"
echo "  uv run python scripts/offline_turn.py --db data/m0_demo.db --reset"
echo "  uv run pytest"
