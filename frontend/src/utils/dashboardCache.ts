import type { EnsembleForecastMap, ForecastMap } from "../api/forecasts";
import type { WeatherEvent } from "../types/market";

const CACHE_KEY = "dashboard_cache_v1";

export interface DashboardCache {
  events: WeatherEvent[];
  totalCount: number;
  forecasts: ForecastMap;
  ensembleForecasts: EnsembleForecastMap;
  marketsSavedAt: number;
  forecastsSavedAt: number;
}

export function readDashboardCache(): DashboardCache | null {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as DashboardCache;
    if (!Array.isArray(parsed.events)) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeDashboardCache(cache: DashboardCache): void {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify(cache));
  } catch {
    /* quota or private mode */
  }
}
