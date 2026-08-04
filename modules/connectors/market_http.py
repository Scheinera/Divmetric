"""Market data via Yahoo chart API (HTTP) + AwesomeAPI — janela diária alinhada."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

import requests

TIMEOUT = 45
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
}

DEFAULT_BENCH = {
    "ibov": {"symbol": "^BVSP", "label": "Ibovespa"},
    "spx": {"symbol": "^GSPC", "label": "S&P 500"},
    "btc": {"symbol": "BTC-USD", "label": "Bitcoin"},
    "gold": {"symbol": "GC=F", "label": "Ouro (futuro)"},
    "dxy": {"symbol": "DX-Y.NYB", "label": "DXY"},
    "usdbrl": {"symbol": "USDBRL=X", "label": "USD/BRL"},
    "us10y": {"symbol": "^TNX", "label": "US 10Y yield"},
    "ewz": {"symbol": "EWZ", "label": "MSCI Brazil ETF"},
}

DEFAULT_B3 = [
    "PETR4.SA",
    "VALE3.SA",
    "ITUB4.SA",
    "BBDC4.SA",
    "BBAS3.SA",
    "WEGE3.SA",
    "ABEV3.SA",
    "B3SA3.SA",
    "RENT3.SA",
    "PRIO3.SA",
    "SUZB3.SA",
    "VBBR3.SA",
    "EQTL3.SA",
    "RADL3.SA",
    "ITSA4.SA",
    "ELET3.SA",
    "VIVT3.SA",
    "BBSE3.SA",
    "CMIG4.SA",
    "TAEE11.SA",
]


def _to_unix(date_str: str) -> int:
    dt = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _yahoo_chart(
    symbol: str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    range_: str | None = None,
    interval: str = "1d",
    events: str | None = "div|split",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch daily (or other) bars. Prefer period1/period2 — range=max downsample and breaks 12m math."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    params: dict[str, Any] = {"interval": interval}
    if events:
        params["events"] = events
    if range_:
        params["range"] = range_
    else:
        start = start_date or "2015-01-01"
        # pad 14 months so calendar trailing-12m always has an anchor
        padded = (datetime.strptime(start[:10], "%Y-%m-%d") - timedelta(days=420)).strftime("%Y-%m-%d")
        params["period1"] = _to_unix(padded)
        params["period2"] = _to_unix(end_date) if end_date else int(datetime.now(timezone.utc).timestamp())

    res = requests.get(url, params=params, timeout=TIMEOUT, headers=UA)
    res.raise_for_status()
    payload = res.json()
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo chart vazio: {symbol}")

    ts = result.get("timestamp") or []
    quote_block = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    opens = quote_block.get("open") or []
    closes = quote_block.get("close") or []
    volumes = quote_block.get("volume") or []
    rows: list[dict[str, Any]] = []
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
        raise RuntimeError(f"Yahoo chart poucos pontos: {symbol} (n={len(rows)})")
    events_block = result.get("events") or {}
    return rows, events_block


def _filter_from(rows: list[dict[str, Any]], start_date: str) -> list[dict[str, Any]]:
    return [r for r in rows if r["date"] >= start_date]


def _trailing_and_cagr(rows: list[dict[str, Any]]) -> tuple[float | None, float | None, float, str]:
    """Trailing ~365 calendar days (not bar-count). CAGR from first bar in the series."""
    last = rows[-1]
    last_px = last["close"]
    d1 = datetime.strptime(last["date"], "%Y-%m-%d")
    cut = (d1 - timedelta(days=365)).strftime("%Y-%m-%d")
    past = [r for r in rows if r["date"] <= cut]
    if past and past[-1]["close"] > 0:
        t12 = ((last_px / past[-1]["close"]) - 1.0) * 100.0
    else:
        t12 = None

    first = rows[0]
    try:
        d0 = datetime.strptime(first["date"], "%Y-%m-%d")
        yrs = max((d1 - d0).days / 365.25, 0.25)
    except Exception:
        yrs = 5.0
    cagr = ((last_px / first["close"]) ** (1.0 / yrs) - 1.0) * 100.0 if first["close"] > 0 else None
    return t12, cagr, last_px, last["date"]


def _trailing_cash_dividends(
    events: dict[str, Any],
    as_of: str,
    lookback_days: int = 365,
) -> tuple[float, int]:
    """Soma cash dividends (eventos Yahoo) no intervalo trailing. Retorna (total, n)."""
    divs = (events or {}).get("dividends") or {}
    if not divs:
        return 0.0, 0
    try:
        end = datetime.strptime(as_of[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except Exception:
        end = datetime.now(timezone.utc)
    start_ts = int((end - timedelta(days=lookback_days)).timestamp())
    end_ts = int(end.timestamp()) + 86400
    total = 0.0
    n = 0
    for item in divs.values():
        ts = int(item.get("date") or 0)
        amt = float(item.get("amount") or 0)
        if start_ts <= ts <= end_ts and amt > 0:
            total += amt
            n += 1
    return total, n


def _trailing_dividend_yield_pct(events: dict[str, Any], last_close: float, as_of: str) -> float | None:
    """Sum cash dividends in trailing ~365d / last close — Yahoo events (no crumb)."""
    if last_close <= 0:
        return None
    total, n = _trailing_cash_dividends(events, as_of)
    if n == 0 or total <= 0:
        return None
    return round(100.0 * total / last_close, 2)


def _total_shareholder_return_12m(
    rows: list[dict[str, Any]],
    events: dict[str, Any],
) -> dict[str, Any] | None:
    """
    Proxy educacional de TSR ~12m:
      (preço_final - preço_inicial + dividendos_cash) / preço_inicial

    Não inclui recompra de ações (buyback) — dado ainda não consolidado de fonte gratuita confiável.
    """
    if len(rows) < 2:
        return None
    last = rows[-1]
    last_px = float(last["close"])
    if last_px <= 0:
        return None
    d1 = datetime.strptime(last["date"], "%Y-%m-%d")
    cut = (d1 - timedelta(days=365)).strftime("%Y-%m-%d")
    past = [r for r in rows if r["date"] <= cut]
    if not past or past[-1]["close"] <= 0:
        return None
    start_px = float(past[-1]["close"])
    start_date = past[-1]["date"]
    div_cash, div_n = _trailing_cash_dividends(events, last["date"])
    price_ret = ((last_px / start_px) - 1.0) * 100.0
    div_contrib = (div_cash / start_px) * 100.0
    tsr = ((last_px - start_px + div_cash) / start_px) * 100.0
    return {
        "total_return_12m_pct": round(tsr, 2),
        "price_return_12m_pct": round(price_ret, 2),
        "dividend_contribution_12m_pct": round(div_contrib, 2),
        "dividends_cash_12m": round(div_cash, 4),
        "dividends_count_12m": div_n,
        "tsr_start_date": start_date,
        "tsr_start_price": round(start_px, 4),
        "buyback_included": False,
        "tsr_method": "price_plus_cash_dividends_trailing_365d",
        "tsr_note": (
            "Total return ≈ variação de preço + dividendos em dinheiro no período. "
            "Recompra (buyback) ainda não entra nesta versão."
        ),
    }


def _monthly_levels(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, float] = {}
    for r in rows:
        by_month[r["date"][:7]] = r["close"]
    return [{"month": m, "value": round(by_month[m], 6)} for m in sorted(by_month.keys())]


def _monthly_returns(levels: list[dict[str, Any]], months: int | None = None) -> list[dict[str, Any]]:
    out = []
    for i in range(1, len(levels)):
        a, b = levels[i - 1], levels[i]
        if a["value"] > 0:
            out.append(
                {
                    "month": b["month"],
                    "return_pct": round((b["value"] / a["value"] - 1.0) * 100.0, 4),
                }
            )
    if months:
        return out[-months:]
    return out


def _indexed(levels: list[dict[str, Any]], base: float = 100.0) -> list[dict[str, Any]]:
    if not levels:
        return []
    first = levels[0]["value"]
    if first <= 0:
        return []
    return [{"month": x["month"], "value": round(base * x["value"] / first, 4)} for x in levels]


def fetch_benchmark_market(
    start_date: str = "2015-01-01",
    benchmarks: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    bench = benchmarks or DEFAULT_BENCH
    items: dict[str, Any] = {}
    monthly_levels: dict[str, Any] = {}
    monthly_returns: dict[str, Any] = {}
    indexed: dict[str, Any] = {}
    errors: list[str] = []

    for key, meta in bench.items():
        symbol = meta["symbol"]
        try:
            raw_rows, _events = _yahoo_chart(symbol, start_date=start_date, interval="1d")
            rows = _filter_from(raw_rows, start_date)
            if len(rows) < 5:
                rows = raw_rows
            # Yield indices (^TNX): use level, not price-return as "rate"
            t12, cagr, last_px, last_date = _trailing_and_cagr(rows)
            if key == "us10y":
                annual = last_px  # already a % yield level
                unit = "% a.a. (nível do título)"
                desc = f"Yahoo chart {symbol} — nível do yield (não retorno de preço)"
            else:
                annual = t12 if t12 is not None else cagr
                unit = "retorno ~12m calendário (proxy) · CAGR na janela"
                desc = f"Yahoo chart diário {symbol} desde {start_date}"
            levels = _monthly_levels(rows)
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "source_layer": "market",
                "annual_rate_pct": round(float(annual), 2) if annual is not None else None,
                "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                "cagr_since_start_pct": round(float(cagr), 2) if cagr is not None else None,
                "last_close": round(last_px, 4),
                "as_of": last_date,
                "start_used": rows[0]["date"],
                "bars": len(rows),
                "unit": unit,
                "description": desc,
            }
            monthly_levels[key] = levels
            monthly_returns[key] = _monthly_returns(levels)
            indexed[key] = _indexed(levels, 100.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "error": str(exc),
                "annual_rate_pct": None,
            }

    # AwesomeAPI fallback USD (daily ~1y; keep if Yahoo failed)
    if items.get("usdbrl", {}).get("annual_rate_pct") is None:
        try:
            res = requests.get(
                "https://economia.awesomeapi.com.br/json/daily/USD-BRL/360",
                timeout=TIMEOUT,
                headers=UA,
            )
            res.raise_for_status()
            data = list(reversed(res.json()))
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
                levels = _monthly_levels(closes)
                items["usdbrl"] = {
                    "id": "usdbrl",
                    "label": "USD/BRL",
                    "symbol": "USD-BRL",
                    "source_layer": "market",
                    "annual_rate_pct": round(float(annual), 2) if annual is not None else None,
                    "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                    "cagr_since_start_pct": round(float(cagr), 2) if cagr is not None else None,
                    "last_close": round(last_px, 4),
                    "as_of": last_date,
                    "start_used": closes[0]["date"],
                    "unit": "variação ~12m",
                    "description": "AwesomeAPI USD-BRL (fallback)",
                }
                monthly_levels["usdbrl"] = levels
                monthly_returns["usdbrl"] = _monthly_returns(levels)
                indexed["usdbrl"] = _indexed(levels, 100.0)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"awesomeapi usdbrl: {exc}")

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance chart API (period1/period2 diário) + AwesomeAPI",
        "start_date": start_date,
        "items": items,
        "monthly_levels": monthly_levels,
        "monthly": monthly_returns,
        "indexed_100": indexed,
        "errors": errors,
        "ok_count": sum(1 for v in items.values() if v.get("annual_rate_pct") is not None),
    }


def fetch_b3_liquidity_and_elite(
    gap_threshold_pct: float = 2.0,
    tickers: list[str] | None = None,
    start_date: str = "2015-01-01",
) -> dict[str, Any]:
    watch = tickers or DEFAULT_B3
    elite = []
    gaps = []
    errors: list[str] = []
    for symbol in watch:
        try:
            raw_rows, events = _yahoo_chart(symbol, start_date=start_date, interval="1d", events="div|split")
            rows = _filter_from(raw_rows, start_date)
            if len(rows) < 2:
                raw_rows, events = _yahoo_chart(symbol, range_="6mo", interval="1d", events="div|split")
                rows = raw_rows
            traded = [r for r in rows if (r.get("volume") or 0) > 0]
            use_rows = traded if len(traded) >= 2 else rows
            if len(use_rows) < 2:
                errors.append(f"{symbol}: hist curto")
                continue
            prev, last = use_rows[-2], use_rows[-1]
            c0, c1 = prev["close"], last["close"]
            o1, v1 = last["open"], last["volume"]
            if c0 <= 0 or c1 <= 0:
                continue
            gap_pct = ((o1 / c0) - 1.0) * 100.0 if o1 > 0 else 0.0
            day_chg = ((c1 / c0) - 1.0) * 100.0
            if v1 <= 0 or o1 <= 0 or abs(gap_pct) > 40:
                gap_pct = 0.0

            t12, cagr, _, _ = _trailing_and_cagr(use_rows)
            dy = _trailing_dividend_yield_pct(events, c1, last["date"])
            tsr = _total_shareholder_return_12m(use_rows, events)
            row = {
                "ticker": symbol.replace(".SA", ""),
                "symbol": symbol,
                "last": round(c1, 4),
                "volume": int(v1),
                "day_change_pct": round(day_chg, 2),
                "open_gap_pct": round(gap_pct, 2),
                "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                "cagr_since_start_pct": round(float(cagr), 2) if cagr is not None else None,
                "start_used": use_rows[0]["date"],
                "as_of": last["date"],
                "bars": len(use_rows),
            }
            if dy is not None:
                row["dividend_yield_pct"] = dy
                row["dividend_yield_method"] = "yahoo_events_trailing_12m_cash"
            if tsr:
                row.update(tsr)
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
        "source": "Yahoo chart diário + eventos de dividendos",
        "start_date": start_date,
        "elite": elite_sorted,
        "gap_attention": sorted(gaps, key=lambda x: abs(x.get("open_gap_pct") or 0), reverse=True),
        "gap_threshold_pct": gap_threshold_pct,
        "errors": errors,
        "ok_count": len(elite_sorted),
    }
