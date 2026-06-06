Ты — senior full-stack engineer и systems architect.

Нужно создать первый этап проекта weather-polymarket-bot как аккуратный, расширяемый монорепо-каркас.

ГЛАВНАЯ ЦЕЛЬ ЭТАПА
Сделать foundation layer для weather-polymarket-bot:
- backend
- frontend
- connectors
- discovery layer через Polymarket Gamma API
- нормализацию погодных рынков
- локальное JSON-хранилище snapshots
- dashboard для просмотра рынков

НЕ НУЖНО НА ЭТОМ ЭТАПЕ:
- НЕ делать trading
- НЕ делать CLOB execution
- НЕ делать автосделки
- НЕ делать Polygon RPC
- НЕ делать wallet/auth
- НЕ делать Open-Meteo ingestion
- НЕ делать forecast engines
- НЕ делать signal engine
- НЕ делать pricing engine
- НЕ делать dead zone strategy
- НЕ делать Postgres
- НЕ делать websocket
- НЕ делать users/auth

На этом этапе нужна только read-only архитектура:
- discovery активных weather markets через Gamma API
- нормализация
- локальное snapshot storage
- backend API
- frontend dashboard

==================================================
ОФИЦИАЛЬНЫЕ РЕФЕРЕНСЫ POLYMARKET — ИСПОЛЬЗОВАТЬ КАК PRIMARY SOURCE
==================================================

Обязательно изучи и используй как основной reference:
1. https://docs.polymarket.com
2. Gamma docs / market data overview / fetching markets guide
3. https://gamma-api.polymarket.com/docs
4. официальный GitHub:
   https://github.com/Polymarket/agents
5. особенно:
   https://github.com/Polymarket/agents/blob/main/agents/polymarket/gamma.py

ВАЖНО:
- Не выдумывай Gamma API.
- Не опирайся на неофициальные SDK как primary source.
- Приоритет референсов:
  1) docs.polymarket.com
  2) gamma-api.polymarket.com/docs
  3) официальный GitHub Polymarket как practical example
- Если точные поля ответа Gamma могут отличаться, делай defensive parsing через .get(...) и optional pydantic fields.

ФАКТЫ, НА КОТОРЫЕ НУЖНО ОПИРАТЬСЯ:
- Gamma API публичный и не требует auth для discovery.
- Для discovery всех активных рынков предпочтительно использовать endpoint /events.
- Для active open events использовать active=true и closed=false.
- Events содержат вложенные markets.
- Нужно учитывать pagination через limit/offset.
- Нужно строить отдельный discovery layer, не смешивая его со strategy/execution.

==================================================
ОБЩИЕ ТРЕБОВАНИЯ К КОДУ
==================================================

- Делай код чистым, модульным и расширяемым.
- Не делай однофайловую кашу.
- Сразу раскладывай код по папкам.
- Используй type hints.
- Используй pydantic models.
- Добавляй docstrings в ключевые классы и сервисы.
- Не дублируй логику.
- Не делай giant functions.
- Разделяй:
  - low-level connector
  - application services
  - backend API layer
  - frontend view layer
  - local storage layer
- Добавь понятные логи.
- Архитектура должна быть ready для будущего расширения под:
  - weather forecast connectors
  - bucket pricing storage
  - SQLite event history
  - signal engine
  - dead zone logic
  - CLOB execution

==================================================
ТЕХСТЕК
==================================================

- Backend: Python 3.12 + FastAPI
- Frontend: React + TypeScript + Vite
- Storage: локальные JSON/JSONL файлы, без тяжелой БД
- HTTP client backend: httpx
- Data models: pydantic
- Frontend fetching: fetch API или axios
- Styling frontend: простой, аккуратный, функциональный UI
- Проект должен запускаться локально
- Добавь docker-compose без сложной infra
- Добавь README с инструкцией запуска

==================================================
СТРУКТУРА ПРОЕКТА
==================================================

Создай проект со структурой:

weather-polymarket-bot/
  backend/
  frontend/
  connectors/
  data/
  scripts/
  README.md
  docker-compose.yml
  .env.example

Подробная структура:

