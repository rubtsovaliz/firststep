import type { WeatherEvent } from "../types/market";
import {
  formatBucketLabel,
  formatPricePercent,
  getLatestMarketSnapshot,
  getTopSummaryFromSnapshot,
} from "../utils/eventPricing";

interface EventPricesCellProps {
  event: WeatherEvent;
}

export function EventPricesCell({ event }: EventPricesCellProps) {
  const outcomes = event.all_outcomes ?? [];
  const { top_bucket, top_price, snapshot_ts } = getTopSummaryFromSnapshot(event);
  const latest = getLatestMarketSnapshot(event);

  const hasTop = top_bucket != null || top_price != null;
  const hasBuckets = outcomes.length > 0;

  if (!hasTop && !hasBuckets) {
    return <span className="prices-cell prices-cell--empty">—</span>;
  }

  return (
    <div className="prices-cell">
      {hasTop ? (
        <div className="prices-cell__top">
          <span>
            Top bucket: <strong>{top_bucket ?? "—"}</strong>
          </span>
          <span>
            Top price: <strong>{formatPricePercent(top_price)}</strong>
          </span>
          {snapshot_ts ? (
            <span className="prices-cell__meta" title="From latest market_snapshots">
              snap {new Date(snapshot_ts).toLocaleString()}
            </span>
          ) : null}
        </div>
      ) : latest == null && hasBuckets ? (
        <div className="prices-cell__top prices-cell__top--muted">
          Top: run discovery to build market_snapshots
        </div>
      ) : null}

      {hasBuckets ? (
        <ul className="prices-cell__buckets" title="Current prices from all_outcomes">
          {outcomes.map((o) => (
            <li
              key={String(o.market_id ?? o.question)}
              className="prices-cell__bucket-line"
            >
              {formatBucketLabel(o)} | YES {formatPricePercent(o.yes_price)} | NO{" "}
              {formatPricePercent(o.no_price)}
              {o.volume != null ? (
                <span className="prices-cell__vol"> · vol {Math.round(o.volume)}</span>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
