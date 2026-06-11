import type { WeatherEvent } from "../types/market";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface EnsembleModelTempResult {
  model: string;
  temp: number | null;
  error?: string | null;
}

export interface ForecastBatchResult {
  city_slug: string;
  date: string;
  metric: "high" | "low";
  model: string | null;
  requested_model?: string | null;
  model_fallback?: boolean;
  unit?: string | null;
  temp: number | null;
  error: string | null;
  models_temps?: EnsembleModelTempResult[] | null;
}

export interface ForecastBatchResponse {
  results: ForecastBatchResult[];
}

export type ForecastMap = Record<string, ForecastBatchResult>;

export type ForecastProgress = {
  loaded: number;
  total: number;
};

export const FORECAST_API_PAUSE_MS = 1500;
/** Ensemble API is stricter; pause after each ensemble city batch. */
export const ENSEMBLE_FORECAST_API_PAUSE_MS = 10000;
export const DASHBOARD_FORECAST_CITY_CHUNK = 1;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export function forecastKey(citySlug: string, date: string, metric: "high" | "low"): string {
  return `${citySlug.trim().toLowerCase()}|${date}|${metric}`;
}

export function eventMetric(event: WeatherEvent): "high" | "low" | null {
  if (event.temperature_metric === "high" || event.temperature_metric === "low") {
    return event.temperature_metric;
  }
  if (event.market_type === "max_temperature") return "high";
  if (event.market_type === "min_temperature") return "low";
  return null;
}

export function isEventForecastable(event: WeatherEvent): boolean {
  return Boolean(event.city_slug && event.date && eventMetric(event));
}

export function eventForecastKey(event: WeatherEvent): string | null {
  const metric = eventMetric(event);
  if (!event.city_slug || !event.date || !metric) {
    return null;
  }
  return forecastKey(event.city_slug, event.date, metric);
}

export function buildForecastItems(events: WeatherEvent[]): Array<{
  city_slug: string;
  date: string;
  metric: "high" | "low";
}> {
  const seen = new Set<string>();
  const items: Array<{ city_slug: string; date: string; metric: "high" | "low" }> = [];

  for (const event of events) {
    const metric = eventMetric(event);
    if (!event.city_slug || !event.date || !metric) continue;
    const key = forecastKey(event.city_slug, event.date, metric);
    if (seen.has(key)) continue;
    seen.add(key);
    items.push({
      city_slug: event.city_slug.trim().toLowerCase(),
      date: event.date,
      metric,
    });
  }
  return items;
}

export function countForecastableEvents(events: WeatherEvent[]): number {
  return events.filter(isEventForecastable).length;
}

export function countLoadedForecastEvents(
  events: WeatherEvent[],
  single: ForecastMap,
  ensemble: ForecastMap,
): number {
  return events.filter((event) => {
    const key = eventForecastKey(event);
    if (key == null) {
      return false;
    }
    const hasSingle = key in single && single[key]?.temp != null;
    const hasEnsemble =
      key in ensemble &&
      ((ensemble[key]?.models_temps?.some((entry) => entry.temp != null) ?? false) ||
        ensemble[key]?.temp != null);
    return hasSingle || hasEnsemble;
  }).length;
}

export function groupForecastItemsByCity(
  items: ReturnType<typeof buildForecastItems>,
): Map<string, ReturnType<typeof buildForecastItems>> {
  const byCity = new Map<string, ReturnType<typeof buildForecastItems>>();
  for (const item of items) {
    const list = byCity.get(item.city_slug) ?? [];
    list.push(item);
    byCity.set(item.city_slug, list);
  }
  return byCity;
}

function resultsToMap(results: ForecastBatchResult[]): ForecastMap {
  const map: ForecastMap = {};
  for (const result of results) {
    map[forecastKey(result.city_slug, result.date, result.metric)] = result;
  }
  return map;
}

