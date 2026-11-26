"""Import a Graphify code graph (`graphify-out/graph.json`) next to the conversation memory of a project.

Graphify (github.com/Graphify-Labs/graphify, Apache-2.0) builds a graph of a codebase from the tree-sitter AST and
writes it as networkx node-link JSON: top-level `nodes` and `links` (older files: `edges`), node fields `id`, `label`,
`source_file`, `source_location`, `file_type`, `community`; edge fields `source`, `target`, `relation`, `confidence`
(EXTRACTED / INFERRED / AMBIGUOUS) and `confidence_score`. Unknown fields are ignored.

Every edge here carries an origin label:
- `code`         - an edge Graphify extracted from the code (confidence EXTRACTED);
- `inferred`     - an edge Graphify inferred (INFERRED / AMBIGUOUS), and every link between a conversation concept and a
                   code node, made by an exact name match (a file path said in the chat = that file; an identifier said
                   in the chat = a code symbol with the same name);
- `conversation` - the memory's own edges between conversation concepts (they stay in their own tables).

The code layer lives in separate tables of the project's SQLite store and is used only by the graph view: recall does
not search code (not checked; see README, limits). Re-importing replaces the previous code layer. No model, no network.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS code_nodes (id TEXT PRIMARY KEY, label TEXT NOT NULL, file TEXT NOT NULL DEFAULT '',
    loc TEXT NOT NULL DEFAULT '', file_type TEXT NOT NULL DEFAULT '', community INTEGER);
CREATE TABLE IF NOT EXISTS code_edges (src TEXT NOT NULL, dst TEXT NOT NULL, relation TEXT NOT NULL,
    confidence TEXT NOT NULL, score REAL NOT NULL, origin TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS code_links (concept TEXT NOT NULL, code TEXT NOT NULL, how TEXT NOT NULL,
    origin TEXT NOT NULL DEFAULT 'inferred', PRIMARY KEY (concept, code));
CREATE TABLE IF NOT EXISTS code_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""
SCORE = {"EXTRACTED": 1.0, "INFERRED": 0.55, "AMBIGUOUS": 0.2}
# names too generic to say "the chat talks about this symbol"
GENERIC = {"main", "init", "__init__", "__main__", "test", "tests", "run", "setup", "utils", "util", "config", "data",
           "self", "index", "app", "core", "base", "types", "helpers", "common", "constants", "settings", "readme.md",
           "__init__.py", "conftest.py", "setup.py", "cli", "server", "client", "model", "models", "view", "views"}
IDENT = re.compile(r"[._/()]|[a-z][A-Z]|^[A-Z][a-z]+[A-Z]")


def _norm_path(p: str) -> str:
    return p.replace("\\", "/").lstrip("./").lower()


def _norm_name(s: str) -> str:
    return s.strip().rstrip(")").removesuffix("(").lstrip(".").lower()


def load(path: str | Path) -> dict:
    p = Path(path)
    if p.is_dir():
        p = p / "graph.json" if (p / "graph.json").exists() else p / "graphify-out" / "graph.json"
    data = json.loads(p.read_text("utf-8"))
    if not isinstance(data, dict) or "nodes" not in data:
        raise ValueError(f"{p}: not a Graphify graph.json (no 'nodes')")
    data["_path"] = str(p.resolve())
    return data


def connect(db_path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(str(db_path))
    db.executescript(SCHEMA)
    cols = {r[1] for r in db.execute("PRAGMA table_info(code_nodes)")}
    if "member" not in cols:  # team memory: '' = this device's own graph, else a member's graph from the memory repo
        db.execute("ALTER TABLE code_nodes ADD COLUMN member TEXT NOT NULL DEFAULT ''")
        db.commit()
    return db


MAX_LABEL = 120
MAX_NODES = 20000


def _rel(file: str, root: Path | None) -> str:
    """A path relative to the clone root; an absolute path outside it keeps only its file name (never a home path)."""
    f = (file or "").replace("\\", "/")
    if not f:
        return ""
    if re.match(r"^([A-Za-z]:/|/)", f):
        if root is not None:
            r = str(root.resolve()).replace("\\", "/").rstrip("/") + "/"
            if f.lower().startswith(r.lower()):
                return _norm_path(f[len(r):])
        return _norm_path(f.rsplit("/", 1)[-1])
    return _norm_path(f)


def compact(path: str | Path, root: str | Path | None, member: str) -> dict:
    """A member's Graphify graph for the team repo (team_graphs rule): node id, label, file relative to the clone
    root, location, community; edges id-id, relation, confidence. No source text, no absolute paths."""
    data = load(path)
    root = Path(root) if root else None
    nodes, seen = [], set()
    for n in data["nodes"][:MAX_NODES]:
        nid = str(n.get("id", ""))[:200]
        if not nid or nid in seen:
            continue
        seen.add(nid)
        com = n.get("community")
        nodes.append([nid, str(n.get("label") or nid)[:MAX_LABEL], _rel(str(n.get("source_file") or ""), root),
                      str(n.get("source_location") or "")[:40], com if isinstance(com, int) else None])  # fmt: skip
    edges = []
    for e in data.get("links", data.get("edges", [])):
        a, b = str(e.get("source", "")), str(e.get("target", ""))
        if a in seen and b in seen and a != b:
            edges.append([a, b, str(e.get("relation") or "related")[:40], str(e.get("confidence") or "EXTRACTED").upper()[:12]])
    return {"member": member, "nodes": nodes, "edges": edges[: MAX_NODES * 4]}


def import_members(db_path: str | Path, graphs: list[dict]) -> int:
    """Replace the members' code layers (member != '') with these compact graphs; node ids get the member prefix."""
    db = connect(db_path)
    with db:
        old = [r[0] for r in db.execute("SELECT id FROM code_nodes WHERE member != ''")]
        db.execute("DELETE FROM code_nodes WHERE member != ''")
        if old:
            db.executemany("DELETE FROM code_edges WHERE src=?", [(x,) for x in old])
        n = 0
        for g in graphs:
            m = str(g.get("member") or "?")
            pre = f"{m}::"
            rows = [(pre + x[0], x[1], x[2], x[3], "", x[4], m) for x in g.get("nodes", []) if len(x) >= 5]
            db.executemany("INSERT OR IGNORE INTO code_nodes (id, label, file, loc, file_type, community, member) "
                           "VALUES (?,?,?,?,?,?,?)", rows)  # fmt: skip
            db.executemany("INSERT INTO code_edges VALUES (?,?,?,?,?,?)",
                           [(pre + a, pre + b, rel, conf, SCORE.get(conf, 0.5), "code" if conf == "EXTRACTED" else "inferred")
                            for a, b, rel, conf in (e[:4] for e in g.get("edges", []) if len(e) >= 4)])  # fmt: skip
            n += len(rows)
    link_conversation(db)
    db.close()
    return n


