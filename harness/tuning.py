"""Can configuration fix Postgres's ranking? 'Any word' queries only. Writes results/tuning_<ds>.json.
Variants: ts_rank (baseline), ts_rank normalised by document length (flag 1), ts_rank_cd,
and the 'simple' text search configuration (no stemming, no stopwords). Plus SQLite FTS5
without the Porter stemmer, for scale."""
import json, math, sqlite3, statistics as st, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engines import terms
import psycopg

ROOT = Path(__file__).resolve().parent.parent
ds = sys.argv[1]; D = ROOT / "data" / ds
docs = [json.loads(l) for l in (D / "corpus.jsonl").open()]
queries = {j["_id"]: j["text"] for j in map(json.loads, (D / "queries.jsonl").open())}
qrels = {}
for line in list((D / "qrels" / "test.tsv").open())[1:]:
    q, d, s = line.rstrip("\n").split("\t")
    if int(s) > 0: qrels.setdefault(q, {})[d] = int(s)
qs = [q for q in qrels if q in queries]
def ndcg10(r, rel):
    dcg = sum(rel.get(d, 0) / math.log2(i + 2) for i, d in enumerate(r[:10]))
    ideal = sorted(rel.values(), reverse=True)[:10]
    return dcg / sum(g / math.log2(i + 2) for i, g in enumerate(ideal))

c = psycopg.connect("host=localhost port=5499 user=bench dbname=search", autocommit=True)
c.execute("drop table if exists docs2")
c.execute("""create table docs2 (id text primary key, title text, body text,
  tsv_en tsvector generated always as (setweight(to_tsvector('english', coalesce(title,'')),'A') || setweight(to_tsvector('english', coalesce(body,'')),'B')) stored,
  tsv_simple tsvector generated always as (setweight(to_tsvector('simple', coalesce(title,'')),'A') || setweight(to_tsvector('simple', coalesce(body,'')),'B')) stored)""")
with c.cursor() as cur, cur.copy("copy docs2 (id, title, body) from stdin") as cp:
    for d in docs: cp.write_row((d["_id"], d.get("title", ""), d["text"]))
c.execute("create index on docs2 using gin (tsv_en)"); c.execute("create index on docs2 using gin (tsv_simple)"); c.execute("vacuum analyze docs2")
VARIANTS = {
    "ts_rank (baseline)":         ("tsv_en", "english", "ts_rank(tsv_en, q)"),
    "ts_rank, length-normalised": ("tsv_en", "english", "ts_rank(tsv_en, q, 1)"),
    "ts_rank_cd":                 ("tsv_en", "english", "ts_rank_cd(tsv_en, q)"),
    "ts_rank_cd, length-normalised": ("tsv_en", "english", "ts_rank_cd(tsv_en, q, 1)"),
    "'simple' config, ts_rank":   ("tsv_simple", "simple", "ts_rank(tsv_simple, q)"),
}
out = {"dataset": ds, "variants": []}
for name, (col, cfg, rank) in VARIANTS.items():
    nd, lat = [], []
    for q in qs:
        ts = " | ".join(terms(queries[q])) or "x"
        t0 = time.perf_counter()
        r = [x[0] for x in c.execute(f"select id from docs2, to_tsquery('{cfg}', %s) q where {col} @@ q order by {rank} desc limit 100", (ts,))]
        lat.append(time.perf_counter() - t0); nd.append(ndcg10(r, qrels[q]))
    lat.sort()
    out["variants"].append({"engine": "Postgres", "variant": name, "ndcg10": round(st.mean(nd), 4), "p50_ms": round(1000 * lat[len(lat) // 2], 2)})
    print(json.dumps(out["variants"][-1]), flush=True)
s = sqlite3.connect(":memory:")
s.execute("create virtual table d using fts5(id unindexed, title, body, tokenize='unicode61')")
s.executemany("insert into d values (?,?,?)", ((d["_id"], d.get("title", ""), d["text"]) for d in docs))
nd = []
for q in qs:
    ts = " OR ".join('"' + t + '"' for t in terms(queries[q]))
    nd.append(ndcg10([r[0] for r in s.execute("select id from d where d match ? order by bm25(d) limit 100", (ts,))], qrels[q]))
out["variants"].append({"engine": "SQLite FTS5", "variant": "no stemmer (unicode61)", "ndcg10": round(st.mean(nd), 4)})
print(json.dumps(out["variants"][-1]))
(ROOT / "results" / f"tuning_{ds}.json").write_text(json.dumps(out, indent=1))
