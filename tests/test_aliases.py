"""Concept aliases (cotrail/aliases.py): the synthetic dev set of reports/realworld/aliases_rule.md, written with the
rule before the q01-q30 regression. Idea from Hindsight (MIT): trigram entity resolution."""

from __future__ import annotations

from cotrail import aliases as AL
from cotrail.memory import ProjectMemory

MUST_MERGE = [("Postgres", "PostgreSQL"), ("ctxgraph", "ctx-graph"), ("think-to-recall", "think to recall"),
              ("BM25", "BM-25"), ("постгрес", "postgres"), ("ollama", "оллама")]  # fmt: skip
MUST_NOT = [("q25", "q26"), ("v0.6.0", "v0.6.1"), ("gemma2", "gemma3"), ("e1b", "e1c"), ("recall", "recall block"),
            ("test", "install test"), ("sqlite", "postgres")]  # fmt: skip


def _merged(a: str, b: str) -> bool:
    ka, kb = AL.key(a), AL.key(b)
    return AL.eligible(ka) and AL.eligible(kb) and AL.same(ka, kb)[0]


def test_dev_set_by_the_rule():
    assert not [p for p in MUST_NOT if _merged(*p)]
    assert sum(_merged(*p) for p in MUST_MERGE) >= 5, [p for p in MUST_MERGE if not _merged(*p)]


def test_key_and_similarity_are_pg_trgm_style():
    assert AL.key("c:Ctx-Graph v2") == "ctx graph v2"
    assert AL.key("Постгрес") == "postgres"
    assert AL.trigrams("ab") == {"  a", " ab", "ab "}
    assert AL.similarity("postgres", "postgresql") == 8 / 12


def test_pairs_keep_the_first_seen_as_canonical_and_skip_dates_paths_hashes():
    rows = [("c:postgresql", "PostgreSQL", "keyphrase", 5), ("c:postgres", "Postgres", "lemma", 2),
            ("c:постгрес", "постгрес", "lemma", 9), ("c:2026 11 25", "2026-11-25", "ent:DATE", 1),
            ("c:2026 11 25x", "2026-11-25x", "ent:DATE", 1), ("c:a1b2c3d", "a1b2c3d", "lemma", 1),
            ("c:a1b2c3e", "a1b2c3e", "lemma", 1)]  # fmt: skip
    got = {a: c for a, c, _, _ in AL.pairs(rows)}
    assert got == {"c:postgresql": "c:postgres", "c:постгрес": "c:postgres"}


def _turn(i, role, text, ts):
    return {"id": f"t{i}", "session": "s1", "role": role, "ts": ts, "text": text, "source": "transcript"}


def _turns():
    return [
        _turn(1, "user", "Для базы данных берём Postgres.", "2026-11-01T10:00:00Z"),
        _turn(2, "assistant", "Схема в Postgres создана, коммит a1b2c3d.", "2026-11-01T10:05:00Z"),
        _turn(3, "user", "Нет, передумал: уходим с PostgreSQL на SQLite.", "2026-11-05T10:00:00Z"),
        _turn(4, "assistant", "Перешли на SQLite: миграция готова, коммит e4f5a6b.", "2026-11-05T10:10:00Z"),
    ]


def test_a_changed_decision_written_with_another_spelling_is_followed(tmp_path, monkeypatch):
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(_turns())
    out = m.render(m.recall("какую базу данных выбрали", k=6))
    assert "уходим с PostgreSQL на SQLite" in out
    assert m.s.q("SELECT alias, canonical FROM concept_alias WHERE alias LIKE '%postgresql%'")
    assert m.s.q("SELECT COUNT(*) FROM mentions x JOIN concepts c ON c.id=x.concept_id "
                 "WHERE c.label='PostgreSQL'")[0][0] >= 1  # the originals are kept


def test_off_switch_is_the_old_recall(tmp_path, monkeypatch):
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    monkeypatch.setenv("COTRAIL_ALIASES", "off")
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(_turns())
    assert m._alias_map() == {}
    assert "уходим с PostgreSQL на SQLite" not in m.render(m.recall("какую базу данных выбрали", k=6))
