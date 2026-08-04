# Divmetric — modelagem de dados

Marca irmã da [Velumetric](https://velumetric.pages.dev/) (cripto).  
Divmetric = **dividendos, renda, método e liquidez** — produto e schema separados da Velumetric (cripto).

## Princípio

Separar três camadas:

1. **Oficial / API** → números canônicos (histórico + benchmarks)
2. **Mercado consolidado** → yields, agenda, ranking, liquidez/pré-market (cópia diária)
3. **Editorial / método** → custo de oportunidade, elite, analogias, economias prósperas

O site consome apenas **nossos JSON** em `docs/data/` (mínimo processamento no browser).

## Pilares de produto (MVP editorial)

| Pilar | Página | Dados |
|-------|--------|-------|
| Custo de oportunidade | `/metodo/#oportunidade` | `opportunity_cost.json` |
| Ações dominantes / elite | `/metodo/#elite` | `elite_stocks.json` |
| Certeza mensurável | `/metodo/#certeza` | (texto + âncora Selic) |
| Histórico × hoje | `/metodo/#analogias` | `historical_analogs.json` |
| Liquidez / não operar | `/liquidez/` | `liquidity_watch.json` (ex.: pré-market ~2%) |
| Economias prósperas | `/mundo/` | `world_frameworks.json` |

**Regra de ouro:** liquidez primeiro. Explosões de ~2% no pré-market são *sinal de atenção* (fluxo/notícia), não ordem automática.

## Janela de análise

**Início alinhado: `2015-01-01`** (`config/analysis_window.yaml`).  
Todas as séries oficiais e de mercado, analogias Selic×anos, CAGR e índices 100 usam essa âncora (ou o primeiro preço disponível do ativo).

## Fontes

| Camada | Fonte | Papel |
|--------|--------|--------|
| Macro oficial | BCB SGS (Selic, CDI, IPCA, IGP-M, PTAX) | Canônico BR — calculadora e custo de oportunidade |
| IFIX oficial | **B3** `indexStatisticsProxy` (mensal/anual) + carteira do dia | Benchmark canônico de FIIs desde 2015 |
| Mercado | Yahoo chart **diário** (`period1`/`period2`) + AwesomeAPI | Ibov, S&P, BTC, ouro, DXY, USD/BRL, US10Y, EWZ, B3 |
| Dividendos / FIIs individuais | Eventos `div` do Yahoo | Radar DY/TSR; cesta FII complementar ao IFIX |
| Referência | B3 | Contexto de listagem/liquidez |
| Editorial | Suno, InfoMoney | Guias e notícias; citação + link |

### Roadmap de enriquecimento (próximas fontes)

| Tema | Fonte preferida | Status |
|------|-----------------|--------|
| Minério de ferro | Yahoo `TIO=F` / Fastmarkets proxy | Pendente |
| Dow Jones | Yahoo `^DJI` | Pendente (S&P já no ar) |
| Bolsas mundiais | Yahoo `^N225`, `^GDAXI`, `^FTSE`, `^HSI`… | Pendente |
| Brent / WTI | Yahoo `BZ=F`, `CL=F` | Pendente |
| Juros países | FRED (DGS10 etc.) + BCB / banks sites | Pendente (US10Y já proxy Yahoo) |
| COPOM | BCB agenda + atas (HTML/RSS) | Pendente |
| Notícias / agenda / balanços | RSS InfoMoney/Valor + calendar B3/earnings | Pendente (editorial leve; digest estilo Velumetric) |

## Pipelines (alvo)

```
collector (Python, cron)
  → store/ (SQLite/Postgres ou parquet local)
  → export docs/data/*.json
  → Cloudflare Pages
```

### Arquivos exportados (contrato do site)

| Arquivo | Conteúdo |
|---------|----------|
| `meta.json` | versão, `updated_at`, disclaimer |
| `benchmarks.json` | séries/resumo Selic, IPCA, BTC, ouro, DXY, Ibovespa… |
| `dividends_radar.json` | top yields + próximos pagamentos (cópia consolidada) |
| `tickers_catalog.json` | cadastro ticker/setor/tipo (ação, FII) |
| `history_monthly.json` | retornos mensais agregados para projeções |
| `opportunity_cost.json` | âncoras de custo de oportunidade |
| `elite_stocks.json` | filtros e listas de líderes/elite |
| `historical_analogs.json` | método + analogias regime passado×hoje |
| `liquidity_watch.json` | regras de liquidez + pré-market |
| `world_frameworks.json` | comparativo economias prósperas |

## Calculadora

Entrada: aporte, prazo (meses), aporte mensal opcional.  
Saída: projeção ilustrativa vs benchmarks (Selic / BTC / ouro / Ibov / DXY proxy).  
**Educacional** — não é recomendação nem backtest certificado.

## Fronteira com Velumetric

| Velumetric | Divmetric |
|------------|-----------|
| Cripto, score, digest, setups | Dividendos, DY, FIIs, projeção vs Selic |
| Schema próprio | Schema próprio |
| Login produto cripto | (futuro) login/assinatura Divmetric |

Link cruzado no footer/nav apenas — **sem misturar payloads**.

## Roadmap curto

1. Scaffold Pages + data contract + calculadora stub ✅
2. Pilares Método / Liquidez / Mundo ✅
3. Collector BCB + benchmarks + liquidez/pré-market
4. Preencher elite_stocks e analogias com histórico real
5. Radar dividendos (import consolidado)
