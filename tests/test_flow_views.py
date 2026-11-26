"""«Волны» / «Живая память»: the MCP call log (calls.py), the data builder (flow.py), the page and `view --live`.
Synthetic data only."""

from __future__ import annotations

import datetime as dt
import json
import threading
import urllib.request

import pytest

from cotrail import calls as CL
from cotrail.embed import HashingEncoder
from cotrail.memory import ProjectMemory


def test_log_line_has_ids_and_duration_only(tmp_path):
    t = dt.datetime(2026, 11, 1, 12, 0, tzinfo=dt.UTC)
    CL.log_call(tmp_path, "recall", "секретный текст #1a2b3c4d: ... #0f0f0f0f, #1a2b3c4d again, #t3 topic", 12.6, now=t)
    raw = (tmp_path / "calls.jsonl").read_text("utf-8")
    assert "секрет" not in raw and "topic" not in raw
    c = json.loads(raw)
    assert c == {"t": "2026-11-01T12:00:00.000Z", "tool": "recall", "ids": ["1a2b3c4d", "0f0f0f0f"], "ms": 13}
    assert CL.read_calls(tmp_path) == [c]


def test_log_rotates_and_is_bounded(tmp_path, monkeypatch):
    monkeypatch.setattr(CL, "MAX_BYTES", 300)
    for i in range(40):
        CL.log_call(tmp_path, "expand", f"Record #{i:08x}", i)
    assert (tmp_path / "calls.1.jsonl").exists()
    assert (tmp_path / "calls.jsonl").stat().st_size < 300 + 100
    assert (tmp_path / "calls.1.jsonl").stat().st_size < 300 + 100
    got = CL.read_calls(tmp_path)
    assert got[-1]["ids"] == [f"{39:08x}"] and len(got) < 40  # the oldest part was dropped


