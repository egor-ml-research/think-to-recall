"""Decision memory, round 3 (user check 17.11): the `decisions` tool, per-clause statuses, whole decision text,
decision -> execution report, claude.ai export import. Offline, HashingEncoder."""

import json
import zipfile

from ctxgraph import cc_transcripts as CC
from ctxgraph.embed import HashingEncoder
from ctxgraph.memory import ProjectMemory, classify, format_decisions


def _mem(tmp_path):
    return ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")


def _turn(i, role, text, ts, session="s1"):
    return {"id": f"t{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


def test_decisions_tool_returns_text_not_an_error(tmp_path):
    from ctxgraph import memory_mcp as M

    m = _mem(tmp_path)
    m.remember("Для базы данных используем PostgreSQL.", ts="2026-11-01T10:00:00Z")
    m.remember("Базу данных не меняем — она в утверждённом плане.", ts="2026-11-02T10:00:00Z")
    M._mem = m
    try:
        out = M.decisions(10)
    finally:
        M._mem = None
    text = out if isinstance(out, str) else str(out)
    assert "2026-11-02 [не делать]: Базу данных не меняем" in text and "2026-11-01 [делать]" in text
    assert format_decisions([]) == "No decisions recorded yet."


def test_status_is_per_clause_not_per_message():
    # "убираем" is a decision to act, "пока не трогай — решаю отдельно" is a hold, not "не делать"
    assert classify("user", "`DESIGN.md` и `API.md` пока не трогай — решаю отдельно.") == ("decision", "hold")
    assert classify("user", "Убираем идею модуля аналитики из мобильного приложения полностью:") == ("decision", "yes")
    assert classify("user", "Слой убираем, а README пока не трогай.") == ("decision", "yes+hold")
    assert classify("user", "Веб-версию не трогать — там всё остаётся как есть.") == ("decision", "no")
    assert classify("user", "Базу данных не меняем?") == ("said", "")


def test_list_after_colon_inherits_the_decision_and_is_shown_whole(tmp_path):
    m = _mem(tmp_path)
    long_tail = " ".join(["Пришли таблицу dev целиком и черновик, прочитаю и запускаем поиск."] * 6)
    text = ("Да, запускай сборку сейчас.\nВ плане релиза до заморозки поменяй приоритеты — по итогам беты, открыто:\n\n"
            "* главная: оплата картой против оплаты по счёту, на iOS и Android, проверка на двух магазинах;\n"
            "* вторичные: тёмная тема, push-уведомления;\n" + long_tail)
    r = m.remember(text, ts="2026-11-08T10:00:00Z")
    st = {t: s for t, (s, _) in zip(
        [x for (x,) in m.s.q("SELECT text FROM fragments WHERE episode_id=? ORDER BY idx", (r["episode"],))],
        [m._status()[f] for (f,) in m.s.q("SELECT id FROM fragments WHERE episode_id=? ORDER BY idx", (r["episode"],))])}
    assert st[next(t for t in st if t.startswith("главная"))] == "decision"
    assert st[next(t for t in st if t.startswith("Пришли"))] == "said"  # the list ended
    out = m.render(m.recall("главная оплата картой", k=3))
    assert "главная: оплата картой против оплаты по счёту, на iOS и Android, проверка на двух магазинах" in out  # not cut


def test_decision_is_linked_to_the_report_that_it_was_done(tmp_path):
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Переименуй сервис в billing-api и обнови ссылки в README.", "2026-11-09T10:00:00Z"),
        _turn(2, "assistant", "Готово: сервис переименован в billing-api, ссылки в README обновлены, коммит 4f1c2d9.",
              "2026-11-09T10:05:00Z"),
        _turn(3, "user", "Убираем модуль аналитики из мобильного приложения.", "2026-11-09T11:00:00Z"),
        _turn(4, "assistant", "Коллективный слой я пока не трогал, не сделано.", "2026-11-09T11:01:00Z"),
        _turn(5, "user", "Отлично, спасибо, дальше по плану.", "2026-11-09T12:00:00Z"),
        _turn(6, "assistant", "Модуль аналитики удалён из мобильного приложения (коммит 7e3a1b2).", "2026-11-10T09:00:00Z",
              session="s2"),  # another session, after another user turn: not a reply to turn 3
    ])
    d = m.done_for("t1")
    assert d and d["commit"] == "4f1c2d9" and d["date"] == "2026-11-09" and "Переименуй" in d["decision"]
    assert m.done_for("t3") is None  # "не сделано" is not a report of done work; s2 is not a reply
    out = m.render(m.recall("переименовать сервис billing-api", k=2))
    # the report is nested under the request it closes and takes no slot of its own
    assert "-> выполнено" not in out and "→ сделано 2026-11-09, коммит 4f1c2d9 (#t2)" in out
    assert "· итоговый отчёт ассистента" not in out
    # the link is kept as a reference in `decisions`
    m.remember("Убираем старый README полностью.", ts="2026-11-11T10:00:00Z", session="s3")
    assert "справка — отчёт" not in format_decisions(m.decisions())  # no reply -> no link
    m.import_turns([_turn(7, "user", "Убираем папку archive из корня репозитория.", "2026-11-12T10:00:00Z", "s4"),
                    _turn(8, "assistant", "Папку archive удалил из корня репозитория, коммит 1a2b3c4.", "2026-11-12T10:02:00Z", "s4")])
    assert "справка — отчёт в ответе 2026-11-12, коммит 1a2b3c4" in format_decisions(m.decisions())