weather-polymarket-bot/
  backend/
    app/
      api/
        routes/
          health.py
          markets.py
          discovery.py
        dependencies.py
      services/
        discovery_service.py
        market_service.py
        snapshot_service.py
      models/
        api_models.py
        market_models.py
      core/
        config.py
        logging.py
      main.py
    requirements.txt

  connectors/
    polymarket/
      gamma_client.py
      market_normalizer.py
      weather_market_filter.py
      schemas.py

  frontend/
    src/
      api/
        markets.ts
      components/
        MarketTable.tsx
        FiltersBar.tsx
        StatusCard.tsx
      pages/
        Dashboard.tsx
      types/
        market.ts
      App.tsx
      main.tsx
      index.css
    package.json
    vite.config.ts

  data/
    snapshots/
      active_weather_markets.json
      discovery_status.json
      markets/
    raw/
      gamma_events_raw.json

  scripts/
    bootstrap.sh

  README.md
  docker-compose.yml
  .env.example

==================================================
АРХИТЕКТУРНАЯ ИДЕЯ
==================================================

Архитектура должна быть read-only и многослойной:

1. connectors/polymarket
- отвечает только за интеграцию с внешним Gamma API
- никаких application-specific side effects внутри low-level client
- никаких UI concerns
- никаких trading concerns

2. backend/services
- orchestration
- discovery
- normalization
- snapshot persistence
- querying saved markets

3. backend/api/routes
- thin API layer
- вызывает сервисы
- возвращает API response models

4. frontend
- не ходит напрямую в Gamma API
- работает только с backend API
- показывает dashboard и статус discovery

==================================================
CONNECTORS LAYER
==================================================

Создай connectors/polymarket с такими файлами:

1. gamma_client.py
Low-level client для Gamma API.
Он должен:
- использовать httpx
- иметь configurable base_url, timeout, page_limit, max_pages
- уметь получать events через /events
- поддерживать pagination через limit/offset
- уметь safely retry в разумных пределах
- возвращать сырой JSON или pydantic-parsed structures
- НЕ содержать бизнес-логику приложения
- НЕ фильтровать weather внутри gamma_client
- НЕ сохранять файлы на диск внутри gamma_client

2. schemas.py
Pydantic models для внешнего Gamma API.
Сделай defensive parsing.
Все неоднозначные поля — optional.
Разреши extra поля при необходимости.
Минимально опиши:
- GammaTag
- GammaMarket
- GammaEvent

Сделай модели устойчивыми к отсутствующим полям:
- id
- slug
- title
- question
- description
- active
- closed
- endDate
- volume
- liquidity
- category
- tags
- markets
- outcomes
- outcomePrices
- clobTokenIds
и т.д. только как optional-safe schema.

3. weather_market_filter.py
Отдельный расширяемый слой weather filtering.
Сделай класс или набор функций.
На первом этапе используй heuristics-based rules:
- category/tag содержит weather/climate/temperature/rain/snow/wind/forecast
- title/question/event title содержит:
  - highest temperature
  - temperature in
  - rain
  - rainfall
  - snowfall
  - wind
  - weather
  - hottest
  - coldest
  - precipitation
  - hottest city
  - high temperature
  - low temperature

Сделай это легко расширяемым.
Никакого hardcode “только temperature”.
Заложи foundation под future rules-based parsing.

4. market_normalizer.py
Нормализует Gamma event + market в внутреннюю структуру WeatherMarket.
Должен быть устойчив к отсутствующим полям.
Должен извлекать:
- slug
- title
- event_title
- question
- tags
- category
- active
- closed
- end_date
- liquidity
- volume
- outcomes
- outcome_prices
- market_type
- city_hint
- country_hint
- resolution_source_hint
- raw_source

Сохраняй в raw_source полезный фрагмент исходного event/market, а не абсолютно весь мусорный объект, если это слишком шумно.

==================================================
ВНУТРЕННЯЯ НОРМАЛИЗОВАННАЯ МОДЕЛЬ
==================================================

Создай внутреннюю модель WeatherMarket.
Поля:

