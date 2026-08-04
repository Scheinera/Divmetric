"""Divmetric collector — janela alinhada desde 2015 + fontes oficiais/mercado ricas."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from modules.connectors.bcb import fetch_official_rates  # noqa: E402
from modules.connectors.market_http import (  # noqa: E402
    fetch_b3_liquidity_and_elite,
    fetch_benchmark_market,
)

DATA = ROOT / "docs" / "data"
CONFIG = ROOT / "config" / "analysis_window.yaml"
DISCLAIMER = "Conteúdo educacional. Não é recomendação de investimento."


def load_window() -> dict[str, Any]:
    defaults = {
        "start_date": "2015-01-01",
        "start_year": 2015,
        "b3_elite": None,
        "market_benchmarks": None,
    }
    if not CONFIG.exists() or yaml is None:
        return defaults
    raw = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    analysis = raw.get("analysis") or {}
    return {
        "start_date": analysis.get("start_date") or defaults["start_date"],
        "start_year": analysis.get("start_year") or defaults["start_year"],
        "rationale": analysis.get("rationale") or "",
        "b3_elite": raw.get("b3_elite"),
        "market_benchmarks": raw.get("market_benchmarks"),
    }


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
    prev_items = {}
    if previous:
        for row in previous.get("items") or []:
            if row.get("id") and row.get("annual_rate_pct") is not None and row.get("source_layer") == "market":
                prev_items[row["id"]] = row
    prev_hist = load_json("history_aligned.json") or {}
    prev_monthly = (prev_hist.get("returns") or {}) or ((load_json("history_monthly.json") or {}).get("series") or {})

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
    if previous_liq and previous_liq.get("status") == "live":
        return {
            "fetched_at": liq.get("fetched_at"),
            "source": liq.get("source"),
            "elite": (previous_elite or {}).get("b3_watch") or [],
            "gap_attention": previous_liq.get("watch") or [],
            "gap_threshold_pct": liq.get("gap_threshold_pct", 2.0),
            "errors": liq.get("errors") or [],
            "ok_count": 0,
            "stale": True,
            "start_date": liq.get("start_date"),
        }
    return liq


def build_benchmarks(official: dict[str, Any], market: dict[str, Any], start_date: str) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    selic = official.get("selic") or {}
    ipca = official.get("ipca") or {}
    cdi = (official.get("series") or {}).get("cdi") or {}

    items.append(
        {
            "id": "selic",
            "label": "Selic",
            "source_layer": "official",
            "annual_rate_pct": selic.get("annual_rate_pct"),
            "unit": selic.get("unit") or "a.a.",
            "description": f"BCB SGS {selic.get('series_code')} · ref {selic.get('as_of')}",
            "as_of": selic.get("as_of"),
        }
    )
    if cdi.get("latest") is not None:
        items.append(
            {
                "id": "cdi",
                "label": "CDI",
                "source_layer": "official",
                "annual_rate_pct": cdi.get("latest"),
                "unit": cdi.get("unit") or "% a.a.",
                "description": f"BCB SGS {cdi.get('series_code')} · ref {cdi.get('as_of')}",
                "as_of": cdi.get("as_of"),
            }
        )
    items.append(
        {
            "id": "ipca",
            "label": "IPCA (12m)",
            "source_layer": "official",
            "annual_rate_pct": ipca.get("annual_rate_pct"),
            "unit": ipca.get("unit") or "%",
            "description": f"BCB SGS {ipca.get('series_code')} · ref {ipca.get('as_of')}",
            "as_of": ipca.get("as_of"),
        }
    )

    for key in ("ibov", "spx", "btc", "gold", "dxy", "usdbrl", "us10y", "ewz"):
        row = (market.get("items") or {}).get(key) or {}
        if row.get("annual_rate_pct") is None and row.get("error"):
            continue
        if not row:
            continue
        items.append(
            {
                "id": key,
                "label": row.get("label") or key,
                "source_layer": "market",
                "annual_rate_pct": row.get("annual_rate_pct"),
                "trailing_12m_pct": row.get("trailing_12m_pct"),
                "cagr_since_start_pct": row.get("cagr_since_start_pct"),
                "unit": row.get("unit") or "retorno",
                "description": row.get("description") or "",
                "as_of": row.get("as_of"),
                "symbol": row.get("symbol"),
                "last_close": row.get("last_close"),
                "start_used": row.get("start_used"),
            }
        )

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "currency": "BRL",
        "analysis_start": start_date,
        "note": (
            f"Séries alinhadas desde {start_date}. "
            "Selic/CDI/IPCA = BCB. Demais = Yahoo chart (CAGR desde a janela + retorno ~12m). Educacional."
        ),
        "items": items,
        "sources": {"official": official.get("source"), "market": market.get("source")},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def build_history_aligned(official: dict[str, Any], market: dict[str, Any], start_date: str) -> dict[str, Any]:
    official_monthly = {}
    for key, series in (official.get("series") or {}).items():
        if series.get("monthly"):
            official_monthly[key] = series["monthly"]

    return {
        "status": "live",
        "analysis_start": start_date,
        "granularity": "monthly",
        "base_index": 100,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "official_levels": official_monthly,
        "market_levels": market.get("monthly_levels") or {},
        "market_indexed_100": market.get("indexed_100") or {},
        "returns": market.get("monthly") or {},
        "note": (
            "Todas as séries de mercado usam nível de fim de mês desde analysis_start. "
            "Índice 100 = primeiro mês disponível na janela (ou primeiro preço do ativo)."
        ),
        "sources": {"official": official.get("source"), "market": market.get("source")},
    }


def build_history_monthly(market: dict[str, Any], start_date: str) -> dict[str, Any]:
    return {
        "granularity": "monthly",
        "status": "live",
        "analysis_start": start_date,
        "note": "Retornos mensais alinhados à janela — uso educacional.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "series": market.get("monthly") or {},
    }


def build_opportunity_cost(official: dict[str, Any], benchmarks: dict[str, Any], start_date: str) -> dict[str, Any]:
    by_id = {i["id"]: i for i in benchmarks.get("items") or []}
    selic = (official.get("selic") or {}).get("annual_rate_pct")
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "analysis_start": start_date,
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
                "metric": "taxa oficial a.a.",
            },
            {
                "id": "spx",
                "label": "S&P 500",
                "certainty": "média",
                "role": "equity mercados desenvolvidos",
                "annual_rate_pct": (by_id.get("spx") or {}).get("trailing_12m_pct"),
                "trailing_12m_pct": (by_id.get("spx") or {}).get("trailing_12m_pct"),
                "cagr_since_start_pct": (by_id.get("spx") or {}).get("cagr_since_start_pct"),
                "metric": "retorno ~12m + CAGR desde janela",
            },
            {
                "id": "elite_equity",
                "label": "Ibovespa / líderes",
                "certainty": "média-baixa",
                "role": "crescimento com liquidez BR",
                "annual_rate_pct": (by_id.get("ibov") or {}).get("trailing_12m_pct"),
                "trailing_12m_pct": (by_id.get("ibov") or {}).get("trailing_12m_pct"),
                "cagr_since_start_pct": (by_id.get("ibov") or {}).get("cagr_since_start_pct"),
                "metric": "retorno ~12m + CAGR desde janela",
            },
            {
                "id": "gold",
                "label": "Ouro",
                "certainty": "média",
                "role": "reserva / hedge",
                "annual_rate_pct": (by_id.get("gold") or {}).get("trailing_12m_pct"),
                "trailing_12m_pct": (by_id.get("gold") or {}).get("trailing_12m_pct"),
                "cagr_since_start_pct": (by_id.get("gold") or {}).get("cagr_since_start_pct"),
                "metric": "retorno ~12m + CAGR desde janela",
            },
            {
                "id": "btc",
                "label": "Bitcoin",
                "certainty": "baixa",
                "role": "opção assimétrica (alta vol)",
                "annual_rate_pct": (by_id.get("btc") or {}).get("trailing_12m_pct"),
                "trailing_12m_pct": (by_id.get("btc") or {}).get("trailing_12m_pct"),
                "cagr_since_start_pct": (by_id.get("btc") or {}).get("cagr_since_start_pct"),
                "metric": "retorno ~12m + CAGR desde janela",
            },
        ],
        "disclaimer": DISCLAIMER,
    }


def build_elite(liq: dict[str, Any], start_date: str) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "analysis_start": start_date,
        "definition": {
            "market_dominators": "Empresas que concentram volume, attendance e tese setorial — líderes de liquidez e influência de preço.",
            "elite": "Subconjunto líquido com histórico desde a janela de análise — não é tip de compra.",
        },
        "filters_educational": [
            "Liquidez diária suficiente",
            "Histórico desde a janela alinhada (2015+)",
            "Governança e divulgação transparentes",
            "Comparar DY e CAGR sem confundir com sinal",
        ],
        "b3_watch": liq.get("elite") or [],
        "us_watch": [],
        "source": liq.get("source"),
        "note": "Ordenado por volume da última sessão; inclui CAGR desde analysis_start quando disponível.",
        "disclaimer": DISCLAIMER,
    }


def build_liquidity(liq: dict[str, Any], start_date: str) -> dict[str, Any]:
    thr = liq.get("gap_threshold_pct", 2.0)
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "analysis_start": start_date,
        "rule": "Avaliar liquidez antes de qualquer ideia de operação. Sem liquidez, o passado e a notícia não salvam a saída.",
        "do_not_operate_when": [
            "Spread amplo / livro fino",
            "Volume atípico sem contexto",
            "Papel fora do radar de elite/líderes sem tese clara",
            "Gap ou explosão sem lastro de fluxo",
        ],
        "premarket": {
            "example_threshold_pct": thr,
            "interpretation": (
                "Explosões de ~2% no gap de abertura vs fechamento anterior são sinal de atenção "
                "(fluxo/notícia) — não gatilho automático. Em B3 usamos gap de abertura como proxy educativo."
            ),
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


def build_dividends_radar(liq: dict[str, Any], start_date: str) -> dict[str, Any]:
    rows = []
    for e in liq.get("elite") or []:
        if e.get("dividend_yield_pct") is None:
            continue
        rows.append(
            {
                "ticker": e.get("ticker"),
                "dividend_yield_pct": e.get("dividend_yield_pct"),
                "last": e.get("last"),
                "cagr_since_start_pct": e.get("cagr_since_start_pct"),
                "trailing_12m_pct": e.get("trailing_12m_pct"),
                "as_of": e.get("as_of"),
                "source": "yahoo_chart_dividends_trailing_12m",
            }
        )
    rows = sorted(rows, key=lambda x: x.get("dividend_yield_pct") or 0, reverse=True)
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "analysis_start": start_date,
        "source_layer": "market",
        "source_note": (
            "DY = soma dos dividendos em dinheiro (eventos Yahoo chart) nos últimos ~365 dias "
            "dividida pelo último preço. Agenda B3/Status Invest pode enriquecer com export autorizado."
        ),
        "top_yield": rows,
        "upcoming_payments": [],
        "status": "live",
    }


def _selic_analogs(official: dict[str, Any], market: dict[str, Any], start_date: str) -> list[dict[str, Any]]:
    selic_now = (official.get("selic") or {}).get("annual_rate_pct")
    monthly = ((official.get("series") or {}).get("selic") or {}).get("monthly") or []
    if selic_now is None or not monthly:
        return []

    # Meses com Selic perto da atual (±1,0 pp)
    near = [m for m in monthly if abs(float(m["value"]) - float(selic_now)) <= 1.0]
    # Agrupar por ano
    by_year: dict[str, list[float]] = {}
    for m in near:
        y = m["month"][:4]
        by_year.setdefault(y, []).append(float(m["value"]))

    ibov_ret = (market.get("monthly") or {}).get("ibov") or []
    ibov_map = {x["month"]: x["return_pct"] for x in ibov_ret}
    spx_map = {x["month"]: x["return_pct"] for x in ((market.get("monthly") or {}).get("spx") or [])}

    analogs = []
    current_year = datetime.now(timezone.utc).strftime("%Y")
    for year, vals in sorted(by_year.items()):
        if year == current_year:
            continue
        # Retorno Ibov/SPX no ano (soma aproximada log-less: compounding monthly)
        months = [f"{year}-{mm:02d}" for mm in range(1, 13)]
        ibov_factor = 1.0
        spx_factor = 1.0
        n_i = n_s = 0
        for mo in months:
            if mo in ibov_map:
                ibov_factor *= 1.0 + float(ibov_map[mo]) / 100.0
                n_i += 1
            if mo in spx_map:
                spx_factor *= 1.0 + float(spx_map[mo]) / 100.0
                n_s += 1
        analogs.append(
            {
                "id": f"selic_near_{year}",
                "title": f"Ano {year}: Selic próxima de {selic_now}%",
                "year": year,
                "selic_avg_near_pct": round(sum(vals) / len(vals), 2),
                "months_matched": len(vals),
                "ibov_year_return_pct": round((ibov_factor - 1.0) * 100.0, 2) if n_i >= 6 else None,
                "spx_year_return_pct": round((spx_factor - 1.0) * 100.0, 2) if n_s >= 6 else None,
                "note": "Analogia de regime de juro — não implica o mesmo resultado à frente.",
            }
        )
    return analogs[-8:]


def build_analogs(official: dict[str, Any], market: dict[str, Any], start_date: str) -> dict[str, Any]:
    selic = (official.get("selic") or {}).get("annual_rate_pct")
    regime = "Selic elevada" if (selic or 0) >= 10 else "Selic moderada/baixa"
    analogs = [
        {
            "id": "current_selic_regime",
            "title": f"Regime atual — {regime}",
            "selic_annual_rate_pct": selic,
            "analysis_start": start_date,
            "note": "Âncora automática; compare com anos em que a Selic esteve em banda semelhante.",
        }
    ]
    analogs.extend(_selic_analogs(official, market, start_date))
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "analysis_start": start_date,
        "thesis": "Mercados rimam: regimes de juro, liquidez e narrativas se repetem com variações. Estudar o passado não prevê o futuro — reduz surpresa.",
        "method": [
            "Isolar o regime (Selic alta/baixa, dólar, risco global)",
            f"Usar a janela alinhada desde {start_date}",
            "Mapear Ibovespa/S&P/ouro/BTC no mesmo período",
            "Espelhar com notícias e fluxo de hoje (sem forçar narrativa)",
            "Liquidez primeiro — analogia sem saída não serve",
        ],
        "analogs": analogs,
        "note": "Gerado a partir de BCB Selic + retornos mensais Yahoo desde a janela.",
        "disclaimer": "Conteúdo educacional. Analogia ≠ previsão.",
    }


def build_world(market: dict[str, Any], official: dict[str, Any], start_date: str) -> dict[str, Any]:
    items = market.get("items") or {}
    selic = (official.get("selic") or {}).get("annual_rate_pct")
    ipca = (official.get("ipca") or {}).get("annual_rate_pct")
    us10y = (items.get("us10y") or {}).get("last_close")

    def snap(key: str) -> dict[str, Any]:
        row = items.get(key) or {}
        return {
            "label": row.get("label"),
            "trailing_12m_pct": row.get("trailing_12m_pct"),
            "cagr_since_start_pct": row.get("cagr_since_start_pct"),
            "as_of": row.get("as_of"),
            "start_used": row.get("start_used"),
        }

    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "status": "live",
        "analysis_start": start_date,
        "question": "Como economias mais prósperas tratam certeza, dividendos, liquidez e custo de oportunidade?",
        "themes": [
            {
                "id": "certainty",
                "title": "Busca de certeza",
                "summary": (
                    f"No Brasil a âncora atual é Selic ~{selic}% a.a. (IPCA 12m ~{ipca}%). "
                    f"Nos EUA, o yield de 10 anos (~{us10y}% se disponível) é referência de custo de oportunidade em USD."
                ),
            },
            {
                "id": "dividends",
                "title": "Dividendos e total return",
                "summary": "Mercados maduros olham total shareholder return (dividendos + recompra + preço). DY isolado sem liquidez é armadilha.",
            },
            {
                "id": "liquidity",
                "title": "Liquidez primeiro",
                "summary": "Institucionais evitam ativos em que não conseguem entrar/sair sem mover o preço — princípio universal.",
            },
            {
                "id": "opportunity_cost",
                "title": "Custo de oportunidade",
                "summary": (
                    f"Desde {start_date}, compare CAGR de S&P 500, Ibovespa, ouro e BTC contra a Selic — "
                    "o prêmio de risco precisa compensar a incerteza."
                ),
            },
        ],
        "snapshots": {
            "brazil_selic": selic,
            "brazil_ipca_12m": ipca,
            "spx": snap("spx"),
            "ibov": snap("ibov"),
            "ewz": snap("ewz"),
            "gold": snap("gold"),
            "btc": snap("btc"),
            "dxy": snap("dxy"),
            "us10y": snap("us10y"),
        },
        "regions": [
            {
                "id": "us",
                "label": "Estados Unidos",
                "notes": [
                    "S&P 500 como proxy de equity desenvolvida",
                    "US 10Y como âncora de juro longo em USD",
                ],
            },
            {
                "id": "br",
                "label": "Brasil",
                "notes": [
                    "Selic/CDI/IPCA (BCB) como âncoras locais",
                    "Ibovespa + EWZ para preço e acesso internacional",
                ],
            },
            {
                "id": "global_hard",
                "label": "Reservas globais",
                "notes": [
                    "Ouro e DXY como leituras de risco/âncora",
                    "BTC como ativo assimétrico (alta vol) na mesma janela",
                ],
            },
        ],
        "disclaimer": DISCLAIMER,
    }


def build_tickers_catalog(liq: dict[str, Any], start_date: str) -> dict[str, Any]:
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
                "dividend_yield_pct": e.get("dividend_yield_pct"),
                "cagr_since_start_pct": e.get("cagr_since_start_pct"),
                "start_used": e.get("start_used"),
            }
        )
    return {
        "version": 2,
        "status": "live",
        "analysis_start": start_date,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "tickers": tickers,
    }


def build_sources_registry(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "analysis_start": window["start_date"],
        "trust_order": [
            "BCB SGS (canônico BR)",
            "Yahoo Finance chart diário + eventos de dividendos",
            "AwesomeAPI (FX fallback)",
            "Editorial (Suno / InfoMoney / B3 educacionais)",
        ],
        "sources": [
            {
                "id": "bcb",
                "name": "Banco Central do Brasil — SGS",
                "trust": "canonical",
                "url": "https://dadosabertos.bcb.gov.br/",
                "fields": ["Selic (432)", "CDI (12)", "IPCA 12m (13522)", "IPCA m (433)", "IGP-M (28655)", "PTAX (1)"],
                "note": "Séries oficiais em chunks ≤10 anos; janela alinhada desde analysis_start.",
            },
            {
                "id": "yahoo",
                "name": "Yahoo Finance chart API",
                "trust": "operational",
                "url": "https://finance.yahoo.com/",
                "fields": ["Ibov", "S&P 500", "BTC", "Ouro", "DXY", "USD/BRL", "US 10Y", "EWZ", "B3 elite", "DY cash events"],
                "note": "period1/period2 + interval=1d (evita downsample de range=max). DY = eventos div trailing 12m.",
            },
            {
                "id": "awesomeapi",
                "name": "AwesomeAPI",
                "trust": "operational",
                "url": "https://docs.awesomeapi.com.br/",
                "fields": ["USD-BRL fallback"],
            },
            {
                "id": "b3",
                "name": "B3 — educacionais / listados",
                "trust": "reference",
                "url": "https://www.b3.com.br/",
                "fields": ["contexto de listagem e liquidez"],
                "note": "Referência de mercado; números do site vêm do collector, não de scrape agressivo.",
            },
            {
                "id": "status_invest",
                "name": "Status Invest",
                "trust": "consolidated_ui",
                "url": "https://statusinvest.com.br/",
                "fields": ["DY consolidado", "agenda", "FII"],
                "note": "Preferir export/API autorizada; não é fonte canônica do MVP.",
            },
            {
                "id": "suno",
                "name": "Suno",
                "trust": "editorial",
                "url": "https://www.suno.com.br/guias/dividendos/",
            },
            {
                "id": "infomoney",
                "name": "InfoMoney",
                "trust": "editorial",
                "url": "https://www.infomoney.com.br/",
            },
        ],
        "rationale": window.get("rationale") or "",
        "disclaimer": DISCLAIMER,
    }


def main() -> int:
    window = load_window()
    start_date = window["start_date"]
    print(f"Divmetric collector: analysis window from {start_date}")

    print("  fetching BCB bundle…")
    official = fetch_official_rates(start_date=start_date)
    print(
        f"  Selic={official['selic']['annual_rate_pct']}% ({official['selic']['as_of']}) "
        f"IPCA12m={official['ipca']['annual_rate_pct']}% ({official['ipca']['as_of']}) "
        f"series_ok={len([k for k,v in (official.get('series') or {}).items() if v.get('latest') is not None])}"
    )

    print("  fetching market benchmarks…")
    prev_bench = load_json("benchmarks.json")
    market = merge_market_preserve(
        prev_bench,
        fetch_benchmark_market(start_date=start_date, benchmarks=window.get("market_benchmarks")),
    )
    print(f"  market ok_count={market.get('ok_count')} errors={len(market.get('errors') or [])}")

    print("  fetching B3 elite/liquidity…")
    prev_elite = load_json("elite_stocks.json")
    prev_liq = load_json("liquidity_watch.json")
    liq = merge_liq_preserve(
        prev_elite,
        prev_liq,
        fetch_b3_liquidity_and_elite(
            gap_threshold_pct=2.0,
            tickers=window.get("b3_elite"),
            start_date=start_date,
        ),
    )
    print(f"  elite ok_count={liq.get('ok_count')} gaps={len(liq.get('gap_attention') or [])}")

    benchmarks = build_benchmarks(official, market, start_date)
    aligned = build_history_aligned(official, market, start_date)

    write_json("benchmarks.json", benchmarks)
    write_json("history_aligned.json", aligned)
    write_json("history_monthly.json", build_history_monthly(market, start_date))
    write_json("opportunity_cost.json", build_opportunity_cost(official, benchmarks, start_date))
    write_json("elite_stocks.json", build_elite(liq, start_date))
    write_json("liquidity_watch.json", build_liquidity(liq, start_date))
    write_json("dividends_radar.json", build_dividends_radar(liq, start_date))
    write_json("historical_analogs.json", build_analogs(official, market, start_date))
    write_json("world_frameworks.json", build_world(market, official, start_date))
    write_json("tickers_catalog.json", build_tickers_catalog(liq, start_date))
    write_json("sources_registry.json", build_sources_registry(window))
    write_json("official_macro.json", {
        "as_of": datetime.now(timezone.utc).date().isoformat(),
        "analysis_start": start_date,
        "source": official.get("source"),
        "series": official.get("series") or {},
        "errors": official.get("errors") or [],
        "disclaimer": DISCLAIMER,
    })
    write_json(
        "meta.json",
        {
            "product": "Divmetric",
            "version": 3,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "disclaimer": DISCLAIMER,
            "status": "live",
            "analysis_start": start_date,
            "analysis_year": window.get("start_year"),
            "layers": {
                "official": "BCB SGS (Selic, CDI, IPCA, IGP-M, PTAX)",
                "market": "Yahoo chart diário (period1/2) + eventos DY + AwesomeAPI",
                "aligned_history": f"monthly from {start_date}",
                "editorial": "Suno / InfoMoney / B3 referência",
            },
            "counts": {
                "benchmarks": len(benchmarks.get("items") or []),
                "elite": len(liq.get("elite") or []),
                "gap_attention": len(liq.get("gap_attention") or []),
                "analog_years": max(0, len((build_analogs(official, market, start_date).get("analogs") or [])) - 1),
                "dividend_rows": len([e for e in (liq.get("elite") or []) if e.get("dividend_yield_pct") is not None]),
            },
        },
    )

    print("Divmetric collector: export OK → docs/data/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
