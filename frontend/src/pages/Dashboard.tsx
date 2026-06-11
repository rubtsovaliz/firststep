import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  loadDashboardForecastsProgressive,
  type EnsembleForecastMap,
  type ForecastMap,
  type ForecastProgress,
} from "../api/forecasts";
import {
  fetchAllMarkets,
  fetchDiscoveryStatus,
  refreshDiscovery,
} from "../api/markets";
import { FiltersBar } from "../components/FiltersBar";
import { MarketTable } from "../components/MarketTable";
import { StatusCard } from "../components/StatusCard";
import type { DiscoveryStatus, WeatherEvent } from "../types/market";
import {
  readDashboardCache,
  writeDashboardCache,
} from "../utils/dashboardCache";

const MARKETS_AUTO_REFRESH_MS = 15 * 60 * 1000;
const FORECASTS_AUTO_REFRESH_MS = 6 * 60 * 60 * 1000;

function filterEvents(
  events: WeatherEvent[],
  search: string,
  activeOnly: boolean,
): WeatherEvent[] {
  let list = events;
  if (activeOnly) {
    list = list.filter((event) => event.active && !event.closed);
  }
  const q = search.trim().toLowerCase();
  if (!q) {
    return list;
  }
  return list.filter(
    (event) =>
      (event.event_title ?? "").toLowerCase().includes(q) ||
      (event.storage_key ?? "").toLowerCase().includes(q) ||
      (event.city_slug ?? "").toLowerCase().includes(q) ||
      (event.city_name ?? "").toLowerCase().includes(q) ||
      (event.date ?? "").toLowerCase().includes(q),
  );
}

function formatTimestamp(ms: number | null | undefined): string | null {
  if (!ms) {
    return null;
  }
  return new Date(ms).toLocaleString();
}

function forecastsAreStale(savedAt: number | null | undefined): boolean {
  if (!savedAt) {
    return true;
  }
  return Date.now() - savedAt >= FORECASTS_AUTO_REFRESH_MS;
}