def import_graph(db_path: str | Path, path: str | Path) -> dict:
    """Replace the code layer of a project store with a Graphify graph.json and link it to the conversation."""
    data = load(path)
    nodes, seen = [], set()
    for n in data["nodes"]:
        nid = str(n.get("id", ""))
        if not nid or nid in seen:
            continue
        seen.add(nid)
        com = n.get("community")
        nodes.append((nid, str(n.get("label") or nid), _norm_path(str(n.get("source_file") or "")),
                      str(n.get("source_location") or ""), str(n.get("file_type") or ""),
                      com if isinstance(com, int) else None))  # fmt: skip
    edges = []
    for e in data.get("links", data.get("edges", [])):
        a, b = str(e.get("source", "")), str(e.get("target", ""))
        if a not in seen or b not in seen or a == b:
            continue
        conf = str(e.get("confidence") or "EXTRACTED").upper()
        score = e.get("confidence_score")
        score = float(score) if isinstance(score, int | float) else SCORE.get(conf, 0.5)
        edges.append((a, b, str(e.get("relation") or "related"), conf, score,
                      "code" if conf == "EXTRACTED" else "inferred"))  # fmt: skip
    db = connect(db_path)
    with db:
        own = [r[0] for r in db.execute("SELECT id FROM code_nodes WHERE member = ''")]
        db.execute("DELETE FROM code_nodes WHERE member = ''")  # the members' layers (team memory) stay
        db.executemany("DELETE FROM code_edges WHERE src=?", [(x,) for x in own])
        db.execute("DELETE FROM code_links")
        db.execute("DELETE FROM code_meta")
        db.executemany("INSERT INTO code_nodes (id, label, file, loc, file_type, community) VALUES (?,?,?,?,?,?)", nodes)
        db.executemany("INSERT INTO code_edges VALUES (?,?,?,?,?,?)", edges)
        meta = {"source": data["_path"], "imported": time.strftime("%Y-%m-%d %H:%M"),
                "graphify_version": str((data.get("graph") or {}).get("graphify_version", "")),
                "schema_version": str((data.get("graph") or {}).get("schema_version", "")),
                "commit": str(data.get("built_at_commit") or "")}  # fmt: skip
        db.executemany("INSERT INTO code_meta VALUES (?,?)", list(meta.items()))
    links = link_conversation(db)
    db.close()
    return {"nodes": len(nodes), "edges": len(edges), "code": sum(e[5] == "code" for e in edges),
            "inferred": sum(e[5] == "inferred" for e in edges), "links": links, "source": data["_path"]}  # fmt: skip


