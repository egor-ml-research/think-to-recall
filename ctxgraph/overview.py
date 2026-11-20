"""`overview()`: a map of the project in <= ~600 tokens, from the store and the project folder (no model, no network).

With an imported Graphify code graph: its communities (Graphify's own `community` field; networkx Leiden seed 0 when
absent) after leaving out tests / scripts / examples / archive / docs, minified and vendored files, paths ignored by
git and paths listed in `overview.exclude` (gitignore-style, project root); tiny communities merged into their
best-linked neighbour. Communities are ranked by 2*A + P + R: A - holds an entry point (a `[project.scripts]` module,
an MCP tool decorator, `__main__`), P - summed PageRank (relative to the top one), R - the share of its files changed
in the last 50 commits. Communities with the same lead file share one line. Each is named by its entry files and most connected files, with up to 3 most connected
functions / classes, the communities it links to (edge counts), and the 1-2 newest user decisions linked to it by an
exact (case-insensitive) code name in the sentence or by the files of the commit its report names. Without a code
graph: the conversation topics with their newest decisions and a hint to build the graph. Budget in characters
(`MAX_CHARS`, rule: reports/realworld/overview_rule.md) with a fixed drop order: second decisions -> symbols ->
links -> whole communities ("+N more").
"""

from __future__ import annotations

import re
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

from ctxgraph.graphify import GENERIC, _norm_name