export function Dashboard() {
  const initialCache = useMemo(() => readDashboardCache(), []);

  const [events, setEvents] = useState<WeatherEvent[]>(() => initialCache?.events ?? []);
  const [totalCount, setTotalCount] = useState(() => initialCache?.totalCount ?? 0);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [dataLoaded, setDataLoaded] = useState(() => Boolean(initialCache?.events?.length));
  const [loading, setLoading] = useState(() => !initialCache?.events?.length);
  const [refreshing, setRefreshing] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [forecasts, setForecasts] = useState<ForecastMap>(() => initialCache?.forecasts ?? {});
  const [ensembleForecasts, setEnsembleForecasts] = useState<EnsembleForecastMap>(
    () => initialCache?.ensembleForecasts ?? {},
  );
  const [pendingForecastKeys, setPendingForecastKeys] = useState<Set<string>>(new Set());
  const [forecastProgress, setForecastProgress] = useState<ForecastProgress>({
    loaded: 0,
    total: 0,
  });
  const [forecastsLoading, setForecastsLoading] = useState(false);
  const [forecastsSavedAt, setForecastsSavedAt] = useState<number | null>(
    () => initialCache?.forecastsSavedAt ?? null,
  );
  const [dataVersion, setDataVersion] = useState(() => Date.now());
  const forecastRunId = useRef(0);
  const marketsRefreshInFlight = useRef(false);
  const forecastsRefreshInFlight = useRef(false);
  const eventsRef = useRef(events);
  const forecastsRef = useRef(forecasts);
  const ensembleForecastsRef = useRef(ensembleForecasts);
  const forecastsSavedAtRef = useRef(forecastsSavedAt);

  eventsRef.current = events;
  forecastsRef.current = forecasts;
  ensembleForecastsRef.current = ensembleForecasts;
  forecastsSavedAtRef.current = forecastsSavedAt;

  const persistCache = useCallback(
    (
      nextEvents: WeatherEvent[],
      nextTotalCount: number,
      nextForecasts: ForecastMap,
      nextEnsemble: EnsembleForecastMap,
      nextForecastsSavedAt: number | null,
    ) => {
      writeDashboardCache({
        events: nextEvents,
        totalCount: nextTotalCount,
        forecasts: nextForecasts,
        ensembleForecasts: nextEnsemble,
        marketsSavedAt: Date.now(),
        forecastsSavedAt: nextForecastsSavedAt ?? 0,
      });
    },
    [],
  );

  useEffect(() => {
    if (!dataLoaded) {
      return;
    }
    persistCache(events, totalCount, forecasts, ensembleForecasts, forecastsSavedAt);
  }, [dataLoaded, events, totalCount, forecasts, ensembleForecasts, forecastsSavedAt, persistCache]);

  useEffect(() => {
    void fetchDiscoveryStatus()
      .then(setStatus)
      .catch(() => {
        /* status is optional */
      });
  }, []);

  useEffect(() => {
    return () => {
      forecastRunId.current += 1;
    };
  }, []);

  const loadForecasts = useCallback(
    async (
      list: WeatherEvent[],
      runId: number,
      options?: { preserveExisting?: boolean },
    ) => {
      const preserveExisting = options?.preserveExisting ?? false;
      forecastsRefreshInFlight.current = true;
      setForecastsLoading(true);

      if (!preserveExisting) {
        setForecasts({});
        setEnsembleForecasts({});
        setPendingForecastKeys(new Set());
        setForecastProgress({ loaded: 0, total: 0 });
      }

      try {
        const result = await loadDashboardForecastsProgressive(
          list,
          ({ single, ensemble, loaded, total, pendingKeys }) => {
            if (forecastRunId.current !== runId) {
              return;
            }
            setForecasts(single);
            setEnsembleForecasts(ensemble);
            setForecastProgress({ loaded, total });
            setPendingForecastKeys(pendingKeys);
          },
          {
            shouldCancel: () => forecastRunId.current !== runId,
            initialSingle: preserveExisting ? forecastsRef.current : undefined,
            initialEnsemble: preserveExisting ? ensembleForecastsRef.current : undefined,
          },
        );

        if (forecastRunId.current === runId) {
          const savedAt = Date.now();
          setForecastsSavedAt(savedAt);
          persistCache(
            eventsRef.current,
            eventsRef.current.length,
            result.single,
            result.ensemble,
            savedAt,
          );
        }
      } catch (forecastErr) {
        if (forecastRunId.current === runId) {
          console.warn("Forecast load failed:", forecastErr);
        }
      } finally {
        if (forecastRunId.current === runId) {
          setForecastsLoading(false);
          setPendingForecastKeys(new Set());
          forecastsRefreshInFlight.current = false;
        }
      }
    },
    [persistCache],
  );

  const loadMarketsFromDisk = useCallback(
    async (cacheBust?: number, options?: { showLoading?: boolean }) => {
      const showLoading = options?.showLoading ?? false;
      if (showLoading) {
        setLoading(true);
      }
      setError(null);
      const bust = cacheBust ?? dataVersion;
      try {
        const [marketsRes, statusRes] = await Promise.all([
          fetchAllMarkets({}, { cacheBust: bust }),
          fetchDiscoveryStatus({ cacheBust: bust }),
        ]);
        const list = marketsRes.events ?? marketsRes.markets ?? [];
        setEvents(list);
        setTotalCount(marketsRes.count ?? list.length);
        setStatus(statusRes);
        setDataLoaded(true);
        return list;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load data");
        return eventsRef.current;
      } finally {
        if (showLoading) {
          setLoading(false);
        }
      }
    },
    [dataVersion],
  );

  const refreshMarkets = useCallback(
    async (options?: { withDiscovery?: boolean; silent?: boolean }) => {
      if (marketsRefreshInFlight.current) {
        return eventsRef.current;
      }
      marketsRefreshInFlight.current = true;
      const withDiscovery = options?.withDiscovery ?? true;
      const silent = options?.silent ?? false;

      if (!silent) {
        setRefreshing(true);
      }
      setError(null);

      try {
        if (withDiscovery) {
          await refreshDiscovery();
        }
        const bust = Date.now();
        setDataVersion(bust);
        return await loadMarketsFromDisk(bust, { showLoading: !silent && !dataLoaded });
      } catch (err) {
        setError(err instanceof Error ? err.message : "Market refresh failed");
        return eventsRef.current;
      } finally {
        marketsRefreshInFlight.current = false;
        if (!silent) {
          setRefreshing(false);
        }
      }
    },
    [dataLoaded, loadMarketsFromDisk],
  );

  const refreshForecasts = useCallback(
    async (options?: { silent?: boolean; force?: boolean }) => {
      const silent = options?.silent ?? false;
      const force = options?.force ?? false;
      const list = eventsRef.current;
      if (!list.length) {
        return;
      }
      if (!force && !forecastsAreStale(forecastsSavedAtRef.current)) {
        return;
      }
      if (forecastsRefreshInFlight.current) {
        return;
      }
      const runId = ++forecastRunId.current;
      await loadForecasts(list, runId, { preserveExisting: silent });
    },
    [loadForecasts],
  );

  const bootstrappedRef = useRef(false);

  useEffect(() => {
    if (bootstrappedRef.current) {
      return;
    }
    bootstrappedRef.current = true;

    void (async () => {
      const hadCache = Boolean(initialCache?.events?.length);
      let list = await loadMarketsFromDisk(undefined, { showLoading: !hadCache });
      if (!list.length) {
        list = await refreshMarkets({ withDiscovery: true, silent: true });
      }
      if (list.length && forecastsAreStale(forecastsSavedAtRef.current)) {
        await refreshForecasts({ silent: Boolean(forecastsSavedAtRef.current) });
      }
    })();
  }, [initialCache, loadMarketsFromDisk, refreshForecasts, refreshMarkets]);

  useEffect(() => {
    if (!dataLoaded) {
      return;
    }

    const marketsTimer = window.setInterval(() => {
      void refreshMarkets({ withDiscovery: true, silent: true });
    }, MARKETS_AUTO_REFRESH_MS);

    const forecastsTimer = window.setInterval(() => {
      void refreshForecasts({ silent: true, force: true });
    }, FORECASTS_AUTO_REFRESH_MS);

    return () => {
      window.clearInterval(marketsTimer);
      window.clearInterval(forecastsTimer);
    };
  }, [dataLoaded, refreshForecasts, refreshMarkets]);

  const handleReloadData = async () => {
    setReloading(true);
    setError(null);
    try {
      const bust = Date.now();
      setDataVersion(bust);
      await loadMarketsFromDisk(bust, { showLoading: false });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reload data");
    } finally {
      setReloading(false);
    }
  };

  const handleRefreshDiscovery = async () => {
    const list = await refreshMarkets({ withDiscovery: true, silent: false });
    if (list.length) {
      const runId = ++forecastRunId.current;
      await loadForecasts(list, runId, { preserveExisting: false });
    }
  };

  const handleRefreshForecasts = async () => {
    await refreshForecasts({ silent: false, force: true });
  };

  const displayedEvents = useMemo(
    () => filterEvents(events, search, activeOnly),
    [events, search, activeOnly],
  );

  const stats = useMemo(() => {
    const active = events.filter((event) => event.active && !event.closed).length;
    const withBuckets = events.filter((event) => (event.all_outcomes?.length ?? 0) > 0).length;
    return { total: events.length, active, withBuckets };
  }, [events]);

  const weatherCount =
    status?.total_weather_events ?? status?.total_weather_markets ?? 0;

  return (
    <div className="dashboard">
      <section className="dashboard__cards">
        <StatusCard
          label="Weather events (table)"
          value={
            dataLoaded
              ? totalCount > events.length
                ? `${displayedEvents.length} / ${totalCount}`
                : displayedEvents.length
              : "—"
          }
          hint={
            dataLoaded && totalCount > events.length
              ? "Increase API limit or add pagination to load the rest"
              : undefined
          }
        />
        <StatusCard label="Active events" value={dataLoaded ? stats.active : "—"} />
        <StatusCard label="With buckets" value={dataLoaded ? stats.withBuckets : "—"} />
        <StatusCard
          label="Discovery"
          value={status?.discovery_mode ?? status?.status ?? "—"}
          hint={`${weatherCount} events · scan ${status?.full_scan_events ?? 0} · tag ${status?.weather_tag_events ?? 0}`}
        />
      </section>

      <FiltersBar
        search={search}
        onSearchChange={setSearch}
        activeOnly={activeOnly}
        onActiveOnlyChange={setActiveOnly}
        onRefreshDiscovery={() => void handleRefreshDiscovery()}
        onReloadData={dataLoaded ? () => void handleReloadData() : undefined}
        onRefreshForecasts={dataLoaded ? () => void handleRefreshForecasts() : undefined}
        reloading={reloading}
        refreshing={refreshing}
        forecastsLoading={forecastsLoading}
        lastRefresh={status?.last_refresh_at}
        lastForecastsAt={formatTimestamp(forecastsSavedAt)}
        autoRefreshHint="Рынки: каждые 15 мин · температуры: каждые 6 ч"
      />

      {error ? <div className="error-banner">{error}</div> : null}
      {loading && !dataLoaded ? (
        <p className="loading">Загрузка событий…</p>
      ) : (
        <>
          {forecastProgress.total > 0 ? (
            <p className="history-meta">
              Прогнозы: {forecastProgress.loaded} / {forecastProgress.total} событий
              {forecastsLoading ? " · обновление…" : ""}
            </p>
          ) : null}
          <MarketTable
            events={displayedEvents}
            forecasts={forecasts}
            ensembleForecasts={ensembleForecasts}
            pendingForecastKeys={pendingForecastKeys}
          />
        </>
      )}
    </div>
  );
}
