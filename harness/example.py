"""Find FiQA queries where Tantivy's top result is judged relevant and none of Postgres's top 3 is,
and print the titles/snippets of each engine's top 3 for the first few. usage: python example.py"""
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from engines import Postgres, Tantivy
ROOT = Path(__file__).resolve().parent.parent; D = ROOT / "data" / "fiqa"
docs = {d["_id"]: d for d in map(json.loads, (D / "corpus.jsonl").open())}
queries = {j["_id"]: j["text"] for j in map(json.loads, (D / "queries.jsonl").open())}
qrels = {}
for line in list((D / "qrels" / "test.tsv").open())[1:]:
    q, d, s = line.rstrip("\n").split("\t"); qrels.setdefault(q, set()).add(d)
pg = Postgres("or")
tv = Tantivy("or", str(ROOT / "data" / "work" / "fiqa.tantivy"))
import tantivy
tv.index = tantivy.Index.open(tv.path); tv.searcher = tv.index.searcher()
found = []
for q in qrels:
    t, p = tv.search(queries[q], 3), pg.search(queries[q], 3)
    if t and t[0] in qrels[q] and not set(p) & qrels[q] and len(queries[q].split()) <= 12:
        found.append(q)
print(len(found), "queries where Tantivy's #1 is relevant and Postgres's top 3 has none")
for q in found[:3]:
    print("\nQUERY:", queries[q])
    for name, ids in (("Tantivy", tv.search(queries[q], 3)), ("Postgres", pg.search(queries[q], 3))):
        for i, d in enumerate(ids, 1):
            print(f"  {name:8} #{i} {'REL' if d in qrels[q] else '   '} {len(docs[d]['text'].split()):4}w  {docs[d]['text'][:110]!r}")
