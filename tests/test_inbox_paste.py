"""Inbox from the advisor chat and explicit pastes (the inbox rule); `later done`; the team join
wording on a rerun. Synthetic only."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cotrail import cli
from cotrail.cc_transcripts import pasted_blocks, turns
from cotrail.memory import ProjectMemory, inbox_items

ADVISOR = """План на вечер понятен.

**Сообщение для Claude Code:**
> 1. Добавь повторные попытки сетевых вызовов git в синхронизации памяти
>    с паузами между попытками.
> 2. Команда team leave выключает синхронизацию проекта.

Остальное завтра."""


def _t(i, role, text, ts, session="s1", source="transcript"):
    return {"id": f"t{i}", "session": session, "role": role, "ts": ts, "text": text, "source": source}


def _mem(tmp_path, monkeypatch):
    monkeypatch.setenv("COTRAIL_LANG", "ru")
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    return ProjectMemory(tmp_path / "proj", home=tmp_path / "home")


def test_inbox_items_are_parsed_per_numbered_item() -> None:
    assert inbox_items(ADVISOR) == [
        "Добавь повторные попытки сетевых вызовов git в синхронизации памяти с паузами между попытками.",
        "Команда team leave выключает синхронизацию проекта."]
    en = "Message for Claude Code:\n> Rename the sync log file and update the docs."
    assert inbox_items(en) == ["Rename the sync log file and update the docs."]
    plain = "### Сообщение для Claude Code\n1. Первая задача про индекс\n2. Вторая задача про кэш\n\nКонец."
    assert inbox_items(plain) == ["Первая задача про индекс", "Вторая задача про кэш"]
    assert inbox_items("Сообщение для Claude Code — это хорошая идея.") == []


def test_inbox_opens_closes_by_report_and_by_hand(tmp_path, monkeypatch) -> None:
    import cotrail.memory as M

    monkeypatch.setattr(M, "CLOSE_RULE_SINCE", "2000-01-01")  # the reports come after the close rule
    m = _mem(tmp_path, monkeypatch)
    m.import_turns([_t(1, "user", "Что дальше по синхронизации?", "2026-11-22T18:00:00Z", "adv", "chat"),
                    _t(2, "assistant", ADVISOR, "2026-11-22T18:01:00Z", "adv", "chat")])  # fmt: skip
    items = m.inbox()
    assert len(items) == 2 and all(i["record"] == "t2" and i["date"] == "2026-11-22" for i in items)
    assert m.inbox_line() == "От советника: 2 новых заданий. `inbox` — список."
    m.import_turns([_t(3, "user", "Сделай повторы для git.", "2026-11-23T09:00:00Z", "cc"),
                    _t(4, "assistant", "Готово: повторные попытки сетевых вызовов git в синхронизации, паузы 2-10 с, "
                                       "коммит 05d3421.", "2026-11-23T10:00:00Z", "cc")])  # fmt: skip
    left = m.inbox()  # the close rule A: shared stems only propose
    assert len(left) == 2 and [i["looks_done"] for i in left if i["text"].startswith("Добавь")] == ["t4"]
    assert "Похоже, сделано — подтвердите: 1." in m.inbox_line()
    first = next(i["id"] for i in left if i["text"].startswith("Добавь"))
    m.import_turns([_t(5, "user", "Отчитайся.", "2026-11-23T11:00:00Z", "cc2"),
                    _t(6, "assistant", f"Задание {first} выполнено, коммит 05d3421.", "2026-11-23T12:00:00Z", "cc2")])
    left = m.inbox()
    assert [i["text"][:7] for i in left] == ["Команда"]
    assert m.close_by_hand(left[0]["id"], "inbox") and m.inbox() == [] and m.inbox_line() == ""
    assert {i["done"] for i in m.inbox(include_done=True)} == {"by report #t6", "by hand"}
    assert m.close_by_hand(first, "inbox", reopen=True) and [i["id"] for i in m.inbox()] == [first]


def test_later_done_by_hand(tmp_path, monkeypatch, capsys) -> None:
    m = _mem(tmp_path, monkeypatch)
    m.import_turns([_t(1, "user", "Кэширование ответов через Redis оставим на потом.", "2026-11-10T10:00:00Z"),
                    _t(2, "assistant", "Хорошо, кэш пока не делаю.", "2026-11-10T10:01:00Z")])  # fmt: skip
    iid = m.later()[0]["id"]
    m.s.db.close()
    import cotrail.memory as M

    monkeypatch.setattr(M, "HOME", tmp_path / "home")
    cli.main(["--project", str(tmp_path / "proj"), "--home", str(tmp_path / "home"), "later", "done", iid])
    assert "Closed." in capsys.readouterr().out
    assert ProjectMemory(tmp_path / "proj", home=tmp_path / "home").later() == []


def _transcript(path: Path, user_text: str) -> Path:
    rows = [{"type": "user", "uuid": "u1", "sessionId": "s", "timestamp": "2026-11-22T20:00:00Z",
             "message": {"role": "user", "content": user_text}},
            {"type": "assistant", "uuid": "a1", "sessionId": "s", "timestamp": "2026-11-22T20:01:00Z",
             "message": {"role": "assistant", "content": [{"type": "text", "text": "Посмотрел вывод, всё в порядке."}]}}]  # fmt: skip
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), "utf-8")
    return path


def test_pasted_content_and_terminal_blocks_are_never_the_users_rules(tmp_path, monkeypatch) -> None:
    raw = ("Вот что вывело:\n<pasted_content id=\"1\">The repository MUST be private; never make it public.\n"
           "From now on the Stop hook syncs in the background after each reply.</pasted_content>\n"
           "PS C:\\work\\app> cotrail team status\nAlways keep the sync log under 400 lines.\nDone.\n\n"
           "Проверь, что всё синхронизировалось.")  # fmt: skip
    pb = pasted_blocks(raw)
    assert "MUST be private" in pb and "Always keep the sync log" in pb and "Проверь" not in pb
    f = _transcript(tmp_path / "s.jsonl", raw)
    ts = list(turns(f))
    assert ts[0]["pasted"] and "MUST be private" in ts[0]["text"]  # the text stays, marked as pasted
    m = _mem(tmp_path, monkeypatch)
    m.import_claude_code(files=[f])
    assert m.rules() == []
    st = dict(m.s.q("SELECT f.text, s.status FROM frag_status s JOIN fragments f ON f.id=s.fragment"))
    assert all(v == "pasted" for k, v in st.items() if "MUST" in k or "Always" in k)
    assert not any(v == "pasted" for k, v in st.items() if "Проверь" in k)


def test_team_join_rerun_says_already_imported(tmp_path, monkeypatch) -> None:
    import pytest

    S = pytest.importorskip("cotrail.sync")  # team memory (experimental): not in every build
    from cotrail import team as T

    fake = tmp_path / "userhome"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    proj = tmp_path / "proj"
    proj.mkdir()
    subprocess.run(["git", "-C", str(proj), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", "https://github.com/example-org/demo"], check=True)
    from cotrail.memory import project_slug

    d = fake / ".claude" / "projects" / project_slug(proj)
    d.mkdir(parents=True)
    _transcript(d / "s.jsonl", "Решили: логи пишем в JSON, ротация раз в сутки.")
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "mem.git")], check=True)
    logs: list[str] = []
    for _ in range(2):
        T.join(proj, str(tmp_path / "mem.git"), tmp_path / "h", name="Dev", check=lambda r: "local", log=logs.append)
    joined = [x for x in logs if x.startswith("Joined")]
    assert "imported 2 turn(s)" in joined[0] and "already imported 2 turn(s) earlier; 0 new" in joined[1]


def test_expand_shows_the_record_in_full_even_after_a_brief_recall(tmp_path, monkeypatch) -> None:
    import cotrail.memory as M

    m = _mem(tmp_path, monkeypatch)
    long_user = "Решили: отчёт по синхронизации. " + " ".join(f"пункт {i} про ретраи и паузы сети" for i in range(400))
    report = "Сделано: " + " ".join(f"шаг {i} выполнен в модуле sync" for i in range(300)) + " КОНЕЦ_ОТЧЁТА"
    m.import_turns([_t(1, "user", long_user, "2026-11-23T09:00:00Z", "x"),
                    _t(2, "assistant", report, "2026-11-23T10:00:00Z", "x")])  # fmt: skip
    m._shown = set()  # an MCP session (economy b): a brief recall marks the record as shown
    m.render(m.recall("ретраи и паузы сети"), detail="brief")
    out = m.expand("t1")
    assert "пункт 399 про ретраи" in out and "КОНЕЦ_ОТЧЁТА" in out
    monkeypatch.setattr(M, "EXPAND_MAX", 1000)
    out = m.expand("t1")
    assert f"… {len(long_user) - 1000} more chars" in out and f"… {len(report) - 1000} more chars" in out
