"""Project memory MVP (ctxgraph/memory.py, cli hook): offline, HashingEncoder, synthetic Claude Code transcripts."""

import json
from pathlib import Path

from ctxgraph import cc_transcripts as CC
from ctxgraph.embed import HashingEncoder
from ctxgraph.memory import ProjectMemory, project_slug, queue_transcript, rrf


def _line(kind, text, ts, uid, session="s1", **extra):
    msg = {"role": kind, "content": text if kind == "user" else [{"type": "text", "text": text}]}
    return json.dumps({"type": kind, "message": msg, "timestamp": ts, "uuid": uid, "sessionId": session, **extra})


def _transcript(path: Path) -> Path:
    rows = [
        _line("user", "Для базы выбираем PostgreSQL, MongoDB не подходит.", "2026-11-01T10:00:00Z", "u1"),
        _line("assistant", "Хорошо, схема будет в PostgreSQL с миграциями через Alembic.", "2026-11-01T10:01:00Z", "a1"),
        _line("user", "<system-reminder>служебное</system-reminder>", "2026-11-01T10:02:00Z", "u2"),
        json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "content": "x"}]},
                    "timestamp": "2026-11-01T10:03:00Z", "uuid": "t1", "sessionId": "s1"}),
        _line("user", "У меня грыжа диска, поэтому никаких поездок дольше двух часов.", "2026-11-02T09:00:00Z", "u3"),
        _line("assistant", "Понял, длинные поездки исключаем.", "2026-11-02T09:01:00Z", "a3", isSidechain=True),
    ]
    path.write_text("\n".join(rows), "utf-8")
    return path


def test_transcript_reader_keeps_only_what_people_said(tmp_path):
    ts = list(CC.turns(_transcript(tmp_path / "s1.jsonl")))
    assert [t["id"] for t in ts] == ["u1", "a1", "u3"]  # no reminders, tool results, sidechains
    assert ts[0]["role"] == "user" and ts[1]["role"] == "assistant" and ts[0]["ts"].startswith("2026-11-01")


def test_import_is_idempotent_and_recall_finds_by_steps(tmp_path):
    t = _transcript(tmp_path / "s1.jsonl")
    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    r1 = m.import_claude_code(files=[t])
    r2 = m.import_claude_code(files=[t])
    assert r1["new"] == 3 and r2["new"] == 0
    # the decisive fact is far from the question but close to a reasoning step
    q = "Посоветуй, куда съездить на выходных?"
    hits = m.recall(q, ["ограничения здоровья пользователя: грыжа диска, поездки не дольше двух часов"], k=3)
    assert any(h.episode == "u3" for h in hits)
    assert hits[0].ts.startswith("2026-11-0")
    out = m.render(hits)
    assert out.startswith("Memories from earlier conversations") and "грыжа" in out


def test_rrf_and_forget(tmp_path):
    assert rrf(["a", "b"], ["b", "c"])[0] == "b"
    t = _transcript(tmp_path / "s1.jsonl")
    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    m.import_claude_code(files=[t])
    assert m.forget("u3")
    assert all(h.episode != "u3" for h in m.recall("грыжа диска поездки", k=5))


def test_decisions_status_and_chronology(tmp_path):
    from ctxgraph.memory import classify

    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    m.remember("Для базы данных используем MongoDB.", ts="2026-11-01T10:00:00Z")
    m.remember("Предлагаю черновик: перейти на DeepSeek для базы данных.", role="assistant", ts="2026-11-02T10:00:00Z")
    m.remember("Передумал: MongoDB не используем, для базы данных берём PostgreSQL.", ts="2026-11-03T10:00:00Z")
    rows = m.decisions()
    assert [r["date"] for r in rows] == ["2026-11-03", "2026-11-01"] and rows[0]["kind"] == "не делать"
    hits = m.recall("какая база данных", k=3)
    assert [h.ts[:10] for h in hits] == sorted(h.ts[:10] for h in hits)  # oldest first
    assert {h.status for h in hits} >= {"decision"}
    # the assistant's message closes the 01.11 turn: it is nested under it, not a slot of its own
    assert any(h.report is not None and h.ts.startswith("2026-11-01") for h in hits)
    out = m.render(hits)
    assert "не применено" in out
    # chronology with a status per record, no "latest / current" marker (it attached to unrelated decisions)
    heads = [ln for ln in out.splitlines() if ln.startswith("[2026-")]
    assert heads[-1].startswith("[2026-11-03 · решение")
    assert "последнее решение" not in out and "выполнено" not in out
    assert classify("assistant", "Закоммитил исправление (коммит 1ec39ea).") == ("applied", "1ec39ea")
    assert classify("user", "Базу данных не меняем — она в утверждённом плане.") == ("decision", "no")


def test_transcript_noise_is_dropped():
    from ctxgraph.cc_transcripts import clean, dedupe

    raw = "\n".join(["Готово.", "```", "git status", " M file.py", "```", "warning: LF will be replaced", "$ ls",
                     "Итог: всё работает."])  # fmt: skip
    t = clean(raw)
    assert "git status" not in t and "warning" not in t and "$ ls" not in t and "Итог" in t
    line = "Длинная строка, которую потом вставят ещё раз целиком без изменений."
    turns = [{"id": "1", "role": "user", "ts": "a", "text": line},
             {"id": "2", "role": "user", "ts": "b", "text": line + "\nНовое сообщение."}]
    assert [x["text"] for x in dedupe(turns)] == [line, "Новое сообщение."]


def test_hook_queue_is_ingested_lazily(tmp_path, monkeypatch):
    import ctxgraph.memory as M

    monkeypatch.setattr(M, "HOME", tmp_path / "home")
    t = _transcript(tmp_path / "s1.jsonl")
    q = queue_transcript(tmp_path / "proj", str(t))
    assert q.parent.name == project_slug(tmp_path / "proj") and q.exists()
    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    assert m.ingest_pending() == 3 and not q.exists()
