"""'Later' items (rules written before the code): cues, the user's "later" to a proposal, auto-close by a report,
the session line, the note next to recall, Beads read-only. Synthetic projects only."""

import json
import subprocess
import sys

from cotrail import beads
from cotrail.memory import ProjectMemory, classify, format_later


def _t(i, role, text, ts, session="s1"):
    return {"id": f"l{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


RU = [
    _t(1, "user", "Кэширование ответов через Redis оставим на потом.", "2026-11-10T10:00:00Z"),
    _t(2, "assistant", "Хорошо, кэш пока не делаю.", "2026-11-10T10:01:00Z"),
    _t(3, "user", "Сначала миграции базы, потом тесты.", "2026-11-11T10:00:00Z"),
    _t(4, "assistant", "Миграции и тесты готовы, коммит 2b3c4d5.", "2026-11-11T11:00:00Z"),
    _t(5, "user", "Сделай повторные попытки для очереди задач.", "2026-11-12T10:00:00Z"),
    _t(6, "assistant", "Повторные попытки готовы. Добавить экспорт отчётов в CSV?", "2026-11-12T11:00:00Z"),
    _t(7, "user", "потом", "2026-11-12T11:01:00Z"),
]
DONE = [
    _t(8, "user", "Теперь займись кэшированием.", "2026-11-14T10:00:00Z", "s2"),
    _t(9, "assistant", "Кэширование ответов через Redis готово, коммит 7e8f9a0.", "2026-11-14T11:00:00Z", "s2"),
]


def _mem(tmp_path, monkeypatch, turns):
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    monkeypatch.setenv("COTRAIL_LANG", "ru")
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(turns)
    return m


def test_cues():
    assert classify("user", "Кэширование ответов через Redis оставим на потом.") == ("decision", "hold")
    assert "hold" not in classify("user", "Сначала миграции базы, потом тесты.")[1]
    assert classify("user", "TODO: add rate limiting to the booking API.")[1] == "hold"
    assert classify("user", "Let's leave the Redis cache for later.")[1] == "hold"
    assert classify("user", "Вернёмся к этому позже, когда будет нагрузка.")[1] == "hold"


def test_open_items_and_session_line(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, RU)
    items = m.later()
    texts = [i["text"] for i in items]
    assert any("Redis оставим на потом" in t for t in texts)
    assert any("экспорт отчётов в CSV" in t for t in texts)  # the user's "потом" to a proposal
    assert not any("миграции базы" in t for t in texts)  # "сначала X, потом Y" is an order, not a deferral
    line = m.later_line()
    assert line.startswith("На потом — открытых пунктов: 2;") and "CSV" in line  # the newest first
    out = format_later(items)
    assert "#l7" in out and "#l1" in out


def test_shared_stems_only_propose_an_explicit_report_closes(tmp_path, monkeypatch):
    # the close rule A5: before the rule a stem match keeps the old silent close, marked unconfirmed
    old = _mem(tmp_path / "old", monkeypatch, RU + DONE)
    assert not any("Redis" in i["text"] for i in old.later())
    assert [i["closed"] for i in old.later(include_closed=True) if "Redis" in i["text"]] == [
        "by the old rule (unconfirmed) #l9"]
    import cotrail.memory as M

    monkeypatch.setattr(M, "CLOSE_RULE_SINCE", "2000-01-01")  # these reports come after the rule
    # the close rule A: >= 3 shared stems -> "looks done - confirm", the item stays open
    m = _mem(tmp_path, monkeypatch, RU + DONE)
    red = [i for i in m.later() if "Redis" in i["text"]]
    assert red and red[0]["looks_done"] == "l9" and "Похоже, сделано — подтвердите: 1." in m.later_line()
    assert "похоже, сделано" in format_later(m.later())
    done_line = [_t(10, "user", "Закрой хвосты.", "2026-11-15T10:00:00Z", "s3"),
                 _t(11, "assistant", "Готово: кэширование ответов через Redis, коммит 1a2b3c4.", "2026-11-15T11:00:00Z", "s3")]
    m3 = _mem(tmp_path / "c", monkeypatch, RU + DONE + done_line)
    assert not any("Redis" in i["text"] for i in m3.later())
    closed = [i for i in m3.later(include_closed=True) if "Redis" in i["text"]]
    assert closed[0]["closed"] == "by report #l11"
    ru = [dict(t, id="laterx77" if t["id"] == "l7" else t["id"]) for t in RU]  # real ids are 8 characters long
    by_id = [_t(12, "user", "Что с хвостами?", "2026-11-16T10:00:00Z", "s4"),
             _t(13, "assistant", "Пункт #laterx77 закрыт в коммите 9f8e7d6.", "2026-11-16T11:00:00Z", "s4")]
    mention = [_t(12, "user", "Что с хвостами?", "2026-11-16T10:00:00Z", "s4"),
               _t(13, "assistant", "В память добавлен пункт #laterx77 про экспорт.", "2026-11-16T11:00:00Z", "s4")]
    assert any("CSV" in i["text"] for i in _mem(tmp_path / "e", monkeypatch, ru + mention).later())  # a bare mention
    m4 = _mem(tmp_path / "d", monkeypatch, ru + by_id)
    assert not any("CSV" in i["text"] for i in m4.later())
    assert m3.close_by_hand("l1", "later", reopen=True)  # reopened by hand: an explicit report no longer closes it
    assert any("Redis" in i["text"] for i in m3.later())
    assert m3.close_by_hand("l1", "later") and not any("Redis" in i["text"] for i in m3.later())
    weak = [_t(8, "user", "Посмотри Redis.", "2026-11-14T10:00:00Z", "s2"),
            _t(9, "assistant", "Redis ответов не хранит, коммит 7e8f9a0.", "2026-11-14T11:00:00Z", "s2")]
    m2 = _mem(tmp_path / "b", monkeypatch, RU + weak)
    assert any("Redis" in i["text"] for i in m2.later())  # 2 shared stems (redis, ответ) do not close it


def test_note_next_to_recall(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, RU)
    hits = m.recall("Что с повторными попытками очереди?", k=6)
    m._last_query = "кэширование ответов и повторные попытки"
    note = m._later_note(hits)
    assert note.startswith("на потом по этой теме:") and "Redis" in note


def test_beads_read_only(tmp_path, monkeypatch):
    proj = tmp_path / "proj"
    (proj / ".beads").mkdir(parents=True)
    lines = [
        {"_type": "issue", "id": "bd-a1", "title": "Rate limiting for the booking API", "status": "deferred",
         "updated_at": "2026-11-15T09:00:00Z"},
        {"_type": "issue", "id": "bd-a2", "title": "Nightly backup", "status": "open", "defer_until": "2026-12-01"},
        {"_type": "issue", "id": "bd-a3", "title": "Old idea", "status": "closed", "labels": ["later"]},
        {"_type": "issue", "id": "bd-a4", "title": "Fix login", "status": "open"},
        {"_type": "memory", "id": "m1", "title": "not an issue", "status": "deferred"},
    ]
    body = "\n".join(json.dumps(x) for x in lines) + "\n{broken line\n"
    (proj / ".beads" / "issues.jsonl").write_text(body, "utf-8")
    before = (proj / ".beads" / "issues.jsonl").read_bytes()
    assert [b["id"] for b in beads.deferred(proj)] == ["bd-a1", "bd-a2"]
    m = _mem(tmp_path, monkeypatch, RU)
    ids = [i["id"] for i in m.later()]
    assert "bd-a1" in ids and "bd-a2" in ids and "bd-a3" not in ids and "bd-a4" not in ids
    assert (proj / ".beads" / "issues.jsonl").read_bytes() == before  # never written
    assert beads.deferred(tmp_path / "nothing") == []


def test_session_start_hook_prints_one_line(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, RU)
    m.s.db.close()
    argv = [sys.executable, "-m", "cotrail.cli", "--home", str(tmp_path / "home"), "hook-start"]
    r = subprocess.run(argv, input=json.dumps({"cwd": str(tmp_path / "proj")}), capture_output=True, text=True,
                       encoding="utf-8", timeout=120, env={**__import__("os").environ, "COTRAIL_LANG": "ru"})
    assert r.returncode == 0 and r.stdout.strip().startswith("На потом — открытых пунктов: 2;")
    r = subprocess.run(argv, input=json.dumps({"cwd": str(tmp_path / "other")}), capture_output=True, text=True,
                       timeout=120)  # fmt: skip
    assert r.returncode == 0 and r.stdout.strip() == ""  # no store for this project: nothing


def test_setup_writes_the_session_start_hook_once(tmp_path):
    from cotrail import setup as S

    proj = tmp_path / "proj"
    proj.mkdir()
    for _ in range(2):
        p, _st = S.write_hook(proj, None)
    data = json.loads(p.read_text("utf-8"))
    start = [h["command"] for g in data["hooks"]["SessionStart"] for h in g["hooks"]]
    stop = [h["command"] for g in data["hooks"]["Stop"] for h in g["hooks"]]
    assert start == ["cotrail hook-start"] and stop == ["cotrail hook-stop"]
