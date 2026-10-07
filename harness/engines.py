"""Four full-text engines behind one interface: build(docs) -> (seconds, bytes); search(q, k) -> [doc ids].

Each uses its own documented English analysis:
  Postgres  to_tsvector('english'), title weighted A, body B, GIN index, ranked by ts_rank
  SQLite    FTS5 with tokenize='porter unicode61', ranked by bm25()
  DuckDB    fts extension, stemmer='english', stopwords='english', match_bm25
  Tantivy   en_stem tokenizer on title and body, BM25
Query modes: "or" = any term may match (what BM25 engines do by default);
             "and" = every term must match (the default for Postgres websearch_to_tsquery and SQLite FTS5).
"""
import os, re, shutil, sqlite3, time
from pathlib import Path

WORD = re.compile(r"[A-Za-z0-9]+")
def terms(q):
    return [t.lower() for t in WORD.findall(q)]

def dir_size(p):
    p = Path(p)
    return p.stat().st_size if p.is_file() else sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

class Postgres:
    name = "Postgres"
    DSN = "host=localhost port=5499 user=bench dbname=search"
    def __init__(self, mode):
        import psycopg
        self.mode = mode
        with psycopg.connect("host=localhost port=5499 user=bench dbname=postgres", autocommit=True) as c:
            if not c.execute("select 1 from pg_database where datname='search'").fetchone():
                c.execute("create database search")
        self.c = psycopg.connect(self.DSN, autocommit=True)
    def build(self, docs):
        c = self.c
        c.execute("drop table if exists docs")
        c.execute("""create table docs (id text primary key, title text, body text,
            tsv tsvector generated always as (setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
                                              setweight(to_tsvector('english', coalesce(body, '')), 'B')) stored)""")
        t0 = time.perf_counter()
        with c.cursor() as cur, cur.copy("copy docs (id, title, body) from stdin") as cp:
            for d in docs:
                cp.write_row((d["_id"], d.get("title", ""), d["text"]))
        c.execute("create index docs_tsv on docs using gin (tsv)")
        c.execute("vacuum analyze docs")
        dt = time.perf_counter() - t0
        size = c.execute("select pg_total_relation_size('docs')").fetchone()[0]
        return dt, size
    def search(self, q, k=100):
        if self.mode == "and":
            sql = ("select id from docs, websearch_to_tsquery('english', %s) query where tsv @@ query "
                   "order by ts_rank(tsv, query) desc limit %s")
            args = (q, k)
        else:
            ts = " | ".join(terms(q)) or "x"
            sql = ("select id from docs, to_tsquery('english', %s) query where tsv @@ query "
                   "order by ts_rank(tsv, query) desc limit %s")
            args = (ts, k)
        return [r[0] for r in self.c.execute(sql, args).fetchall()]

class SQLite:
    name = "SQLite FTS5"
    def __init__(self, mode, path):
        self.mode, self.path = mode, path
    def build(self, docs):
        if os.path.exists(self.path):
            os.remove(self.path)
        self.c = sqlite3.connect(self.path)
        self.c.execute("create virtual table docs using fts5(id unindexed, title, body, tokenize='porter unicode61')")
        t0 = time.perf_counter()
        self.c.executemany("insert into docs values (?, ?, ?)", ((d["_id"], d.get("title", ""), d["text"]) for d in docs))
        self.c.execute("insert into docs(docs) values('optimize')")
        self.c.commit()
        return time.perf_counter() - t0, dir_size(self.path)
    def search(self, q, k=100):
        ts = ['"' + t + '"' for t in terms(q)]
        if not ts:
            return []
        expr = (" OR " if self.mode == "or" else " ").join(ts)
        return [r[0] for r in self.c.execute("select id from docs where docs match ? order by bm25(docs) limit ?", (expr, k))]

class DuckDB:
    name = "DuckDB FTS"
    def __init__(self, mode, path):
        self.mode, self.path = mode, path
    def build(self, docs):
        import duckdb
        for p in (self.path, self.path + ".wal"):
            if os.path.exists(p):
                os.remove(p)
        self.c = duckdb.connect(self.path)
        self.c.execute("install fts; load fts")
        self.c.execute("create table docs (id varchar, title varchar, body varchar)")
        t0 = time.perf_counter()
        self.c.executemany("insert into docs values (?, ?, ?)", [(d["_id"], d.get("title", ""), d["text"]) for d in docs])
        self.c.execute("pragma create_fts_index('docs', 'id', 'title', 'body', stemmer='english', stopwords='english')")
        self.c.execute("checkpoint")
        return time.perf_counter() - t0, dir_size(self.path)
    def search(self, q, k=100):
        conj = 1 if self.mode == "and" else 0
        return [r[0] for r in self.c.execute(
            "select id from (select id, fts_main_docs.match_bm25(id, ?, conjunctive := ?) as s from docs) "
            "where s is not null order by s desc limit ?", [q, conj, k]).fetchall()]

class Tantivy:
    name = "Tantivy"
    def __init__(self, mode, path):
        self.mode, self.path = mode, path
    def build(self, docs):
        import tantivy
        shutil.rmtree(self.path, ignore_errors=True); os.makedirs(self.path)
        sb = tantivy.SchemaBuilder()
        sb.add_text_field("id", stored=True, tokenizer_name="raw")
        sb.add_text_field("title", tokenizer_name="en_stem")
        sb.add_text_field("body", tokenizer_name="en_stem")
        self.schema = sb.build()
        self.index = tantivy.Index(self.schema, path=self.path)
        t0 = time.perf_counter()
        w = self.index.writer(heap_size=256_000_000)
        for d in docs:
            w.add_document(tantivy.Document(id=d["_id"], title=d.get("title", ""), body=d["text"]))
        w.commit(); w.wait_merging_threads()
        self.index.reload()
        self.searcher = self.index.searcher()
        return time.perf_counter() - t0, dir_size(self.path)
    def search(self, q, k=100):
        ts = terms(q)
        if not ts:
            return []
        expr = (" AND " if self.mode == "and" else " ").join(ts)
        query = self.index.parse_query(expr, ["title", "body"])
        return [self.searcher.doc(a)["id"][0] for _, a in self.searcher.search(query, k).hits]
