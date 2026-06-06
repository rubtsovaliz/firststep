#!/usr/bin/env python3
"""Validate API cache headers and snake_case price fields in list response."""

from __future__ import annotations

import json
import sys
from urllib.error import URLError
from urllib.request import Request, urlopen

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def check(path: str) -> None:
    url = f"{BASE}{path}"
    req = Request(url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=30) as resp:
        cc = resp.headers.get("Cache-Control", "")
        body = json.loads(resp.read().decode())
        print(f"OK {path}")
        print(f"  Cache-Control: {cc}")
        if "no-store" not in cc:
            raise SystemExit(f"FAIL: expected no-store in Cache-Control for {path}")
        if path.startswith("/api/markets"):
            events = body.get("events") or body.get("markets") or []
            if events:
                e = events[0]
                if "all_outcomes" not in e:
                    raise SystemExit("FAIL: missing all_outcomes in event")
                if e["all_outcomes"] and "yes_price" not in e["all_outcomes"][0]:
                    raise SystemExit("FAIL: bucket missing yes_price (snake_case)")
                if "price" in e["all_outcomes"][0]:
                    raise SystemExit("FAIL: legacy 'price' field present on bucket")


def main() -> None:
    try:
        check("/api/markets?limit=1")
        check("/api/discovery/status")
        check(f"/api/markets?limit=1&_={__import__('time').time()}")
        print("\nAll fresh-price validation checks passed.")
    except URLError as exc:
        raise SystemExit(f"Cannot reach {BASE}: {exc}") from exc


if __name__ == "__main__":
    main()
