"""Data for the «Волны» (topic streamgraph) and «Живая память» (topic tree with MCP call pulses) views.

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
        topics.append({"id": idx[k], "name": tp.name.get(k, "") or f"тема {idx[k] + 1}", "n": len(rs),
                       "last": max(r["d"] for r in rs), "first": min(r["d"] for r in rs),
                       "color": PALETTE[idx[k] % len(PALETTE)]})  # fmt: skip
    if rest:
        rs = [r for r in recs if r["topic"] == other]
        topics.append({"id": other, "name": f"другие темы ({len(rest)})", "n": len(rs), "last": max(r["d"] for r in rs),
                       "first": min(r["d"] for r in rs), "color": "#7d7d86", "other": True})  # fmt: skip
    return {"records": recs, "topics": topics}
