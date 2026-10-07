"""Fixed-width tables from results/{scifact,fiqa}.json."""
import json
from pathlib import Path
R = Path(__file__).resolve().parent.parent / "results"
BEIR = {"scifact": 0.665, "fiqa": 0.236}
for ds, title in (("scifact", "SciFact: 5,183 documents, 300 test queries"), ("fiqa", "FiQA: 57,638 documents, 648 test queries")):
    d = json.loads((R / f"{ds}.json").read_text())
    print(f"{title}, 'any word' mode\n")
    print(f"{'engine':14}{'nDCG@10':>9}{'recall@100':>12}{'p50 ms':>9}{'p95 ms':>9}{'build s':>9}{'MB':>7}")
    print(f"{'-'*13:14}{'-'*7:>9}{'-'*10:>12}{'-'*6:>9}{'-'*6:>9}{'-'*7:>9}{'-'*5:>7}")
    for e in sorted((e for e in d["engines"] if e["mode"] == "or"), key=lambda e: -e["ndcg10"]):
        print(f"{e['engine']:14}{e['ndcg10']:>9.3f}{e['recall100']:>12.3f}{e['p50_ms']:>9.2f}{e['p95_ms']:>9.2f}{e['build_s']:>9.2f}{e['index_mb']:>7.1f}")
    print(f"{'BEIR BM25':14}{BEIR[ds]:>9.3f}   (published Lucene baseline, for reference)")
    print("\n")
print("'All words must match': queries that returned nothing\n")
print(f"{'engine':14}{'SciFact (of 300)':>18}{'FiQA (of 648)':>16}")
print(f"{'-'*13:14}{'-'*16:>18}{'-'*13:>16}")
S, F = (json.loads((R / f"{x}.json").read_text()) for x in ("scifact", "fiqa"))
for name in ("Postgres", "SQLite FTS5", "Tantivy", "DuckDB FTS"):
    a = next(e for e in S["engines"] if e["engine"] == name and e["mode"] == "and")
    b = next(e for e in F["engines"] if e["engine"] == name and e["mode"] == "and")
    print(f"{name:14}{a['empty_results']:>18}{b['empty_results']:>16}")

print("\n")
print("Can configuration fix Postgres? nDCG@10, 'any word' queries\n")
print(f"{'variant':38}{'SciFact':>9}{'FiQA':>8}")
print(f"{'-'*37:38}{'-'*7:>9}{'-'*6:>8}")
TS, TF = (json.loads((R / f"tuning_{x}.json").read_text()) for x in ("scifact", "fiqa"))
for a, b in zip(TS["variants"], TF["variants"]):
    lab = f"{a['engine']}: {a['variant']}".replace("Postgres: ", "Postgres ").replace("SQLite FTS5: ", "SQLite ")
    print(f"{lab:38}{a["ndcg10"]:>9.3f}{b['ndcg10']:>8.3f}")
