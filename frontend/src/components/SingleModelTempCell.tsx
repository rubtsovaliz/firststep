import { lookupForecast } from "../api/forecasts";
import type { ForecastMap } from "../api/forecasts";
import type { WeatherEvent } from "../types/market";

interface SingleModelTempCellProps {
  event: WeatherEvent;
  forecasts: ForecastMap;
  loading?: boolean;
}

export function SingleModelTempCell({
  event,
  forecasts,
  loading = false,
}: SingleModelTempCellProps) {
  const row = lookupForecast(forecasts, event);
  if (loading && !row) {
    return <span className="cell-muted">…</span>;
  }
  if (!row) {
    return <span className="cell-muted">—</span>;
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

  const unit = row.unit ?? event.unit ?? "C";
  const model = row.model ?? "—";
  const title = row.model_fallback
    ? `Запрошена ${row.requested_model ?? "—"}, используется fallback: ${model}`
    : `Модель: ${model}`;
  return (
    <span title={title}>
      {row.temp}°{unit}{" "}
      <span className="cell-muted">
        ({model}
        {row.model_fallback ? "*" : ""})
      </span>
    </span>
  );
}