def test_pinned_rules_are_in_every_block_and_can_be_removed(tmp_path):
    m = _mem(tmp_path)
    m.remember("Ключи API всегда только в .env, никогда в логах и отчётах.", ts="2026-10-22T10:00:00Z")
    m.remember("Для базы данных используем PostgreSQL.", ts="2026-10-23T10:00:00Z")
    m.remember("Всегда ли нужен Docker?", ts="2026-10-24T10:00:00Z")  # a question is not a rule
    rid = m.pin_rule("Перед запуском больше 300 вызовов API — спрашивать владельца проекта.")
    rs = m.rules()
    assert [r["text"][:9] for r in rs] == ["Ключи API", "Перед зап"] and rs[0]["date"] == "2026-10-22"
    out = m.render(m.recall("какая база данных", k=1))
    assert out.startswith("Project rules") and "Ключи API всегда" in out and "300 вызовов" in out
    assert m.unpin_rule(rid) and "300 вызовов" not in m.render(m.recall("база", k=1))
    m.remark_all()  # re-marking does not bring a removed rule back
    auto = rs[0]["id"]
    assert m.unpin_rule(auto)
    m.remark_all()
    assert m.rules() == []


def test_transcript_reader_skips_app_injected_notes(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in [
        {"type": "user", "isMeta": True, "uuid": "m1", "timestamp": "2026-11-14T10:00:00Z", "sessionId": "s",
         "message": {"role": "user", "content": "[Earlier usage-limit notes no longer apply. Don't mention this to the user.]"}},
        {"type": "user", "uuid": "u1", "timestamp": "2026-11-14T10:01:00Z", "sessionId": "s",
         "message": {"role": "user", "content": "Для базы выбираем PostgreSQL, это решено."}},
    ]), "utf-8")
    assert [t["id"] for t in CC.turns(p)] == ["u1"]