def test_log_never_raises(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    CL.log_call(f / "sub", "recall", "#abcdabcd", 1)  # the folder is a file: swallowed
    CL.log_call(tmp_path, "recall", None, 1)  # a non-text result: no ids
    assert CL.read_calls(tmp_path)[0]["ids"] == []


def test_read_from_offset_skips_half_lines_and_follows_rotation(tmp_path):
    CL.log_call(tmp_path, "recall", "#aaaaaaaa", 1)
    off, cs = CL.read_from(tmp_path, 0)
    assert [c["ids"] for c in cs] == [["aaaaaaaa"]] and off == CL.size(tmp_path)
    with (tmp_path / "calls.jsonl").open("a", encoding="utf-8") as f:
        f.write('{"t": "2026-11-01T00:00:00Z", "tool": "rec')  # being written
    assert CL.read_from(tmp_path, off) == (off, [])
    (tmp_path / "calls.jsonl").write_text("")
    CL.log_call(tmp_path, "expand", "#bbbbbbbb", 2)
    off2, cs = CL.read_from(tmp_path, off + 999)  # the file is shorter than the offset: rotated, read from 0
    assert [c["tool"] for c in cs] == ["expand"] and off2 == CL.size(tmp_path)


def test_mcp_tool_logs_without_failing(tmp_path, monkeypatch):
    from cotrail import memory_mcp as MM

    class Fake:
        dir = tmp_path

    monkeypatch.setattr(MM, "_mem", Fake())
    MM._log("recall", "- 2026-11-01 · #12345678: gist", 5.0)
    assert CL.read_calls(tmp_path)[0]["ids"] == ["12345678"]
    monkeypatch.setattr(CL, "log_call", lambda *a, **k: 1 / 0)
    MM._log("recall", "x", 1.0)  # an error inside logging is swallowed


def _mem(tmp_path):
    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    turns = []
    for i, (u, a) in enumerate([
        ("Решили: данные храним в SQLite на устройстве, сервер синхронизации не нужен.", "Готово: схема SQLite, коммит 3f2a9c1."),
        ("Экспорт в CSV отложим на потом.", ""),
        ("Переходим с SQLite на устройстве на сервер синхронизации с Postgres.", "Готово: сервер с Postgres, коммит 6f12d9e."),
        ("Как считать серию?", ""),
    ]):
        ts = f"2026-11-0{i + 1}T10:00:00Z"
        turns.append({"id": f"00000000-0000-4000-8000-00000000000{i}", "session": "s1", "role": "user", "ts": ts, "text": u})
        if a:
            turns.append({"id": f"00000000-0000-4000-8000-00000000010{i}", "session": "s1", "role": "assistant",
                          "ts": ts.replace("10:00", "10:05"), "text": a})  # fmt: skip
    m.import_turns(turns)
    return m


def test_flow_records_statuses_and_change_chain(tmp_path):
    pytest.importorskip("networkx")
    from cotrail.flow import build

    d = build(_mem(tmp_path))
    st = {r["t"][:12]: r for r in d["records"]}
    assert [r["d"] for r in d["records"]] == sorted(r["d"] for r in d["records"])
    assert st["Решили: данн"]["st"] == "decision" and st["Экспорт в CS"]["st"] == "later"
    assert st["Переходим с "]["st"] == "change" and st["Как считать "]["st"] == ""
    ch, old = st["Переходим с "], st["Решили: данн"]
    assert ch["chg"] == [old["id"]] and old["by"] == [ch["id"]] and ch["rep"].startswith("Готово")
    assert all(len(r["id"]) == 8 for r in d["records"])
    assert all(-1 <= r["topic"] < len(d["topics"]) for r in d["records"])


def test_page_has_live_mode_three_license_calls_and_trees(tmp_path):
    pytest.importorskip("networkx")
    from cotrail.viewer import export_html

    m = _mem(tmp_path)
    CL.log_call(m.dir, "recall", "#00000000", 3)
    html = export_html(m, out=tmp_path / "v.html", mode="live").read_text("utf-8")
    for s in ('data-mode="live"', "const FLOW = ", "/*! three - license:", "Copyright © 2010-2023 three.js authors",
              "/*! force-graph - license:"):  # fmt: skip
        assert s in html, s
    assert "/*__THREE__*/" not in html and "/*__FLOW__*/" not in html and 'data-mode="waves"' not in html
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst $", 1)[0].replace("<\\/", "</"))
    assert data["mode"] == "live" and data["live"] is False and len(data["calls"]) == 1
    tr = data["trees"]
    assert len(tr["sessions"]) == 1 and len(tr["turns"]) == 6 and tr["code"] == []
    assert {t[3] for t in tr["turns"]} == {"u", "a"} and all(t[1] == 0 for t in tr["turns"])
    assert data["offset"] == CL.size(m.dir) and data["flow"]["records"]


def test_view_live_serves_page_and_calls_on_localhost(tmp_path):
    pytest.importorskip("networkx")
    from cotrail.viewer import serve

    m = _mem(tmp_path)
    got = {}
    ready = threading.Event()
    th = threading.Thread(target=serve, args=(m,), kwargs={"port": 0, "on_ready": lambda u: (got.update(url=u), ready.set())},
                          daemon=True)  # fmt: skip
    th.start()
    assert ready.wait(120)
    url = got["url"]
    assert url.startswith("http://127.0.0.1:")
    page = urllib.request.urlopen(url, timeout=10).read().decode("utf-8")
    assert '"live": true' in page
    CL.log_call(m.dir, "expand", "Record #00000000", 4)
    j = json.loads(urllib.request.urlopen(url + "calls?offset=0", timeout=10).read())
    assert [c["tool"] for c in j["calls"]] == ["expand"] and j["offset"] == CL.size(m.dir)
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(url + "graph.sqlite", timeout=10)


def test_trees_side_sessions_hang_on_their_parent(tmp_path):
    from cotrail.flow import trees

    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    turns = [{"id": f"00000000-0000-4000-8000-0000000000{i:02d}", "session": ss, "role": "user", "text": f"Сделай шаг {i} в модуле.",
              "ts": f"2026-11-0{1 + i // 3}T10:0{i % 3}:00Z"} for i, ss in enumerate(["main", "main", "main", "side", "side", "main"])]  # fmt: skip
    turns[3]["agent"] = {"kind": "brief", "parent": "main"}
    m.import_turns(turns)
    tr = trees(m)
    by = {s["id"]: s for s in tr["sessions"]}
    assert by["side"]["side"] and not by["main"]["side"]
    assert tr["sessions"][by["side"]["parent"]]["id"] == "main" and by["main"]["parent"] == -1
    assert [t[1] for t in tr["turns"]].count(tr["sessions"].index(by["side"])) == 2


def test_trees_code_by_folder_without_vendor(tmp_path):
    import sqlite3

    from cotrail.flow import trees

    m = _mem(tmp_path)
    db = sqlite3.connect(m.db_path)
    db.execute("CREATE TABLE IF NOT EXISTS code_nodes (id TEXT PRIMARY KEY, label TEXT, file TEXT, loc TEXT, file_type TEXT, community INTEGER)")
    db.executemany("INSERT INTO code_nodes VALUES (?,?,?,?,?,?)", [
        ("a", "recall", "pkg/memory.py", "L10", "code", 0), ("b", "expand", "pkg/memory.py", "L90", "code", 0),
        ("c", "main", "cli.py", "L1", "code", 0), ("v", "xY", "pkg/vendor/lib.min.js", "L2", "code", 1)])
    db.commit()
    code = trees(m)["code"]
    assert [d["name"] for d in code] == ["pkg", "."] and code[0]["files"][0]["name"] == "pkg/memory.py"
    assert [n[0] for n in code[0]["files"][0]["nodes"]] == ["recall", "expand"]


def test_clean_name_drops_articles_and_repeats():
    from cotrail.flow import clean_name

    assert clean_name("the stats screen · StreakChart · that grace day") == "stats screen · StreakChart · grace day"
    assert clean_name("SQLite · sqlite · Postgres") == "SQLite · Postgres" and clean_name("синхронизация · сервер") == "синхронизация · сервер"


def test_page_is_english_by_default_with_a_russian_switch(tmp_path):
    pytest.importorskip("networkx")
    from cotrail.viewer import export_html

    html = export_html(_mem(tmp_path), out=tmp_path / "v.html").read_text("utf-8")
    assert "/*__I18N__*/" not in html and "const I18N = " in html and 'let lang = "en";' in html
    assert 'data-lang="en"' in html and 'data-lang="ru"' in html and '"Что подскажет память": "What the assistant sees"' in html
    assert html.index("const I18N = ") < html.index("const DATA = ")  # tr() exists before the page script runs


def test_trees_split_a_dominant_folder(tmp_path):
    import sqlite3

    from cotrail.flow import trees

    m = _mem(tmp_path)
    db = sqlite3.connect(m.db_path)
    db.execute("CREATE TABLE IF NOT EXISTS code_nodes (id TEXT PRIMARY KEY, label TEXT, file TEXT, loc TEXT, file_type TEXT, community INTEGER)")
    rows = [(f"s{i}", f"f{i}", f"app/sync/f{i % 2}.py", "L1", "code", 0) for i in range(6)]
    rows += [(f"p{i}", f"g{i}", f"app/paywall/g{i % 2}.py", "L1", "code", 0) for i in range(4)] + [("t0", "t", "tests/t.py", "L1", "code", 0)]
    db.executemany("INSERT INTO code_nodes VALUES (?,?,?,?,?,?)", rows)
    db.commit()
    assert [d["name"] for d in trees(m)["code"]] == ["app/sync", "app/paywall", "tests"]
