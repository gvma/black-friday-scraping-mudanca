#!/usr/bin/env python3
"""Rastreador de preços para a Black Friday (fonte: zoom.com.br).

Uso:
  python3 tracker.py              # coleta tudo, salva no SQLite, exporta CSVs e gera o relatório
  python3 tracker.py --dry-run    # só mostra qual produto cada item da watchlist encontrou
  python3 tracker.py --only ar    # coleta só uma categoria (ar, robo, louca, ventilador)
  python3 tracker.py --report     # só regenera CSVs + relatório a partir do banco

Saídas (na pasta deste arquivo):
  dados/precos.db          banco SQLite (fonte da verdade, acumula todas as coletas)
  dados/*.csv              exportações para Excel / Google Sheets
  relatorio.html           página para abrir no navegador

Só usa a biblioteca padrão do Python; as requisições passam pelo `curl` do sistema.
"""
import argparse
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from statistics import median
from urllib.parse import quote_plus

from watchlist import CATEGORIES, ITEMS

BASE = Path(__file__).resolve().parent
DATA = BASE / "dados"
DB_PATH = DATA / "precos.db"
REPORT = BASE / "relatorio.html"
ZOOM = "https://www.zoom.com.br"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0 Safari/537.36")
SITE = "https://gvma.github.io/black-friday-scraping-mudanca/"
DELAY = 2.0  # segundos entre requisições — educado com o site

# Voltagem da casa: 220 V. Descarta anúncios que dizem só 110/127 V.
WRONG_VOLT = re.compile(r"\b(110|127)\s?v\b", re.I)
OK_VOLT = re.compile(r"220|bivolt", re.I)


def voltage_ok(title):
    return not (WRONG_VOLT.search(title or "") and not OK_VOLT.search(title or ""))


# ----------------------------------------------------------------- coleta
def fetch(url, tries=3):
    for i in range(tries):
        r = subprocess.run(
            ["curl", "-sL", "--compressed", "--max-time", "40", "-A", UA,
             "-H", "Accept-Language: pt-BR,pt;q=0.9", "-w", "\n%{http_code}", url],
            capture_output=True)
        body, _, code = r.stdout.decode("utf-8", "replace").rpartition("\n")
        if r.returncode == 0 and code == "200":
            return body
        time.sleep(DELAY * (i + 2))
    raise RuntimeError(f"falhou ({code or r.returncode}): {url}")