async function fetchForecastChunk(
  endpoint: "/api/forecasts/batch" | "/api/forecasts/ensemble/batch",
  items: ReturnType<typeof buildForecastItems>,
): Promise<ForecastMap> {
  if (items.length === 0) {
    return {};
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
    body: JSON.stringify({ items }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Forecast request failed: ${response.status}`);
  }

  const data = (await response.json()) as ForecastBatchResponse;
  return resultsToMap(data.results);
}

async function fetchForecastBatchFromEndpoint(
  endpoint: string,
  events: WeatherEvent[],
): Promise<ForecastMap> {
  const items = buildForecastItems(events);
  if (items.length === 0) {
    return {};
  }

  const response = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
    body: JSON.stringify({ items }),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Forecast request failed: ${response.status}`);
  }

  const data = (await response.json()) as ForecastBatchResponse;
  return resultsToMap(data.results);
}

export async function fetchForecastsBatch(events: WeatherEvent[]): Promise<ForecastMap> {
  return fetchForecastBatchFromEndpoint("/api/forecasts/batch", events);
}

export async function fetchEnsembleForecastsBatch(
  events: WeatherEvent[],
): Promise<EnsembleForecastMap> {
  return fetchForecastBatchFromEndpoint("/api/forecasts/ensemble/batch", events);
}

export type EnsembleForecastMap = ForecastMap;

export async function loadDashboardForecastsProgressive(
  events: WeatherEvent[],
  onProgress: (state: {
    single: ForecastMap;
    ensemble: ForecastMap;
    loaded: number;
    total: number;
    pendingKeys: Set<string>;
  }) => void,
  options?: {
    cityChunkSize?: number;
    shouldCancel?: () => boolean;
    initialSingle?: ForecastMap;
    initialEnsemble?: ForecastMap;
  },
): Promise<{ single: ForecastMap; ensemble: ForecastMap }> {
  const total = countForecastableEvents(events);
  const items = buildForecastItems(events);
  const byCity = groupForecastItemsByCity(items);
  const citySlugs = [...byCity.keys()].sort();
  const chunkSize = options?.cityChunkSize ?? DASHBOARD_FORECAST_CITY_CHUNK;

  let single: ForecastMap = { ...(options?.initialSingle ?? {}) };
  let ensemble: ForecastMap = { ...(options?.initialEnsemble ?? {}) };

  const remainingCities = new Set(citySlugs);

  const pendingKeysForRemainingCities = (): Set<string> =>
    new Set(
      events
        .filter(
          (event) =>
            isEventForecastable(event) &&
            event.city_slug &&
            remainingCities.has(event.city_slug),
        )
        .map((event) => event.storage_key),
    );

  const emit = () => {
    onProgress({
      single,
      ensemble,
      loaded: countLoadedForecastEvents(events, single, ensemble),
      total,
      pendingKeys: pendingKeysForRemainingCities(),
    });
  };

  emit();

  for (let i = 0; i < citySlugs.length; i += chunkSize) {
    if (options?.shouldCancel?.()) {
      break;
    }
    const chunkCities = citySlugs.slice(i, i + chunkSize);
    const chunkItems = chunkCities.flatMap((city) => byCity.get(city) ?? []);

    // Ensemble first — single forecast burns the shared IP quota before ensemble runs.
    ensemble = {
      ...ensemble,
      ...(await fetchForecastChunk("/api/forecasts/ensemble/batch", chunkItems)),
    };
    if (options?.shouldCancel?.()) {
      break;
    }
    await sleep(ENSEMBLE_FORECAST_API_PAUSE_MS);
    if (options?.shouldCancel?.()) {
      break;
    }
    single = { ...single, ...(await fetchForecastChunk("/api/forecasts/batch", chunkItems)) };

    for (const city of chunkCities) {
      remainingCities.delete(city);
    }

    emit();

    if (i + chunkSize < citySlugs.length && !options?.shouldCancel?.()) {
      await sleep(FORECAST_API_PAUSE_MS);
    }
  }

  return { single, ensemble };
}

export function lookupForecast(
  forecasts: ForecastMap,
  event: WeatherEvent,
): ForecastBatchResult | null {
  const metric = eventMetric(event);
  if (!event.city_slug || !event.date || !metric) return null;
  return forecasts[forecastKey(event.city_slug, event.date, metric)] ?? null;
}
