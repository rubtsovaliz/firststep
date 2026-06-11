import type { EnsembleForecastMap, ForecastMap } from "../api/forecasts";
import type { HistoryEvent } from "../api/history";
import { historyEventToWeatherEvent } from "../api/history";
import { EnsembleTempCell } from "./EnsembleTempCell";
import { SingleModelTempCell } from "./SingleModelTempCell";

interface HistoryTableProps {
  events: HistoryEvent[];
  forecasts: ForecastMap;
  ensembleForecasts: EnsembleForecastMap;
  pendingKeys: Set<string>;
}

export function HistoryTable({
  events,
  forecasts,
  ensembleForecasts,
  pendingKeys,
}: HistoryTableProps) {
  if (events.length === 0) {
    return <p className="empty-state history-table-empty">Нет дат для этого города.</p>;
  }

  return (
    <table className="market-table history-table">
      <thead>
        <tr>
          <th>Date</th>
          <th>Metric</th>
          <th>Win</th>
          <th>Single model</th>
          <th>Ensemble</th>
        </tr>
      </thead>
      <tbody>
        {events.map((row) => {
          const weatherEvent = historyEventToWeatherEvent(row);
          const loading = pendingKeys.has(row.storage_key);
          return (
            <tr key={row.storage_key}>
              <td>{row.date}</td>
              <td>{row.metric}</td>
              <td>
                {row.win ? <span className="cell-win__pill">{row.win}</span> : null}
              </td>
              <td>
                <SingleModelTempCell
                  event={weatherEvent}
                  forecasts={forecasts}
                  loading={loading}
                />
              </td>
              <td>
                <EnsembleTempCell
                  event={weatherEvent}
                  forecasts={ensembleForecasts}
                  loading={loading}
                />
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
