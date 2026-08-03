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

- `Divmetric_Daily_Collect` @ 05:45 — atualiza `docs/data` (collector)
- `GitHub_Daily_Publish` — já inclui este repo (commit/push diário)
- Hub cron 09:15 UTC — republica no Cloudflare Pages

Conteúdo educacional. Não é recomendação de investimento.
