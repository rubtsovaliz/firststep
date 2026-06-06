#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

mkdir -p data/raw data/snapshots data/snapshots/events

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example"
fi

echo "Data directories ready:"
echo "  - data/raw"
echo "  - data/snapshots"
echo "  - data/snapshots/events   (one file per city+date, e.g. seoul_2026-06-05.json)"
echo ""
echo "Backend (from repo root):"
echo "  pip install -r backend/requirements.txt"
echo "  PYTHONPATH=. uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000"
echo ""
echo "Frontend:"
echo "  cd frontend && npm install && npm run dev"
echo ""
echo "Docker:"
echo "  docker compose up --build"