def _export(tmp_path):
    conv = [
        {"uuid": "c-ctx-1", "name": "shop-app: зачем убирать модуль аналитики", "created_at": "2026-11-08T09:00:00Z",
         "chat_messages": [
             {"uuid": "m1", "sender": "human", "created_at": "2026-11-08T09:00:00Z", "text": "",
              "content": [{"type": "text", "text": "Модуль аналитики убираем из мобильного приложения: это отдельный продукт."}],
              "attachments": [{"file_name": "notes.txt", "extracted_content": "секретный текст вложения"}]},
             {"uuid": "m2", "sender": "assistant", "created_at": "2026-11-08T09:01:00Z",
              "content": [{"type": "thinking", "thinking": "скрытые рассуждения"},
                          {"type": "tool_use", "name": "web_search", "input": {}},
                          {"type": "text", "text": "Понял: модуль аналитики — отдельный продукт, в мобильном приложении его не будет."}]},
         ]},
        {"uuid": "c-other", "name": "Рецепт борща", "created_at": "2026-11-01T09:00:00Z",
         "chat_messages": [{"uuid": "m3", "sender": "human", "created_at": "2026-11-01T09:00:00Z",
                            "text": "Как сварить борщ на четверых?"}]},
    ]
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(conv, ensure_ascii=False))
        f.writestr("projects.json", "[]")
    return z


def test_claude_ai_export_import_is_selective_idempotent_and_skips_hidden_parts(tmp_path):
    m = _mem(tmp_path)
    z = _export(tmp_path)
    r1 = m.import_claude_ai(z, match="shop-app|аналитик")
    r2 = m.import_claude_ai(z, match="shop-app|аналитик")
    assert (r1["conversations"], r1["of"], r1["new"], r2["new"]) == (1, 2, 2, 0)
    assert r1["skipped"].get("thinking") == 1 and r1["skipped"].get("tool_use") == 1 and r1["skipped"].get("attachments") == 1
    texts = " ".join(t for (t,) in m.s.q("SELECT text FROM episodes"))
    assert "отдельный продукт" in texts and "борщ" not in texts
    assert "скрытые рассуждения" not in texts and "секретный текст вложения" not in texts
    out = m.render(m.recall("почему убрали модуль аналитики", k=2))
    assert "· claude.ai ·" in out and "2026-11-08" in out


def test_questions_rules_lists_and_closing_a_conditional_decision(tmp_path):
    # 5. a question or a remark is not a decision, even with a cue word
    assert classify("user", "ок, почему я в демо не вижу что предлагает RAG система, и что было выбрано, что нет.")[0] == "said"
    # 7. a standing rule is a rule (pinned), not a decision
    assert classify("user", "Пришли оценку стоимости; без моего «да» не запускай.") == ("rule", "")
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Убираем модуль аналитики из мобильного приложения:\n\n"
                         "1. Найди все упоминания и удали модули.\n"
                         "2. После моего «да»: удалить тестовый стенд и создать заново из чистого образа.\n"
                         "3. Веб-версию не трогать.", "2026-11-09T19:22:00Z", "s1"),
        _turn(2, "assistant", "Нашёл все упоминания; жду твоего «да» на пересоздание.", "2026-11-09T19:30:00Z", "s1"),
        _turn(3, "user", "Yes, recreate", "2026-11-09T19:38:00Z", "s1"),
        # the conversation continues in a new session file (compaction / resume): it starts with the assistant
        _turn(4, "assistant", "Тестовый стенд создан заново из чистого образа, коммит 7e3a1b2.",
              "2026-11-09T19:42:00Z", "s1-continued"),
    ])
    rows = m.decisions()
    lead = next(r for r in rows if r["decision"].startswith("Убираем модуль аналитики"))
    # 6. the lead line is kept together with its list, the items are not separate decisions
    assert "1. Найди все упоминания" in lead["decision"] and "3. Веб-версию" in lead["decision"]
    assert not any(r["decision"].startswith(("Найди", "После моего")) for r in rows)
    # 4. the conditional item is closed by the later confirmation and the report of done work
    z = lead["resolved"]
    assert z and z["confirmed"] == "2026-11-09" and z["commit"] == "7e3a1b2"
    assert "подтверждено 2026-11-09 → выполнено 2026-11-09" in format_decisions(rows)


