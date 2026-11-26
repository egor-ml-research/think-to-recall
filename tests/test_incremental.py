"""Invariant: a store fed turn by turn gives the same recall, decisions and expand as a store fed the same turns at once
. Both modes; the quality mode only when its model is downloaded."""

import pytest

from cotrail.memory import ProjectMemory, format_decisions
from tests.test_english import TURNS as EN

RU = [
    {"id": f"r{i}", "session": s, "role": role, "ts": ts, "text": text, "source": "transcript"}
    for i, (s, role, ts, text) in enumerate([
        ("a", "user", "2026-11-12T10:00:00Z", "Для очереди задач берём Redis, Celery не используем."),
        ("a", "assistant", "2026-11-12T10:30:00Z", "Сделано: очередь на Redis, коммит 1a2b3c4, тесты проходят."),
        ("b", "user", "2026-11-13T09:00:00Z", "Меняем Redis на встроенную очередь SQLite, чтобы не держать отдельный сервис."),
        ("b", "assistant", "2026-11-13T09:40:00Z", "Перешёл на очередь в SQLite, Redis убран, коммит 5d6e7f8. Добавить ретраи?"),
        ("b", "user", "2026-11-13T09:41:00Z", "да"),
        ("b", "assistant", "2026-11-13T10:00:00Z", "Ретраи добавлены, коммит 9a8b7c6."),
    ])  # fmt: skip
]
QUESTIONS = ["Which database did we choose?", "Where do API keys go?", "Что используем для очереди задач?",
             "Добавили ли ретраи?", "What did we postpone?"]


def _snapshot(m):
    out = {q: m.render(m.recall(q, k=6)) for q in QUESTIONS}
    out["decisions"] = format_decisions(m.decisions())
    for e in ("t1", "t7", "t8", "r0", "r2", "r4"):
        out["expand " + e] = m.expand(e)
    return out


def _run(tmp_path, monkeypatch, quality):
    monkeypatch.delenv("COTRAIL_LANG", raising=False)
    if quality:
        monkeypatch.setenv("COTRAIL_QUALITY", "1")
    else:
        monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    turns = EN + RU
    batch = ProjectMemory(tmp_path / "proj", home=tmp_path / "batch")
    batch.import_turns(turns)
    one = ProjectMemory(tmp_path / "proj", home=tmp_path / "one")
    for t in sorted(turns, key=lambda t: (t["ts"], t["id"])):
        one.import_turns([t])
        one.recall("warm the caches between turns", k=6)  # a query between imports must not freeze any statistic
    a, b = _snapshot(batch), _snapshot(one)
    assert a.keys() == b.keys()
    for k in a:
        assert a[k] == b[k], k


def test_one_by_one_equals_batch_bm25(tmp_path, monkeypatch):
    _run(tmp_path, monkeypatch, quality=False)


def test_one_by_one_equals_batch_quality(tmp_path, monkeypatch):
    from cotrail import model as M

    if not M.is_cached():
        pytest.skip("the quality model is not downloaded here")
    _run(tmp_path, monkeypatch, quality=True)
