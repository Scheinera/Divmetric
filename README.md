# Divmetric

Marca irmã da **Velumetric**, focada em **dividendos**, rendimento e projeções comparadas (Selic, BTC, ouro, DXY, índices).

## URLs

- Cloudflare Pages: https://divmetric.pages.dev/
- GitHub Pages: https://scheinera.github.io/Divmetric/ (workflow)
- Repo: https://github.com/Scheinera/Divmetric

## Deploy

Publicação Cloudflare via hub na Velumetric (`deploy-divmetric-pages.yml`), disparada por:
- push em `docs/**` neste repo (dispatch)
- cron diário no hub
- `workflow_dispatch`

```bash
gh workflow run deploy-divmetric-pages.yml --repo Scheinera/Velumetric
```

Preview local:

```bash
npx wrangler pages dev docs --port 8788
```

## Rotina / agenda

- `Divmetric_Daily_Collect` @ 05:45 — atualiza `docs/data` (collector; sem `pip` diário)
- `GitHub_Daily_Publish` @ 23:00 — roda o collector de novo e faz commit/push se houver mudança
- Hub Cloudflare — republica Pages após push (e cron/dispatch no Velumetric)

Conteúdo educacional. Não é recomendação de investimento.
