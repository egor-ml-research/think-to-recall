"""Token economy of recall (rules written before the code): (a) one line when nothing is about the question,
(b) no repeats within one MCP session, (c) a query-matched gist in one-line records, (d) compact labels.
Synthetic projects only, offline (BM25)."""

import datetime as dt
import re

from ctxgraph import memory_mcp
from ctxgraph.memory import ProjectMemory, economy_flags

Y = str(dt.date.today().year)


def _t(i, role, text, ts, session):
    return {"id": f"t{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


EN = [
    _t(1, "user", "We are building a table booking service. For the database we will use Postgres.", f"{Y}-01-03T10:00:00Z", "s1"),
    _t(2, "assistant", "Created the Postgres schema with Alembic migrations, commit 3f2a1b9.", f"{Y}-01-03T10:20:00Z", "s1"),
    _t(3, "user", "API keys always go only in .env, never in logs or reports.", f"{Y}-01-04T09:00:00Z", "s2"),
    _t(4, "assistant", "Understood, keys stay in .env.", f"{Y}-01-04T09:01:00Z", "s2"),
    _t(5, "user", "No, I changed my mind: the load is small, we switch from Postgres to SQLite.", "2025-12-10T15:00:00Z", "s4"),
    _t(6, "assistant", "Switched to SQLite: migrations rewritten, data moved, tests 48/48 pass, commit 9c4e7d2.",
       "2025-12-10T15:40:00Z", "s4"),
]
RU = [
    _t(1, "user", "Для бота клиники берём Telegram. Хостинг оставляем на Hetzner, а платежи через ЮKassa.",
       f"{Y}-02-01T10:00:00Z", "s1"),
    _t(2, "assistant", "Бот на Telegram создан, коммит 1a2b3c4.", f"{Y}-02-01T10:30:00Z", "s1"),
]


def _mem(tmp_path, monkeypatch, turns, eco="a,b,c,d"):
    monkeypatch.setenv("CTXGRAPH_ECONOMY", eco)
    monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    monkeypatch.delenv("CTXGRAPH_LANG", raising=False)
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(turns)
    return m


def test_flags():
    assert economy_flags("off") == set() and economy_flags("all") == {"a", "b", "c", "d"}
    assert economy_flags("a, d,x") == {"a", "d"}


def test_a_one_line_when_nothing_is_about_the_question(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, EN)
    out = m.render(m.recall("Which font did the client approve for the bakery landing page?", k=6))
    assert out.endswith("Nothing in memory on this question.") and "Memories from earlier" not in out
    assert "API keys always go only in .env" in out  # the pinned rules stay
    out = m.render(m.recall("Which database did we choose?", k=6))  # "choose" is absent from the store
    assert "Memories from earlier" in out and "SQLite" in out
    # a step can bring the block back: the record it finds may sit on the main line
    out = m.render(m.recall("What should I do next?", ["database migrations to SQLite"], k=6))
    assert "Memories from earlier" in out
    off = _mem(tmp_path / "off", monkeypatch, EN, eco="off")
    assert "Memories from earlier" in off.render(off.recall("Which font for the bakery landing page?", k=6))


def test_b_no_repeats_within_a_session_and_fresh(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, EN)
    monkeypatch.setattr(memory_mcp, "_mem", m)
    first = memory_mcp.recall("Which database did we choose?", detail="brief")
    assert "shown earlier" not in first and "SQLite" in first
    again = memory_mcp.recall("Which database did we choose?", detail="brief")
    stubs = re.findall(r"^- #(\w+) \(shown earlier\): \d\d-\d\d · .+$", again, re.M)
    assert stubs and "Switched to SQLite" not in again
    assert "Switched to SQLite" in m.expand(stubs[0])  # expand still gives the record in full
    assert "shown earlier" not in memory_mcp.recall("Which database did we choose?", detail="brief", fresh=True)
    # the CLI path (no session) never stubs
    cli = _mem(tmp_path / "cli", monkeypatch, EN)
    h = cli.recall("Which database did we choose?", k=6)
    assert cli.render(h) == cli.render(cli.recall("Which database did we choose?", k=6))


def test_c_gist_matches_the_question(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, RU)
    out = m.render(m.recall("Через что принимаем платежи?", k=6), detail="brief")
    assert "платежи через ЮKassa" in out
    plain = _mem(tmp_path / "p", monkeypatch, RU, eco="a,d")
    out = plain.render(plain.recall("Через что принимаем платежи?", k=6), detail="brief")
    assert "Для бота клиники берём Telegram" in out  # without (c): the first decision sentence


def test_d_compact_labels_and_expand_by_short_id(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, EN)
    out = m.render(m.recall("database Postgres SQLite migrations", k=6), detail="brief")
    assert "- 01-03 · decision · " in out  # this year: no year; short status words
    assert "2025-12-10" in out  # another year: in full
    ids = re.findall(r"#(\w+)", out.split("Memories from earlier", 1)[1])
    assert ids and all(len(i) <= 8 for i in ids)  # synthetic ids are short already; real ones: 4-8
    for i in ids:
        assert "No record" not in m.expand(i)
    full = m.render(m.recall("database Postgres SQLite migrations", k=6))
    assert re.search(r"\[01-03 · decision · #\w{4,8}\]", full) and "→ report 01-03, commit 3f2a1b9" in full \
        or "→ done 01-03, commit 3f2a1b9" in full


def test_d_topic_shown_once_in_a_row(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, EN)
    lines = ["- 01-01 · decision · topic: db · #aaaa: x", "- 01-02 · decision · topic: db · #bbbb: y",
             "- 01-03 · decision · topic: api · #cccc: z"]
    assert m._dedupe_topics(lines) == ["- 01-01 · decision · topic: db · #aaaa: x", "- 01-02 · decision · #bbbb: y",
                                       "- 01-03 · decision · topic: api · #cccc: z"]


def test_b_shown_records_reset_on_compaction_and_new_session(tmp_path, monkeypatch):
    import ctxgraph.memory as MM

    m = _mem(tmp_path, monkeypatch, EN)
    tdir = tmp_path / "transcripts"
    tdir.mkdir()
    monkeypatch.setattr(MM, "claude_project_dir", lambda p: tdir)
    monkeypatch.setattr(memory_mcp, "_mem", m)
    s1 = tdir / "s1.jsonl"
    s1.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n', "utf-8")
    q = "Which database did we choose?"
    assert "shown earlier" not in memory_mcp.recall(q, detail="brief")
    assert "shown earlier" in memory_mcp.recall(q, detail="brief")
    with open(s1, "a", encoding="utf-8") as f:  # the context was compacted
        f.write('{"type":"user","isCompactSummary":true,"message":{"role":"user","content":"This session is being '
                'continued from a previous conversation"}}\n')
    assert "shown earlier" not in memory_mcp.recall(q, detail="brief")
    assert "shown earlier" in memory_mcp.recall(q, detail="brief")
    import os, time

    s2 = tdir / "s2.jsonl"  # a new session: a newer transcript
    s2.write_text('{"type":"user","message":{"role":"user","content":"hi"}}\n', "utf-8")
    t = time.time() + 5
    os.utime(s2, (t, t))
    assert "shown earlier" not in memory_mcp.recall(q, detail="brief")
