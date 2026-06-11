interface FiltersBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  activeOnly: boolean;
  onActiveOnlyChange: (value: boolean) => void;
  onRefreshDiscovery: () => void;
  onReloadData?: () => void;
  onRefreshForecasts?: () => void;
  reloading?: boolean;
  refreshing: boolean;
  forecastsLoading?: boolean;
  lastRefresh?: string | null;
  lastForecastsAt?: string | null;
  autoRefreshHint?: string;
}

export function FiltersBar({
  search,
  onSearchChange,
  activeOnly,
  onActiveOnlyChange,
  onRefreshDiscovery,
  onReloadData,
  onRefreshForecasts,
  reloading = false,
  refreshing,
  forecastsLoading = false,
  lastRefresh,
  lastForecastsAt,
  autoRefreshHint,
}: FiltersBarProps) {
  return (
    <div className="filters-bar">
      <input
        type="search"
        placeholder="Search title, slug, event, city..."
        value={search}
        onChange={(e) => onSearchChange(e.target.value)}
        className="filters-bar__search"
      />
      <label className="filters-bar__checkbox">
        <input
          type="checkbox"
          checked={activeOnly}
          onChange={(e) => onActiveOnlyChange(e.target.checked)}
        />
        Active only
      </label>
      <button
        type="button"
        onClick={onRefreshDiscovery}
        disabled={refreshing || reloading}
        className="filters-bar__button"
      >
        {refreshing ? "Refreshing..." : "Refresh discovery"}
      </button>
      {onReloadData ? (
        <button
          type="button"
          onClick={onReloadData}
          disabled={refreshing || reloading}
          className="filters-bar__button filters-bar__button--secondary"
        >
          {reloading ? "Loading..." : "Reload prices"}
        </button>
      ) : null}
      {onRefreshForecasts ? (
        <button
          type="button"
          onClick={onRefreshForecasts}
          disabled={refreshing || reloading || forecastsLoading}
          className="filters-bar__button filters-bar__button--secondary"
        >
          {forecastsLoading ? "Loading..." : "Refresh temps"}
        </button>
      ) : null}
      <span className="filters-bar__meta">
        Discovery: {lastRefresh ?? "never"}
        {lastForecastsAt ? ` · Temps: ${lastForecastsAt}` : ""}
        {autoRefreshHint ? ` · ${autoRefreshHint}` : ""}
      </span>
    </div>
  );
}
