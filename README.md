# Weather Polymarket Bot

Read-only foundation for discovering and snapshotting weather-related markets on Polymarket via the public Gamma API.

## What this project does

- Fetches active events from Gamma API (`/events`)
- Filters weather-related events and markets (heuristics)
- Normalizes market metadata into internal `WeatherMarket` records
- Persists JSON snapshots (aggregate + per-market files with append-only history)
- Exposes a FastAPI backend and React dashboard

## Phase 1 scope

**Included:** discovery, normalization, local JSON storage, REST API, dashboard.

**Not included:** trading, CLOB execution, wallets, forecasts (Open-Meteo), signals, Postgres, websockets, auth.

Integration is based on official Polymarket documentation:

- https://docs.polymarket.com
- https://gamma-api.polymarket.com/docs
- https://github.com/Polymarket/agents (see `agents/polymarket/gamma.py`)

Gamma API is used only for read-only discovery and metadata. This system does not place orders.

## Architecture

```
connectors/polymarket   → low-level Gamma HTTP client, schemas, filters, normalizer
backend/app/services    → discovery orchestration, snapshot I/O, market queries
backend/app/api         → thin FastAPI routes
frontend                → dashboard (backend API only)
data/                   → raw + snapshot JSON files
```

## Folder structure

```
weather-polymarket-bot/
  backend/app/          FastAPI app
  connectors/polymarket Gamma integration
  frontend/src/         React dashboard
  data/raw/             gamma_events_raw.json
  data/snapshots/       active_weather_markets.json, discovery_status.json, markets/
  scripts/bootstrap.sh
```

## Run locally

### Prerequisites

- Python 3.12+
- Node.js 20+

### Bootstrap

```bash
bash scripts/bootstrap.sh
cp .env.example .env   # if not created by bootstrap
```

### Backend

From repository root:

```bash
pip install -r backend/requirements.txt
set PYTHONPATH=.          # Windows PowerShell: $env:PYTHONPATH="."
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — Vite proxies `/api` to the backend.

### Docker Compose

```bash
docker compose up --build
```

## Refresh discovery

- API: `POST http://localhost:8000/api/discovery/refresh`
- Dashboard: click **Refresh discovery**

Writes:

- `data/raw/gamma_events_raw.json` (combined full scan + `tag_slug=weather`)
- `data/snapshots/active_weather_events.json`
- `data/snapshots/discovery_status.json`
- `data/snapshots/events/{city_slug}_{date}_{high|low}.json` (one Polymarket event = all buckets, append-only `market_snapshots`)

Discovery mode: **combined** — paginated `/events` (`active=true`, `closed=false`) plus weather tag shortcut, deduplicated by event id/slug.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| POST | `/api/discovery/refresh` | Run Gamma discovery + save snapshots |
| GET | `/api/discovery/status` | Last refresh metadata |
| GET | `/api/markets` | List markets (`search`, `active_only`, `limit`, `offset`) |
| GET | `/api/markets/{storage_key}` | Per-event file (e.g. `seoul_2026-06-05_high`, `seoul_2026-06-05_low`) with history |

## Snapshot storage design

- **One Polymarket event = one file** under `data/snapshots/events/` — key `{city_slug}_{date}_{high|low}.json` (highest and lowest for the same city/date are separate files)
- **`all_outcomes`** holds every temperature bucket with `bucket_low` / `bucket_high` from `parse_temp_range`
- **Append-only** `market_snapshots` and `forecast_snapshots` (forecasts filled in a later phase)
- No trading fields (`position`, `pnl`, `order_id`, etc.) in phase 1

## Next planned phases

- Open-Meteo / forecast connectors and `forecast_snapshots`
- Bucket temperature parsing and pricing analytics
- Signal engine and dead-zone logic
- Optional SQLite event history
- CLOB execution (separate module, opt-in)

## Environment variables

See `.env.example`.