def link_conversation(db: sqlite3.Connection) -> int:
    """`inferred` links: conversation concept <-> code node by an exact name match (no embeddings, no fuzzy match)."""
    has = db.execute("SELECT 1 FROM sqlite_master WHERE name='concepts'").fetchone()
    db.execute("DELETE FROM code_links")
    if not has:
        db.commit()
        return 0
    by_file: dict[str, list[str]] = defaultdict(list)  # full relative path -> file node(s)
    by_base: dict[str, list[str]] = defaultdict(list)  # basename -> file node(s)
    by_name: dict[str, list[str]] = defaultdict(list)  # symbol name -> nodes
    for nid, label, file in db.execute("SELECT id, label, file FROM code_nodes"):
        base = file.rsplit("/", 1)[-1]
        if file and label.lower() in (base, file):
            by_file[file].append(nid)
            by_base[base].append(nid)
        else:
            by_name[_norm_name(label)].append(nid)
    rows = []
    for cid, label, kind in db.execute("SELECT id, label, kind FROM concepts"):
        if kind == "path" or "/" in label:
            p = _norm_path(label.split(":")[0])
            hit = by_file.get(p) or [n for f, ns in by_file.items() if f.endswith("/" + p) and "/" in p for n in ns]
            if not hit and "/" not in p and p not in GENERIC:
                hit = by_base.get(p, [])
            how = "path"
        else:
            k = _norm_name(label)
            if len(k) < 4 or k in GENERIC or not IDENT.search(label.strip()) and kind != "identifier":
                continue
            hit, how = by_name.get(k, []), "name"
        if 0 < len(hit) <= 3:
            rows += [(cid, h, how, "inferred") for h in hit]
    db.executemany("INSERT OR IGNORE INTO code_links VALUES (?,?,?,?)", rows)
    db.commit()
    return len(rows)


def layer(db_path: str | Path, concepts: set[str], cap: int = 220) -> dict:
    """The code part of the view: code nodes linked to the shown concepts, their code neighbours, then the most
    connected code nodes, at most `cap`; edges among them and the inferred links to the shown concepts."""
    db = sqlite3.connect(str(db_path))
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='code_nodes'").fetchone():
        return {"nodes": [], "links": [], "meta": {}}
    deg: dict[str, int] = defaultdict(int)
    nb: dict[str, set[str]] = defaultdict(set)
    elist = db.execute("SELECT src, dst, relation, confidence, score, origin FROM code_edges").fetchall()
    for a, b, *_ in elist:
        deg[a] += 1
        deg[b] += 1
        nb[a].add(b)
        nb[b].add(a)
    links = [(c, k, how) for c, k, how in db.execute("SELECT concept, code, how FROM code_links") if c in concepts]
    keep: list[str] = []
    for _, k, _ in links:
        if k not in keep:
            keep.append(k)
    for k in list(keep):
        keep += [x for x in sorted(nb[k], key=lambda x: -deg[x])[:4] if x not in keep]
    keep += [x for x in sorted(deg, key=lambda x: (-deg[x], x)) if x not in keep]
    info = {r[0]: r for r in db.execute("SELECT id, label, file, loc, file_type, community FROM code_nodes")}
    # vendored / minified libraries are not the project's code (their symbols are short names with many edges)
    junk = {i for i, r in info.items() if "/vendor/" in "/" + (r[2] or "") or (r[2] or "").endswith(".min.js")}
    keep = [x for x in keep if x not in junk]
    keep_set = set(keep[:cap])
    if not deg:
        keep_set |= set(list(info)[:cap])
    nodes = [{"id": "code:" + i, "label": info[i][1], "file": info[i][2], "loc": info[i][3], "ftype": info[i][4],
              "deg": deg.get(i, 0), "origin": "code"} for i in sorted(keep_set) if i in info]  # fmt: skip
    out = [{"source": "code:" + a, "target": "code:" + b, "rel": r, "conf": c, "w": s, "origin": o}
           for a, b, r, c, s, o in elist if a in keep_set and b in keep_set]  # fmt: skip
    out += [{"source": c, "target": "code:" + k, "rel": "mentions " + how, "w": 1.0, "origin": "inferred"}
            for c, k, how in links if k in keep_set]  # fmt: skip
    meta = dict(db.execute("SELECT key, value FROM code_meta").fetchall())
    meta["total_nodes"] = len(info)
    db.close()
    return {"nodes": nodes, "links": out, "meta": meta}
