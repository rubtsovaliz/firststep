import type { MarketSnapshot, WeatherEvent, WeatherOutcome } from "../types/market";

/**
 * Pricing rules (snake_case fields only):
 * - Bucket YES/NO: always from event.all_outcomes (current scan).
 * - Top bucket/price: from latest market_snapshots entry by ts (not stale aggregate).
 */

/** Normalize API payload — snake_case only, no camelCase remapping. */
export function normalizeWeatherEvent(raw: WeatherEvent): WeatherEvent {
  return {
    ...raw,
    all_outcomes: [...(raw.all_outcomes ?? [])],
    market_snapshots: [...(raw.market_snapshots ?? [])],
    tags: raw.tags ?? [],
  };
}

export function formatPricePercent(price: number | null | undefined): string {
  if (price == null || Number.isNaN(price)) {
    return "—";
  }
  const pct = price * 100;
  const digits = pct >= 10 || pct === 0 ? 1 : 2;
  return `${pct.toFixed(digits)}%`;
}

export function formatBucketLabel(outcome: WeatherOutcome): string {
  const unit = outcome.unit ?? "C";
  const low = outcome.bucket_low;
  const high = outcome.bucket_high;

  if (low === -999) {
    return `≤${high}${unit}`;
  }
  if (high === 999) {
    return `≥${low}${unit}`;
  }
  if (low === high) {
    return `${low}${unit}`;
  }
  return `${low}-${high}${unit}`;
}

function snapshotTimeMs(snapshot: MarketSnapshot): number {
  const t = Date.parse(snapshot.ts);
  return Number.isNaN(t) ? 0 : t;
}

/** Latest snapshot by ts — safe if array order ever diverges from append-only. */
export function getLatestMarketSnapshot(
  event: WeatherEvent,
): MarketSnapshot | null {
  const snapshots = event.market_snapshots;
  if (!snapshots?.length) {
    return null;
  }
  if (snapshots.length === 1) {
    return snapshots[0];
  }
  return [...snapshots].sort(
    (a, b) => snapshotTimeMs(a) - snapshotTimeMs(b),
  )[snapshots.length - 1];
}

/** Top summary for event header — ONLY from latest market_snapshots. */
export function getTopSummaryFromSnapshot(event: WeatherEvent): {
  top_bucket: string | null;
  top_price: number | null;
  snapshot_ts: string | null;
} {
  const latest = getLatestMarketSnapshot(event);
  if (!latest) {
    return { top_bucket: null, top_price: null, snapshot_ts: null };
  }
  return {
    top_bucket: latest.top_bucket ?? null,
    top_price: latest.top_price ?? null,
    snapshot_ts: latest.ts ?? null,
  };
}

/** @deprecated Use getTopSummaryFromSnapshot; kept for tests without snapshots. */
export function computeTopFromOutcomes(event: WeatherEvent): {
  top_bucket: string | null;
  top_price: number | null;
} {
  const outcomes = event.all_outcomes ?? [];
  if (!outcomes.length) {
    return { top_bucket: null, top_price: null };
  }
  const top = outcomes.reduce((best, o) => {
    const p = o.yes_price ?? -1;
    const bestP = best.yes_price ?? -1;
    return p > bestP ? o : best;
  });
  return {
    top_bucket: formatBucketLabel(top),
    top_price: top.yes_price ?? null,
  };
}

/**
 * UI must use getTopSummaryFromSnapshot only.
 * Fallback below is for tests / diagnostics when market_snapshots is empty.
 */
export function getTopSummaryWithOutcomesFallback(event: WeatherEvent): {
  top_bucket: string | null;
  top_price: number | null;
  snapshot_ts: string | null;
} {
  const fromSnapshot = getTopSummaryFromSnapshot(event);
  if (fromSnapshot.top_bucket != null || fromSnapshot.top_price != null) {
    return fromSnapshot;
  }
  const fallback = computeTopFromOutcomes(event);
  return { ...fallback, snapshot_ts: null };
}

/** @alias getTopSummaryWithOutcomesFallback — do not use in production UI */
export const getTopSummary = getTopSummaryWithOutcomesFallback;
