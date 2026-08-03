# Divmetric — modelagem de dados

Marca irmã da [Velumetric](https://velumetric.pages.dev/) (cripto).  
Divmetric = **dividendos, renda e projeção em reais** — produto e schema separados.

## Princípio

Separar três camadas:

1. **Oficial / API** → números canônicos (histórico + benchmarks)
2. **Mercado consolidado** → yields, agenda, ranking (cópia diária no nosso banco)
3. **Editorial** → educação e contexto (links/citações, não ledger)

O site consome apenas **nossos JSON** em `docs/data/` (mínimo processamento no browser).

## Fontes

| Camada | Fonte | Papel |
|--------|--------|--------|
| Macro oficial | BCB SGS (Selic, IPCA…) | Referência da calculadora |
| Mercado | BRAPI / Yahoo / provedor B3 | Preços e índices (Ibov, S&P), ouro, BTC, DXY |
| Dividendos BR | Status Invest (export/API autorizada — **sem scrape agressivo**) | DY, agenda, FII, ranking |
| Editorial | Suno, InfoMoney | Guias e notícias; citação + link |

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
2. Collector BCB + benchmarks
3. Radar dividendos (import consolidado)
4. Deploy Pages + link na Velumetric
