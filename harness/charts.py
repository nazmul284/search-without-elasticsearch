"""Quality vs latency, both datasets, 'any word' mode. usage: uv run --with matplotlib python charts.py <out.png>"""
import json, sys
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
R = Path(__file__).resolve().parent.parent / "results"
BEIR_BM25 = {"scifact": 0.665, "fiqa": 0.236}         # Thakur et al. 2021, Table 2 (Anserini/Lucene BM25)
COL = {"Postgres": "#2563eb", "SQLite FTS5": "#0f766e", "DuckDB FTS": "#c2410c", "Tantivy": "#7c3aed"}
fig, axes = plt.subplots(1, 2, figsize=(10, 5.2), dpi=200)
for ax, ds, title in zip(axes, ("scifact", "fiqa"), ("SciFact: 5,183 docs, 300 queries", "FiQA: 57,638 docs, 648 queries")):
    d = json.loads((R / f"{ds}.json").read_text())
    for e in d["engines"]:
        if e["mode"] != "or": continue
        ax.scatter(e["p50_ms"], e["ndcg10"], s=110, color=COL[e["engine"]], zorder=3, edgecolor="white")
        off = {("scifact", "SQLite FTS5"): (-78, 7), ("scifact", "DuckDB FTS"): (8, -13),
               ("scifact", "Tantivy"): (8, -14)}.get((ds, e["engine"]), (7, -3))
        ax.annotate(e["engine"], (e["p50_ms"], e["ndcg10"]), xytext=off, textcoords="offset points",
                    fontsize=9.5, color=COL[e["engine"]])
    ax.axhline(BEIR_BM25[ds], color="#6b7280", ls=":", lw=1)
    ax.text(190, BEIR_BM25[ds], "BEIR's Lucene BM25 ", fontsize=8, color="#6b7280", ha="right",
            va="top" if ds == "scifact" else "bottom")      # below the line on SciFact, where the labels above crowd it
    ax.set_xscale("log"); ax.set_xlim(0.1, 200)
    ax.set_title(title, fontsize=10.5, color="#1f2328", loc="left")
    ax.set_xlabel("median query latency, ms (log scale)", fontsize=9.5, color="#6b7280")
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ax.tick_params(colors="#6b7280"); ax.grid(color="#eeeeee", zorder=0)
axes[0].set_ylabel("nDCG@10 (higher is better)", fontsize=10, color="#6b7280")
axes[0].set_ylim(0.5, 0.72); axes[1].set_ylim(0.1, 0.28)
fig.text(0.02, 0.96, "Tantivy was the fastest everywhere. Postgres ranked worst everywhere.", fontsize=13.5, weight="bold", color="#1f2328")
fig.text(0.02, 0.915, "'Any word may match' mode, each engine with its own English stemming; dotted line = the BEIR paper's BM25 baseline",
         fontsize=9.5, color="#6b7280")
fig.text(0.02, 0.012, "Apple M2 · Postgres 16.15, SQLite 3.53.1, DuckDB 1.5.6, Tantivy 0.26.2 · github.com/nazmul284/search-without-elasticsearch",
         fontsize=6.6, color="#6b7280")
fig.subplots_adjust(left=0.08, right=0.98, top=0.83, bottom=0.14, wspace=0.22)
fig.savefig(sys.argv[1], facecolor="white"); print("ok")