- id: str | int | None
- event_id: str | int | None
- slug: str
- title: str
- question: str | None
- event_title: str | None
- category: str | None
- tags: list[str]
- active: bool
- closed: bool
- end_date: str | None
- liquidity: float | None
- volume: float | None
- outcomes: list[str]
- outcome_prices: list[float] | None
- market_type: str | None
- city_hint: str | None
- country_hint: str | None
- resolution_source_hint: str | None
- raw_source: dict

ВАЖНО:
- defensive parsing
- не падать на неполных данных
- title/slug стараться нормализовать аккуратно
- если slug отсутствует, предусмотреть безопасный fallback slug
- если outcomes/outcomePrices отсутствуют, возвращать пустой список или None, но не падать

==================================================
SNAPSHOT STORAGE — ОБЯЗАТЕЛЬНО РЕАЛИЗОВАТЬ В JSON-СТИЛЕ
==================================================

Используй локальное JSON-хранилище как foundation layer.
НЕ использовать Postgres.
НЕ использовать SQLite на этом этапе.
НЕ использовать Redis.

Нужно совместимое и расширяемое хранение в стиле weather-bot, но адаптированное под discovery-only phase.

Структура хранения:
- data/raw/gamma_events_raw.json
- data/snapshots/active_weather_markets.json
- data/snapshots/discovery_status.json
- data/snapshots/markets/{market_slug}.json

ВАЖНО:
На phase 1 нет торговли, но storage нужно строить так, чтобы потом можно было расширить в сторону полноценного market history.

Сделай два уровня хранения:

A. AGGREGATE SNAPSHOTS
1. raw gamma response:
   data/raw/gamma_events_raw.json

2. normalized weather markets list:
   data/snapshots/active_weather_markets.json

3. discovery status/meta:
   data/snapshots/discovery_status.json

B. PER-MARKET FILE STORAGE
Каждый нормализованный weather market хранить отдельным JSON-файлом:
- data/snapshots/markets/{market_slug}.json

Slug должен быть filename-safe.
Если slug пустой, сделай deterministic fallback, например от event_id/market_id/title.

==================================================
КАК ИМЕННО ХРАНИТЬ PER-MARKET FILE
==================================================

Сделай хранение по принципу:
- one market = one file
- append-only snapshots history
- current market state + история snapshots в одном JSON

Создай функции примерно такого вида:
- market_path(slug: str) -> Path
- load_market(slug: str) -> dict | None
- save_market(market: dict) -> None
- load_all_markets() -> list[dict]
- new_market_file(weather_market: WeatherMarket) -> dict

Структура файла market snapshot должна быть такой:

{
  "slug": "...",
  "market_id": "...",
  "event_id": "...",
  "title": "...",
  "question": "...",
  "event_title": "...",
  "category": "...",
  "tags": [],
  "active": true,
  "closed": false,
  "end_date": "...",
  "liquidity": null,
  "volume": null,
  "outcomes": [],
  "outcome_prices": null,
  "market_type": null,
  "city_hint": null,
  "country_hint": null,
  "resolution_source_hint": null,

  "status": "discovered",
  "last_seen_at": "...",
  "first_seen_at": "...",
  "last_refreshed_at": "...",

  "market_snapshots": [],
  "raw_source": {},
  "created_at": "...",
  "updated_at": "..."
}

Пояснения:
- status на этом этапе может быть:
  - discovered
  - inactive
  - closed
  - archived
- first_seen_at — когда впервые найден
- last_seen_at — когда последний раз найден в discovery
- last_refreshed_at — когда последний раз обновлен из Gamma
- created_at / updated_at — технические timestamps

==================================================
MARKET SNAPSHOTS — APPEND-ONLY HISTORY
==================================================

Поле market_snapshots должно быть append-only массивом.
На каждом refresh нужно добавлять snapshot состояния рынка.

Структура одного market snapshot:

{
  "ts": "...",
  "active": true,
  "closed": false,
  "end_date": "...",
  "liquidity": null,
  "volume": null,
  "outcomes_count": 0,
  "outcome_prices": null
}

Если есть смысл, можно добавить:
- "title"
- "question"
- "event_title"
но не обязательно дублировать слишком много.

Главное:
- не перезаписывать историю snapshots
- append новый snapshot на каждый refresh
- верхнеуровневые поля market file должны отражать текущее состояние
- market_snapshots должны хранить историю изменений

