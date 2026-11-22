"""Data for «Живая память»: records with status and topic, and the two trees (chat sessions with their side sessions,
Graphify code by folder and file) for the 3D view.

Read-only over the store: SQL plus `Topics` (topics.py, the same Leiden topics recall and expand use).
A record = a user turn that is not forgotten, with the assistant's report that closed it. Its status, one per record
(first that holds): "change" - one of its sentences replaces an earlier decision (the `supersedes` table);
"later" - a held decision; "decision" - a decision / confirmation / pinned rule of the user; "report" - the
assistant's report of done work closed it; "" - anything else (a question, a status message).
"""

from __future__ import annotations

from collections import Counter, defaultdict

STATUSES = ("decision", "change", "report", "later")
MAX_TOPICS = 16  # more topics -> the smallest ones are merged into one "other topics" stream / branch
PALETTE = ["#8b7fd6", "#4fa58a", "#d39a4a", "#c96a62", "#5b9ac7", "#b878a8", "#93ad5e", "#c98b6b", "#5fb3b3",
           "#9d86c9", "#c4ad57", "#7aa67f", "#7f9fc9", "#c47f95", "#a08c7c", "#8b98a5"]  # fmt: skip


_ART = __import__("re").compile(r"^(?:the|a|an|that|this|these|those|its|our|their)\s+", __import__("re").I)


def clean_name(name: str) -> str:
    """A topic name for display: English concept labels without a leading article ("the stats screen" -> "stats
    screen"), repeats dropped."""
    out: list[str] = []
    for part in name.split(" · "):
        x = _ART.sub("", part.strip()).strip(" '\"")
        if x and x.lower() not in {o.lower() for o in out}:
            out.append(x)
    return " · ".join(out) or name


def _cut(t: str, n: int) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def build(mem) -> dict:
    """{"records": [...], "topics": [...]} for the page; topics by number of records, the tail merged."""
    from ctxgraph.topics import Topics

    s = mem.s
    users = s.q("SELECT e.id, COALESCE(m.ts,''), e.text FROM episodes e LEFT JOIN turn_meta m ON m.episode=e.id "
                "WHERE e.role='user' AND e.t_expired IS NULL ORDER BY m.ts, e.id")  # fmt: skip
    st = defaultdict(list)  # episode -> [(status, ref, text)]
    for ep, status, ref, text in s.q("SELECT f.episode_id, s.status, s.ref, f.text FROM frag_status s "
                                     "JOIN fragments f ON f.id=s.fragment ORDER BY f.episode_id, f.idx"):  # fmt: skip
        st[ep].append((status, ref or "", text))
    ep_of = lambda f: f.split(":")[1] if f.count(":") >= 2 else f  # noqa: E731 - "f:<episode>:<idx>"
    rep, by = defaultdict(set), defaultdict(set)
    for new_f, old_f in s.q("SELECT new_fragment, old_fragment FROM supersedes"):
        a, b = ep_of(new_f), ep_of(old_f)
        if a != b:
            rep[a].add(b)
            by[b].add(a)
    try:
        finals = mem._finals()  # report episode -> (the user turn it closes, session)
    except Exception:  # noqa: BLE001 - the view still draws without reports
        finals = {}
    report_of = {u: r for r, (u, _) in finals.items() if u}
    try:
        tp = Topics(s)
    except Exception:  # noqa: BLE001 - no networkx / an empty graph: no topics
        tp = None
    alive = {e for e, _, _ in users}
    recs = []
    for e, ts, text in users:
        if not ts:
            continue
        mine, r = st.get(e, []), report_of.get(e)
        rs = [x for x in st.get(r, []) if x[0] in ("applied", "report")] if r else []
        refs = {p for x in mine if x[0] == "decision" for p in x[1].split("+") if p}
        if rep.get(e, set()) & alive:
            status = "change"
        elif "hold" in refs:
            status = "later"
        elif refs or any(x[0] in ("confirm", "closed", "rule") for x in mine):
            status = "decision"
        elif rs:
            status = "report"
        else:
            status = ""
        want = ("decision", "rule", "confirm", "closed")
        gist = next((x[2] for x in mine if x[0] in want), "") or text
        k = tp.of_record([e] + ([r] if r else [])) if tp else None
        recs.append({"id": e[:8], "ts": ts[:19], "d": ts[:10], "st": status, "topic": -1 if k is None else k,
                     "t": _cut(gist, 240), "rep": _cut(rs[0][2], 200) if rs else "",
                     "chg": sorted(x[:8] for x in rep.get(e, set()) & alive),
                     "by": sorted(x[:8] for x in by.get(e, set()) & alive)})  # fmt: skip
    cnt = Counter(r["topic"] for r in recs if r["topic"] >= 0)
    top = [k for k, _ in sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))]
    keep, rest = top[:MAX_TOPICS], set(top[MAX_TOPICS:])
    idx = {k: i for i, k in enumerate(keep)}
    other = len(keep) if rest else None
    for r in recs:  # topics renumbered 0..n-1 by size; merged tail = n; no topic = -1
        r["topic"] = idx.get(r["topic"], other if r["topic"] in rest else -1)
    topics = []
    for k in keep:
        rs = [r for r in recs if r["topic"] == idx[k]]
        topics.append({"id": idx[k], "name": clean_name(tp.name.get(k, "")) or f"тема {idx[k] + 1}", "n": len(rs),
                       "last": max(r["d"] for r in rs), "first": min(r["d"] for r in rs),
                       "color": PALETTE[idx[k] % len(PALETTE)]})  # fmt: skip
    if rest:
        rs = [r for r in recs if r["topic"] == other]
        topics.append({"id": other, "name": f"другие темы ({len(rest)})", "merged": len(rest), "n": len(rs), "last": max(r["d"] for r in rs),
                       "first": min(r["d"] for r in rs), "color": "#7d7d86", "other": True})  # fmt: skip
    return {"records": recs, "topics": topics}


