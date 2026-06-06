import type {
  DiscoveryRefreshResponse,
  DiscoveryStatus,
  MarketsListResponse,
  WeatherEvent,
} from "../types/market";
import { normalizeWeatherEvent } from "../utils/eventPricing";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

export type FetchOptions = {
  /** Bust browser/proxy cache after discovery rescan (unix ms). */
  cacheBust?: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: {
      "Cache-Control": "no-cache",
      Pragma: "no-cache",
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

function withCacheBust(path: string, cacheBust?: number): string {
  if (!cacheBust) {
    return path;
  }
  const sep = path.includes("?") ? "&" : "?";
  return `${path}${sep}_=${cacheBust}`;
}

/** Backend max page size; frontend must pass limit (old API default was 100). */
export const MARKETS_PAGE_LIMIT = 5000;

export async function fetchMarkets(
  params?: {
    search?: string;
    active_only?: boolean;
    limit?: number;
    offset?: number;
  },
  options?: FetchOptions,
): Promise<MarketsListResponse> {
  const query = new URLSearchParams();
  if (params?.search) query.set("search", params.search);
  if (params?.active_only) query.set("active_only", "true");
  query.set("limit", String(params?.limit ?? MARKETS_PAGE_LIMIT));
  if (params?.offset != null && params.offset > 0) {
    query.set("offset", String(params.offset));
  }
  const path = withCacheBust(`/api/markets?${query.toString()}`, options?.cacheBust);
  const data = await request<MarketsListResponse>(path);
  return mapMarketsResponse(data);
}

/** Load every page from backend until count is exhausted. */
export async function fetchAllMarkets(
  params?: {
    search?: string;
    active_only?: boolean;
  },
  options?: FetchOptions,
): Promise<MarketsListResponse> {
  const pageSize = MARKETS_PAGE_LIMIT;
  let offset = 0;
  let total = 0;
  const all: MarketsListResponse["events"] = [];

  while (true) {
    const page = await fetchMarkets(
      {
        ...params,
        limit: pageSize,
        offset,
      },
      options,
    );
    const batch = page.events ?? page.markets ?? [];
    total = page.count;
    all.push(...batch);
    if (batch.length === 0 || all.length >= total) {
      break;
    }
    offset += pageSize;
  }

  const events = all.map((e) => normalizeWeatherEvent(e));
  return { count: total, events, markets: events };
}

function mapMarketsResponse(data: MarketsListResponse): MarketsListResponse {
  const raw = data.events ?? data.markets ?? [];
  const events = raw.map((e) => normalizeWeatherEvent(e as WeatherEvent));
  return { count: data.count, events, markets: events };
}

export async function fetchDiscoveryStatus(
  options?: FetchOptions,
): Promise<DiscoveryStatus> {
  return request<DiscoveryStatus>(
    withCacheBust("/api/discovery/status", options?.cacheBust),
  );
}

export async function refreshDiscovery(): Promise<DiscoveryRefreshResponse> {
  return request<DiscoveryRefreshResponse>("/api/discovery/refresh", {
    method: "POST",
    cache: "no-store",
  });
}
