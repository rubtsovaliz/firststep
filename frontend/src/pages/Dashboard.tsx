import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchAllMarkets,
  fetchDiscoveryStatus,
  refreshDiscovery,
} from "../api/markets";
import { FiltersBar } from "../components/FiltersBar";
import { MarketTable } from "../components/MarketTable";
import { StatusCard } from "../components/StatusCard";
import type { DiscoveryStatus, WeatherEvent } from "../types/market";

export function Dashboard() {
  const [events, setEvents] = useState<WeatherEvent[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [status, setStatus] = useState<DiscoveryStatus | null>(null);
  const [search, setSearch] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [reloading, setReloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dataVersion, setDataVersion] = useState(() => Date.now());

  const load = useCallback(
    async (cacheBust?: number) => {
    setLoading(true);
    setError(null);
    const bust = cacheBust ?? dataVersion;
    try {
      const [marketsRes, statusRes] = await Promise.all([
        fetchAllMarkets(
          { search: search || undefined, active_only: activeOnly },
          { cacheBust: bust },
        ),
        fetchDiscoveryStatus({ cacheBust: bust }),
      ]);
      const list = marketsRes.events ?? marketsRes.markets ?? [];
      setEvents(list);
      setTotalCount(marketsRes.count ?? list.length);
      setStatus(statusRes);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoading(false);
    }
  },
    [search, activeOnly, dataVersion],
  );

  useEffect(() => {
    void load();
  }, [load]);

  const handleReloadData = async () => {
    setReloading(true);
    setError(null);
    try {
      const bust = Date.now();
      setDataVersion(bust);
      await load(bust);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reload data");
    } finally {
      setReloading(false);
    }
  };

  const handleRefreshDiscovery = async () => {
    setRefreshing(true);
    setError(null);
    try {
      await refreshDiscovery();
      const bust = Date.now();
      setDataVersion(bust);
      await load(bust);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Discovery refresh failed");
    } finally {
      setRefreshing(false);
    }
  };

  const stats = useMemo(() => {
    const active = events.filter((e) => e.active && !e.closed).length;
    const withBuckets = events.filter((e) => (e.all_outcomes?.length ?? 0) > 0).length;
    return { total: events.length, active, withBuckets };
  }, [events]);

  const weatherCount =
    status?.total_weather_events ?? status?.total_weather_markets ?? 0;

  return (
    <div className="dashboard">
      <header className="dashboard__header">
        <h1>Weather Polymarket Bot</h1>
        <p>Read-only discovery — one JSON file per city/date event</p>
      </header>

      <section className="dashboard__cards">
        <StatusCard
          label="Weather events (table)"
          value={
            totalCount > events.length
              ? `${events.length} / ${totalCount}`
              : stats.total
          }
          hint={
            totalCount > events.length
              ? "Increase API limit or add pagination to load the rest"
              : undefined
          }
        />
        <StatusCard label="Active events" value={stats.active} />
        <StatusCard label="With buckets" value={stats.withBuckets} />
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
        onReloadData={() => void handleReloadData()}
        reloading={reloading}
        refreshing={refreshing}
        lastRefresh={status?.last_refresh_at}
      />

      {error ? <div className="error-banner">{error}</div> : null}
      {loading ? <p className="loading">Loading...</p> : <MarketTable events={events} />}
    </div>
  );
}
