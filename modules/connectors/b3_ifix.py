"""IFIX oficial — B3 indexStatisticsProxy / indexProxy (fonte canônica)."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any

import requests

TIMEOUT = 45
UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://sistemaswebb3-listados.b3.com.br/indexStatisticsPage/monthly-evolution/IFIX?language=pt-br",
    "Origin": "https://sistemaswebb3-listados.b3.com.br",
}

STATS_BASE = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall"
LIST_BASE = "https://sistemaswebb3-listados.b3.com.br/indexProxy/indexCall"


def _b64(payload: dict[str, Any]) -> str:
    return base64.b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")).decode("ascii")


def _get_stats(method: str, payload: dict[str, Any]) -> Any:
    url = f"{STATS_BASE}/{method}/{_b64(payload)}"
    res = requests.get(url, timeout=TIMEOUT, headers=UA)
    res.raise_for_status()
    if not res.content:
        return None
    return res.json()


def _get_list(method: str, payload: dict[str, Any]) -> Any:
    url = f"{LIST_BASE}/{method}/{_b64(payload)}"
    res = requests.get(
        url,
        timeout=TIMEOUT,
        headers={**UA, "Referer": "https://sistemaswebb3-listados.b3.com.br/indexPage/day/IFIX?language=pt-br"},
    )
    res.raise_for_status()
    if not res.content:
        return None
    return res.json()


def _parse_br_number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # B3: 3.785,52
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except Exception:
        return None


def fetch_ifix_monthly(start_date: str = "2015-01-01", end_date: str | None = None) -> list[dict[str, Any]]:
    """Evolução mensal oficial (chunks ≤10 anos — regra da UI B3)."""
    end = end_date or datetime.now(timezone.utc).date().isoformat()
    start_y = int(start_date[:4])
    end_y = int(end[:4])
    # UI: dateInitial = (selectFrom-1)-01-01, dateFinal = selectTo-12-31, span selectTo-selectFrom <= 10
    points: list[dict[str, Any]] = []
    select_from = start_y
    while select_from <= end_y:
        select_to = min(select_from + 9, end_y)
        payload = {
            "index": "IFIX",
            "language": "pt-br",
            "dateInitial": f"{select_from - 1}-01-01",
            "dateFinal": f"{select_to}-12-31",
        }
        chunk = _get_stats("GetMonthlyEvolution", payload) or []
        if not isinstance(chunk, list):
            raise RuntimeError(f"IFIX monthly inesperado: {type(chunk)}")
        for row in chunk:
            y = int(row.get("year"))
            m = int(row.get("month"))
            val = row.get("indexClosingRate")
            if val is None:
                continue
            month = f"{y:04d}-{m:02d}"
            if month < start_date[:7] or month > end[:7]:
                continue
            points.append({"month": month, "value": float(val), "date": f"{month}-01"})
        select_from = select_to + 1

    by_month = {p["month"]: p for p in points}
    return [by_month[k] for k in sorted(by_month.keys())]


def fetch_ifix_yearly() -> list[dict[str, Any]]:
    payload = {
        "pageNumber": 1,
        "pageSize": 50,
        "index": "IFIX",
        "language": "pt-br",
        "year": 1968,
        "yearEnd": int(datetime.now(timezone.utc).strftime("%Y")),
    }
    data = _get_stats("GetYearlyVariation", payload) or {}
    rows = data.get("results") or []
    out = []
    for row in rows:
        year = row.get("year")
        close = _parse_br_number(row.get("nominalClosingIndex"))
        var_pct = _parse_br_number(row.get("nominalAnnualVariation"))
        if year is None or close is None:
            continue
        out.append(
            {
                "year": int(year),
                "closing_index": close,
                "annual_variation_pct": var_pct,
            }
        )
    return sorted(out, key=lambda x: x["year"])


def fetch_ifix_portfolio() -> dict[str, Any]:
    payload = {"language": "pt-br", "index": "IFIX"}
    data = _get_list("GetPortfolioDay", payload) or {}
    header = data.get("header") or {}
    results = data.get("results") or []
    constituents = []
    for row in results:
        code = row.get("cod") or row.get("code")
        if not code:
            continue
        constituents.append(
            {
                "ticker": str(code).replace(".SA", ""),
                "name": row.get("asset") or row.get("description") or row.get("spec") or None,
                "part_pct": _parse_br_number(row.get("part") or row.get("partPct")),
                "theorical_qty": _parse_br_number(row.get("theoricalQty") or row.get("theoreticalQty")),
            }
        )
    constituents = sorted(
        constituents,
        key=lambda x: x.get("part_pct") if x.get("part_pct") is not None else -1,
        reverse=True,
    )
    as_of_raw = header.get("date")
    as_of = None
    if as_of_raw:
        try:
            as_of = datetime.strptime(str(as_of_raw), "%d/%m/%y").date().isoformat()
        except Exception:
            try:
                as_of = datetime.strptime(str(as_of_raw), "%d/%m/%Y").date().isoformat()
            except Exception:
                as_of = str(as_of_raw)
    return {
        "as_of": as_of,
        "header": {
            "reductor": header.get("reductor"),
            "theorical_qty_total": header.get("theoricalQty"),
            "part": header.get("part"),
        },
        "constituents": constituents,
        "count": len(constituents),
    }


def fetch_ifix_bundle(start_date: str = "2015-01-01") -> dict[str, Any]:
    monthly = fetch_ifix_monthly(start_date=start_date)
    if len(monthly) < 3:
        raise RuntimeError("IFIX monthly curto")
    yearly = fetch_ifix_yearly()
    portfolio = fetch_ifix_portfolio()

    last = monthly[-1]
    cut = f"{int(last['month'][:4]) - 1}-{last['month'][5:]}"
    past = [m for m in monthly if m["month"] <= cut]
    t12 = None
    if past and past[-1]["value"] > 0:
        t12 = ((last["value"] / past[-1]["value"]) - 1.0) * 100.0

    first = monthly[0]
    d0 = datetime.strptime(first["month"] + "-01", "%Y-%m-%d")
    d1 = datetime.strptime(last["month"] + "-01", "%Y-%m-%d")
    yrs = max((d1 - d0).days / 365.25, 0.25)
    cagr = ((last["value"] / first["value"]) ** (1.0 / yrs) - 1.0) * 100.0 if first["value"] > 0 else None

    returns = []
    for i in range(1, len(monthly)):
        a, b = monthly[i - 1], monthly[i]
        if a["value"] > 0:
            returns.append(
                {
                    "month": b["month"],
                    "return_pct": round((b["value"] / a["value"] - 1.0) * 100.0, 4),
                }
            )
    indexed = []
    base = first["value"]
    for m in monthly:
        indexed.append({"month": m["month"], "value": round(100.0 * m["value"] / base, 4)})

    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "B3 indexStatisticsProxy + indexProxy (IFIX oficial)",
        "source_urls": {
            "stats": "https://sistemaswebb3-listados.b3.com.br/indexStatisticsPage/monthly-evolution/IFIX?language=pt-br",
            "b3_page": "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/indice-fundos-de-investimentos-imobiliarios-ifix-estatisticas-historicas.htm",
        },
        "start_date": start_date,
        "latest": round(float(last["value"]), 4),
        "as_of_month": last["month"],
        "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
        "cagr_since_start_pct": round(float(cagr), 2) if cagr is not None else None,
        "monthly_levels": [{"month": m["month"], "value": round(m["value"], 6)} for m in monthly],
        "monthly_returns": returns,
        "indexed_100": indexed,
        "yearly": yearly,
        "portfolio": portfolio,
        "trust": "canonical",
    }