def next_state(html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise RuntimeError("página sem __NEXT_DATA__ (layout mudou ou bloqueio)")
    return json.loads(m.group(1))["props"]["initialReduxState"]


def find_product(item):
    """Busca no Zoom e devolve o hit que casa com o padrão do item."""
    cat = CATEGORIES[item["cat"]]
    st = next_state(fetch(f"{ZOOM}/busca/{quote_plus(item['query'])}"))
    hits = [h for h in st["hits"]["hits"] if h.get("type") == "product"]
    inc = re.compile(item["match"], re.I)
    req = re.compile(cat.get("require", ""), re.I)
    excl = [re.compile(x, re.I) for x in (cat.get("exclude"), item.get("exclude")) if x]
    ok = [h for h in hits if inc.search(h["name"]) and req.search(h["name"])
          and voltage_ok(h["name"]) and not any(e.search(h["name"]) for e in excl)]
    # mais lojas = produto "canônico" com mais ofertas; depois o mais barato
    ok.sort(key=lambda h: (-(h.get("storeCount") or 0), h.get("price") or 1e9))
    return ok[0] if ok else None


def product_details(hit):
    st = next_state(fetch(ZOOM + hit["url"]))
    pid = str(hit["sourceId"])
    offers = [o for o in (st.get("offers", {}).get("displayOffers") or []) if voltage_ok(o.get("name"))]
    days = (st.get("priceHistory", {}).get("priceHistory", {}).get(pid) or {}).get("days") or []
    tip = ((st.get("priceTip", {}).get(pid) or {}).get("priceTip") or {})
    return offers, days, tip


# ----------------------------------------------------------------- banco
SCHEMA = """
CREATE TABLE IF NOT EXISTS coletas (
  coleta_em TEXT, item_id TEXT, categoria TEXT, produto_id TEXT, nome TEXT, url TEXT,
  preco REAL, loja TEXT, preco_parcelado REAL, parcelas INTEGER, n_lojas INTEGER,
  nota REAL, n_avaliacoes INTEGER, min_40d REAL, mediana_40d REAL, max_40d REAL,
  dica_zoom TEXT, erro TEXT,
  PRIMARY KEY (coleta_em, item_id));
CREATE TABLE IF NOT EXISTS ofertas (
  coleta_em TEXT, item_id TEXT, loja TEXT, marketplace INTEGER, preco REAL,
  preco_parcelado REAL, parcelas INTEGER, titulo TEXT);
CREATE TABLE IF NOT EXISTS historico (
  produto_id TEXT, item_id TEXT, data TEXT, preco REAL, loja_id TEXT,
  PRIMARY KEY (produto_id, data));
"""


def db():
    DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.executescript(SCHEMA)
    return con


def collect(con, items, dry_run=False):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    for n, item in enumerate(items, 1):
        print(f"[{n}/{len(items)}] {item['id']:<28}", end=" ", flush=True)
        row = {"coleta_em": now, "item_id": item["id"], "categoria": item["cat"], "erro": None}
        try:
            hit = find_product(item)
            time.sleep(DELAY)
            if not hit:
                raise RuntimeError("nenhum produto casou com o padrão")
            row.update(produto_id=str(hit["sourceId"]), nome=hit["name"], url=ZOOM + hit["url"],
                       nota=hit.get("preciseRating"), n_avaliacoes=hit.get("ratingTotal"),
                       n_lojas=hit.get("storeCount"))
            if dry_run:
                print(f"R$ {hit['price']:>9,.2f}  {hit['name'][:80]}")
                continue
            offers, days, tip = product_details(hit)
            time.sleep(DELAY)
            if offers:
                best = min(offers, key=lambda o: o["price"])
                row.update(preco=best["price"], loja=best["sellerName"],
                           preco_parcelado=best.get("totalPrice") or None,
                           parcelas=best.get("numParcels") or None, n_lojas=len({o["sellerName"] for o in offers}))
            else:
                row.update(preco=hit.get("price"), loja=(hit.get("bestOffer") or {}).get("merchantName"))
            prices = [d["price"] for d in days if d.get("price")]
            if prices:
                row.update(min_40d=round(min(prices), 2), mediana_40d=round(median(prices), 2),
                           max_40d=round(max(prices), 2))
            row["dica_zoom"] = tip.get("description")
            for o in offers:
                con.execute("INSERT INTO ofertas VALUES (?,?,?,?,?,?,?,?)",
                            (now, item["id"], o["sellerName"], int(bool(o.get("sellerIsMarketplace"))),
                             o["price"], o.get("totalPrice") or None, o.get("numParcels") or None, o.get("name")))
            for d in days:
                con.execute("INSERT OR REPLACE INTO historico VALUES (?,?,?,?,?)",
                            (row["produto_id"], item["id"], d["date"], round(d["price"], 2), str(d.get("merchantId"))))
            print(f"R$ {row['preco']:>9,.2f}  ({row.get('loja')})  {row['nome'][:60]}")
        except Exception as e:  # um item com problema não derruba a coleta
            row["erro"] = str(e)[:300]
            print("ERRO:", row["erro"])
        if not dry_run:
            cols = ",".join(row)
            con.execute(f"INSERT OR REPLACE INTO coletas ({cols}) VALUES ({','.join('?' * len(row))})",
                        list(row.values()))
            con.commit()


# ----------------------------------------------------------------- análise
def latest(con, upto=None):
    """Última coleta válida de cada item (até `upto`, se dado) + métricas de custo-benefício."""
    upto = upto or "9999"
    con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""
        SELECT c.* FROM coletas c
        JOIN (SELECT item_id, MAX(coleta_em) m FROM coletas WHERE erro IS NULL AND coleta_em <= ?
              GROUP BY item_id) x
          ON x.item_id = c.item_id AND x.m = c.coleta_em""", (upto,))]
    con.row_factory = None
    meta = {i["id"]: i for i in ITEMS}
    rows = [r for r in rows if r["item_id"] in meta]
    for r in rows:
        it = meta[r["item_id"]]
        r["qualidade"] = it["quality"]
        r["observacao"] = it["note"]
        hist = [p for (p,) in con.execute(
            "SELECT preco FROM historico WHERE produto_id=? AND data <= ? ORDER BY data",
            (r["produto_id"], upto[:10]))]
        r["min_historico"] = round(min(hist), 2) if hist else None
        r["dias_historico"] = len(hist)
        ref = r["mediana_40d"]
        r["vs_mediana_pct"] = round((r["preco"] / ref - 1) * 100, 1) if ref else None
        r["veredito"] = verdict(r)
        r["qtd"] = CATEGORIES[r["categoria"]]["quantity"]
        r["total"] = round(r["preco"] * r["qtd"], 2)
    # custo-benefício: qualidade por real, normalizado 0–100 dentro da categoria
    for cat in CATEGORIES:
        rs = [r for r in rows if r["categoria"] == cat]
        if not rs:
            continue
        raw = {id(r): r["qualidade"] ** 2 / r["preco"] for r in rs}  # qualidade pesa mais que preço
        top = max(raw.values())
        for r in rs:
            r["custo_beneficio"] = round(100 * raw[id(r)] / top)
    rows.sort(key=lambda r: (list(CATEGORIES).index(r["categoria"]), -r["custo_beneficio"]))
    return rows


def verdict(r):
    p, mn, med = r["preco"], r["min_40d"], r["mediana_40d"]
    if not med:
        return "sem histórico"
    if r["max_40d"] - mn <= mn * 0.01:
        return "preço estável"
    if p <= mn * 1.01:
        return "menor preço em 40 dias"
    if p <= med * 0.95:
        return "abaixo do normal"
    if p >= med * 1.05:
        return "acima do normal — espere"
    return "preço normal"


# ----------------------------------------------------------------- exportação
def export_csv(con, rows):
    def dump(name, header, data):
        with open(DATA / name, "w", newline="", encoding="utf-8-sig") as f:  # BOM: acentos certos no Excel
            w = csv.writer(f, delimiter=";")
            w.writerow(header)
            w.writerows(data)

    cols = ["categoria", "item_id", "nome", "preco", "loja", "qtd", "total", "qualidade",
            "custo_beneficio", "veredito", "vs_mediana_pct", "min_40d", "mediana_40d", "max_40d",
            "min_historico", "n_lojas", "nota", "n_avaliacoes", "observacao", "url", "coleta_em"]
    dump("resumo_atual.csv", cols, [[r.get(c) for c in cols] for r in rows])
    for table, fname in [("coletas", "coletas.csv"), ("ofertas", "ofertas.csv"), ("historico", "historico.csv")]:
        cur = con.execute(f"SELECT * FROM {table} ORDER BY 1, 2")
        dump(fname, [d[0] for d in cur.description], cur.fetchall())


def brl(v):
    return "—" if v is None else "R$ " + f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def sparkline(con, pid, upto="9999", w=140, h=34):
    pts = con.execute("SELECT data, preco FROM historico WHERE produto_id=? AND data <= ? ORDER BY data",
                      (pid, upto[:10])).fetchall()
    if len(pts) < 2:
        return ""
    ys = [p for _, p in pts]
    lo, hi = min(ys), max(ys)
    span = (hi - lo) or 1
    coords = " ".join(f"{i * w / (len(ys) - 1):.1f},{h - 3 - (y - lo) / span * (h - 6):.1f}" for i, y in enumerate(ys))
    lx, ly = coords.split()[-1].split(",")
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" '
            f'aria-label="De {brl(ys[0])} a {brl(ys[-1])} em {len(ys)} dias">'
            f'<title>{pts[0][0]} → {pts[-1][0]}: mín {brl(lo)}, máx {brl(hi)}</title>'
            f'<polyline points="{coords}" fill="none" stroke="var(--line)" stroke-width="1.6"/>'
            f'<circle cx="{lx}" cy="{ly}" r="2.6" fill="var(--accent)"/></svg>')


CSS = """:root{--bg:#f7f6f3;--card:#fff;--fg:#1d1d1b;--muted:#6b6a66;--border:#e4e2dc;--accent:#2f6fde;--line:#8a8983;
--good-bg:#e3f3e6;--good:#1f6b33;--bad-bg:#fbe7e4;--bad:#9b2c1e;--top:#eef4ff}
@media (prefers-color-scheme:dark){:root{--bg:#151514;--card:#1f1f1d;--fg:#ecebe7;--muted:#9c9b96;--border:#34332f;
--accent:#6d9bff;--line:#8f8e89;--good-bg:#1c3324;--good:#8fd6a2;--bad-bg:#3a201c;--bad:#f0a196;--top:#1d2638}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.45 -apple-system,system-ui,sans-serif}
main{max-width:1200px;margin:0 auto;padding:24px 16px 64px}h1{margin:0 0 4px;font-size:26px}
h2{font-size:18px;margin:0 0 6px}h2 .muted{font-weight:400;font-size:14px;margin-left:8px}
section,.basket{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px;margin-top:18px}
.muted{color:var(--muted);font-size:12.5px}.small{font-size:12.5px;white-space:nowrap}
.scroll{overflow-x:auto}table{border-collapse:collapse;width:100%;min-width:1050px}td:first-child{min-width:300px}
th{text-align:left;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);padding:6px 8px;border-bottom:1px solid var(--border)}
td{padding:10px 8px;border-bottom:1px solid var(--border);vertical-align:top}tr.top{background:var(--top)}
td.num{white-space:nowrap}a{color:var(--fg);text-decoration-color:var(--border)}a:hover{color:var(--accent)}
.cb{height:7px;background:var(--border);border-radius:4px;width:110px;margin:6px 0 3px}.cb span{display:block;height:100%;background:var(--accent);border-radius:4px}
.badge{display:inline-block;padding:2px 8px;border-radius:99px;font-size:12px;background:var(--border)}
.badge.good{background:var(--good-bg);color:var(--good)}.badge.bad{background:var(--bad-bg);color:var(--bad)}
.tips{margin:4px 0 10px;padding-left:18px;color:var(--muted);font-size:13px}
.basket ul{list-style:none;padding:0;margin:8px 0}.basket li{display:flex;justify-content:space-between;gap:12px;padding:5px 0;border-bottom:1px dashed var(--border)}
.basket .sum{font-size:18px;text-align:right}.warn{color:var(--bad);font-size:13px}
nav{margin:0 0 14px;font-size:14px;display:flex;gap:16px;flex-wrap:wrap}
nav a{color:var(--accent);text-decoration:none}
.runs td,.runs th{white-space:nowrap}.up{color:var(--bad)}.down{color:var(--good)}
"""


def esc(s):
    return (str(s) if s is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace('"', "&quot;")


def basket_of(rows):
    """Cesta sugerida: melhor custo-benefício de cada categoria (rows já vem ordenado)."""
    best = {}
    for r in rows:
        best.setdefault(r["categoria"], r)
    return list(best.values())


def html_report(con, rows, out=REPORT, upto=None, nav=""):
    upto = upto or con.execute("SELECT MAX(coleta_em) FROM coletas").fetchone()[0] or "9999"
    last = max((r["coleta_em"] for r in rows), default="—")
    n_coletas = con.execute("SELECT COUNT(DISTINCT coleta_em) FROM coletas WHERE coleta_em <= ?", (upto,)).fetchone()[0]
    errors = con.execute("SELECT item_id, erro FROM coletas WHERE coleta_em=? AND erro IS NOT NULL", (upto,)).fetchall()

    # cesta sugerida: melhor custo-benefício de cada categoria
    basket, sections = [], []
    for cat, cfg in CATEGORIES.items():
        rs = [r for r in rows if r["categoria"] == cat]
        if not rs:
            continue
        best = rs[0]
        basket.append(best)
        trs = []
        for r in rs:
            offers = con.execute("SELECT loja, preco FROM ofertas WHERE coleta_em=? AND item_id=? ORDER BY preco",
                                 (r["coleta_em"], r["item_id"])).fetchall()
            ofs = "<br>".join(f"{esc(l)}: {brl(p)}" for l, p in offers[:4])
            badge = {"menor preço em 40 dias": "good", "abaixo do normal": "good",
                     "acima do normal — espere": "bad"}.get(r["veredito"], "")
            delta = "" if r["vs_mediana_pct"] is None else f'{r["vs_mediana_pct"]:+.1f}% vs mediana'
            trs.append(f"""<tr{' class="top"' if r is best else ''}>
              <td><a href="{esc(r['url'])}" target="_blank" rel="noopener">{esc(r['nome'])}</a>
                  <div class="muted">{esc(r['observacao'])}</div></td>
              <td class="num"><b>{brl(r['preco'])}</b><div class="muted">{esc(r['loja'])}</div></td>
              <td><div class="cb"><span style="width:{r['custo_beneficio']}%"></span></div>
                  <span class="muted">{r['custo_beneficio']} · qualidade {r['qualidade']}</span></td>
              <td><span class="badge {badge}">{esc(r['veredito'])}</span><div class="muted">{delta}</div></td>
              <td class="num">{brl(r['min_40d'])}<div class="muted">mediana {brl(r['mediana_40d'])}</div></td>
              <td>{sparkline(con, r['produto_id'], upto)}</td>
              <td class="small">{ofs}</td></tr>""")
        tips = "".join(f"<li>{esc(t)}</li>" for t in cfg["tips"])
        qty = f" · precisa de {cfg['quantity']}" if cfg["quantity"] > 1 else ""
        sections.append(f"""<section><h2>{esc(cfg['label'])}<span class="muted">{qty}</span></h2>
          <ul class="tips">{tips}</ul>
          <div class="scroll"><table><thead><tr><th>Produto</th><th>Menor preço agora</th><th>Custo-benefício</th>
          <th>Momento</th><th>Mín. 40 dias</th><th>Histórico</th><th>Lojas</th></tr></thead>
          <tbody>{''.join(trs)}</tbody></table></div></section>""")

    total = sum(r["total"] for r in basket)
    basket_li = "".join(f"<li><span>{esc(CATEGORIES[r['categoria']]['label'].split(' (')[0])}"
                        f"{' ×' + str(r['qtd']) if r['qtd'] > 1 else ''}: {esc(r['nome'][:70])}</span>"
                        f"<b>{brl(r['total'])}</b></li>" for r in basket)
    err_html = ("<p class='warn'>Itens com erro na última coleta: " +
                ", ".join(f"{esc(i)} ({esc(e)})" for i, e in errors) + "</p>") if errors else ""

    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Preços da Mudança</title>
<style>{CSS}</style></head><body><main>
{nav}<h1>Preços da mudança — Black Friday</h1>
<div class="muted">Coleta: {esc(last)} · {n_coletas} coleta(s) no banco · fonte: Zoom (agrega Amazon, Magalu, Casas Bahia, Americanas, Fast Shop e outras)</div>
{err_html}
<div class="basket"><h2>Cesta sugerida (melhor custo-benefício de cada categoria)</h2><ul>{basket_li}</ul>
<div class="sum">Total: <b>{brl(total)}</b></div>
<div class="muted">Custo-benefício = qualidade² ÷ preço, normalizado para 100 no melhor da categoria. A nota de qualidade é um julgamento editável em watchlist.py.
"Momento" compara o preço de agora com os últimos 40 dias — é o que denuncia a "metade do dobro".</div></div>
{''.join(sections)}
</main></body></html>"""
    Path(out).write_text(html, encoding="utf-8")


def page(title, body):
    return (f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<style>{CSS}</style></head><body><main>{body}</main></body></html>')


def build_site(con, outdir):
    """Site estático para o GitHub Pages: última coleta, histórico e um relatório por coleta."""
    outdir = Path(outdir)
    (outdir / "coletas").mkdir(parents=True, exist_ok=True)
    (outdir / "dados").mkdir(exist_ok=True)
    runs = [r for (r,) in con.execute("SELECT DISTINCT coleta_em FROM coletas ORDER BY 1")]
    slug = lambda run: run.replace(" ", "_").replace(":", "")
    summary = []
    for run in runs:
        rows = latest(con, run)
        if not rows:
            continue
        nav = '<nav><a href="../index.html">← Última coleta</a><a href="../historico.html">Todas as coletas</a></nav>'
        html_report(con, rows, outdir / "coletas" / f"{slug(run)}.html", run, nav)
        n, err = con.execute("SELECT SUM(erro IS NULL), SUM(erro IS NOT NULL) FROM coletas WHERE coleta_em=?",
                             (run,)).fetchone()
        good = sum(r["veredito"] in ("menor preço em 40 dias", "abaixo do normal") for r in rows)
        cats = {r["categoria"]: r["total"] for r in basket_of(rows)}
        summary.append((run, n, err, sum(cats.values()), good, cats))
    if summary:
        nav = '<nav><a href="historico.html">Todas as coletas</a><a href="dados/resumo_atual.csv">Baixar CSV</a></nav>'
        html_report(con, latest(con), outdir / "index.html", runs[-1], nav)
    # histórico de coletas
    trs, prev = [], None
    for run, n, err, total, good, cats in summary:
        d = ""
        if prev is not None:  # compara só categorias presentes nas duas coletas
            common = cats.keys() & prev.keys()
            a, b = sum(cats[c] for c in common), sum(prev[c] for c in common)
            d = "=" if abs(a - b) <= 0.5 else f'<span class="{"up" if a > b else "down"}">{(a / b - 1) * 100:+.1f}%</span>'
            new = sorted(cats.keys() - prev.keys())
            if new:
                d += f' <span class="muted">(entrou: {", ".join(new)})</span>'
        trs.append(f'<tr><td><a href="coletas/{slug(run)}.html">{esc(run)}</a></td><td>{n}</td>'
                   f'<td>{err or ""}</td><td><b>{brl(total)}</b></td><td>{d}</td><td>{good}</td></tr>')
        prev = cats
    chart = ""
    if len(summary) > 1:
        ys = [x[3] for x in summary]
        lo, hi = min(ys), max(ys)
        span, w, h = (hi - lo) or 1, 600, 120
        pts = " ".join(f"{i * w / (len(ys) - 1):.1f},{h - 8 - (y - lo) / span * (h - 16):.1f}" for i, y in enumerate(ys))
        chart = (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" preserveAspectRatio="none" role="img" '
                 f'aria-label="Total da cesta de {brl(ys[0])} a {brl(ys[-1])}">'
                 f'<polyline points="{pts}" fill="none" stroke="var(--accent)" stroke-width="2" '
                 f'vector-effect="non-scaling-stroke"/></svg>'
                 f'<div class="muted">mín {brl(lo)} · máx {brl(hi)}</div>')
    body = (f'<nav><a href="index.html">← Última coleta</a><a href="dados/coletas.csv">CSV de todas as coletas</a></nav>'
            f'<h1>Todas as coletas</h1><div class="muted">{len(summary)} coleta(s). A cesta é o melhor '
            f'custo-benefício de cada categoria naquele momento.</div>'
            f'<section><h2>Total da cesta ao longo do tempo</h2>{chart or "<p class=muted>Precisa de 2+ coletas.</p>"}</section>'
            f'<section><div class="scroll"><table class="runs" style="min-width:0"><thead><tr><th>Coleta</th><th>Produtos</th>'
            f'<th>Erros</th><th>Cesta sugerida</th><th>vs anterior</th><th>Em bom momento</th></tr></thead>'
            f'<tbody>{"".join(reversed(trs))}</tbody></table></div></section>')
    (outdir / "historico.html").write_text(page("Todas as coletas", body), encoding="utf-8")
    for f in DATA.glob("*.csv"):
        (outdir / "dados" / f.name).write_bytes(f.read_bytes())
    (outdir / ".nojekyll").write_text("")
    print(f"site em {outdir} ({len(summary)} coletas)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", choices=list(CATEGORIES))
    ap.add_argument("--report", action="store_true", help="não coleta; só regenera CSVs/relatório")
    ap.add_argument("--notify", action="store_true", help="mostra notificação do macOS com os destaques")
    ap.add_argument("--site", metavar="PASTA", help="gera o site estático (GitHub Pages) nesta pasta")
    a = ap.parse_args()
    con = db()
    if not a.report:
        items = [i for i in ITEMS if not a.only or i["cat"] == a.only]
        collect(con, items, a.dry_run)
        if a.dry_run:
            return
    rows = latest(con)
    export_csv(con, rows)
    html_report(con, rows, nav=f'<nav><a href="{SITE}">Site com todas as coletas ↗</a></nav>')
    print(f"\n{len(rows)} produtos · CSVs em {DATA} · relatório em {REPORT}")
    if a.site:
        build_site(con, a.site)
    if a.notify:
        notify(con, rows)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        markdown_summary(con, rows, os.environ["GITHUB_STEP_SUMMARY"])


def highlights(con, rows):
    """Quedas desde a coleta anterior, itens em bom momento e nº de erros."""
    runs = [r for (r,) in con.execute("SELECT DISTINCT coleta_em FROM coletas ORDER BY 1 DESC LIMIT 2")]
    drops = []
    if len(runs) == 2:
        drops = con.execute("""SELECT a.item_id, b.preco, a.preco FROM coletas a JOIN coletas b
            ON a.item_id=b.item_id AND b.coleta_em=? WHERE a.coleta_em=? AND a.preco <= b.preco*0.97""",
                            (runs[1], runs[0])).fetchall()
    good = [r for r in rows if r["veredito"] in ("menor preço em 40 dias", "abaixo do normal")]
    errors = con.execute("SELECT item_id, erro FROM coletas WHERE coleta_em=? AND erro IS NOT NULL",
                         (runs[0],)).fetchall() if runs else []
    return drops, good, errors


def notify(con, rows):
    """Notificação do macOS."""
    drops, good, errors = highlights(con, rows)
    title = f"Preços da mudança: {len(drops)} queda(s), {len(good)} em bom momento"
    body = "; ".join(f"{i} {brl(b)}→{brl(n)}" for i, b, n in drops[:3]) or \
        "; ".join(f"{r['item_id']} {brl(r['preco'])}" for r in good[:3]) or "Nada de especial agora."
    if errors:
        body += f" ({len(errors)} erro(s))"
    q = lambda t: t.replace("\\", "").replace('"', "'")
    subprocess.run(["osascript", "-e", f'display notification "{q(body)}" with title "{q(title)}"'],
                   capture_output=True)


def markdown_summary(con, rows, path):
    """Resumo em Markdown (usado como resumo do job no GitHub Actions)."""
    drops, good, errors = highlights(con, rows)
    basket = {}
    for r in rows:  # rows já vem ordenado por custo-benefício dentro da categoria
        basket.setdefault(r["categoria"], r)
    out = [f"## Preços da mudança — {max((r['coleta_em'] for r in rows), default='')}", "",
           f"**Cesta sugerida:** {brl(sum(r['total'] for r in basket.values()))}", ""]
    if drops:
        out += ["### Quedas desde a coleta anterior (≥ 3%)", ""]
        out += [f"- {i}: {brl(b)} → **{brl(n)}** ({(n / b - 1) * 100:+.1f}%)" for i, b, n in drops]
        out.append("")
    if good:
        out += ["### Em bom momento (vs. últimos 40 dias)", "", "| Produto | Preço | Loja | vs mediana |", "|---|---|---|---|"]
        out += [f"| {r['nome'][:60]} | {brl(r['preco'])} | {r['loja']} | {r['vs_mediana_pct']:+.1f}% |" for r in good]
        out.append("")
    if errors:
        out += ["### Erros", ""] + [f"- {i}: {e}" for i, e in errors]
    Path(path).open("a", encoding="utf-8").write("\n".join(out) + "\n")


if __name__ == "__main__":
    sys.exit(main())
