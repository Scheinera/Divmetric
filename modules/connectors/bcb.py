"""BCB SGS — séries oficiais (Selic, IPCA)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

SGS_BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
TIMEOUT = 30

# https://www3.bcb.gov.br/sgspub/
SERIES = {
    "selic": {"code": 432, "label": "Selic", "unit": "a.a."},
    "ipca_12m": {"code": 13522, "label": "IPCA 12 meses", "unit": "a.a. acum."},
}


def fetch_series(code: int, *, last_n: int | None = None) -> list[dict[str, Any]]:
    if last_n:
        url = f"{SGS_BASE.format(code=code)}/ultimos/{last_n}?formato=json"
    else:
        url = f"{SGS_BASE.format(code=code)}?formato=json"
    res = requests.get(url, timeout=TIMEOUT)
    res.raise_for_status()
    data = res.json()
    if not isinstance(data, list):
        raise RuntimeError(f"BCB SGS {code}: resposta inesperada")
    return data


def latest_value(code: int) -> tuple[float, str]:
    rows = fetch_series(code, last_n=1)
    if not rows:
        raise RuntimeError(f"BCB SGS {code}: vazio")
    row = rows[-1]
    raw = str(row.get("valor", "")).replace(",", ".")
    return float(raw), str(row.get("data") or "")


def fetch_official_rates() -> dict[str, Any]:
    selic, selic_as_of = latest_value(SERIES["selic"]["code"])
    ipca, ipca_as_of = latest_value(SERIES["ipca_12m"]["code"])
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "BCB SGS",
        "selic": {
            "annual_rate_pct": selic,
            "as_of": selic_as_of,
            "series_code": SERIES["selic"]["code"],
            "label": SERIES["selic"]["label"],
            "unit": SERIES["selic"]["unit"],
        },
        "ipca": {
            "annual_rate_pct": ipca,
            "as_of": ipca_as_of,
            "series_code": SERIES["ipca_12m"]["code"],
            "label": SERIES["ipca_12m"]["label"],
            "unit": SERIES["ipca_12m"]["unit"],
        },
    }
