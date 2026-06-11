import type { EnsembleForecastMap, ForecastMap } from "../api/forecasts";
import type { HistoryCity, HistoryEvent } from "../api/history";
import { needsHistoryOpenMeteoFetch } from "../api/history";
import { HistoryTable } from "./HistoryTable";

interface HistoryCityAccordionProps {
  cities: HistoryCity[];
  cityEvents: Record<string, HistoryEvent[]>;
  expandedCities: Set<string>;
  loadingCities: Set<string>;
  loadingCityFiles: Set<string>;
  loadingCityOpenMeteo: Set<string>;
  forecasts: ForecastMap;
  ensembleForecasts: EnsembleForecastMap;
  pendingKeys: Set<string>;
  onToggleCity: (citySlug: string, open: boolean) => void;
  onLoadCityFromFiles: (citySlug: string) => void;
  onLoadCityFromOpenMeteo: (citySlug: string) => void;
}

function formatCityLabel(slug: string): string {
  return slug
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function HistoryCityAccordion({
  cities,
  cityEvents,
  expandedCities,
  loadingCities,
  loadingCityFiles,
  loadingCityOpenMeteo,
  forecasts,
  ensembleForecasts,
  pendingKeys,
  onToggleCity,
  onLoadCityFromFiles,
  onLoadCityFromOpenMeteo,
}: HistoryCityAccordionProps) {
  if (cities.length === 0) {
    return <p className="empty-state">Нет записей в истории.</p>;
  }

  return (
    <div className="history-accordion">
      {cities.map((city) => {
        const isOpen = expandedCities.has(city.city_slug);
        const events = cityEvents[city.city_slug] ?? [];
        const isLoading = loadingCities.has(city.city_slug);
        const isLoadingFiles = loadingCityFiles.has(city.city_slug);
        const isLoadingOpenMeteo = loadingCityOpenMeteo.has(city.city_slug);
        const missingCount = events.filter(needsHistoryOpenMeteoFetch).length;
        const cityBusy = isLoadingFiles || isLoadingOpenMeteo;

        return (
          <details
            key={city.city_slug}
            className="history-details"
            open={isOpen}
            onToggle={(e) => {
              onToggleCity(city.city_slug, e.currentTarget.open);
            }}
          >
            <summary className="history-details__summary">
              <span className="history-details__title">
                {formatCityLabel(city.city_slug)}
              </span>
              <span className="history-details__stats">
                <span>{city.event_count} дат</span>
                {city.forecasts_cached_count > 0 ? (
                  <span className="history-details__cached">
                    {city.forecasts_cached_count} в файлах
                  </span>
                ) : null}
                {isLoading ? <span className="history-details__loading">загрузка…</span> : null}
              </span>
            </summary>
            <div className="detail-body">
              <div className="history-details__toolbar">
                <button
                  type="button"
                  className="filters-bar__button filters-bar__button--secondary history-details__btn"
                  disabled={cityBusy || (isLoading && events.length === 0)}
                  onClick={(e) => {
                    e.preventDefault();
                    onLoadCityFromFiles(city.city_slug);
                  }}
                >
                  {isLoadingFiles ? "Читаю…" : "Из файлов"}
                </button>
                <button
                  type="button"
                  className="filters-bar__button history-details__btn"
                  disabled={cityBusy || missingCount === 0 || events.length === 0}
                  onClick={(e) => {
                    e.preventDefault();
                    onLoadCityFromOpenMeteo(city.city_slug);
                  }}
                  title={
                    events.length === 0
                      ? "Дождитесь загрузки дат"
                      : missingCount === 0
                        ? "Все прогнозы уже сохранены в файлах"
                        : `Запросить Open-Meteo для ${missingCount} дат`
                  }
                >
                  {isLoadingOpenMeteo ? "Open-Meteo…" : "Open-Meteo"}
                </button>
                {events.length > 0 ? (
                  <span className="history-details__toolbar-meta">
                    без прогноза: {missingCount}
                  </span>
                ) : null}
              </div>
              {isLoading && events.length === 0 ? (
                <p className="loading history-details__body-loading">Загрузка дат…</p>
              ) : (
                <HistoryTable
                  events={events}
                  forecasts={forecasts}
                  ensembleForecasts={ensembleForecasts}
                  pendingKeys={pendingKeys}
                />
              )}
            </div>
          </details>
        );
      })}
    </div>
  );
}
