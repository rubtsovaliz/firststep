import { useCallback, useEffect, useRef, useState } from "react";
import type { EnsembleForecastMap, ForecastMap } from "../api/forecasts";
import {
  collectLoadedCityEvents,
  fetchHistoryCities,
  fetchHistoryCityEvents,
  fetchHistoryForecastsWithPause,
  forecastsFromHistoryEvents,
  mergeHistoryEvents,
  needsHistoryOpenMeteoFetch,
  type HistoryCity,
  type HistoryEvent,
} from "../api/history";
import { HistoryCityAccordion } from "../components/HistoryCityAccordion";

function applyMapsFromCityEvents(cityEvents: Record<string, HistoryEvent[]>) {
  const { single, ensemble } = forecastsFromHistoryEvents(collectLoadedCityEvents(cityEvents));
  return { single, ensemble };
}

export function History() {
  const [cities, setCities] = useState<HistoryCity[]>([]);
  const [cityEvents, setCityEvents] = useState<Record<string, HistoryEvent[]>>({});
  const [expandedCities, setExpandedCities] = useState<Set<string>>(new Set());
  const [loadingCities, setLoadingCities] = useState<Set<string>>(new Set());
  const [loadingCityFiles, setLoadingCityFiles] = useState<Set<string>>(new Set());
  const [loadingCityOpenMeteo, setLoadingCityOpenMeteo] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [forecasts, setForecasts] = useState<ForecastMap>({});
  const [ensembleForecasts, setEnsembleForecasts] = useState<EnsembleForecastMap>({});
  const [pendingKeys, setPendingKeys] = useState<Set<string>>(new Set());
  const forecastRunId = useRef(0);

  const updateForecastMaps = useCallback((nextCityEvents: Record<string, HistoryEvent[]>) => {
    const { single, ensemble } = applyMapsFromCityEvents(nextCityEvents);
    setForecasts(single);
    setEnsembleForecasts(ensemble);
  }, []);

  const clearForecastState = useCallback(() => {
    setForecasts({});
    setEnsembleForecasts({});
    setPendingKeys(new Set());
  }, []);

  const loadCities = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistoryCities();
      setCities(data.cities);
      setCityEvents({});
      setExpandedCities(new Set());
      clearForecastState();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load history");
      setCities([]);
      setCityEvents({});
      clearForecastState();
    } finally {
      setLoading(false);
    }
  }, [clearForecastState]);

  useEffect(() => {
    void loadCities();
  }, [loadCities]);

  const loadCityEvents = useCallback(
    async (citySlug: string) => {
      setLoadingCities((prev) => new Set(prev).add(citySlug));
      try {
        const data = await fetchHistoryCityEvents(citySlug);
        setCityEvents((prev) => {
          if (prev[citySlug]) {
            return prev;
          }
          const next = { ...prev, [citySlug]: data.events };
          updateForecastMaps(next);
          return next;
        });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Не удалось загрузить город");
      } finally {
        setLoadingCities((prev) => {
          const next = new Set(prev);
          next.delete(citySlug);
          return next;
        });
      }
    },
    [updateForecastMaps],
  );

  const handleToggleCity = useCallback(
    (citySlug: string, open: boolean) => {
      setExpandedCities((prev) => {
        const next = new Set(prev);
        if (open) {
          next.add(citySlug);
        } else {
          next.delete(citySlug);
        }
        return next;
      });
      if (open) {
        void loadCityEvents(citySlug);
      }
    },
    [loadCityEvents],
  );

  const refreshCitySummaries = useCallback(async () => {
    const data = await fetchHistoryCities();
    setCities(data.cities);
  }, []);

  const fetchOpenMeteoForStorageKeys = useCallback(
    async (storageKeys: string[], runId: number) => {
      setPendingKeys(new Set(storageKeys));
      await fetchHistoryForecastsWithPause(storageKeys, async (filled) => {
        if (forecastRunId.current !== runId) {
          return;
        }
        setCityEvents((prev) => {
          const next: Record<string, HistoryEvent[]> = {};
          for (const [slug, rows] of Object.entries(prev)) {
            next[slug] = mergeHistoryEvents(rows, filled);
          }
          updateForecastMaps(next);
          setPendingKeys(
            new Set(
              collectLoadedCityEvents(next)
                .filter(
                  (row) =>
                    storageKeys.includes(row.storage_key) &&
                    needsHistoryOpenMeteoFetch(row),
                )
                .map((row) => row.storage_key),
            ),
          );
          return next;
        });
      });
      if (forecastRunId.current !== runId) {
        return;
      }
      setPendingKeys(new Set());
      await refreshCitySummaries();
    },
    [refreshCitySummaries, updateForecastMaps],
  );

  const handleLoadCityFromFiles = async (citySlug: string) => {
    setLoadingCityFiles((prev) => new Set(prev).add(citySlug));
    setError(null);
    try {
      const data = await fetchHistoryCityEvents(citySlug);
      setCityEvents((prev) => {
        const next = { ...prev, [citySlug]: data.events };
        updateForecastMaps(next);
        return next;
      });
      await refreshCitySummaries();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить из файлов");
    } finally {
      setLoadingCityFiles((prev) => {
        const next = new Set(prev);
        next.delete(citySlug);
        return next;
      });
    }
  };

  const handleLoadCityFromOpenMeteo = async (citySlug: string) => {
    const events = cityEvents[citySlug] ?? [];
    const missing = events
      .filter(needsHistoryOpenMeteoFetch)
      .map((row) => row.storage_key);
    if (missing.length === 0) {
      return;
    }

    const runId = ++forecastRunId.current;
    setLoadingCityOpenMeteo((prev) => new Set(prev).add(citySlug));
    setError(null);
    try {
      await fetchOpenMeteoForStorageKeys(missing, runId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить с Open-Meteo");
      setPendingKeys(new Set());
    } finally {
      if (forecastRunId.current === runId) {
        setLoadingCityOpenMeteo((prev) => {
          const next = new Set(prev);
          next.delete(citySlug);
          return next;
        });
      }
    }
  };

  return (
    <div className="dashboard">
      {error ? <div className="error-banner">{error}</div> : null}

      {loading ? (
        <p className="loading">Загрузка городов…</p>
      ) : (
        <>
          <HistoryCityAccordion
            cities={cities}
            cityEvents={cityEvents}
            expandedCities={expandedCities}
            loadingCities={loadingCities}
            loadingCityFiles={loadingCityFiles}
            loadingCityOpenMeteo={loadingCityOpenMeteo}
            forecasts={forecasts}
            ensembleForecasts={ensembleForecasts}
            pendingKeys={pendingKeys}
            onToggleCity={handleToggleCity}
            onLoadCityFromFiles={(slug) => void handleLoadCityFromFiles(slug)}
            onLoadCityFromOpenMeteo={(slug) => void handleLoadCityFromOpenMeteo(slug)}
          />
        </>
      )}
    </div>
  );
}
