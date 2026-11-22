"""Obsidian-style HTML view of a project's memory graph.

Topics = Louvain communities of concepts; concepts shared by several topics are drawn in their topics' colours.
Per topic: what memory recall returns for it (the same `ProjectMemory.recall` the assistant gets) and the user's
decisions about it, split into "decided to do" / "decided not to do" (cue-word rules over the user's own sentences,
no LLM; labelled as such in the UI). The HTML embeds conversation text: a LOCAL file only."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from pathlib import Path

from ctxgraph.flow import clean_name
from ctxgraph.memory import clause_kinds

# units and filler words that co-occur with everything in chat about experiments (would become hubs)
STOP = {"ответ", "млн", "тыс", "часов", "часа", "час", "минут", "минуты", "секунд", "дней", "день", "раз", "строка",
        "строки", "вариант", "вопрос", "вопросы", "пункт", "шаг", "число", "итог", "файл", "проект", "сейчас", "так",
        "ок", "ok", "да", "нет", "вывод", "таблица", "место", "часть", "конец", "начало", "%", "п.п", "пп"}
# muted, distinguishable on dark and light backgrounds
PALETTE = ["#8b7fd6", "#4fa58a", "#d39a4a", "#c96a62", "#5b9ac7", "#b878a8", "#93ad5e", "#c98b6b", "#5fb3b3", "#9d86c9",
           "#c4ad57", "#7aa67f", "#7f9fc9", "#c47f95", "#a08c7c", "#8b98a5"]
# a user's sentence is a decision if it has one of these cues (questions excluded); negative cues win



def export_html(mem, top: int = 700, out: Path | None = None, mode: str | None = None, live: bool = False) -> Path:
    """mode: "2d" / "3d" / "cosmos" / "live", or None to open the mode last used in the page (localStorage)."""
    import networkx as nx

    s = mem.s
    name = mem.project.name
    meta = {e: {"ts": ts, "role": r, "session": ss} for e, ts, r, ss in s.q(
        "SELECT m.episode, m.ts, e.role, m.session FROM turn_meta m JOIN episodes e ON e.id=m.episode")}
    n_frag = s.q("SELECT COUNT(*) FROM fragments WHERE kind='sentence'")[0][0]
    ep_of = dict(s.q("SELECT id, episode_id FROM fragments"))
    # concepts: frequent enough to matter, not so frequent that they are hubs (in > 6 % of sentences)
    cons = s.q("SELECT id, label, kind, n_fragments FROM concepts WHERE n_fragments >= 3 AND n_fragments <= ? "
               "ORDER BY n_fragments DESC, id", (max(8, int(0.025 * n_frag)),))  # fmt: skip
    cons = [c for c in cons if c[1].lower() not in STOP and not c[1].isdigit() and len(c[1]) > 1][:top]
    keep = {c[0] for c in cons}
    G = nx.Graph()
    for c, lab, kind, n in cons:
        G.add_node(c, label=lab, kind=kind, n=n)
    for a, b, rel, w, ti in s.q("SELECT src, dst, rel, weight, t_invalid FROM edges WHERE rel IN ('cooccur','synonym')"):
        if a in keep and b in keep and a != b:
            ww = math.log1p(w) if rel == "cooccur" else 0.5 * w
            if G.has_edge(a, b):
                G[a][b]["weight"] += ww
            else:
                G.add_edge(a, b, weight=ww, rel=rel, invalid=ti is not None)
    G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
    comms = nx.community.louvain_communities(G, weight="weight", resolution=1.1, seed=0)
    comms = sorted([c for c in comms if len(c) >= 3], key=len, reverse=True)
    comm_of = {n: i for i, c in enumerate(comms) for n in c}
    topics = []
    for i, c in enumerate(comms):
        lead = sorted(c, key=lambda n: -G.degree(n, weight="weight"))[:3]
        topics.append({"id": i, "name": clean_name(" · ".join(G.nodes[n]["label"] for n in lead)), "size": len(c),
                       "color": PALETTE[i % len(PALETTE)]})  # fmt: skip
    # quotes, dates, sessions per concept
    frags = defaultdict(list)
    for cid_, fid, text, seq in s.q("SELECT m.concept_id, f.id, f.text, f.seq FROM mentions m JOIN fragments f "
                                    "ON f.id=m.fragment_id ORDER BY f.seq"):  # fmt: skip
        if cid_ in G:
            frags[cid_].append((fid, text, seq))
    nodes = []
    for n in G:
        k = G.degree(n, weight="weight")
        share = Counter()
        for m in G[n]:
            if m in comm_of:
                share[comm_of[m]] += G[n][m]["weight"]
        if n in comm_of:
            share[comm_of[n]] += 0.0
        tot = sum(share.values()) or 1.0
        part = 1 - sum((v / tot) ** 2 for v in share.values())  # participation coefficient
        main = [t for t, v in share.most_common() if v / tot >= 0.3][:3]
        fl = frags[n]
        tss = sorted(meta.get(ep_of.get(f[0], ""), {}).get("ts", "") for f in fl)
        tss = [t for t in tss if t]
        quotes = []
        for fid, text, _ in fl[-6:]:
            m_ = meta.get(ep_of.get(fid, ""), {})
            quotes.append({"t": text[:280], "ts": m_.get("ts", "")[:10], "role": m_.get("role", "")})
        nodes.append({"id": n, "label": G.nodes[n]["label"], "n": G.nodes[n]["n"], "deg": round(k, 2),
                      "topic": comm_of.get(n, -1), "bridge": len(main) >= 2 and part >= 0.55, "topics": main,
                      "part": round(part, 2), "first": tss[0][:10] if tss else "", "last": tss[-1][:10] if tss else "",
                      "sessions": len({meta.get(ep_of.get(f[0], ""), {}).get("session") for f in fl}), "quotes": quotes,
                      "origin": "conversation"})  # fmt: skip
    links = [{"source": a, "target": b, "w": round(d["weight"], 2), "rel": d["rel"], "invalid": d["invalid"],
              "origin": "conversation"} for a, b, d in G.edges(data=True)]  # fmt: skip
    # the code layer imported from Graphify (`ctxgraph import-graphify`), if any: origin "code" / "inferred"
    from ctxgraph.graphify import layer

    code = layer(mem.db_path, set(G), cap=600)
    nodes += code["nodes"]
    links += code["links"]
    # decisions: the user's own sentences with decision cues, attached to the topic of their concepts
    topic_of_frag: dict[str, Counter] = defaultdict(Counter)
    for cid_, fid in s.q("SELECT concept_id, fragment_id FROM mentions"):
        if cid_ in comm_of:
            topic_of_frag[fid][comm_of[cid_]] += 1
    decisions = []
    for fid, text, ep in s.q("SELECT f.id, f.text, f.episode_id FROM fragments f JOIN episodes e ON e.id=f.episode_id "
                             "WHERE e.role='user' AND e.t_expired IS NULL AND f.kind='sentence' ORDER BY f.seq"):  # fmt: skip
        t = text.strip()
        if not (15 <= len(t) <= 320) or t.endswith("?"):
            continue
        kinds = clause_kinds(t)
        if not kinds:
            continue
        tv = topic_of_frag.get(fid)
        kind = "yes" if "yes" in kinds else "no" if "no" in kinds else "hold"
        decisions.append({"t": t, "ts": meta.get(ep, {}).get("ts", "")[:10], "kind": kind,
                          "topic": tv.most_common(1)[0][0] if tv else -1})  # fmt: skip
    # what recall returns for each topic (the assistant gets the same block)
    for tp in topics:
        lead = sorted(comms[tp["id"]], key=lambda n: -G.degree(n, weight="weight"))
        tp["concepts"] = [{"id": n, "label": G.nodes[n]["label"], "n": G.nodes[n]["n"]} for n in lead[:14]]
        tp["query"] = " ".join(G.nodes[n]["label"] for n in lead[:5])
        try:
            hits = mem.recall(tp["query"], k=5)
        except Exception:  # noqa: BLE001 - the view must still render without the model
            hits = []
        tp["recall"] = [{"ts": h.ts[:10], "role": h.role, "t": h.sentence[:260], "ep": h.episode[:8]} for h in hits]
        tp["n_mentions"] = sum(G.nodes[n]["n"] for n in comms[tp["id"]])
    counts = s.counts()
    data = {"name": name, "topics": topics, "nodes": nodes, "links": links, "decisions": decisions, "mode": mode or "",
            "code": code["meta"],
            "stats": {"turns": len(meta), "sentences": n_frag, "concepts": counts.get("concepts"),
                      "shown": len(nodes) - len(code["nodes"]), "bridges": sum(x.get("bridge", False) for x in nodes),
                      "from": min((v["ts"] for v in meta.values() if v["ts"]), default="")[:10],
                      "to": max((v["ts"] for v in meta.values() if v["ts"]), default="")[:10]},
            "daily": dict(sorted(Counter(v["ts"][:10] for v in meta.values() if v["ts"]).items()))}  # fmt: skip
    # «Живая память»: records by topic and status, the chat and code trees (flow.py), the MCP call log (calls.py: ids only)
    from ctxgraph import calls as CL
    from ctxgraph.flow import build as flow_build
    from ctxgraph.flow import trees as flow_trees

    data["flow"] = flow_build(mem)
    data["trees"] = flow_trees(mem, {r["id"]: r["st"] for r in data["flow"]["records"]})
    data["calls"] = CL.read_calls(mem.dir)
    data["live"], data["offset"] = bool(live), CL.size(mem.dir)
    html = render(data)
    out = Path(out) if out else mem.dir / "graph.html"
    out.write_text(html, "utf-8")
    return out


def _lib(name: str) -> str:
    """A vendored library with its license text in front (MIT / ISC, vendor/<name>.LICENSE): the page works offline."""
    here = Path(__file__).parent / "vendor"
    lic = (here / f"{name}.LICENSE").read_text("utf-8").replace("*/", "* /")
    return f"/*! {name} - license:\n{lic}\n*/\n" + (here / f"{name}.min.js").read_text("utf-8")


def render(data: dict) -> str:
    here = Path(__file__).parent
    html = (here / "viewer_template.html").read_text("utf-8").replace("/*__I18N__*/", (here / "viewer_i18n.js").read_text("utf-8"))
    html = html.replace("/*__FORCE_GRAPH__*/", _lib("force-graph"))
    html = html.replace("/*__FORCE_GRAPH_3D__*/", _lib("3d-force-graph"))
    html = html.replace("/*__THREE__*/", _lib("three"))  # MIT, the 3D «Живая память»
    html = html.replace("/*__COSMOS__*/", (here / "viewer_cosmos.js").read_text("utf-8"))  # the cosmic mode, plain Canvas 2D
    html = html.replace("/*__FLOW__*/", (here / "viewer_flow.js").read_text("utf-8"))  # «Живая память»
    return html.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False).replace("</", r"<\/"))


def serve(mem, port: int = 8765, mode: str = "live", on_ready=None) -> None:
    """`ctxgraph view --live`: the page and the call log on 127.0.0.1 only (stdlib HTTP server, no other files).
    GET / - the page (built once at start); GET /calls?offset=N - calls appended after byte N of calls.jsonl:
    {"offset": new offset, "calls": [...]} (ids and durations, never text). Ctrl+C stops it."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from urllib.parse import parse_qs, urlparse

    from ctxgraph import calls as CL

    tmp = export_html(mem, out=mem.dir / "graph_live.html", mode=mode, live=True)
    page, folder = tmp.read_bytes(), mem.dir

    class H(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802 - the stdlib name
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                body, kind = page, "text/html; charset=utf-8"
            elif u.path == "/calls":
                try:
                    off = int((parse_qs(u.query).get("offset") or ["0"])[0])
                except ValueError:
                    off = 0
                new, cs = CL.read_from(folder, off)
                body, kind = json.dumps({"offset": new, "calls": cs}).encode(), "application/json"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):  # quiet
            pass

    srv = None
    for p in (port, *range(port + 1, port + 20), 0):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), H)
            break
        except OSError:
            continue
    url = f"http://127.0.0.1:{srv.server_address[1]}/"
    if on_ready:
        on_ready(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
