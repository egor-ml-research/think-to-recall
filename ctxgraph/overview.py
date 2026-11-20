"""`overview()`: a map of the project in <= ~600 tokens, from the store only (no code read, no model, no network).

With an imported Graphify code graph: its communities (Graphify's own `community` field; networkx Leiden seed 0 when
absent), minified / vendored files left out and tiny communities merged into their best-linked neighbour; each named by
its 1-2 most connected files, with up to 3 most connected functions / classes, the communities it links to (edge
counts), and the 1-2 newest user decisions that name its code EXACTLY (a code-looking token: `file.py`, `snake_name`,
`CamelName`, `call()`; a plain word never links). Without a code graph: the conversation topics with their newest
decisions and a hint to build the graph. Budget in characters (`MAX_CHARS`, rule: reports/realworld/overview_rule.md)
with a fixed drop order: decisions of small communities -> symbols -> links -> small communities ("+N more").
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict

from ctxgraph.graphify import GENERIC, IDENT, _norm_name

MAX_CHARS = 1500  # 600 tokens x 2.54 chars/token (XLM-R, code-name heavy text), fixed before measuring
MAX_SHOWN = 8
SKIP_FILE = re.compile(r"(^|/)(vendor|node_modules|dist|build|third_party|site-packages|\.venv)/|\.min\.(js|css)$")
TEST_FILE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[^/]*$")
TOKEN = re.compile(r"[A-Za-z_][\w./\\-]*(?:\(\))?")


def _base(path: str) -> str:
    parts = path.rsplit("/", 2)
    b = parts[-1]
    return f"{parts[-2]}/{b}" if b.startswith("__init__") and len(parts) > 1 else b


def _communities(nodes: dict[str, tuple], edges: list[tuple[str, str]]) -> dict[str, int]:
    com = {n: v[3] for n, v in nodes.items() if v[3] is not None}
    if com:
        nxt = max(com.values()) + 1
        for n in sorted(nodes):  # a node Graphify left without a community: its own
            if n not in com:
                com[n], nxt = nxt, nxt + 1
        return com
    import networkx as nx

    G = nx.Graph()
    G.add_nodes_from(sorted(nodes))
    G.add_edges_from(edges)
    try:
        parts = nx.community.leiden_communities(G, seed=0)
    except (NotImplementedError, AttributeError):  # networkx without a Leiden backend
        parts = nx.community.louvain_communities(G, seed=0)
    parts = sorted(parts, key=lambda c: (-len(c), min(c)))
    return {n: i for i, c in enumerate(parts) for n in c}


def _merge_tiny(com: dict[str, int], edges: list[tuple[str, str]]) -> dict[str, int]:
    size = Counter(com.values())
    tiny = max(5, int(0.01 * len(com)))
    link: dict[int, Counter] = defaultdict(Counter)
    for a, b in edges:
        x, y = com[a], com[b]
        if x != y:
            link[x][y] += 1
            link[y][x] += 1
    into = {c: c for c in size}
    while True:
        small = sorted((c for c in size if size[c] < tiny and link[c]), key=lambda c: (size[c], c))
        if not small:
            break
        c = small[0]
        t = max(link[c], key=lambda o: (link[c][o], size[o], -o))
        size[t] += size.pop(c)
        for o, w in link.pop(c).items():
            link[o].pop(c, None)
            if o != t:
                link[t][o] += w
                link[o][t] += w
        for k, v in into.items():
            if v == c:
                into[k] = t
    return {n: into[c] for n, c in com.items()}


def _code_map(db) -> dict | None:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='code_nodes'").fetchone():
        return None
    nodes = {r[0]: r[1:] for r in db.execute("SELECT id, label, file, file_type, community FROM code_nodes")
             if r[2] and r[3] in ("code", "") and not SKIP_FILE.search(r[2])}  # fmt: skip
    if not nodes:
        return None
    edges = sorted({(a, b) for a, b in db.execute("SELECT src, dst FROM code_edges") if a in nodes and b in nodes and a != b})
    com = _merge_tiny(_communities(nodes, edges), edges)
    deg: Counter = Counter()
    pair: Counter = Counter()
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
        if com[a] != com[b]:
            pair[(com[a], com[b])] += 1
            pair[(com[b], com[a])] += 1
    members: dict[int, list[str]] = defaultdict(list)
    for n in sorted(nodes):
        members[com[n]].append(n)
    order = sorted(members, key=lambda c: (-len(members[c]), c))
    idx = {c: i + 1 for i, c in enumerate(order)}  # display ids c1, c2, ... by size
    info, owner = {}, defaultdict(set)
    for c in order:
        fscore: Counter = Counter()
        syms: list[tuple[int, str]] = []
        for n in members[c]:
            label, file = nodes[n][0], nodes[n][1]
            fscore[file] += deg[n] + 1
            base = file.rsplit("/", 1)[-1]
            is_file = label.lower() in (base.lower(), file.lower()) or label.lower().endswith("/" + base.lower())
            owner[base.lower()].add(c)
            if not is_file:
                name = _norm_name(label)
                owner[name].add(c)
                if not TEST_FILE.search(file):
                    syms.append((-deg[n], label.strip().removesuffix("()").lstrip(".")))
        files = sorted(fscore, key=lambda f: (bool(TEST_FILE.search(f)), -fscore[f], f))
        seen, top = set(), []
        for _, s in sorted(syms):
            if s not in seen and len(top) < 3:
                seen.add(s)
                top.append(s)
        names: list[str] = []
        for f in files[:2]:
            if _base(f) not in names:
                names.append(_base(f))
        links = sorted(((o, w) for (x, o), w in pair.items() if x == c), key=lambda t: (-t[1], idx[t[0]]))[:3]
        info[c] = {"size": len(members[c]), "files": names, "syms": top, "links": [(idx[o], w) for o, w in links]}
    names = {k: next(iter(v)) for k, v in owner.items() if len(v) == 1 and len(k) >= 4 and k not in GENERIC}
    return {"order": order, "idx": idx, "info": info, "names": names, "nodes": len(nodes), "n_com": len(order)}


def _decisions(mem) -> list[tuple[str, str, str]]:
    """(ts, episode, sentence) of the user's decisions, newest first; forgotten records left out."""
    rows = mem.s.q("SELECT COALESCE(m.ts,''), f.episode_id, f.text, f.idx FROM frag_status s "
                   "JOIN fragments f ON f.id=s.fragment JOIN episodes e ON e.id=f.episode_id "
                   "LEFT JOIN turn_meta m ON m.episode=e.id WHERE s.status='decision' AND e.t_expired IS NULL")  # fmt: skip
    rows = sorted(rows, key=lambda r: (r[0], r[1], -r[3]), reverse=True)
    return [(ts, ep, " ".join(t.split())) for ts, ep, t, _ in rows]


