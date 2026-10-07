"""Build each engine on a BEIR dataset, run every test query, score against the qrels.
usage: python bench.py <dataset> <out.json>    (dataset: scifact | fiqa)"""
import json, math, statistics as st, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engines import Postgres, SQLite, DuckDB, Tantivy

ROOT = Path(__file__).resolve().parent.parent
ds = sys.argv[1]; D = ROOT / "data" / ds; W = ROOT / "data" / "work"; W.mkdir(exist_ok=True)
docs = [json.loads(l) for l in (D / "corpus.jsonl").open()]
queries = {j["_id"]: j["text"] for j in map(json.loads, (D / "queries.jsonl").open())}
qrels = {}
for line in list((D / "qrels" / "test.tsv").open())[1:]:
    q, d, s = line.rstrip("\n").split("\t")
    if int(s) > 0:
        qrels.setdefault(q, {})[d] = int(s)
qs = [q for q in qrels if q in queries]

def ndcg10(ranked, rel):
    dcg = sum(rel.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    return dcg / sum(g / math.log2(i + 2) for i, g in enumerate(ideal))

def recall100(ranked, rel):
    return len(set(ranked[:100]) & set(rel)) / len(rel)

engines = [Postgres("and"), Postgres("or"), SQLite("and", str(W / f"{ds}.sqlite")), SQLite("or", str(W / f"{ds}.sqlite")),
           DuckDB("and", str(W / f"{ds}.duckdb")), DuckDB("or", str(W / f"{ds}.duckdb")),
           Tantivy("and", str(W / f"{ds}.tantivy")), Tantivy("or", str(W / f"{ds}.tantivy"))]
out = {"dataset": ds, "docs": len(docs), "queries": len(qs), "engines": []}
built = {}
for e in engines:
    if e.name not in built:                       # build once per engine; both modes share the index
        built[e.name] = e.build(docs)
        shared = e
    else:
        for attr in ("c", "index", "searcher", "schema"):
            if hasattr(shared, attr):
                setattr(e, attr, getattr(shared, attr))
    build_s, size = built[e.name]
    for q in qs[:20]:                              # warm-up
        e.search(queries[q])
    lat, nd, rc, empty = [], [], [], 0
    for q in qs:
        t0 = time.perf_counter(); r = e.search(queries[q]); lat.append(time.perf_counter() - t0)
        nd.append(ndcg10(r, qrels[q])); rc.append(recall100(r, qrels[q])); empty += not r
    lat.sort()
    rec = {"engine": e.name, "mode": e.mode, "build_s": round(build_s, 2), "index_mb": round(size / 2**20, 1),
           "ndcg10": round(st.mean(nd), 4), "recall100": round(st.mean(rc), 4), "empty_results": empty,
           "p50_ms": round(1000 * lat[len(lat) // 2], 2), "p95_ms": round(1000 * lat[int(len(lat) * .95)], 2)}
    out["engines"].append(rec); print(json.dumps(rec), flush=True)
Path(sys.argv[2]).write_text(json.dumps(out, indent=1))