==================================================
ЧТО ХРАНИТЬ В AGGREGATE FILES
==================================================

1. active_weather_markets.json
Сохраняй в виде объекта, а не просто голого массива, например:

{
  "generated_at": "...",
  "source": "gamma_api",
  "count": 123,
  "markets": [ ... normalized WeatherMarket ... ]
}

2. discovery_status.json
Например:

{
  "last_refresh_at": "...",
  "total_events_fetched": 0,
  "total_weather_markets": 0,
  "raw_snapshot_path": "data/raw/gamma_events_raw.json",
  "normalized_snapshot_path": "data/snapshots/active_weather_markets.json",
  "per_market_snapshot_dir": "data/snapshots/markets",
  "status": "ok" 
}

Если refresh ни разу не запускался, backend не должен падать.
Должен уметь:
- вернуть пустой список рынков
- вернуть статус “never refreshed yet” или аналогичное состояние

==================================================
BACKEND SERVICE LAYER
==================================================

Создай backend/app/services:

1. snapshot_service.py
Отвечает за локальное файловое хранение.
Должен:
- гарантировать наличие папок
- читать/писать raw snapshot
- читать/писать normalized snapshot
- читать/писать discovery_status
- читать/писать per-market files
- обновлять per-market file по схеме:
  - если market не существовал -> создать через new_market_file(...)
  - если существовал -> обновить текущие поля
  - добавить snapshot в market_snapshots
  - обновить updated_at, last_seen_at, last_refreshed_at

Сделай код аккуратным, с Pathlib.
Используй json.dumps(..., indent=2, ensure_ascii=False)

2. discovery_service.py
Должен:
- вызывать gamma_client
- получать активные events
- фильтровать weather-related events/markets
- нормализовать результаты
- сохранять raw snapshot в data/raw/gamma_events_raw.json
- сохранять normalized snapshot в data/snapshots/active_weather_markets.json
- обновлять discovery_status.json
- синхронизировать per-market files в data/snapshots/markets/
- возвращать список weather markets

Дополнительно:
- если на новом refresh какой-то ранее найденный market больше не active/open, ты можешь:
  - либо не удалять market file
  - а обновлять его status в archived/inactive/closed при возможности
- не делай destructive deletion без необходимости

3. market_service.py
Должен:
- читать уже сохраненный normalized snapshot
- читать per-market files
- уметь отдавать список рынков
- уметь фильтровать по query params
- поддерживать:
  - search
  - active_only
  - limit
  - offset
- уметь искать рынок по slug
- если snapshots отсутствуют, корректно возвращать пустой результат

==================================================
BACKEND API
==================================================

Создай FastAPI backend со следующими endpoint’ами:

GET /health
- возвращает ok status

POST /api/discovery/refresh
- запускает discovery weather markets из Gamma API
- сохраняет fresh snapshot
- возвращает:
  - total_events_fetched
  - total_weather_markets
  - generated_at
  - snapshot paths

GET /api/discovery/status
- возвращает:
  - когда был последний refresh
  - сколько events fetched
  - сколько weather markets найдено
  - путь к raw snapshot
  - путь к normalized snapshot
  - путь к per-market dir
  - статус

GET /api/markets
- возвращает нормализованный список weather markets
- поддерживает query params:
  - search
  - active_only
  - limit
  - offset

GET /api/markets/{slug}
- возвращает один рынок по slug
- желательно возвращать per-market JSON с текущим состоянием и history snapshots

Добавь response models через pydantic.

==================================================
CONFIG
==================================================

Добавь config через environment variables:

- BACKEND_HOST
- BACKEND_PORT
- GAMMA_BASE_URL
- GAMMA_PAGE_LIMIT
- GAMMA_MAX_PAGES
- REQUEST_TIMEOUT_SECONDS
- SNAPSHOT_DIR
- RAW_DIR
- FRONTEND_ORIGIN

Можно дополнительно:
- MARKETS_SNAPSHOT_DIR
- LOG_LEVEL

Сделай:
- backend/app/core/config.py
- .env.example

==================================================
PAGINATION И RATE SAFETY
==================================================

