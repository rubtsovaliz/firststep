export interface WeatherOutcome {
  market_id?: string | number | null;
  question: string;
  bucket_low: number;
  bucket_high: number;
  unit?: string | null;
  yes_price?: number | null;
  no_price?: number | null;
  volume?: number | null;
  liquidity?: number | null;
  token_id?: string | null;
  outcomes?: string[];
  outcome_prices?: number[] | null;
  raw_source?: Record<string, unknown>;
}

export interface MarketSnapshot {
  ts: string;
  active?: boolean;
  closed?: boolean;
  end_date?: string | null;
  liquidity?: number | null;
  volume?: number | null;
  outcomes_count?: number;
  top_bucket?: string | null;
  top_price?: number | null;
  event_title?: string | null;
}

export interface WeatherEvent {
  storage_key: string;
  event_id?: string | number | null;
  event_slug?: string | null;
  event_title: string;
  city_slug: string;
  city_name?: string | null;
  date: string;
  unit?: string | null;
  active: boolean;
  closed: boolean;
  end_date?: string | null;
  event_end_date?: string | null;
  liquidity?: number | null;
  volume?: number | null;
  /** Temperature-only phase; null for rain/wind/precipitation events. */
  market_type?: "max_temperature" | "min_temperature" | null;
  temperature_metric?: "high" | "low" | null;
  tags: string[];
  all_outcomes: WeatherOutcome[];
  market_snapshots?: MarketSnapshot[];
}

export interface MarketsListResponse {
  count: number;
  events: WeatherEvent[];
  markets?: WeatherEvent[];
}

export interface DiscoveryStatus {
  last_refresh_at?: string | null;
  total_events_fetched: number;
  total_weather_events?: number;
  total_weather_markets?: number;
  full_scan_events?: number;
  weather_tag_events?: number;
  discovery_mode?: string;
  raw_snapshot_path: string;
  normalized_snapshot_path: string;
  per_event_snapshot_dir?: string;
  per_market_snapshot_dir: string;
  status: string;
}

export interface DiscoveryRefreshResponse {
  total_events_fetched: number;
  total_weather_events?: number;
  total_weather_markets?: number;
  discovery_mode?: string;
  generated_at: string;
}
