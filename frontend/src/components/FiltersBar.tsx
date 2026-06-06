interface FiltersBarProps {
  search: string;
  onSearchChange: (value: string) => void;
  activeOnly: boolean;
  onActiveOnlyChange: (value: boolean) => void;
  onRefreshDiscovery: () => void;
  onReloadData?: () => void;
  reloading?: boolean;
  refreshing: boolean;
  lastRefresh?: string | null;
}

export function FiltersBar({
  search,
  onSearchChange,
  activeOnly,
  onActiveOnlyChange,
  onRefreshDiscovery,
  onReloadData,
  reloading = false,
  refreshing,
  lastRefresh,
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
      <span className="filters-bar__meta">
        Last refresh: {lastRefresh ?? "never"}
      </span>
    </div>
  );
}