MAX_CHARS = 1500  # 600 tokens x 2.54 chars/token (XLM-R, code-name heavy text), fixed before measuring
MAX_TOKENS = 600  # hard (post-run rule of v0.5.7): XLM-R tokens when its tokenizer is cached, else chars / 2.3
TOPLEVEL = re.compile(r"^(?:src/)?[^/]+/[^/]+\.py$|^[^/]+\.py$")
MAX_SHOWN = 8
RECENT = 50  # commits for R
SKIP_FILE = re.compile(r"(^|/)(vendor|node_modules|dist|build|third_party|site-packages|\.venv)/|\.min\.(js|css)$")
SKIP_DIR = re.compile(r"(^|/)(tests|scripts|examples|archive|docs)/")
TEST_FILE = re.compile(r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[^/]*$")
TOKEN = re.compile(r"[A-Za-z_][\w./\\-]*")
TOOL_DEF = re.compile(r"^[ \t]*@(?:\w+\.)*tool\b[^\n]*\n(?:[ \t]*@[^\n]*\n)*[ \t]*(?:async[ \t]+)?def[ \t]+(\w+)", re.M)
MAIN = re.compile(r"""if\s+__name__\s*==\s*["']__main__["']""")
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")


class Ignore:
    """gitignore-style patterns: `#` comments, trailing `/` = directory, a `/` inside or in front anchors at the root,
    `*`, `?`, `**`; `!` lines are skipped. Paths: relative, `/`-separated, matched case-insensitively."""

    def __init__(self, lines) -> None:
        self.rx = []
        for ln in lines:
            ln = ln.strip()
            if not ln or ln.startswith(("#", "!")):
                continue
            body = ln.rstrip("/")
            anchored = "/" in body
            body = body.lstrip("/")
            r = ""
            i = 0
            while i < len(body):
                if body.startswith("**/", i):
                    r, i = r + "(?:.*/)?", i + 3
                elif body.startswith("**", i):
                    r, i = r + ".*", i + 2
                elif body[i] == "*":
                    r, i = r + "[^/]*", i + 1
                elif body[i] == "?":
                    r, i = r + "[^/]", i + 1
                else:
                    r, i = r + re.escape(body[i]), i + 1
            # a match of the pattern or of a directory above the path
            self.rx.append(re.compile(("^" if anchored else "^(?:.*/)?") + r + "(?:/.*)?$", re.I))

    def __call__(self, path: str) -> bool:
        return any(r.match(path) for r in self.rx)


_TOK: list = []


def _ntok(text: str) -> int:
    """XLM-R (multilingual-e5-base) tokens when `tokenizers` and the cached tokenizer.json are there (no download);
    otherwise ceil(chars / 2.3), an overestimate (measured 2.48-3.19 chars/token)."""
    if not _TOK:
        tk = None
        try:
            from tokenizers import Tokenizer

            from ctxgraph import model as M

            f = M.snapshot_dir() / "tokenizer.json"
            tk = Tokenizer.from_file(str(f)) if f.is_file() else None
        except Exception:  # noqa: BLE001 - no tokenizer: the estimate
            tk = None
        _TOK.append(tk)
    if _TOK[0] is not None:
        return len(_TOK[0].encode(text, add_special_tokens=False).ids)
    return -(-len(text) * 10 // 23)


def _git(root: Path, *args: str, stdin: str | None = None) -> str:
    try:
        r = subprocess.run(["git", "-C", str(root), *args], input=stdin, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)  # fmt: skip
        return r.stdout if r.returncode in (0, 1) else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _is_repo(root: Path) -> bool:
    return _git(root, "rev-parse", "--is-inside-work-tree").strip() == "true"


def _excluded(root: Path | None, files: set[str], repo: bool) -> set[str]:
    out = {f for f in files if SKIP_FILE.search(f) or SKIP_DIR.search(f)}
    if root is None:
        return out
    rules = []
    p = root / "overview.exclude"
    if p.is_file():
        rules.append(Ignore(p.read_text("utf-8", errors="replace").splitlines()))
    if repo:
        rest = sorted(files - out)
        out |= {x.strip().replace("\\", "/").lower() for x in
                _git(root, "check-ignore", "--no-index", "--stdin", stdin="\n".join(rest) + "\n").splitlines()}  # fmt: skip
    elif (root / ".gitignore").is_file():
        rules.append(Ignore((root / ".gitignore").read_text("utf-8", errors="replace").splitlines()))
    for f in files:
        if any(r(f) for r in rules):
            out.add(f)
    return out


def _is_file_node(label: str, file: str) -> bool:
    base = file.rsplit("/", 1)[-1]
    lab = label.lower()
    return lab in (base.lower(), file.lower()) or lab.endswith("/" + base.lower())


def _entry_nodes(root: Path | None, nodes: dict[str, tuple]) -> set[str]:
    """The entry FUNCTIONS: (i) `[project.scripts]` targets, (ii) MCP tool functions, (iii) the functions called in an
    `if __name__ == "__main__":` block (else the file node); `__main__.py` -> its file node."""
    file_node: dict[str, str] = {}
    by_name: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for nid in sorted(nodes):
        label, file = nodes[nid][0], nodes[nid][1]
        if _is_file_node(label, file):
            file_node.setdefault(file, nid)
        else:
            by_name[file][_norm_name(label)].append(nid)
    files = sorted({v[1] for v in nodes.values()})

    def pick(f: str, names) -> list[str]:
        hit = [n for nm in names for n in by_name[f].get(nm.lower(), [])]
        return hit or ([file_node[f]] if f in file_node else [])

    out = {file_node[f] for f in files if f.rsplit("/", 1)[-1] == "__main__.py" and f in file_node}
    if root is None:
        return out
    try:
        import tomllib

        scripts = tomllib.loads((root / "pyproject.toml").read_text("utf-8")).get("project", {}).get("scripts", {})
    except (OSError, ValueError):
        scripts = {}
    for target in scripts.values():
        mod, _, func = str(target).partition(":")
        mod = mod.strip().replace(".", "/").lower()
        for f in files:
            if f in (mod + ".py", mod + "/__init__.py") or f.endswith(("/" + mod + ".py", "/" + mod + "/__init__.py")):
                out |= set(pick(f, [func.strip()] if func.strip() else []))
    for f in files:
        p = root / f
        try:
            if not (p.is_file() and p.stat().st_size <= 1_000_000):
                continue
            t = p.read_text("utf-8", errors="replace")
        except OSError:
            continue
        tools = TOOL_DEF.findall(t)
        if tools:
            out |= {n for nm in tools for n in by_name[f].get(nm.lower(), [])}
        m = MAIN.search(t)
        if m:
            block = []
            for ln in t[m.end():].split("\n")[1:]:
                if ln.strip() and not ln[:1].isspace():
                    break
                block.append(ln)
            out |= set(pick(f, re.findall(r"\b([A-Za-z_]\w*)\s*\(", "\n".join(block))))
    return out


def _pagerank(nodes: list[str], edges: list[tuple[str, str]], d: float = 0.85) -> dict[str, float]:
    n = len(nodes)
    if not n:
        return {}
    outs: dict[str, list[str]] = defaultdict(list)
    for a, b in edges:
        outs[a].append(b)
    pr = {x: 1.0 / n for x in nodes}
    for _ in range(200):
        dang = sum(pr[x] for x in nodes if not outs[x])
        new = {x: (1 - d) / n + d * dang / n for x in nodes}
        for a in nodes:
            if outs[a]:
                share = d * pr[a] / len(outs[a])
                for b in outs[a]:
                    new[b] += share
        diff = sum(abs(new[x] - pr[x]) for x in nodes)
        pr = new
        if diff < 1e-10:
            break
    return pr


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


def _base(path: str) -> str:
    parts = path.rsplit("/", 2)
    b = parts[-1]
    return f"{parts[-2]}/{b}" if b.startswith("__init__") and len(parts) > 1 else b


def _stem(base: str) -> str:
    m = re.match(r"^(.+)\.[a-z]{1,4}$", base)
    return m.group(1) if m else base


def _code_map(db, root: Path | None) -> dict | None:
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='code_nodes'").fetchone():
        return None
    nodes = {r[0]: r[1:] for r in db.execute("SELECT id, label, file, file_type, community FROM code_nodes")
             if r[2] and r[3] in ("code", "")}  # fmt: skip
    repo = root is not None and _is_repo(root)
    drop = _excluded(root, {v[1] for v in nodes.values()}, repo)
    nodes = {k: v for k, v in nodes.items() if v[1] not in drop}
    if not nodes:
        return None
    edges = sorted({(a, b) for a, b in db.execute("SELECT src, dst FROM code_edges") if a in nodes and b in nodes and a != b})
    com = _merge_tiny(_communities(nodes, edges), edges)
    deg: Counter = Counter()
    for a, b in edges:
        deg[a] += 1
        deg[b] += 1
    members: dict[int, list[str]] = defaultdict(list)
    for n in sorted(nodes):
        members[com[n]].append(n)
    entry = _entry_nodes(root, nodes)
    entry_files = {nodes[n][1] for n in entry}
    recent = set()
    if repo:
        recent = {x.strip().lower() for x in _git(root, "log", "-n", str(RECENT), "--name-only", "--format=").splitlines()}
    pr = _pagerank(sorted(nodes), edges)
    psum = {c: sum(pr[n] for n in ms) for c, ms in members.items()}
    pmax = max(psum.values()) or 1.0
    score = {}
    for c, ms in members.items():
        fs = {nodes[n][1] for n in ms}
        score[c] = 2 * bool(entry.intersection(ms)) + psum[c] / pmax + len(fs & recent) / len(fs)
    order = sorted(members, key=lambda c: (-score[c], -len(members[c]), c))

    def ranked_files(ms: list[str]) -> list[str]:
        fscore: Counter = Counter()
        for n in ms:
            fscore[nodes[n][1]] += deg[n] + 1
        ent = sorted((f for f in fscore if f in entry_files), key=lambda f: (-fscore[f], f))[:2]
        rest = sorted(fscore, key=lambda f: (bool(TEST_FILE.search(f)), -fscore[f], f))
        return ent + [f for f in rest if f not in ent]

    # diversity: communities with the same lead file become one line, at the rank of the best of them
    line_of: dict[str, int] = {}
    into: dict[int, int] = {}
    for c in order:
        into[c] = line_of.setdefault(ranked_files(members[c])[0], c)
    com = {n: into[c] for n, c in com.items()}
    order = [c for c in order if into[c] == c]
    members = defaultdict(list)
    for n in sorted(nodes):
        members[com[n]].append(n)
    pair: Counter = Counter()
    for a, b in edges:
        if com[a] != com[b]:
            pair[(com[a], com[b])] += 1
            pair[(com[b], com[a])] += 1
    idx = {c: i + 1 for i, c in enumerate(order)}  # display ids c1, c2, ... by rank
    # top-level module files are named on their home line (the line holding most of their nodes)
    per_line = Counter((nodes[n][1], com[n]) for n in nodes)
    home: dict[str, int] = {}
    for (f, c), k in sorted(per_line.items()):
        if TOPLEVEL.match(f) and not f.endswith("__init__.py") and (
                f not in home or (k, -idx[c]) > (per_line[(f, home[f])], -idx[home[f]])):
            home[f] = c
    info, owner = {}, defaultdict(set)
    for c in order:
        syms: list[tuple[int, str]] = []
        for n in members[c]:
            label, file = nodes[n][0], nodes[n][1]
            base = file.rsplit("/", 1)[-1]
            for k in {base, _stem(base), *file.split("/")[:-1]}:
                owner[k.lower()].add(c)
            if not _is_file_node(label, file):
                owner[_norm_name(label)].add(c)
                if not TEST_FILE.search(file):
                    syms.append((-deg[n], label.strip().removesuffix("()").lstrip(".")))
        files = ranked_files(members[c])
        seen, top = set(), []
        for _, sym in sorted(syms):
            if sym not in seen and len(top) < 3:
                seen.add(sym)
                top.append(sym)
        names: list[str] = []
        for f in files:
            if len(names) < 3 and _base(f) not in names:
                names.append(_base(f))
        for f in files:
            if home.get(f) == c and _base(f) not in names:
                names.append(_base(f))
        links = sorted(((o, w) for (x, o), w in pair.items() if x == c), key=lambda t: (-t[1], idx[t[0]]))[:3]
        info[c] = {"size": len(members[c]), "files": names, "syms": top, "links": [(idx[o], w) for o, w in links],
                   "fileset": set(files)}  # fmt: skip
    names = {k: next(iter(v)) for k, v in owner.items() if len(v) == 1 and len(k) >= 4 and k not in GENERIC}
    file_com = {nodes[n][1]: com[n] for n in sorted(nodes)}
    return {"order": order, "idx": idx, "info": info, "names": names, "nodes": len(nodes), "n_com": len(order),
            "file_com": file_com, "repo": repo}  # fmt: skip


def _decisions(mem) -> list[tuple]:
    """(ts, episode, sentence, fragment id, ref) of the user's decisions, newest first; forgotten records left out."""
    rows = mem.s.q("SELECT COALESCE(m.ts,''), f.episode_id, f.text, f.idx, f.id, s.ref FROM frag_status s "
                   "JOIN fragments f ON f.id=s.fragment JOIN episodes e ON e.id=f.episode_id "
                   "LEFT JOIN turn_meta m ON m.episode=e.id WHERE s.status='decision' AND e.t_expired IS NULL")  # fmt: skip
    rows = sorted(rows, key=lambda r: (r[0], r[1], -r[3]), reverse=True)
    return [(ts, ep, " ".join(t.split()), fid, ref) for ts, ep, t, _, fid, ref in rows]


def _cands(tok: str) -> set[str]:
    t = tok.lower().removesuffix("()")
    base = re.split(r"[/\\]", t)[-1]
    return {t, base, _stem(base), *(p for p in re.split(r"[/\\.]", t) if p)}


def _tokens(text: str) -> list[tuple[int, set[str]]]:
    return [(m.start(), _cands(m.group(0).rstrip(".-/\\"))) for m in TOKEN.finditer(text)]


def _window(text: str, pos: int, n: int = 80) -> str:
    if len(text) <= n:
        return text
    a = max(0, min(pos - 25, len(text) - n))
    s = text[a:a + n].strip()
    return ("…" if a else "") + s + ("…" if a + n < len(text) else "")


def _date(ts: str, year: str) -> str:
    return ts[5:10] if ts[:4] == year else ts[:10] or "?"


def _link(mem, cm: dict, decs: list[tuple], root: Path | None) -> dict[int, list[tuple]]:
    """Each decision to the community with most votes (names + its report's commit); newest first per community."""
    toks = [_tokens(d[2]) for d in decs]
    freq: Counter = Counter()
    for tk in toks:
        freq.update({k for _, cs in tk for k in cs})
    cap = max(3, 0.05 * len(decs))
    names = {k: c for k, c in cm["names"].items() if freq[k] <= cap}
    shown: dict[str, list[str]] = {}
    per: dict[int, list[tuple]] = defaultdict(list)
    for (ts, ep, text, fid, ref), tk in zip(decs, toks, strict=True):
        votes: Counter = Counter()
        first: dict[int, int] = {}
        for pos, cs in tk:
            for k in sorted(cs & names.keys()):
                votes[names[k]] += 1
                first.setdefault(names[k], pos)
        commit = ""
        if cm["repo"] and "yes" in ref.split("+"):
            try:
                done = mem.done_for(ep, fid)
            except Exception:  # noqa: BLE001 - a store without vectors: no commit path
                done = None
            h = HASH.search((done or {}).get("commit") or "")
            if h:
                h = h.group(0)
                if h not in shown:
                    shown[h] = [x.strip().replace("\\", "/").lower() for x in
                                _git(root, "show", "--name-only", "--format=", h).splitlines() if x.strip()]  # fmt: skip
                cnt = Counter(cm["file_com"][f] for f in shown[h] if f in cm["file_com"])
                if 1 <= sum(cnt.values()) <= 15:
                    tied = [c for c in cnt if cnt[c] == max(cnt.values())]
                    if len(tied) > 1:  # a tie: only to a tied community that also has a name match, else no vote
                        tied = sorted((c for c in tied if votes[c]), key=lambda c: (-votes[c], cm["idx"][c]))[:1]
                    if tied:
                        votes[tied[0]] += 1
                        commit = h[:7]
        if not votes:
            continue
        c = max(votes, key=lambda x: (votes[x], -cm["idx"][x]))
        if len(per[c]) < 2:
            per[c].append((ts, ep, text, first.get(c), commit if c not in first else ""))
    return per


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
    """Drop in the fixed order until the text fits (chars <= max_chars AND tokens <= MAX_TOKENS): second decisions
    (lowest-ranked first) -> symbols -> links -> whole lines from the bottom (into "+N more"); then the "+N more" line
    takes as many names as still fit (folded first); a text that still does not fit is cut."""

    def fits(t: str) -> bool:
        return len(t) <= max_chars and _ntok(t) <= MAX_TOKENS

    hidden = len(rest)
    text = _render(head, items, [], hidden, hint)
    for field in ("k", "syms", "links"):
        for it in reversed(items):
            while not fits(text) and (it[field] if field != "k" else it["k"] > 1):
                if field == "k":
                    it["k"] -= 1
                else:
                    it[field] = it[field][:-1]
                text = _render(head, items, [], hidden, hint)
    folded: list[str] = []
    while not fits(text) and len(items) > 1:
        folded.insert(0, items.pop()["short"])
        hidden += 1
        text = _render(head, items, [], hidden, hint)
    names: list[str] = []
    for nm in folded + rest:
        if not fits(_render(head, items, names + [nm], hidden, hint)):
            break
        names.append(nm)
    text = _render(head, items, names, hidden, hint)
    while not fits(text) and len(text) > 1:
        text = text[:max(1, min(len(text), max_chars) - 20)].rstrip() + "…"
    return text


def _line(it: dict) -> str:
    return (f"#c{it['n']} {', '.join(it['files'])}" + (" — " + ", ".join(it["syms"]) if it["syms"] else "")
            + (" | ↔ " + ", ".join(f"c{o} ({w})" for o, w in it["links"]) if it["links"] else ""))  # fmt: skip


def overview(mem, max_chars: int = MAX_CHARS) -> str:
    """The project map (see the module doc). `mem`: a ProjectMemory."""
    decs = _decisions(mem)
    year = max((d[0][:4] for d in decs), default="")
    root = Path(mem.project) if getattr(mem, "project", None) else None
    cm = _code_map(mem.s.db, root)
    if not cm:
        return _topics_view(mem, decs, year, max_chars)
    per = _link(mem, cm, decs, root)
    items = []
    for c in cm["order"][:MAX_SHOWN]:
        i = cm["info"][c]
        dec = [f"{_date(ts, year)} {_window(text, pos or 0)}" + (f" → {h}" if h else "") + f" (#{mem._id(ep)})"
               for ts, ep, text, pos, h in per[c]]  # fmt: skip
        items.append({"files": i["files"], "syms": list(i["syms"]), "links": list(i["links"]), "dec": dec,
                      "k": len(dec), "short": i["files"][0], "n": cm["idx"][c], "line": _line})  # fmt: skip
    rest = [cm["info"][c]["files"][0] for c in cm["order"][MAX_SHOWN:]]
    head = (f"Project map: {cm['n_com']} code areas, {cm['nodes']} nodes (Graphify; #cN by rank: entry points, "
            "PageRank, recent commits; ↔ edges; expand(#id) = a record)")
    return _fit(head, items, rest, "", max_chars)


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
    for ts, ep, text, _, _ in decs:
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
