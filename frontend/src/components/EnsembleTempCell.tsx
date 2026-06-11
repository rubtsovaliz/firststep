import { lookupForecast, type EnsembleForecastMap } from "../api/forecasts";
import type { WeatherEvent } from "../types/market";

interface EnsembleTempCellProps {
  event: WeatherEvent;
  forecasts: EnsembleForecastMap;
  loading?: boolean;
}

export function EnsembleTempCell({
  event,
  forecasts,
  loading = false,
}: EnsembleTempCellProps) {
  const row = lookupForecast(forecasts, event);
  if (loading && !row) {
    return <span className="cell-muted">…</span>;
  }
  if (!row) {
    return <span className="cell-muted">—</span>;
  }

  const unit = row.unit ?? event.unit ?? "C";
  const models = row.models_temps ?? [];

  if (models.length > 0) {
    const visible = models.filter((entry) => entry.temp != null);
    if (visible.length === 0) {
      const title = models
        .map((entry) => `${entry.model}: ${entry.error ?? "нет данных"}`)
        .join("\n");
      return (
        <span className="cell-muted" title={title}>
          —
        </span>
      );
    }

    return (
      <span
        title={visible.map((entry) => `${entry.model}: ${entry.temp}°${unit}`).join("\n")}
      >
        {visible.map((entry) => (
          <span key={entry.model}>
            {entry.temp}°{unit}{" "}
            <span className="cell-muted">({entry.model})</span>{" "}
          </span>
        ))}
      </span>
    );
  }

  if (row.error) {
    return (
      <span className="cell-muted" title={row.error}>
        —
      </span>
    );
  }

  if (row.temp == null) {
    return <span className="cell-muted">—</span>;
  }

  const model = row.model ?? "—";
  return (
    <span title={`Ансамбль: ${model}`}>
      {row.temp}°{unit}{" "}
      <span className="cell-muted">({model})</span>
    </span>
  );
}
