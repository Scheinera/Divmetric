"""Market data via Yahoo chart API (HTTP) + CoinGecko + AwesomeAPI."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

TIMEOUT = 45
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}

YAHOO_BENCH = {
    "ibov": {"symbol": "^BVSP", "label": "Ibovespa"},
    "btc": {"symbol": "BTC-USD", "label": "Bitcoin"},
    "gold": {"symbol": "GC=F", "label": "Ouro (futuro)"},
    "dxy": {"symbol": "DX-Y.NYB", "label": "DXY"},
    "usdbrl": {"symbol": "USDBRL=X", "label": "USD/BRL"},
}

B3_WATCH = [
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "WEGE3.SA",
    "ABEV3.SA",
    "B3SA3.SA",
    "BBAS3.SA",
    "RENT3.SA",
    "PRIO3.SA",
]


def _yahoo_chart(symbol: str, range_: str = "5y", interval: str = "1d") -> list[dict[str, Any]]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{requests.utils.quote(symbol, safe='')}"
    res = requests.get(url, params={"range": range_, "interval": interval}, timeout=TIMEOUT, headers=UA)
    res.raise_for_status()
    payload = res.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart vazio: {symbol}")
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote.get("open") or []
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    rows = []
    for i, t in enumerate(ts):
        c = closes[i] if i < len(closes) else None
        if c is None:
            continue
        o = opens[i] if i < len(opens) else None
        v = volumes[i] if i < len(volumes) else 0
        rows.append(
            {
                "date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"),
                "open": float(o) if o is not None else 0.0,
                "close": float(c),
                "volume": float(v or 0),
            }
        )
    if len(rows) < 5:
        raise RuntimeError(f"Yahoo chart poucos pontos: {symbol}")
    return rows


def _trailing_and_cagr(rows: list[dict[str, Any]]) -> tuple[float | None, float | None, float, str]:
    last = rows[-1]
    idx = max(0, len(rows) - 253)
    start = rows[idx]["close"]
    last_px = last["close"]
    t12 = ((last_px / start) - 1.0) * 100.0 if start else None
    first = rows[0]
    try:
        d0 = datetime.strptime(first["date"], "%Y-%m-%d")
        d1 = datetime.strptime(last["date"], "%Y-%m-%d")
        yrs = max((d1 - d0).days / 365.25, 0.25)
    except Exception:
        yrs = 5.0
    cagr = ((last_px / first["close"]) ** (1.0 / yrs) - 1.0) * 100.0 if first["close"] > 0 else None
    return t12, cagr, last_px, last["date"]


def _monthly(rows: list[dict[str, Any]], months: int = 24) -> list[dict[str, Any]]:
    by_month: dict[str, float] = {}
    for r in rows:
        by_month[r["date"][:7]] = r["close"]
    keys = sorted(by_month.keys())
    out = []
    for i in range(1, len(keys)):
        a, b = keys[i - 1], keys[i]
        pa, pb = by_month[a], by_month[b]
        if pa > 0:
            out.append({"month": b, "return_pct": round((pb / pa - 1.0) * 100.0, 4)})
    return out[-months:]


def fetch_benchmark_market() -> dict[str, Any]:
    items: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    errors: list[str] = []
    for key, meta in YAHOO_BENCH.items():
        symbol = meta["symbol"]
        try:
            rows = _yahoo_chart(symbol, range_="5y", interval="1d")
            t12, cagr, last_px, last_date = _trailing_and_cagr(rows)
            annual = t12 if t12 is not None else cagr
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "source_layer": "market",
                "annual_rate_pct": round(float(annual), 2) if annual is not None else None,
                "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                "cagr_approx_pct": round(float(cagr), 2) if cagr is not None else None,
                "last_close": round(last_px, 4),
                "as_of": last_date,
                "unit": "retorno 12m (proxy anual ilustrativo)",
                "description": f"Yahoo chart {symbol} — retorno ~12m educativo",
            }
            monthly[key] = _monthly(rows, 24)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "error": str(exc),
                "annual_rate_pct": None,
            }

    # Reinforce USD/BRL via AwesomeAPI if missing
    if items.get("usdbrl", {}).get("annual_rate_pct") is None:
        try:
            res = requests.get(
                "https://economia.awesomeapi.com.br/json/daily/USD-BRL/360",
                timeout=TIMEOUT,
                headers=UA,
            )
            res.raise_for_status()
            data = res.json()
            # API returns newest first
            data = list(reversed(data))
            closes = []
            for row in data:
                ts = int(row.get("timestamp") or 0)
                bid = float(row.get("bid") or 0)
                if ts and bid > 0:
                    d = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    closes.append({"date": d, "open": bid, "close": bid, "volume": 0})
            if len(closes) >= 5:
                t12, cagr, last_px, last_date = _trailing_and_cagr(closes)
                annual = t12 if t12 is not None else cagr
                items["usdbrl"] = {
                    "id": "usdbrl",
                    "label": "USD/BRL",
                    "symbol": "USD-BRL",
                    "source_layer": "market",
                    "annual_rate_pct": round(float(annual), 2) if annual is not None else None,
                    "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                    "cagr_approx_pct": round(float(cagr), 2) if cagr is not None else None,
                    "last_close": round(last_px, 4),
                    "as_of": last_date,
                    "unit": "variação ~12m",
                    "description": "AwesomeAPI USD-BRL — proxy cambial educativo",
                }
                monthly["usdbrl"] = _monthly(closes, 24)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"awesomeapi usdbrl: {exc}")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo chart API + AwesomeAPI",
        "items": items,
        "monthly": monthly,
        "errors": errors,
        "ok_count": sum(1 for v in items.values() if v.get("annual_rate_pct") is not None),
    }


def fetch_b3_liquidity_and_elite(gap_threshold_pct: float = 2.0) -> dict[str, Any]:
    elite = []
    gaps = []
    errors: list[str] = []
    for symbol in B3_WATCH:
        try:
            rows = _yahoo_chart(symbol, range_="1mo", interval="1d")
            traded = [r for r in rows if (r.get("volume") or 0) > 0]
            if len(traded) >= 2:
                rows = traded
            if len(rows) < 2:
                errors.append(f"{symbol}: hist curto")
                continue
            prev, last = rows[-2], rows[-1]
            c0, c1 = prev["close"], last["close"]
            o1, v1 = last["open"], last["volume"]
            if c0 <= 0 or c1 <= 0:
                continue
            gap_pct = ((o1 / c0) - 1.0) * 100.0 if o1 > 0 else 0.0
            day_chg = ((c1 / c0) - 1.0) * 100.0
            if v1 <= 0 or o1 <= 0 or abs(gap_pct) > 40:
                gap_pct = 0.0
            row = {
                "ticker": symbol.replace(".SA", ""),
                "symbol": symbol,
                "last": round(c1, 4),
                "volume": int(v1),
                "day_change_pct": round(day_chg, 2),
                "open_gap_pct": round(gap_pct, 2),
                "as_of": last["date"],
            }
            elite.append(row)
            if v1 > 0 and o1 > 0 and abs(gap_pct) >= gap_threshold_pct:
                gaps.append(
                    {
                        **row,
                        "signal": "pre_open_gap_attention",
                        "threshold_pct": gap_threshold_pct,
                        "note": "Gap abertura vs fechamento anterior ≥ limiar — atenção (não é ordem).",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
    elite_sorted = sorted(elite, key=lambda x: x.get("volume") or 0, reverse=True)
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo chart API (B3)",
        "elite": elite_sorted,
        "gap_attention": sorted(gaps, key=lambda x: abs(x.get("open_gap_pct") or 0), reverse=True),
        "gap_threshold_pct": gap_threshold_pct,
        "errors": errors,
        "ok_count": len(elite_sorted),
    }
