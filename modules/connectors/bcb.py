"""BCB SGS — séries oficiais amplas desde a janela de análise."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import requests

SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
TIMEOUT = 45

DEFAULT_SERIES = {
    "selic": {"code": 432, "label": "Selic meta", "unit": "a.a."},
    "cdi": {"code": 12, "label": "CDI (% a.d.)", "unit": "% a.d."},
    "ipca_12m": {"code": 13522, "label": "IPCA acumulado 12 meses", "unit": "%"},
    "ipca_m": {"code": 433, "label": "IPCA variação mensal", "unit": "% m/m"},
    "usd_ptax": {"code": 1, "label": "Dólar PTAX (venda)", "unit": "BRL"},
    "igpm_m": {"code": 28655, "label": "IGP-M variação mensal", "unit": "% m/m"},
}


def _parse_br_date(value: str) -> str | None:
    # BCB: dd/mm/yyyy
    try:
        return datetime.strptime(value.strip(), "%d/%m/%Y").date().isoformat()
    except Exception:
        return None


def _fetch_raw(url: str) -> list[dict[str, Any]]:
    headers = {"Accept": "application/json"}
    res = requests.get(url, timeout=TIMEOUT, headers=headers)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, list):
        raise RuntimeError(f"BCB resposta inesperada: {url}")
    return data


def _rows_to_points(data: list[dict[str, Any]], start_date: str | None, end_date: str | None) -> list[dict[str, Any]]:
    out = []
    for row in data:
        iso = _parse_br_date(str(row.get("data") or ""))
        raw = str(row.get("valor", "")).replace(",", ".")
        try:
            val = float(raw)
        except Exception:
            continue
        if not iso:
            continue
        if start_date and iso < start_date:
            continue
        if end_date and iso > end_date:
            continue
        out.append({"date": iso, "value": val})
    return out


def fetch_series(
    code: int,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    last_n: int | None = None,
) -> list[dict[str, Any]]:
    if last_n:
        url = f"{SGS_BASE.format(code=code)}/ultimos/{last_n}?formato=json"
        return _rows_to_points(_fetch_raw(url), None, None)

    # BCB limita janelas longas (máx. ~10 anos em séries diárias). Fatias de ~8 anos.
    # Nunca usar /ultimos/N no histórico: isso corta a janela alinhada (ex.: só 2025+).
    if not start_date:
        start_date = "2015-01-01"
    if not end_date:
        end_date = datetime.now(timezone.utc).date().isoformat()

    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    points: list[dict[str, Any]] = []
    cursor = start
    # ~8 anos civis; margem abaixo do teto ~10 anos do SGS
    max_span = timedelta(days=365 * 8 + 2)

    while cursor <= end:
        chunk_end = min(cursor + max_span, end)
        url = (
            f"{SGS_BASE.format(code=code)}?formato=json"
            f"&dataInicial={cursor.strftime('%d/%m/%Y')}"
            f"&dataFinal={chunk_end.strftime('%d/%m/%Y')}"
        )
        try:
            chunk = _rows_to_points(_fetch_raw(url), start_date, end_date)
            points.extend(chunk)
        except Exception as exc:
            # Retry com metade da janela (evita 406 / timeout)
            mid_date = cursor + timedelta(days=max((chunk_end - cursor).days // 2, 30))
            if mid_date >= chunk_end:
                raise RuntimeError(f"BCB {code} falhou em {cursor}..{chunk_end}: {exc}") from exc
            for sub_start, sub_end in ((cursor, mid_date), (mid_date + timedelta(days=1), chunk_end)):
                if sub_start > sub_end:
                    continue
                sub_url = (
                    f"{SGS_BASE.format(code=code)}?formato=json"
                    f"&dataInicial={sub_start.strftime('%d/%m/%Y')}"
                    f"&dataFinal={sub_end.strftime('%d/%m/%Y')}"
                )
                points.extend(_rows_to_points(_fetch_raw(sub_url), start_date, end_date))
        if chunk_end >= end:
            break
        cursor = chunk_end + timedelta(days=1)

    # dedupe by date
    by_date = {p["date"]: p for p in points}
    return [by_date[k] for k in sorted(by_date.keys())]


def latest_from_series(points: list[dict[str, Any]]) -> tuple[float, str]:
    if not points:
        raise RuntimeError("série BCB vazia")
    last = points[-1]
    return float(last["value"]), str(last["date"])


def fetch_official_bundle(start_date: str = "2015-01-01") -> dict[str, Any]:
    end = datetime.now(timezone.utc).date().isoformat()
    series_out: dict[str, Any] = {}
    errors: list[str] = []
    for key, meta in DEFAULT_SERIES.items():
        try:
            points = fetch_series(meta["code"], start_date=start_date, end_date=end)
            if not points:
                raise RuntimeError("vazio")
            latest, as_of = latest_from_series(points)
            # CDI série 12 vem em % a.d. — anualiza approx base 252 para o snapshot
            display_latest = latest
            display_unit = meta["unit"]
            if key == "cdi" and latest is not None and abs(latest) < 1:
                display_latest = round(((1.0 + latest / 100.0) ** 252 - 1.0) * 100.0, 2)
                display_unit = "% a.a. (approx 252)"
            monthly = _to_monthly(points, key)
            series_out[key] = {
                **meta,
                "unit": display_unit,
                "series_code": meta["code"],
                "latest": display_latest,
                "raw_latest": latest,
                "as_of": as_of,
                "points_count": len(points),
                "monthly": monthly,
            }
            if key == "selic":
                series_out[key]["points"] = points  # histórico diário para decisões COPOM

        except Exception as exc:  # noqa: BLE001
            errors.append(f"{key}/{meta['code']}: {exc}")
            series_out[key] = {**meta, "series_code": meta["code"], "error": str(exc)}

    selic = series_out.get("selic") or {}
    ipca = series_out.get("ipca_12m") or {}
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "BCB SGS",
        "start_date": start_date,
        "end_date": end,
        "series": series_out,
        "errors": errors,
        # Compat com collector atual
        "selic": {
            "annual_rate_pct": selic.get("latest"),
            "as_of": selic.get("as_of"),
            "series_code": selic.get("series_code"),
            "label": selic.get("label"),
            "unit": selic.get("unit"),
        },
        "ipca": {
            "annual_rate_pct": ipca.get("latest"),
            "as_of": ipca.get("as_of"),
            "series_code": ipca.get("series_code"),
            "label": ipca.get("label"),
            "unit": ipca.get("unit"),
        },
    }


def _to_monthly(points: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    """Último valor de cada mês (ou soma para variações mensais já mensais)."""
    by_month: dict[str, float] = {}
    for p in points:
        by_month[p["date"][:7]] = float(p["value"])
    return [{"month": m, "value": round(by_month[m], 6)} for m in sorted(by_month.keys())]


# Alias
def fetch_official_rates(start_date: str = "2015-01-01") -> dict[str, Any]:
    return fetch_official_bundle(start_date=start_date)
