"""Median word count of each engine's #1 result across all FiQA test queries, vs the median relevant doc.
Writes results/lengths.json."""
import json, statistics as st, sys, sqlite3
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engines import Postgres, Tantivy, terms
import tantivy
ROOT = Path(__file__).resolve().parent.parent; D = ROOT / "data" / "fiqa"
docs = {d["_id"]: d for d in map(json.loads, (D / "corpus.jsonl").open())}
queries = {j["_id"]: j["text"] for j in map(json.loads, (D / "queries.jsonl").open())}
qrels = {}
for line in list((D / "qrels" / "test.tsv").open())[1:]:
    q, d, s = line.rstrip("\n").split("\t"); qrels.setdefault(q, set()).add(d)
wc = lambda d: len(docs[d]["text"].split())
pg = Postgres("or"); tv = Tantivy("or", str(ROOT / "data" / "work" / "fiqa.tantivy"))
tv.index = tantivy.Index.open(tv.path); tv.searcher = tv.index.searcher()
sq = sqlite3.connect(str(ROOT / "data" / "work" / "fiqa.sqlite"))
def sqlite_top(q):
    ts = " OR ".join('"' + t + '"' for t in terms(q))
    return [r[0] for r in sq.execute("select id from docs where docs match ? order by bm25(docs) limit 1", (ts,))]
out = {"relevant_docs_median_words": st.median(wc(d) for v in qrels.values() for d in v),
       "corpus_median_words": st.median(wc(d) for d in docs)}
for name, fn in (("Postgres ts_rank", lambda q: pg.search(q, 1)), ("Tantivy", lambda q: tv.search(q, 1)), ("SQLite FTS5", sqlite_top)):
    tops = [fn(queries[q]) for q in qrels]
    out[name] = st.median(wc(t[0]) for t in tops if t)
(ROOT / "results" / "lengths.json").write_text(json.dumps(out, indent=1)); print(json.dumps(out))
