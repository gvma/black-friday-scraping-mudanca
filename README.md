# Preços da mudança — Black Friday

Acompanha preços de ar-condicionado (×2), robô aspirador, lava-louças, ventilador de teto e TV 65"
usando o [Zoom](https://www.zoom.com.br), que agrega Amazon, Magalu, Casas Bahia, Americanas,
Fast Shop, Mercado Livre e outras. Só usa Python 3 padrão + `curl`.

## Uso

```bash
python3 tracker.py              # coleta (~2 min), salva, exporta CSVs e gera relatorio.html
python3 tracker.py --only ar    # só uma categoria: ar | robo | louca | ventilador | tv
python3 tracker.py --dry-run    # mostra qual produto cada item encontra (para testar a watchlist)
python3 tracker.py --report     # só regenera CSVs + relatório a partir do banco
open relatorio.html
```

## Coleta automática (GitHub Actions)

O workflow `.github/workflows/coleta.yml` roda a cada 4 horas na nuvem do GitHub (Mac pode estar
desligado), coleta, e faz commit de `dados/` e `relatorio.html` de volta no repositório.
Depois de 28/11/2026 ele não coleta mais (desative em Actions → Coleta de preços → Disable).

- **Ver o resumo da última coleta:** aba *Actions* → última execução → *Summary*.
- **Rodar agora:** aba *Actions* → *Coleta de preços* → *Run workflow*.
- **Ver localmente:** `git pull` e `open relatorio.html`.
- **Site (GitHub Pages):** cada coleta também publica `https://gvma.github.io/black-friday-scraping-mudanca/`,
  com o relatório atual, a página *Todas as coletas* (total da cesta ao longo do tempo) e um relatório
  por coleta. Requer repositório público e *Settings → Pages → Source: GitHub Actions*.
  Para gerar o site localmente: `python3 tracker.py --report --site _site`.

Só considera aparelhos 220 V (descarta anúncios marcados 110/127 V).

## Arquivos

| Arquivo | O que é |
|---|---|
| `watchlist.py` | Produtos acompanhados, nota de qualidade e dicas — edite aqui |
| `dados/precos.db` | SQLite com todas as coletas (fonte da verdade) |
| `dados/resumo_atual.csv` | Último preço de cada produto + custo-benefício e veredito |
| `dados/coletas.csv` | Todas as coletas (uma linha por produto por execução) |
| `dados/ofertas.csv` | Preço em cada loja, por coleta |
| `dados/historico.csv` | Preço diário (40 dias do Zoom + o que for acumulando) |
| `relatorio.html` | Página com cesta sugerida, tabelas e mini-gráficos |

CSVs usam `;` e UTF-8 com BOM — abrem direto no Excel; no Google Sheets, importe com separador `;`.

## Como ler

- **Custo-benefício**: qualidade² ÷ preço, normalizado para 100 no melhor da categoria.
  A qualidade (1–5) é um julgamento editável em `watchlist.py`.
- **Momento**: compara o preço atual com os últimos 40 dias.
  "acima do normal — espere" é o sinal clássico de "metade do dobro".
