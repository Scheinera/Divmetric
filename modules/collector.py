"""Divmetric collector — BCB + Yahoo → docs/data/*.json"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.connectors.bcb import fetch_official_rates  # noqa: E402
from modules.connectors.market_http import (  # noqa: E402
    fetch_b3_liquidity_and_elite,
    fetch_benchmark_market,
)

DATA = ROOT / "docs" / "data"
DISCLAIMER = "Conteúdo educacional. Não é recomendação de investimento."


def write_json(name: str, payload: dict[str, Any]) -> Path:
    DATA.mkdir(parents=True, exist_ok=True)
    path = DATA / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_json(name: str) -> dict[str, Any] | None:
    path = DATA / name
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def merge_market_preserve(previous: dict[str, Any] | None, market: dict[str, Any]) -> dict[str, Any]:
    """If Yahoo rate-limits, keep last good annual_rate_pct / monthly series."""
    prev_items = {}
    if previous:
        for row in previous.get("items") or []:
            if row.get("id") and row.get("annual_rate_pct") is not None and row.get("source_layer") == "market":
                prev_items[row["id"]] = row
    prev_monthly = (load_json("history_monthly.json") or {}).get("series") or {}

    items = market.get("items") or {}
    monthly = market.get("monthly") or {}
    for key, row in list(items.items()):
        if row.get("annual_rate_pct") is None and key in prev_items:
            kept = dict(prev_items[key])
            kept["stale"] = True
            kept["error_current"] = row.get("error")
            items[key] = kept
            if key in prev_monthly and key not in monthly:
                monthly[key] = prev_monthly[key]
    market["items"] = items
    market["monthly"] = monthly
    return market


def merge_liq_preserve(previous_elite: dict[str, Any] | None, previous_liq: dict[str, Any] | None, liq: dict[str, Any]) -> dict[str, Any]:
    if (liq.get("ok_count") or 0) > 0:
        return liq
    # Fallback to previous exports
    if previous_liq and (previous_liq.get("watch") or previous_liq.get("status") == "live"):
        out = dict(previous_liq)
        out["stale"] = True
        out["note_fallback"] = "Yahoo rate-limit/erro — mantendo snapshot anterior"
        return {
            "fetched_at": liq.get("fetched_at"),
            "source": liq.get("source"),
            "elite": (previous_elite or {}).get("b3_watch") or [],
            "gap_attention": out.get("watch") or [],
            "gap_threshold_pct": liq.get("gap_threshold_pct", 2.0),
            "errors": liq.get("errors") or [],
            "ok_count": 0,
            "stale": True,
        }
    return liq


def build_benchmarks(official: dict[str, Any], market: dict[str, Any]) -> dict[str, Any]:
    items = []
    selic = official["selic"]
    ipca = official["ipca"]
    items.append(
        {
            "id": "selic",
            "label": "Selic",
            "source_layer": "official",
            "annual_rate_pct": selic["annual_rate_pct"],
            "unit": selic["unit"],
            "description": f"BCB SGS {selic['series_code']} · ref {selic['as_of']}",
            "as_of": selic["as_of"],
        }
    )
    items.append(
        {
            "id": "ipca",
            "label": "IPCA (12m)",
            "source_layer": "official",
            "annual_rate_pct": ipca["annual_rate_pct"],
            "unit": ipca["unit"],
            "description": f"BCB SGS {ipca['series_code']} · ref {ipca['as_of']}",
            "as_of": ipca["as_of"],
        }
    )
    for key in ("ibov", "btc", "gold", "dxy"):
        row = (market.get("items") or {}).get(key) or {}
        if row.get("annual_rate_pct") is None and row.get("error"):
            continue
        items.append(
            {
                "id": key,
                "label": row.get("label") or key,
                "source_layer": "market",
                "annual_rate_pct": row.get("annual_rate_pct"),
                "trailing_12m_pct": row.get("trailing_12m_pct"),
                "cagr_approx_pct": row.get("cagr_approx_pct"),
                "unit": row.get("unit") or "retorno 12m (proxy)",
                "description": row.get("description") or "",
                "as_of": row.get("as_of"),
                "symbol": row.get("symbol"),
                "last_close": row.get("last_close"),
            }
        )
    # USD/BRL as informational (not primary calculator leg unless useful)
    usd = (market.get("items") or {}).get("usdbrl")
    if usd and usd.get("annual_rate_pct") is not None:
        items.append(
            {
                "id": "usdbrl",
                "label": "USD/BRL",
                "source_layer": "market",
                "annual_rate_pct": usd.get("annual_rate_pct"),
                "unit": "variação ~12m",
                "description": "Proxy cambial educativo",
                "as_of": usd.get("as_of"),
                "symbol": usd.get("symbol"),
                "last_close": usd.get("last_close"),
            }
        )
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "currency": "BRL",
        "note": "Selic/IPCA = BCB. Demais = retorno ~12 meses (Yahoo) para projeção educativa — não é retorno garantido.",
        "items": items,
        "sources": {"official": official.get("source"), "market": market.get("source")},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def build_history_monthly(market: dict[str, Any]) -> dict[str, Any]:
    return {
        "granularity": "monthly",
        "status": "live",
        "note": "Retornos mensais (Yahoo) — uso educacional.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "series": market.get("monthly") or {},
    }


def build_opportunity_cost(official: dict[str, Any], benchmarks: dict[str, Any]) -> dict[str, Any]:
    by_id = {i["id"]: i for i in benchmarks.get("items") or []}
    selic = official["selic"]["annual_rate_pct"]
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "principle": "Toda escolha de capital tem um custo implícito: o que você deixou de ganhar na melhor alternativa comparável.",
        "primary_benchmark": "selic",
        "selic_annual_rate_pct": selic,
        "questions": [
            "Quanto rende o mesmo capital na Selic / Tesouro / caixa?",
            "Qual a incerteza (volatilidade e drawdown) da alternativa escolhida?",
            "O prêmio de risco justifica abrir mão da certeza relativa da renda fixa?",
        ],
        "comparisons": [
            {
                "id": "cash_selic",
                "label": "Caixa / Selic",
                "certainty": "alta",
                "role": "âncora de oportunidade",
                "annual_rate_pct": selic,
            },
            {
                "id": "dividends",
                "label": "Carteira de dividendos",
                "certainty": "média",
                "role": "renda + risco de preço",
                "annual_rate_pct": None,
                "note": "Usar DY consolidado quando radar estiver preenchido",
            },
            {
                "id": "elite_equity",
                "label": "Ações de elite / líderes",
                "certainty": "média-baixa",
                "role": "crescimento com liquidez",
                "annual_rate_pct": (by_id.get("ibov") or {}).get("annual_rate_pct"),
            },
            {
                "id": "btc",
                "label": "Bitcoin",
                "certainty": "baixa",
                "role": "opção assimétrica (alta vol)",
                "annual_rate_pct": (by_id.get("btc") or {}).get("annual_rate_pct"),
            },
        ],
        "disclaimer": DISCLAIMER,
    }


def build_elite(liq: dict[str, Any]) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "definition": {
            "market_dominators": "Empresas que concentram volume, attendance e tese setorial — líderes de liquidez e influência de preço.",
            "elite": "Subconjunto com histórico de qualidade (margem, ROE, dividendos consistentes ou moat) — não é tip de compra.",
        },
        "filters_educational": [
            "Liquidez diária suficiente (evitar papel ilíquido)",
            "Participação relevante no índice ou no setor",
            "Governança e divulgação transparentes",
            "Histórico longo o bastante para estudar ciclos",
        ],
        "b3_watch": liq.get("elite") or [],
        "us_watch": [],
        "source": liq.get("source"),
        "note": "Lista inicial via Yahoo (.SA). Ordenada por volume da última sessão.",
        "disclaimer": DISCLAIMER,
    }


def build_liquidity(liq: dict[str, Any]) -> dict[str, Any]:
    thr = liq.get("gap_threshold_pct", 2.0)
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "rule": "Avaliar liquidez antes de qualquer ideias de operação. Sem liquidez, o passado e a notícia não salvam a saída.",
        "do_not_operate_when": [
            "Spread amplo / livro fino",
            "Volume atípico sem contexto",
            "Papel fora do radar de elite/líderes sem tese clara",
            "Gap ou explosão sem lastro de fluxo",
        ],
        "premarket": {
            "example_threshold_pct": thr,
            "interpretation": "Explosões de ~2% no gap de abertura vs fechamento anterior são um sinal de atenção (fluxo/notícia) — não um gatilho automático de compra/venda. Em B3 usamos gap de abertura como proxy educativo do pré-leilão.",
            "checklist": [
                "Há notícia verificável?",
                "O volume relativo confirma interesse?",
                "O papel é líquido o bastante no pregão regular?",
                "Isso altera o custo de oportunidade vs Selic/caixa?",
            ],
        },
        "watch": liq.get("gap_attention") or [],
        "source": liq.get("source"),
        "disclaimer": DISCLAIMER,
    }


def build_dividends_radar(liq: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for e in liq.get("elite") or []:
        if e.get("dividend_yield_pct") is None:
            continue
        rows.append(
            {
                "ticker": e.get("ticker"),
                "dividend_yield_pct": e.get("dividend_yield_pct"),
                "last": e.get("last"),
                "as_of": e.get("as_of"),
                "source": "yahoo_fast_info",
            }
        )
    rows = sorted(rows, key=lambda x: x.get("dividend_yield_pct") or 0, reverse=True)
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "source_layer": "market",
        "source_note": "DY via Yahoo (quando disponível). Agenda Status Invest entra depois com export autorizado.",
        "top_yield": rows,
        "upcoming_payments": [],
        "status": "live_partial",
    }


def build_analogs(official: dict[str, Any]) -> dict[str, Any]:
    selic = official["selic"]["annual_rate_pct"]
    regime = "Selic elevada" if selic >= 10 else "Selic moderada/baixa"
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live_seed",
        "thesis": "Mercados rimam: regimes de juro, liquidez e narrativas se repetem com variações. Estudar o passado não prevê o futuro — reduz surpresa.",
        "method": [
            "Isolar o regime (Selic alta/baixa, dólar, risco global)",
            "Mapear o comportamento de preços e volumes na época análoga",
            "Espelhar com notícias e fluxo de hoje (sem forçar narrativa)",
            "Perguntar: o que foi liquidez vs o que foi thesis?",
        ],
        "analogs": [
            {
                "id": "current_selic_regime",
                "title": f"Regime atual — {regime}",
                "selic_annual_rate_pct": selic,
                "note": "Ponto de partida automático do collector. Completar com janelas históricas manuais/API.",
            }
        ],
        "note": "Cada analogia deve citar janela histórica, ativos observados e diferenças críticas vs hoje.",
        "disclaimer": "Conteúdo educacional. Analogia ≠ previsão.",
    }


def build_tickers_catalog(liq: dict[str, Any]) -> dict[str, Any]:
    tickers = []
    for e in liq.get("elite") or []:
        if not e.get("ticker"):
            continue
        tickers.append(
            {
                "ticker": e["ticker"],
                "symbol": e.get("symbol"),
                "type": "acao",
                "market": "B3",
                "last": e.get("last"),
                "volume": e.get("volume"),
            }
        )
    return {
        "version": 1,
        "status": "live",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
    }


def main() -> int:
    print("Divmetric collector: fetching BCB…")
    official = fetch_official_rates()
    print(
        f"  Selic={official['selic']['annual_rate_pct']}% ({official['selic']['as_of']}) "
        f"IPCA12m={official['ipca']['annual_rate_pct']}% ({official['ipca']['as_of']})"
    )

    print("Divmetric collector: fetching market benchmarks…")
    prev_bench = load_json("benchmarks.json")
    market = merge_market_preserve(prev_bench, fetch_benchmark_market())
    print(f"  market ok_count={market.get('ok_count')} errors={len(market.get('errors') or [])}")

    print("Divmetric collector: fetching B3 liquidity/elite…")
    prev_elite = load_json("elite_stocks.json")
    prev_liq = load_json("liquidity_watch.json")
    liq = merge_liq_preserve(prev_elite, prev_liq, fetch_b3_liquidity_and_elite(gap_threshold_pct=2.0))
    print(f"  elite ok_count={liq.get('ok_count')} gaps={len(liq.get('gap_attention') or [])}")

    benchmarks = build_benchmarks(official, market)
    write_json("benchmarks.json", benchmarks)
    write_json("history_monthly.json", build_history_monthly(market))
    write_json("opportunity_cost.json", build_opportunity_cost(official, benchmarks))
    write_json("elite_stocks.json", build_elite(liq))
    write_json("liquidity_watch.json", build_liquidity(liq))
    write_json("dividends_radar.json", build_dividends_radar(liq))
    write_json("historical_analogs.json", build_analogs(official))
    write_json("tickers_catalog.json", build_tickers_catalog(liq))
    write_json(
        "meta.json",
        {
            "product": "Divmetric",
            "version": 2,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": DISCLAIMER,
            "status": "live",
            "layers": {
                "official": "BCB SGS (Selic 432, IPCA 12m 13522)",
                "market": "Yahoo chart API + AwesomeAPI",
                "dividends": "parcial (Status Invest depois)",
                "editorial": "Suno / InfoMoney (links only)",
            },
            "counts": {
                "benchmarks": len(benchmarks.get("items") or []),
                "elite": len(liq.get("elite") or []),
                "gap_attention": len(liq.get("gap_attention") or []),
            },
        },
    )
    # Keep world_frameworks as editorial seed (no live API)
    world_path = DATA / "world_frameworks.json"
    if world_path.exists():
        world = json.loads(world_path.read_text(encoding="utf-8"))
        world["as_of"] = datetime.now(timezone.utc).date().isoformat()
        world["status"] = "editorial_live_stamp"
        write_json("world_frameworks.json", world)

    print("Divmetric collector: export OK → docs/data/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