Gamma discovery делай через /events.
Реализуй:
- active=true
- closed=false
- order=id
- ascending=false
- limit
- offset

Pagination:
- configurable page limit
- configurable max pages
- не бесконечный цикл
- если страница пустая, останавливайся
- при ошибках логируй аккуратно
- timeout configurable
- retry limited and safe

==================================================
FRONTEND
==================================================

Сделай frontend dashboard на React + TS + Vite.

Требования:
- frontend не должен ходить напрямую в Gamma API
- frontend работает только с backend API
- одна основная страница: Dashboard.tsx

Функциональность:
1. При загрузке вызывает GET /api/markets
2. Также может вызвать GET /api/discovery/status
3. Показывает summary cards:
   - total markets
   - active markets
   - markets with bucket outcomes
4. Показывает таблицу рынков

В таблице вывести:
- title
- slug
- event_title
- active
- closed
- end_date
- outcomes count
- liquidity
- volume
- tags

Добавь:
- поиск по title/slug/event_title
- кнопку refresh discovery -> POST /api/discovery/refresh
- индикатор последнего refresh
- аккуратную обработку loading/error/empty states
- хорошее отображение длинных slug/title
- техничный, чистый UI без дизайнерских излишеств

Компоненты:
- StatusCard.tsx
- FiltersBar.tsx
- MarketTable.tsx

Типы:
- frontend/src/types/market.ts
- фронтенд-модели должны соответствовать backend response

==================================================
README
==================================================

Сделай README с разделами:
- what this project does
- current scope of phase 1
- architecture overview
- folder structure
- how to run backend
- how to run frontend
- how to run via docker-compose
- how to refresh discovery
- available API endpoints
- snapshot storage design
- official Polymarket references used
- next planned phases

Обязательно явно укажи:
- интеграция основана на официальной документации Polymarket
- Gamma API используется только для discovery/metadata
- на этом этапе система read-only и не совершает сделок

==================================================
DOCKER И BOOTSTRAP
==================================================

Добавь:
- docker-compose.yml
- scripts/bootstrap.sh

bootstrap.sh должен:
- подготавливать папки data/raw, data/snapshots, data/snapshots/markets
- выводить подсказки по запуску

docker-compose:
- backend service
- frontend service
- без сложной infra
- с bind mount для data/

==================================================
КОНЕЧНЫЙ РЕЗУЛЬТАТ
==================================================

После завершения должен получиться рабочий локальный проект, где:
- backend поднимается
- frontend поднимается
- можно нажать refresh discovery
- backend тянет active weather markets из Gamma API
- сохраняет raw snapshot
- сохраняет normalized snapshot
- сохраняет per-market JSON files
- frontend показывает рынки в таблице
- если snapshots отсутствуют, всё работает без падений

==================================================
ФОРМАТ РЕЗУЛЬТАТА
==================================================

Сразу создавай файлы проекта.

Покажи:
1. полное дерево файлов
2. содержимое ключевых файлов
3. команды запуска
4. кратко обозначь допущения
5. если Gamma response fields могут отличаться — заложи defensive parsing
6. backend и connectors реализуй сначала полностью
7. frontend делай после backend
8. не делай ничего сверх scope phase 1

==================================================
ОСОБОЕ ТРЕБОВАНИЕ ПО STORAGE STYLE
==================================================

При реализации snapshot storage используй стиль, совместимый с подходом weather bot:
- plain JSON files
- one market = one file
- append-only snapshots
- current market state в верхнем уровне файла
- агрегированные discovery snapshots отдельными файлами
- save/update market file после каждого refresh
- никакой БД на этом этапе

Но адаптируй это под discovery-only stage:
- без position execution
- без trading fields
- без CLOB order lifecycle
- при этом структура должна быть расширяемой для будущих phase 2/3

Если считаешь полезным, можешь заложить в per-market JSON пустое поле для future extensions, например:
- "extensions": {}
но без лишней сложности.

==================================================
ВАЖНО
==================================================

Не пиши демо-скрипт.
Это должен быть качественный foundation layer для дальнейшего развития weather trading bot.

Сделай решение production-minded, но без overengineering.