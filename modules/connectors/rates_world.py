"""World rates — Yahoo US curve + ECB SDMX + BCB Selic snapshot."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from modules.connectors.market_http import _filter_from, _monthly_levels, _trailing_and_cagr, _yahoo_chart

TIMEOUT = 40
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json,text/plain,*/*",
}

YAHOO_YIELDS = {
    "us_3m": {"symbol": "^IRX", "label": "US 3M T-Bill", "unit": "% a.a. (nível)"},
    "us_5y": {"symbol": "^FVX", "label": "US 5Y yield", "unit": "% a.a. (nível)"},
    "us_10y": {"symbol": "^TNX", "label": "US 10Y yield", "unit": "% a.a. (nível)"},
}

# Euro area long-term government bond yield (monthly) — ECB Data Portal
ECB_EU_10Y = (
    "https://data-api.ecb.europa.eu/service/data/IRS/M.I9.L.L40.CI.0000.EUR.N.Z"
    "?lastNObservations=120&format=jsondata"
)


def _ecb_series(url: str) -> list[dict[str, Any]]:
    res = requests.get(url, timeout=TIMEOUT, headers=UA)
    res.raise_for_status()
    payload = res.json()
    series_map = ((payload.get("dataSets") or [{}])[0].get("series") or {})
    if not series_map:
        return []
    ser = next(iter(series_map.values()))
    obs = ser.get("observations") or {}
    time_values = (
        ((payload.get("structure") or {}).get("dimensions") or {}).get("observation") or [{}]
    )[0].get("values") or []
    out = []
    for idx, meta in enumerate(time_values):
        key = str(idx)
        if key not in obs:
            continue
        val = (obs[key] or [None])[0]
        if val is None:
            continue
        period = meta.get("id") or meta.get("name")
        out.append({"month": period, "value": float(val)})
    return out


def fetch_world_rates(start_date: str = "2015-01-01", selic_pct: float | None = None) -> dict[str, Any]:
    items: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    errors: list[str] = []

    if selic_pct is not None:
        items["br_selic"] = {
            "id": "br_selic",
            "label": "Selic (Brasil)",
            "source_layer": "official",
            "latest": selic_pct,
            "unit": "% a.a.",
            "as_of": datetime.now(timezone.utc).date().isoformat(),
            "trust": "canonical",
        }

    for key, meta in YAHOO_YIELDS.items():
        try:
            rows, _ = _yahoo_chart(meta["symbol"], start_date=start_date)
            rows = _filter_from(rows, start_date) or rows
            t12, _cagr, last_px, last_date = _trailing_and_cagr(rows)
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": meta["symbol"],
                "source_layer": "market",
                "latest": round(float(last_px), 3),
                "trailing_12m_change_pct": round(float(t12), 2) if t12 is not None else None,
                "unit": meta["unit"],
                "as_of": last_date,
                "start_used": rows[0]["date"],
            }
            monthly[key] = _monthly_levels(rows)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{meta['symbol']}: {exc}")

    try:
        eu = [m for m in _ecb_series(ECB_EU_10Y) if m["month"] >= start_date[:7]]
        if eu:
            items["eu_10y"] = {
                "id": "eu_10y",
                "label": "Euro area 10Y (ECB IRS)",
                "source_layer": "official",
                "latest": round(float(eu[-1]["value"]), 3),
                "unit": "% a.a.",
                "as_of": eu[-1]["month"],
                "trust": "canonical",
                "source": "ECB Data Portal IRS",
            }
            monthly["eu_10y"] = eu
    except Exception as exc:  # noqa: BLE001
        errors.append(f"ecb_eu_10y: {exc}")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "start_date": start_date,
        "source": "Yahoo yields + ECB Data Portal + BCB Selic",
        "items": items,
        "monthly_levels": monthly,
        "errors": errors,
        "ok_count": len(items),
    }
