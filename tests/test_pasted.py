"""A user turn that is a pasted assistant report (the pasted-reports rule, written before the code). Synthetic data only."""

from ctxgraph.memory import ProjectMemory

REPORT_RU = ("Готово: очередь задач переведена на SQLite, Redis удалён из зависимостей.\n\n"
             "## Что сделано\n"
             "- На будущее: ключи доступа храним только в .env, никогда в репозитории.\n"
             "- Решили оставить ретраи на стороне воркера, повтор через 30 секунд.\n"
             "- Тесты проходят (48 из 48), коммит 3f9a2c1.\n\n"
             "Миграцию старых задач пока отложили до следующего релиза.")
REPORT_EN = ("Done: the task queue now runs on SQLite and Redis is gone from the dependencies.\n\n"
             "## What changed\n"
             "- From now on, always keep access keys in .env and never in the repository.\n"
             "- We decided to keep retries in the worker, with a 30 second backoff.\n"
             "- Tests pass (48 of 48), commit 3f9a2c1.\n\n"
             "Migrating the old jobs is postponed until the next release.")
OWN_RU = "Решили: берём PostgreSQL для отчётов. На будущее: все даты в UTC."
OWN_EN = "Decision: we use PostgreSQL for the reports. From now on, always store dates in UTC."


def _t(i, s, role, ts, text, src):
    return {"id": i, "session": s, "role": role, "ts": ts, "text": text, "source": src}


def _turns(report, own, extra=""):
    return [
        _t("c1", "cc", "user", "2026-11-10T09:00:00Z", "Переведи очередь на SQLite." if report is REPORT_RU else
           "Move the queue to SQLite.", "transcript"),
        _t("c2", "cc", "assistant", "2026-11-10T09:30:00Z", report, "transcript"),
        _t("a1", "advisor", "user", "2026-11-11T10:00:00Z", report, "claude.ai"),  # wholly pasted
        _t("a2", "advisor", "assistant", "2026-11-11T10:01:00Z", "Понял, отчёт хороший." if report is REPORT_RU else
           "Got it, a good report.", "claude.ai"),
        _t("a3", "advisor", "user", "2026-11-11T11:00:00Z", own + "\n\n" + report + extra, "claude.ai"),  # partly
    ]


def _status(m, ep):
    return [st for (st,) in m.s.q("SELECT s.status FROM frag_status s JOIN fragments f ON f.id=s.fragment "
                                  "WHERE f.episode_id=? ORDER BY f.idx", (ep,))]  # fmt: skip


def _snap(m):
    st = dict(m.s.q("SELECT fragment, status || '|' || ref FROM frag_status"))
    return st, sorted(r["text"] for r in m.rules()), sorted(d["decision"] for d in m.decisions()), \
        sorted(x["text"] for x in m.later())


def _check(m, report, own, rule_word):
    assert set(_status(m, "a1")) == {"pasted"}
    refs = {r for (r,) in m.s.q("SELECT s.ref FROM frag_status s JOIN fragments f ON f.id=s.fragment "
                                "WHERE f.episode_id='a1'")}  # fmt: skip
    assert refs == {"c2"}
    st3 = _status(m, "a3")
    assert "pasted" in st3 and st3[0] != "pasted"  # the user's own text keeps its statuses
    rules = [r["text"] for r in m.rules()]
    assert any("UTC" in r for r in rules), rules  # the user's own rule
    assert not any(rule_word in r for r in rules), rules  # the pasted report's "rule" is not pinned
    dec = " ".join(d["decision"] for d in m.decisions())
    assert "PostgreSQL" in dec and "30" not in dec
    assert not any("3f9a2c1" in x["text"] or "релиз" in x["text"] or "release" in x["text"] for x in m.later())
    assert "c2" in m.s.q("SELECT ref FROM turn_paste WHERE episode='a1'")[0][0]


def test_pasted_ru(tmp_path):
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns(_turns(REPORT_RU, OWN_RU))
    _check(m, REPORT_RU, OWN_RU, ".env")
    from ctxgraph.memory import status_label
    assert status_label("pasted", "c2").startswith("вставленный отчёт") or status_label("pasted", "c2").startswith("pasted")


def test_pasted_en(tmp_path):
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns(_turns(REPORT_EN, OWN_EN))
    _check(m, REPORT_EN, OWN_EN, ".env")


def test_paste_before_original_is_remarked(tmp_path):
    """The chat is imported first (its paste looks like the user's decisions), the transcript later: re-marked."""
    for rep, own in ((REPORT_RU, OWN_RU), (REPORT_EN, OWN_EN)):
        turns = _turns(rep, own)
        batch = ProjectMemory(tmp_path / "p", home=tmp_path / ("b" + rep[:2]))
        batch.import_turns(turns)
        late = ProjectMemory(tmp_path / "p", home=tmp_path / ("l" + rep[:2]))
        late.import_turns([t for t in turns if t["source"] == "claude.ai"])
        assert "pasted" not in _status(late, "a1")
        late.import_turns([t for t in turns if t["source"] == "transcript"])
        one = ProjectMemory(tmp_path / "p", home=tmp_path / ("o" + rep[:2]))
        for t in reversed(turns):
            one.import_turns([t])
        assert _snap(batch) == _snap(late) == _snap(one)