def test_steps_never_displace_what_the_question_found(tmp_path):
    m = _mem(tmp_path)
    for i in range(8):
        m.remember(f"Для базы данных проекта выбираем вариант номер {i}: PostgreSQL с репликой {i}.", ts=f"2026-11-0{i + 1}T10:00:00Z")
    m.remember("У меня грыжа диска, поэтому никаких поездок дольше двух часов.", ts="2026-11-09T10:00:00Z")
    plain = m.recall("какую базу данных выбрали", k=3)
    with_steps = m.recall("какую базу данных выбрали", steps=["здоровье пользователя: грыжа, поездки"], k=3)
    main = [h.episode for h in with_steps if h.line == "main"]
    extra = [h for h in with_steps if h.line == "periphery"]
    assert main == [h.episode for h in plain]  # the main line is exactly what the question alone finds
    assert extra and not set(main) & {h.episode for h in extra}  # periphery: only new turns
    assert any("грыжа" in h.text for h in extra)
    out = m.render(with_steps)
    assert out.index("Also found only through the reasoning steps") > max(out.index(f"#{e[:8]}") for e in main)
    # no room left -> the periphery is dropped, the main line stays whole
    tight = m.render(with_steps, max_chars=sum(len(h.text) for h in with_steps if h.line == "main") + 200)
    assert all(f"#{e[:8]}" in tight for e in main) and "грыжа" not in tight


def test_final_report_of_a_turn_weighs_like_a_decision_and_the_recap_is_kept(tmp_path):
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Откати вторую версию правил скидок.", "2026-11-17T09:40:00Z"),
        _turn(2, "assistant", "Предлагаю сначала посмотреть отчёты по двум магазинам, потом решить.", "2026-11-17T09:41:00Z"),
        _turn(3, "assistant", "Вторую версию откатил, коммит 9c0d5e1. Итог: вторая версия не помогла, на тестовой выборке стало 10/3/2.",
              "2026-11-17T09:44:00Z"),
        _turn(4, "user", "Хорошо, дальше по плану.", "2026-11-17T09:50:00Z"),
    ])
    st = {t: s for (t, s) in m.s.q("SELECT f.text, s.status FROM fragments f JOIN frag_status s ON s.fragment=f.id")}
    assert st["Вторую версию откатил, коммит 9c0d5e1."] == "report"  # the final message of the turn
    assert st["Предлагаю сначала посмотреть отчёты по двум магазинам, потом решить."] == "progress"  # not the last message
    out = m.render(m.recall("почему откатили вторую версию", k=2))
    assert "→ сделано 2026-11-17, коммит 9c0d5e1 (#t3)" in out  # nested under the request it closes
    assert "Предлагаю сначала" not in out  # progress of the turn is not searched
    # the desktop app's end-of-turn box: the recap lives in a tool call and is kept as the assistant's text
    content = [{"type": "tool_use", "name": "mcp__ccd_turn__wrap_up", "input": {"recap": "Раунд 2 не помог: 10/3/2."}}]
    assert CC._text(content) == "Раунд 2 не помог: 10/3/2."
    # the assistant's lines are not cut as repeats (a final report restates earlier lines)
    line = "Итог: корзина считает скидку верно, но округление теряет копейки при оплате по счёту."
    ts = CC.dedupe([_turn(9, "assistant", line, "2026-11-17T10:00:00Z"), _turn(10, "assistant", "Готово.\n" + line,
                    "2026-11-17T10:05:00Z")])
    assert line in ts[1]["text"]


