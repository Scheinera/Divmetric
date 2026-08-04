"""Yahoo Finance / yfinance — preços, retornos e gaps educacionais."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import yfinance as yf

TICKERS = {
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


def _sleep(sec: float = 1.2) -> None:
    time.sleep(sec)


def _close_series(symbol: str, period: str = "5y", retries: int = 4) -> pd.Series:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            _sleep(1.0 + attempt * 1.5)
            df = yf.download(
                symbol,
                period=period,
                interval="1d",
                progress=False,
                auto_adjust=True,
                threads=False,
            )
            if df is None or df.empty:
                raise RuntimeError(f"Yahoo: sem dados para {symbol}")
            if isinstance(df.columns, pd.MultiIndex):
                close = df["Close"]
                if isinstance(close, pd.DataFrame):
                    close = close.iloc[:, 0]
            else:
                close = df["Close"]
            close = close.dropna()
            if close.empty:
                raise RuntimeError(f"Yahoo: Close vazio para {symbol}")
            return close.astype(float)
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            _sleep(2.0 + attempt * 2.0)
    raise RuntimeError(f"Yahoo falhou {symbol}: {last_err}")


def trailing_return_pct(close: pd.Series, trading_days: int = 252) -> float | None:
    if len(close) < trading_days + 1:
        if len(close) < 2:
            return None
        start, end = float(close.iloc[0]), float(close.iloc[-1])
    else:
        start, end = float(close.iloc[-(trading_days + 1)]), float(close.iloc[-1])
    if start == 0:
        return None
    return (end / start - 1.0) * 100.0


def cagr_pct(close: pd.Series) -> float | None:
    if len(close) < 2:
        return None
    start, end = float(close.iloc[0]), float(close.iloc[-1])
    if start <= 0 or end <= 0:
        return None
    try:
        days = (close.index[-1] - close.index[0]).days
        yrs = max(days / 365.25, 0.25)
    except Exception:
        yrs = 5.0
    return ((end / start) ** (1.0 / yrs) - 1.0) * 100.0


def monthly_returns(close: pd.Series, months: int = 24) -> list[dict[str, Any]]:
    monthly = close.resample("ME").last().dropna()
    if len(monthly) < 2:
        return []
    rets = monthly.pct_change().dropna().tail(months)
    out = []
    for idx, val in rets.items():
        out.append({"month": idx.strftime("%Y-%m"), "return_pct": round(float(val) * 100.0, 4)})
    return out


def fetch_benchmark_market() -> dict[str, Any]:
    items: dict[str, Any] = {}
    monthly: dict[str, Any] = {}
    errors: list[str] = []
    for key, meta in TICKERS.items():
        symbol = meta["symbol"]
        try:
            close = _close_series(symbol, period="5y")
            t12 = trailing_return_pct(close, 252)
            cagr = cagr_pct(close)
            annual = t12 if t12 is not None else cagr
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "source_layer": "market",
                "annual_rate_pct": round(float(annual), 2) if annual is not None else None,
                "trailing_12m_pct": round(float(t12), 2) if t12 is not None else None,
                "cagr_approx_pct": round(float(cagr), 2) if cagr is not None else None,
                "last_close": round(float(close.iloc[-1]), 4),
                "as_of": close.index[-1].strftime("%Y-%m-%d"),
                "unit": "retorno 12m (proxy anual ilustrativo)",
                "description": f"Yahoo {symbol} — retorno ~12m para projeção educativa",
            }
            monthly[key] = monthly_returns(close, 24)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{symbol}: {exc}")
            items[key] = {
                "id": key,
                "label": meta["label"],
                "symbol": symbol,
                "error": str(exc),
                "annual_rate_pct": None,
            }
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance (yfinance)",
        "items": items,
        "monthly": monthly,
        "errors": errors,
        "ok_count": sum(1 for v in items.values() if v.get("annual_rate_pct") is not None),
    }


def _history_valid(hist: pd.DataFrame) -> pd.DataFrame:
    if hist is None or hist.empty:
        return hist
    # Prefer days with real volume
    if "Volume" in hist.columns:
        traded = hist[hist["Volume"].fillna(0) > 0]
        if len(traded) >= 2:
            return traded
    return hist


def fetch_b3_liquidity_and_elite(gap_threshold_pct: float = 2.0) -> dict[str, Any]:
    elite = []
    gaps = []
    errors: list[str] = []
    for symbol in B3_WATCH:
        try:
            _sleep(1.2)
            t = yf.Ticker(symbol)
            hist = _history_valid(t.history(period="15d", auto_adjust=True))
            if hist is None or len(hist) < 2:
                errors.append(f"{symbol}: hist curto")
                continue
            last = hist.iloc[-1]
            prev = hist.iloc[-2]
            last_close = float(last["Close"])
            prev_close = float(prev["Close"])
            open_px = float(last["Open"]) if pd.notna(last["Open"]) else 0.0
            volume = float(last.get("Volume") or 0)
            if prev_close <= 0 or last_close <= 0:
                continue
            gap_pct = ((open_px / prev_close) - 1.0) * 100.0 if open_px > 0 else 0.0
            day_chg = ((last_close / prev_close) - 1.0) * 100.0
            if volume <= 0 or open_px <= 0 or abs(gap_pct) > 40:
                gap_pct = 0.0
            row = {
                "ticker": symbol.replace(".SA", ""),
                "symbol": symbol,
                "last": round(last_close, 4),
                "volume": int(volume),
                "day_change_pct": round(day_chg, 2),
                "open_gap_pct": round(gap_pct, 2),
                "as_of": hist.index[-1].strftime("%Y-%m-%d"),
            }
            dy = None
            try:
                _sleep(0.4)
                info = t.info or {}
                dy = info.get("dividendYield")
                if dy is not None and float(dy) < 1:
                    dy = float(dy) * 100.0
            except Exception:
                dy = None
            if dy is not None:
                row["dividend_yield_pct"] = round(float(dy), 2)
            elite.append(row)
            if volume > 0 and open_px > 0 and abs(gap_pct) >= gap_threshold_pct:
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
    elite_sorted = sorted(
        [e for e in elite if "volume" in e],
        key=lambda x: x.get("volume") or 0,
        reverse=True,
    )
    return {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance (yfinance)",
        "elite": elite_sorted,
        "gap_attention": sorted(gaps, key=lambda x: abs(x.get("open_gap_pct") or 0), reverse=True),
        "gap_threshold_pct": gap_threshold_pct,
        "errors": errors,
        "ok_count": len(elite_sorted),
    }