def test_fallback_markup_without_original(tmp_path):
    body = ("Вот отчёт из другой сессии:\n\n## Итог\n| шаг | статус |\n|---|---|\n| импорт | ✅ |\n| тесты | ✅ |\n\n"
            "## Детали\nRan 12 commands\n- коммит 1a2b3c4: импорт чатов\n- коммит 5d6e7f8: тесты\n"
            "- На будущее: логи храним 30 дней.\n- Решили оставить SQLite.\n" + "- проверено вручную на копии.\n" * 20 +
            "\nЧто думаешь, решим ли мы так?")
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns([_t("u1", "chat", "user", "2026-11-12T10:00:00Z", body, "claude.ai")])
    st = _status(m, "u1")
    assert "pasted_md" in st and st[0] != "pasted_md" and st[-1] != "pasted_md"  # the framing stays the user's
    assert not any("30 дней" in r["text"] for r in m.rules())
    assert not any("SQLite" in d["decision"] for d in m.decisions())


def test_long_own_list_is_not_pasted(tmp_path):
    body = ("Задание на неделю:\n" + "".join(f"- пункт {i}: проверить модуль {i} и записать вывод в журнал\n"
                                              for i in range(12)) + "Решили: релиз в пятницу. Коммит 1a2b3c4 оставляем.")
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns([_t("u1", "cc", "user", "2026-11-12T10:00:00Z", body, "transcript")])
    assert not {"pasted", "pasted_md"} & set(_status(m, "u1"))


def test_adopted_chat_draft_stays_users(tmp_path):
    """A chat assistant drafts a task, the user sends it to Claude Code as their own: it stays the user's (amendment 1)."""
    draft = ("Решили: переводим очередь задач на SQLite, Redis убираем из зависимостей. Ретраи оставляем на стороне "
             "воркера с повтором через 30 секунд. Миграцию старых задач делаем в следующем релизе, а пока только код "
             "и тесты, без запуска на проде.")
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns([
        _t("a1", "advisor", "user", "2026-11-10T09:00:00Z", "Набросай задание для Claude Code про очередь.", "claude.ai"),
        _t("a2", "advisor", "assistant", "2026-11-10T09:01:00Z", "Вот текст задания:\n\n" + draft, "claude.ai"),
        _t("c1", "cc", "user", "2026-11-10T09:10:00Z", draft, "transcript"),
    ])
    assert not {"pasted", "pasted_md"} & set(_status(m, "c1"))
    assert any("SQLite" in d["decision"] for d in m.decisions())


def test_save_chat_paste(tmp_path):
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns(_turns(REPORT_EN, OWN_EN)[:2])
    m.save_chat("advisor", [{"role": "user", "text": REPORT_EN}, {"role": "assistant", "text": "Got it."}])
    ep = m.s.q("SELECT id FROM episodes WHERE role='user' AND id LIKE 'chat:%'")[0][0]
    assert set(_status(m, ep)) == {"pasted"}
    assert not any(".env" in r["text"] for r in m.rules())


def test_migration_marks_an_old_store(tmp_path):
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    m.import_turns(_turns(REPORT_RU, OWN_RU))
    want = _snap(m)
    m.s.db.execute("DELETE FROM turn_paste")
    m.s.db.execute("DELETE FROM memory_meta WHERE key='pasted_rowid'")
    m.s.db.commit()
    m.remark_all()
    m.s.db.commit()
    del m
    m2 = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    assert _snap(m2)[0] == want[0] and _snap(m2)[2] == want[2]


def test_catch_up_after_older_version(tmp_path):
    """Turns added by an older version (no paste marking) are marked on the next open."""
    m = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    turns = _turns(REPORT_EN, OWN_EN)
    m.import_turns(turns[:2])
    want = ProjectMemory(tmp_path / "p", home=tmp_path / "w")
    want.import_turns(turns)
    top = m.s.q("SELECT value FROM memory_meta WHERE key='pasted_rowid'")[0][0]
    m._paste_set = lambda e: False  # the older version: no paste rule
    m._paste_refresh = lambda a: None
    m.import_turns(turns[2:])
    m.s.db.execute("INSERT OR REPLACE INTO memory_meta VALUES('pasted_rowid', ?)", (top,))
    m.s.db.commit()
    assert "pasted" not in _status(m, "a1")
    del m
    m2 = ProjectMemory(tmp_path / "p", home=tmp_path / "h")
    assert _snap(m2) == _snap(want)