def test_one_report_per_user_turn_and_unlinked_reports_compete(tmp_path):
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Перенеси хранилище памяти на SQLite и закоммить.", "2026-11-20T10:00:00Z"),
        _turn(2, "assistant", "Сейчас перенесу хранилище, жду конец тестов.", "2026-11-20T10:01:00Z"),
        _turn(3, "assistant", "Хранилище памяти перенесено на SQLite, коммит abc1234.", "2026-11-20T10:05:00Z"),
        # a report with no user turn before it (a session that starts with the assistant, no user turn at all)
        _turn(4, "assistant", "Итог ночного прогона: хранилище памяти на SQLite держит 10 000 записей.",
              "2026-11-19T03:00:00Z", session="night"),
    ])
    finals = m._finals()
    assert set(finals) == {"t3", "t4"} and finals["t3"][0] == "t1" and finals["t4"][0] is None  # one report per turn
    hits = m.recall("хранилище памяти SQLite", k=6)
    assert [h.episode for h in hits] == ["t4", "t1"]  # t3 is nested under t1, t2 (progress) is not searched
    assert hits[1].report is not None and hits[1].report.episode == "t3"
    # a later message of the same turn becomes its report; the earlier one goes back to progress
    m.import_turns([_turn(5, "assistant", "Добавил тест миграции хранилища, коммит def5678.", "2026-11-20T10:09:00Z")])
    assert set(m._finals()) == {"t5", "t4"} and m._status()[next(f for f in m._status() if ":t3:" in f)][0] == "progress"


def test_short_user_turn_confirms_the_previous_proposal_and_anchors_the_report(tmp_path):
    assert CC.is_short("Fix them") and CC.is_short("да") and CC.is_short("Yes, recreate")
    assert not CC.is_short("ну что там") and not CC.is_short("сколько там ещё?")  # questions are not confirmations
    assert not CC.is_short("Откатить вторую версию правил скидок")  # > SHORT_WORDS words
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Почему скидка применяется не туда? Разберись с корзиной.", "2026-11-17T09:00:00Z"),
        _turn(2, "assistant", "Предлагаю исправить три проблемы корзины: порядок скидок, округление и "
                              "статус заказа. Исправить их дальше?", "2026-11-17T09:10:00Z"),
        _turn(3, "user", "Fix them", "2026-11-17T09:12:00Z"),
        _turn(4, "assistant", "Сейчас правлю порядок и округление.", "2026-11-17T09:13:00Z"),
        _turn(5, "assistant", "Вторая версия правил скидок записана и закоммичена (2b6f8a3), но не помогла: 10/3/2.",
              "2026-11-17T09:40:00Z"),
        _turn(6, "user", "Откатить вторую версию правил скидок и записать вывод.", "2026-11-17T10:00:00Z"),
    ])
    assert m._confirms() == {"t3": "t2"} and m._finals()["t5"][0] == "t3"  # the report belongs to "Fix them"
    st = {f.split(":")[1]: s for f, (s, _) in m._status().items()}
    assert st.get("t3", "confirm") == "confirm" and st["t4"] == "progress"  # "Fix them" may have no sentence
    hits = m.recall("почему вторая версия правил скидок не помогла", k=3)
    h = next(x for x in hits if x.episode == "t3")  # found through its report, one slot for the whole chain
    assert h.proposal.episode == "t2" and h.report.episode == "t5"
    out = m.render(hits)
    assert "решение: подтверждено пользователем" in out and "→ подтверждено пользователем 2026-11-17: «Fix them»" in out
    assert "→ сделано 2026-11-17, коммит 2b6f8a3 (#t5)" in out
    rows = m.decisions()
    assert any(r["kind"] == "подтверждено" and "Исправить их дальше" in r["decision"] for r in rows)
    # the short turn itself has no place in search: by its own text it is not found
    assert all(x.episode != "t3" for x in m.recall("Fix them", k=1)) or m.recall("Fix them", k=1)[0].report
    # the reader keeps short turns, and repeated "да" are separate events
    ts = CC.dedupe([_turn(7, "user", "да", "2026-11-17T11:00:00Z"), _turn(8, "user", "да", "2026-11-17T11:05:00Z")])
    assert len(ts) == 2