def _matches(text: str, names: dict[str, int]) -> list[tuple[int, str, int]]:
    """(position, token, community) of the code-looking tokens of a sentence that name exactly one community."""
    out = []
    for m in TOKEN.finditer(text):
        tok = m.group(0).rstrip(".-/\\")
        if not IDENT.search(tok):
            continue
        key = _norm_name(tok.replace("\\", "/").rsplit("/", 1)[-1])
        if key in names:
            out.append((m.start(), tok, names[key]))
    return out


def _window(text: str, pos: int, n: int = 90) -> str:
    if len(text) <= n:
        return text
    a = max(0, min(pos - 25, len(text) - n))
    s = text[a:a + n].strip()
    return ("…" if a else "") + s + ("…" if a + n < len(text) else "")


def _date(ts: str, year: str) -> str:
    return ts[5:10] if ts[:4] == year else ts[:10] or "?"


def _render(head: str, items: list[dict], names: list[str], hidden: int, hint: str = "") -> str:
    out = [head]
    for it in items:
        out.append(it["line"](it))
        out += [f"   {d}" for d in it["dec"][:it["k"]]]
    if hidden:
        out.append(f"+{hidden} more: " + ", ".join(names + (["…"] if len(names) < hidden else [])))
    if hint:
        out.append(hint)
    return "\n".join(out)


