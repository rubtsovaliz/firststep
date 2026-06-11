import type { ForecastBatchResult } from "./forecasts";
import type { WeatherEvent } from "../types/market";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export interface HistoryForecastSlice {
  city_slug: string;
  date: string;
  metric: "high" | "low";
  model?: string | null;
  requested_model?: string | null;
  model_fallback?: boolean;
  unit?: string | null;
  temp?: number | null;
  error?: string | null;
  models_temps?: Array<{
    model: string;
    temp: number | null;
    error?: string | null;
  }> | null;
}

export interface HistoryEvent {
  storage_key: string;
  date: string;
  event_title: string;
  city_slug: string;
  metric: "high" | "low";
  win: string;
  unit?: string | null;
  forecasts_cached?: boolean;
  forecasts_saved_at?: string | null;
  single_model?: HistoryForecastSlice | null;
  ensemble?: HistoryForecastSlice | null;
}

export interface HistoryCity {
  city_slug: string;
  event_count: number;
  forecasts_cached_count: number;
}

export interface HistoryCitiesResponse {
  count: number;
  cities: HistoryCity[];
}

export interface HistoryListResponse {
  count: number;
  events: HistoryEvent[];
}

/** Up to API max_length; backend batches Open-Meteo by city. */
export const HISTORY_FORECAST_FETCH_CHUNK = 100;
/** Pause between city batches — single + ensemble (92d) per city. */
export const HISTORY_FORECAST_API_PAUSE_MS = 4000;

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchHistoryForecastsWithPause(
  storageKeys: string[],
  onChunk?: (filled: HistoryEvent[]) => void | Promise<void>,
): Promise<HistoryEvent[]> {
  const results: HistoryEvent[] = [];
  for (let i = 0; i < storageKeys.length; i += HISTORY_FORECAST_FETCH_CHUNK) {
    const chunk = storageKeys.slice(i, i + HISTORY_FORECAST_FETCH_CHUNK);
    const filled = await fetchHistoryForecasts(chunk);
    results.push(...filled);
    if (onChunk) {
      await onChunk(filled);
    }
    if (i + HISTORY_FORECAST_FETCH_CHUNK < storageKeys.length) {
      await sleep(HISTORY_FORECAST_API_PAUSE_MS);
    }
  }
  return results;
}
export const HISTORY_CITY_EVENTS_LIMIT = 5000;

export async function fetchHistoryCities(params?: {
  search?: string;
}): Promise<HistoryCitiesResponse> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);

  const response = await fetch(`${API_BASE}/api/history/cities?${query.toString()}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `History cities request failed: ${response.status}`);
  }
  return response.json() as Promise<HistoryCitiesResponse>;
}

export async function fetchHistoryCityEvents(
  citySlug: string,
  params?: { search?: string },
): Promise<HistoryListResponse> {
  const query = new URLSearchParams();
  query.set("city_slug", citySlug);
  query.set("limit", String(HISTORY_CITY_EVENTS_LIMIT));
  if (params?.search) query.set("search", params.search);

  const response = await fetch(`${API_BASE}/api/history?${query.toString()}`, {
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `History request failed: ${response.status}`);
  }
  return response.json() as Promise<HistoryListResponse>;
}

export async function fetchHistoryForecasts(
  storageKeys: string[],
): Promise<HistoryEvent[]> {
  if (storageKeys.length === 0) {
    return [];
  }
  const response = await fetch(`${API_BASE}/api/history/forecasts/fetch`, {
    method: "POST",
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
    },
    body: JSON.stringify({ storage_keys: storageKeys }),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `History forecast fetch failed: ${response.status}`);
  }
  const data = (await response.json()) as { events: HistoryEvent[] };
  return data.events;
}

export function historyEventToWeatherEvent(row: HistoryEvent): WeatherEvent {
  return {
    storage_key: row.storage_key,
    event_title: row.event_title,
    city_slug: row.city_slug,
    date: row.date,
    unit: row.unit ?? undefined,
    temperature_metric: row.metric,
    market_type: row.metric === "high" ? "max_temperature" : "min_temperature",
    active: false,
    closed: true,
    tags: [],
    all_outcomes: [],
  };
}

export function historySliceToForecastResult(
  slice: HistoryForecastSlice | null | undefined,
): ForecastBatchResult | null {
  if (!slice) {
    return null;
  }
  return {
    city_slug: slice.city_slug,
    date: slice.date,
    metric: slice.metric,
    model: slice.model ?? null,
    requested_model: slice.requested_model ?? null,
    model_fallback: slice.model_fallback ?? false,
    unit: slice.unit ?? null,
    temp: slice.temp ?? null,
    error: slice.error ?? null,
    models_temps: slice.models_temps ?? null,
  };
}

export function forecastKey(citySlug: string, date: string, metric: "high" | "low"): string {
  return `${citySlug.trim().toLowerCase()}|${date}|${metric}`;
}

const HISTORY_ENSEMBLE_PAST_DAYS = 92;

function isWithinEnsembleWindow(eventDate: string): boolean {
  const parsed = Date.parse(`${eventDate}T12:00:00`);
  if (Number.isNaN(parsed)) {
    return false;
  }
  const today = new Date();
  today.setHours(12, 0, 0, 0);
  const deltaDays = Math.floor((today.getTime() - parsed) / 86_400_000);
  return deltaDays >= 0 && deltaDays <= HISTORY_ENSEMBLE_PAST_DAYS;
}

function ensembleHasTemperature(row: HistoryEvent): boolean {
  const ensemble = row.ensemble;
  if (!ensemble) {
    return false;
  }
  if (ensemble.temp != null) {
    return true;
  }
  return (ensemble.models_temps ?? []).some((entry) => entry.temp != null);
}

export function needsEnsembleRefetch(row: HistoryEvent): boolean {
  if (!isWithinEnsembleWindow(row.date)) {
    return false;
  }
  if (!row.ensemble) {
    return true;
  }
  if (ensembleHasTemperature(row)) {
    return false;
  }
  if (row.ensemble.error === "outside_ensemble_window") {
    return isWithinEnsembleWindow(row.date);
  }
  return row.ensemble.error == null || row.ensemble.error === "forecast_unavailable";
}

export function needsHistoryOpenMeteoFetch(row: HistoryEvent): boolean {
  if (!row.forecasts_cached) {
    return true;
  }
  if (row.single_model?.temp == null) {
    return true;
  }
  return needsEnsembleRefetch(row);
}

export function forecastsFromHistoryEvents(events: HistoryEvent[]): {
  single: Record<string, ForecastBatchResult>;
  ensemble: Record<string, ForecastBatchResult>;
} {
  const single: Record<string, ForecastBatchResult> = {};
  const ensemble: Record<string, ForecastBatchResult> = {};
  for (const row of events) {
    const key = forecastKey(row.city_slug, row.date, row.metric);
    const singleResult = historySliceToForecastResult(row.single_model);
    const ensembleResult = historySliceToForecastResult(row.ensemble);
    if (singleResult) {
      single[key] = singleResult;
    }
    if (ensembleResult) {
      ensemble[key] = ensembleResult;
    }
  }
  return { single, ensemble };
}

export function mergeHistoryEvents(
  current: HistoryEvent[],
  updated: HistoryEvent[],
): HistoryEvent[] {
  const byKey = new Map(updated.map((row) => [row.storage_key, row]));
  return current.map((row) => byKey.get(row.storage_key) ?? row);
}

export function collectLoadedCityEvents(
  cityEvents: Record<string, HistoryEvent[]>,
): HistoryEvent[] {
  return Object.values(cityEvents).flat();
}
