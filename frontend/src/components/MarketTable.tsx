import type { WeatherEvent } from "../types/market";
import { EventPricesCell } from "./EventPricesCell";

interface MarketTableProps {
  events: WeatherEvent[];
}

export function MarketTable({ events }: MarketTableProps) {
  if (events.length === 0) {
    return <p className="empty-state">No events found. Run discovery refresh.</p>;
  }

  return (
    <div className="table-wrap">
      <table className="market-table">
        <thead>
          <tr>
            <th>Event</th>
            <th className="col-storage-key">Storage key</th>
            <th>City</th>
            <th>Metric</th>
            <th>Date</th>
            <th>Active</th>
            <th>Closed</th>
            <th>Buckets</th>
            <th>Prices</th>
            <th>Type</th>
            <th>Metric</th>
            <th>Unit</th>
            <th>Volume</th>
            <th className="col-tags">Tags</th>
          </tr>
        </thead>
        <tbody>
          {events.map((e) => (
            <tr key={e.storage_key}>
              <td className="cell-title" title={e.event_title}>
                {e.event_title}
              </td>
              <td className="cell-slug col-storage-key" title={e.storage_key}>
                {e.storage_key}
              </td>
              <td>{e.city_slug}</td>
              <td>{e.date}</td>
              <td>{e.active ? "yes" : "no"}</td>
              <td>{e.closed ? "yes" : "no"}</td>
              <td>{e.all_outcomes?.length ?? 0}</td>
              <td className="cell-prices">
                <EventPricesCell event={e} />
              </td>
              <td>{e.market_type ?? "—"}</td>
              <td>{e.temperature_metric ?? "—"}</td>
              <td>{e.unit ?? "—"}</td>
              <td>{e.volume ?? "—"}</td>
              <td className="cell-tags col-tags">{e.tags?.join(", ") || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