def trees(mem, rec_status: dict[str, str] | None = None, max_code: int = 4000) -> dict:
    """Two trees for «Живая память». Chats: one branch per chat session (by its first turn), its turns as beads; a
    session started by another one (turn_agent: a brief / host first turn - side sessions, subagents) is an offshoot of
    its parent: the brief's parent session when it is in the store, else the main session with the most turns within
    12 h of its start. Code (Graphify, if imported): a branch per top folder, a twig per file, its symbols as beads;
    vendored and minified files are left out."""
    import datetime as dt

    s = mem.s
    rows = s.q("SELECT m.episode, m.session, m.ts, e.role, e.text FROM turn_meta m JOIN episodes e ON e.id=m.episode "
               "WHERE e.t_expired IS NULL AND m.ts != '' ORDER BY m.ts, m.episode")  # fmt: skip
    st = rec_status or {}
    by = defaultdict(list)
    for e, ss, ts, role, text in rows:
        by[ss].append((e, ts, role, text))
    agent = defaultdict(set)
    try:
        for e, kind, parent in s.q("SELECT a.episode, a.kind, a.parent FROM turn_agent a"):
            agent[e].add((kind, parent or ""))
    except Exception:  # noqa: BLE001 - an older store without the table
        pass
    first_of = {ss: v[0] for ss, v in by.items()}
    side = {ss for ss, v in by.items() if any(k in ("brief", "host") for k, _ in agent.get(v[0][0], ()))}
    main = [ss for ss in by if ss not in side]

    def t(x: str) -> float:
        try:
            return dt.datetime.fromisoformat(x.replace("Z", "+00:00")).timestamp()
        except ValueError:
            return 0.0

    parent = {}
    for ss in side:
        e0, ts0, _, _ = first_of[ss]
        p = next((pp for k, pp in agent.get(e0, ()) if k == "brief" and pp in by and pp != ss), None)
        if p is None and main:
            near = {m: sum(1 for _, ts, _, _ in by[m] if abs(t(ts) - t(ts0)) < 12 * 3600) for m in main}
            p = max(main, key=lambda m: (near[m], -abs(t(first_of[m][1]) - t(ts0))))
        parent[ss] = p
    order = sorted(by, key=lambda ss: first_of[ss][1])
    idx = {ss: i for i, ss in enumerate(order)}
    sessions, turns = [], []
    for ss in order:
        v = by[ss]
        lab = next((x[3] for x in v if x[2] == "user"), v[0][3])
        sessions.append({"id": ss[:12], "n": len(v), "first": v[0][1][:19], "last": v[-1][1][:19], "label": _cut(lab, 60),
                         "side": ss in side, "parent": idx.get(parent.get(ss), -1),
                         "src": "claude.ai" if ss.startswith("claude.ai") else "cc"})  # fmt: skip
        for e, ts, role, text in v:
            turns.append([e[:8], idx[ss], ts[:19], "u" if role == "user" else "a", st.get(e[:8], ""), _cut(text, 140)])
    code = []
    try:
        nodes = s.q("SELECT label, file, loc FROM code_nodes WHERE file != '' ORDER BY file, loc, label")
    except Exception:  # noqa: BLE001 - no Graphify layer
        nodes = []
    nodes = [n for n in nodes if "/vendor/" not in "/" + n[1] and not n[1].endswith(".min.js")][:max_code]
    dirs: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    top1 = Counter(f.split("/", 1)[0] if "/" in f else "." for _, f, _ in nodes)
    # a folder holding most of the code (app/, src/) is split one level deeper, so its parts are branches of their own
    deep = {d for d, n in top1.items() if n > 0.4 * len(nodes) and len({f.split("/")[1] for _, f, _ in nodes if f.count("/") >= 2 and f.startswith(d + "/")}) >= 2}
    for label, f, loc in nodes:
        parts = f.split("/")
        top = "/".join(parts[:2]) if parts[0] in deep and len(parts) >= 3 else parts[0] if len(parts) > 1 else "."
        dirs[top][f].append([_cut(label, 60), loc])
    for d, files in sorted(dirs.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
        code.append({"name": d, "n": sum(len(v) for v in files.values()),
                     "files": [{"name": f, "nodes": v} for f, v in sorted(files.items(), key=lambda kv: -len(kv[1]))]})  # fmt: skip
    return {"sessions": sessions, "turns": turns, "code": code}