def test_short_turns_by_dialogue_act(tmp_path):
    assert [CC.short_act(t) for t in ("Fix them", "да", "нет", "Сначала обсудим", "Процесс завершён", "Started")] == \
        ["directive", "agree", "reject", "defer", "status", "status"]
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Разберись, почему падает сборка на CI, и предложи исправление.", "2026-11-20T09:00:00Z"),
        _turn(2, "assistant", "Предлагаю перенести сборку на другой раннер и пересобрать кэш. Переносить?", "2026-11-20T09:10:00Z"),
        _turn(3, "user", "Сначала обсудим", "2026-11-20T09:11:00Z"),
        _turn(4, "assistant", "Хорошо: другой раннер даёт ~6 минут вместо 2, кэш пересобирать не нужно.",
              "2026-11-20T09:15:00Z"),
        _turn(5, "user", "Процесс завершён", "2026-11-20T10:00:00Z"),
        _turn(6, "assistant", "Вижу: сборка на новом раннере прошла, тесты совпали с локальными, коммит 1234abc.", "2026-11-20T10:05:00Z"),
    ])
    assert m._short_status("t3") == ("closed", "hold") and m._short_status("t5") == ("event", "")
    # a status message is a separate event: the report after it belongs to the deferring turn, not to "Процесс завершён"
    assert m._finals()["t6"][0] == "t3" and "t4" not in m._finals()
    rows = m.decisions()
    assert any(r["kind"] == "отложено" and "Переносить?" in r["decision"] for r in rows)
    out = m.render(m.recall("перенос сборки на другой раннер", k=3))
    assert "решение: отложено пользователем" in out and "→ отложено пользователем 2026-11-20: «Сначала обсудим»" in out


def test_infinitive_done_by_user_and_resume_after_summary(tmp_path):
    assert CC.short_act("Откатить миграцию") == "directive"  # directive infinitive
    assert CC.is_request("Удалите старый стенд в панели вручную: Settings → Delete.")
    assert not CC.is_request("Готово, коммит abc1234. Мой вывод ниже.")
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Пересоздай тестовый стенд из чистого образа.", "2026-11-09T19:00:00Z"),
        _turn(2, "assistant", "У меня нет прав на удаление. Удалите старый стенд в панели вручную, потом я создам заново.",
              "2026-11-09T19:10:00Z"),
        _turn(3, "user", "Deleted it", "2026-11-09T19:12:00Z"),
        _turn(4, "assistant", "Стенд создан заново из чистого образа, коммит 7e3a1b2.", "2026-11-09T19:20:00Z"),
        {**_turn(5, "user", "Continue", "2026-11-10T08:00:00Z"), "after_summary": True},
        _turn(6, "assistant", "Продолжаю: ссылки в README обновлены, коммит 4f1c2d9.", "2026-11-10T08:05:00Z"),
    ])
    assert m._short_status("t3") == ("closed", "done") and m._short_status("t5") == ("resume", "")
    # "Continue" after a summary is no anchor: the work goes on, the last message (t6) closes "Deleted it"
    assert "t4" not in m._finals() and m._finals()["t6"][0] == "t3"
    rows = m.decisions()
    assert any(r["kind"] == "выполнено пользователем" and "Удалите старый стенд" in r["decision"] for r in rows)
    out = m.render(m.recall("пересоздать тестовый стенд", k=3))
    assert "просьба ассистента" in out and "→ выполнено пользователем 2026-11-09: «Deleted it»" in out


def test_window_keeps_the_lead_line_of_a_long_list():
    from ctxgraph.memory import _window

    items = "\n".join(f"{k}. " + "Пункт про сборку и тесты, подробно и длинно. " * 6 for k in range(1, 6))
    text = "Сначала вступление о проекте.\n\nУбираем модуль аналитики из приложения полностью:\n\n" + items + \
        "\n6. Веб-версию не трогать."
    out = _window(text, "Веб-версию не трогать.", 300)
    assert out.startswith("…Убираем модуль аналитики из приложения полностью:\n…\n6. Веб-версию не трогать.")