def _fit(head: str, items: list[dict], rest: list[str], hint: str, max_chars: int) -> str:
    """Drop in the fixed order until the text fits: decisions of the smallest -> symbols -> links -> communities
    (into "+N more"); then the "+N more" line takes as many names as still fit (folded ones first)."""
    hidden = len(rest)
    text = _render(head, items, [], hidden, hint)
    for field in ("k", "syms", "links"):
        for it in reversed(items):
            while len(text) > max_chars and (it[field] if field != "k" else it["k"] > 0):
                if field == "k":
                    it["k"] -= 1
                else:
                    it[field] = it[field][:-1]
                text = _render(head, items, [], hidden, hint)
    folded: list[str] = []
    while len(text) > max_chars and len(items) > 1:
        folded.insert(0, items.pop()["short"])
        hidden += 1
        text = _render(head, items, [], hidden, hint)
    names: list[str] = []
    for nm in folded + rest:
        if len(_render(head, items, names + [nm], hidden, hint)) > max_chars:
            break
        names.append(nm)
    text = _render(head, items, names, hidden, hint)
    return text if len(text) <= max_chars else text[:max_chars - 1] + "…"


def overview(mem, max_chars: int = MAX_CHARS) -> str:
    """The project map (see the module doc). `mem`: a ProjectMemory."""
    decs = _decisions(mem)
    year = max((ts[:4] for ts, _, _ in decs), default="")
    cm = _code_map(mem.s.db)
    if cm:
        per: dict[int, list[str]] = defaultdict(list)
        for ts, ep, text in decs:
            hits = _matches(text, cm["names"])
            if not hits:
                continue
            cnt = Counter(c for _, _, c in hits)
            c = max(cnt, key=lambda x: (cnt[x], cm["info"][x]["size"], -cm["idx"][x]))
            if len(per[c]) < 2:
                pos = next(p for p, _, x in hits if x == c)
                per[c].append(f"{_date(ts, year)} {_window(text, pos)} (#{mem._id(ep)})")
        items = []
        for c in cm["order"][:MAX_SHOWN]:
            i = cm["info"][c]
            items.append({"files": i["files"], "syms": list(i["syms"]), "links": list(i["links"]), "dec": per[c],
                          "k": len(per[c]), "short": " ".join(i["files"][:1]), "n": cm["idx"][c],
                          "line": lambda it: (f"#c{it['n']} {', '.join(it['files'])}"
                                              + (" — " + ", ".join(it["syms"]) if it["syms"] else "")
                                              + (" | ↔ " + ", ".join(f"c{o} ({w})" for o, w in it["links"])
                                                 if it["links"] else ""))})  # fmt: skip
        rest = [" ".join(cm["info"][c]["files"][:1]) for c in cm["order"][MAX_SHOWN:]]
        head = (f"Project map: {cm['n_com']} code communities, {cm['nodes']} nodes (Graphify; #cN by size, ↔ = "
                "edges to other communities; decisions name their code; expand(#id) for a record)")
        text = _fit(head, items, rest, "", max_chars)
        return text
    return _topics_view(mem, decs, year, max_chars)


def _topics_view(mem, decs, year, max_chars) -> str:
    hint = "No code graph: `ctxgraph setup --graphify yes` builds one (Graphify, local, no LLM) for a code map."
    if not decs and not mem.s.q("SELECT 1 FROM fragments LIMIT 1"):
        return "The memory of this project is empty (`ctxgraph import`). " + hint
    try:
        t = mem._topics()
    except Exception:  # noqa: BLE001 - e.g. a networkx without Leiden: the decisions alone
        t = None
    per: dict[int, list[str]] = defaultdict(list)
    loose: list[str] = []
    for ts, ep, text in decs:
        k = t.of_record([ep]) if t else None
        line = f"{_date(ts, year)} {_window(text, 0)} (#{mem._id(ep)})"
        if k is None:
            if len(loose) < 2:
                loose.append(line)
        elif len(per[k]) < 2:
            per[k].append(line)
    order = sorted(t.name, key=lambda k: (-t.size[k], k))[:MAX_SHOWN] if t else []
    items = [{"files": [t.name[k]], "syms": [], "links": [], "dec": per[k], "k": len(per[k]), "short": t.name[k],
              "n": i + 1, "line": lambda it: f"#t{it['n']} {it['files'][0]}"} for i, k in enumerate(order)]  # fmt: skip
    if loose:
        items.append({"files": ["(no topic)"], "syms": [], "links": [], "dec": loose, "k": len(loose), "short": "",
                      "n": 0, "line": lambda it: "latest decisions"})  # fmt: skip
    head = f"Project map from the conversation: {len(t.name) if t else 0} topics (#tN by size; expand(#id) for a record)"
    rest = [t.name[k] for k in sorted(t.name, key=lambda k: (-t.size[k], k))[MAX_SHOWN:]] if t else []
    return _fit(head, items, rest, hint, max_chars)
