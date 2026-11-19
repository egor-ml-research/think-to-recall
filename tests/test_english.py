"""English as a first language of the product (the cue dictionary is written before the checks): labels, cues, dialogue acts.

A synthetic English project: Postgres -> SQLite, a rule about .env, a deferral. Offline (BM25; the quality mode only
when its model is downloaded)."""

import pytest

from ctxgraph import cc_transcripts as CC
from ctxgraph.memory import ProjectMemory, classify, format_decisions


def _t(i, role, text, ts, session):
    return {"id": f"t{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


TURNS = [
    _t(1, "user", "We are building a table booking service. For the database we will use Postgres.", "2026-11-03T10:00:00Z", "s1"),
    _t(2, "assistant", "Created the Postgres schema with Alembic migrations, commit 3f2a1b9.", "2026-11-03T10:20:00Z", "s1"),
    _t(3, "user", "API keys always go only in .env, never in logs or reports.", "2026-11-04T09:00:00Z", "s2"),
    _t(4, "assistant", "Understood, keys stay in .env.", "2026-11-04T09:01:00Z", "s2"),
    _t(5, "user", "Let's postpone the Redis cache until next month.", "2026-11-05T09:00:00Z", "s3"),
    _t(6, "assistant", "OK, no Redis for now.", "2026-11-05T09:01:00Z", "s3"),
    _t(7, "user", "No, I changed my mind: the load is small, we switch from Postgres to SQLite.", "2026-11-10T15:00:00Z", "s4"),
    _t(8, "assistant", "Switched to SQLite: migrations rewritten, data moved, tests 48/48 pass, commit 9c4e7d2.",
       "2026-11-10T15:40:00Z", "s4"),
    _t(9, "user", "Add basic monitoring for the booking API.", "2026-11-11T09:00:00Z", "s5"),
    _t(10, "assistant", "Monitoring is added. Should I also add a nightly backup of the SQLite file?", "2026-11-11T09:30:00Z", "s5"),
    _t(11, "user", "later", "2026-11-11T09:31:00Z", "s5"),
]


def _mem(tmp_path, monkeypatch, quality=False):
    monkeypatch.delenv("CTXGRAPH_LANG", raising=False)
    if quality:
        monkeypatch.setenv("CTXGRAPH_QUALITY", "1")
    else:
        monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(TURNS)
    return m


def test_english_cues():
    assert classify("user", "For the database we will use Postgres.") == ("decision", "yes")
    assert classify("user", "Use SQLite for tests.") == ("decision", "yes")
    assert classify("user", "Do not use Docker for the dev setup.") == ("decision", "no")
    assert classify("user", "Let's postpone the Redis cache until next month.") == ("decision", "hold")
    # a negation in a subordinate clause is not a refusal: the refusal status comes from the main clause only
    assert classify("user", "We switch from Postgres to SQLite so we do not pay for a separate server.") == \
        ("decision", "yes")
    for s in ("We move to SQLite.", "Let's migrate to SQLite.", "Replace Postgres with SQLite.", "We go with SQLite.",
              "We settle on SQLite.", "Drop Postgres in favour of SQLite.", "Переходим на SQLite.",
              "Меняем Postgres на SQLite.", "Вместо Postgres берём SQLite."):
        assert classify("user", s) == ("decision", "yes"), s
    assert classify("user", "Use SQLite because we do not need a server.") == ("decision", "yes")
    assert classify("user", "Do not use Docker because it is slow.") == ("decision", "no")
    assert classify("user", "Переходим на SQLite, чтобы не платить за сервер.") == ("decision", "yes")
    assert classify("user", "Is Redis needed here?")[0] == "said"  # a question is not a decision
    assert classify("user", "API keys always go only in .env, never in logs or reports.") == ("rule", "")
    assert classify("assistant", "Switched to SQLite: tests 48/48 pass, commit 9c4e7d2.")[0] == "applied"
    assert classify("assistant", "I could also add a nightly backup if you want.")[0] == "proposal"
    assert [CC.short_act(x) for x in ("go ahead", "sounds good", "let's ship", "later", "nope", "done")] == \
        ["agree", "agree", "directive", "defer", "reject", "status"]


def _check(m, via=True):
    assert m.lang == "en"  # most of the user's letters are Latin
    out = m.render(m.recall("Which database did we choose?", k=6))
    assert out.startswith("Project rules") and "API keys always go only in .env" in out  # the pinned rule
    assert "[2026-11-03 · decision: do · #t1]" in out and "→ done 2026-11-03, commit 3f2a1b9 (#t2)" in out
    assert "we switch from Postgres to SQLite" in out and "commit 9c4e7d2" in out
    assert out.index("we will use Postgres") < out.index("we switch from Postgres to SQLite")
    assert not any(w in out for w in ("решение", "сделано", "коммит", "пользователь"))  # no Russian labels
    x = m.expand("t8")  # from the report: the whole thread
    # the thread comes through shared entities; a Leiden topic name needs WordNet data, which a default install lacks
    assert x.startswith("Record #t7 in full") and "we will use Postgres" in x and "Topic: " in x
    d = format_decisions(m.decisions())
    assert "[on hold]: Let's postpone the Redis cache" in d
    assert "[deferred]: assistant's proposal" in d and "nightly backup" in d and "(«later»)" in d
    assert "for reference - the report in the reply 2026-11-03, commit 3f2a1b9" in d


def test_english_project_bm25(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch)
    assert m.mode == "bm25"
    _check(m)


def test_english_project_quality(tmp_path, monkeypatch):
    from ctxgraph import model as M

    if not M.is_cached():
        pytest.skip("the quality model is not downloaded here")
    m = _mem(tmp_path, monkeypatch, quality=True)
    assert m.mode == "hybrid"
    _check(m)


def test_label_language_can_be_forced(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch)
    monkeypatch.setenv("CTXGRAPH_LANG", "ru")
    out = m.render(m.recall("Which database did we choose?", k=6))
    assert "решение: делать" in out and "коммит 3f2a1b9" in out


def test_english_project_without_spacy(tmp_path, monkeypatch):
    """The default install has no spaCy: English concepts come from the rules fallback; the same checks hold."""
    from ctxgraph.v2 import english

    monkeypatch.setattr(english, "available", lambda: False)
    m = _mem(tmp_path, monkeypatch)
    _check(m)
