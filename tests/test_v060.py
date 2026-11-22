"""v0.6.0 (rules written before the code): save_chat, the import_claude_ai tool, permanent-only rules with the
migration, a hold on the user's yes closed by that yes, the .mcpb manifest. Synthetic data, offline (HashingEncoder)."""

import json
import zipfile

from ctxgraph.embed import HashingEncoder
from ctxgraph.memory import ProjectMemory, classify, is_rule


def _export(tmp_path):
    conv = [
        {"uuid": "c-notes-1", "name": "Заметки: выбор базы", "created_at": "2026-11-08T09:00:00Z",
         "chat_messages": [
             {"uuid": "m1", "sender": "human", "created_at": "2026-11-08T09:00:00Z",
              "text": "Для заметок берём SQLite: один файл, без сервера."},
             {"uuid": "m2", "sender": "assistant", "created_at": "2026-11-08T09:01:00Z",
              "text": "Понял: SQLite в одном файле, сервер базы не нужен."}]},
        {"uuid": "c-other", "name": "Рецепт борща", "created_at": "2026-11-01T09:00:00Z",
         "chat_messages": [{"uuid": "m3", "sender": "human", "created_at": "2026-11-01T09:00:00Z",
                            "text": "Как сварить борщ на четверых?"}]},
    ]
    z = tmp_path / "export.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("conversations.json", json.dumps(conv, ensure_ascii=False))
        f.writestr("projects.json", "[]")
    return z


def _mem(tmp_path):
    return ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")


def _turn(i, role, text, ts, session="s1"):
    return {"id": f"t{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


CHAT = [
    {"role": "user", "text": "Для заметок берём SQLite, Postgres для этого проекта избыточен."},
    {"role": "assistant", "text": "Понял: SQLite в одном файле, схему пришлю следующим сообщением."},
    {"role": "user", "text": "Да"},
    {"role": "assistant", "text": "Схема готова: две таблицы, notes и tags, миграция в migrations/001.sql."},
    {"role": "user", "text": "Да"},
    {"role": "assistant", "text": "Добавил индекс по тегам, тесты проходят, изменения закоммичены (a1b2c3d)."},
]


def test_save_chat_is_idempotent_by_portions(tmp_path):
    m = _mem(tmp_path)
    r1 = m.save_chat("Заметки: база", CHAT[:4], offset=0)
    r2 = m.save_chat("Заметки: база", CHAT[2:], offset=2)  # overlapping portion: only the 2 last turns are new
    r3 = m.save_chat("Заметки: база", CHAT, offset=0)  # the whole chat again: nothing new
    assert (r1["new"], r2["new"], r3["new"]) == (4, 2, 0)
    # the repeated short "Да" at two positions is two records
    assert m.s.q("SELECT COUNT(*) FROM episodes WHERE text='Да'")[0][0] == 2
    src = {o for (o,) in m.s.q("SELECT origin FROM turn_meta")}
    assert src == {"chat"} and m.s.q("SELECT DISTINCT session FROM turn_meta")[0][0] == "chat:Заметки: база"
    # statuses as for transcripts: the user's decision, the last assistant message of a turn is its report
    assert any(r["decision"].startswith("Для заметок берём SQLite") for r in m.decisions())
    st = {t: s for t, s in m.s.q("SELECT f.text, s.status FROM frag_status s JOIN fragments f ON f.id=s.fragment")}
    assert st.get("Добавил индекс по тегам, тесты проходят, изменения закоммичены (a1b2c3d).") == "report"
    # given timestamps are kept; missing ones keep the order
    r = m.save_chat("Другой чат", [{"role": "user", "text": "Отчёты пишем по-русски, код по-английски.",
                                    "ts": "2026-11-01T10:00:00Z"}, {"role": "tool", "text": "x"}])
    assert (r["new"], r["skipped"]) == (1, 1)
    assert m.s.q("SELECT ts FROM turn_meta WHERE session='chat:Другой чат'")[0][0] == "2026-11-01T10:00:00Z"


def test_save_chat_and_import_tools(tmp_path):
    from ctxgraph import memory_mcp as M

    m = _mem(tmp_path)
    M._mem = m
    try:
        out = M.save_chat("Заметки: база", CHAT, 0)
        assert "Saved 6 new of 6" in out and "last portion" in out
        many = [{"role": "user" if i % 2 == 0 else "assistant", "text": f"Реплика номер {i} в длинном чате о заметках"}
                for i in range(35)]
        out = M.save_chat("Длинный", many, 0)
        assert "Saved 30 new of 30" in out and "offset=30" in out
        assert "Saved 5 new of 5" in M.save_chat("Длинный", many[30:], 30)
        z = _export(tmp_path)
        lst = M.import_claude_ai(str(z))
        assert "Nothing imported" in lst and "Рецепт борща" in lst and "Заметки: выбор базы" in lst
        assert m.s.q("SELECT COUNT(*) FROM turn_meta WHERE origin='claude.ai'")[0][0] == 0
        assert "Imported 2 new" in M.import_claude_ai(str(z), match="заметки|SQLite")
        assert "Imported 0 new" in M.import_claude_ai(str(z), match="заметки|SQLite")
        assert "nothing imported" in M.import_claude_ai(str(z), match="нет-такого")
    finally:
        M._mem = None


def test_only_permanent_user_rules_are_rules():
    yes = ["Ключи API всегда только в .env.", "Никогда не публикуй реальные переписки.",
           "На будущее: эмбеддинги сохраняй как датасет.", "API keys go only in .env, never in logs.",
           "From now on, write reports in English."]
    no = ["Решение: по умолчанию — BM25 (без модели).",  # an ordinary decision
          "Если смешанный не хуже полного — делаем его режимом по умолчанию.",  # conditional
          "Другая сессия сейчас правит README, никогда не перезаписывай его целиком.",  # temporary note
          "Реализацию и демо начинай только после моего «да».",  # a hold
          "Пришли оценку стоимости; без моего «да» не запускай.",
          "Я только что закоммитил правки в отчёт.", "Это не только быстрее, но и дешевле.",
          "If the mixed view is not worse, we always use it.", "Use BM25 by default for new stores.",
          "Всегда ли нужен Docker?"]
    assert [t for t in yes if not is_rule(t)] == []
    assert [t for t in no if is_rule(t)] == []
    assert classify("user", "Решение: по умолчанию — BM25 (без модели).")[0] != "rule"


def test_migration_drops_stale_auto_rules_keeps_manual(tmp_path):
    m = _mem(tmp_path)
    m.remember("Ключи API всегда только в .env.", ts="2026-10-22T10:00:00Z")
    m.pin_rule("По умолчанию — BM25, это ручное правило.")
    db = m.db_path
    # rules pinned by an older version: an ordinary decision and an agent task's line
    m.s.db.execute("INSERT INTO pinned_rules VALUES('aaaaaa','Решение: по умолчанию — BM25.','2026-10-23','auto','',0)")
    m.s.db.execute("INSERT INTO pinned_rules VALUES('bbbbbb','Never copy the private file whole.','2026-10-24','auto',"
                   "'f:agent-ep:0',0)")
    m.s.db.execute("INSERT INTO turn_agent VALUES('agent-ep','brief','')")
    m.s.db.execute("INSERT INTO pinned_rules VALUES('cccccc','Всегда пиши тесты.','2026-10-25','auto','',1)")
    m.s.db.commit()
    m.s.db.close()
    m2 = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    assert m2.db_path == db
    assert sorted(r["text"][:12] for r in m2.rules()) == ["Ключи API вс", "По умолчанию"]
    # the user's removal stays a removal
    assert m2.s.q("SELECT removed FROM pinned_rules WHERE id='cccccc'")[0][0] == 1


def test_hold_on_the_users_yes_closes_on_that_yes(tmp_path):
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Архитектуру утверждаю. Реализацию и демо начинай только после моего «да».", "2026-10-30T07:37:00Z"),
        _turn(2, "assistant", "Документ готов, жду подтверждения.", "2026-10-30T07:40:00Z"),
        _turn(3, "user", "Да, начинай", "2026-10-30T07:56:00Z"),
        _turn(4, "assistant", "Работаю.", "2026-10-30T07:57:00Z"),
        _turn(5, "user", "Правки к документу внёс, продолжай.", "2026-10-30T07:58:00Z"),
        _turn(6, "assistant", "Граф v2 на примере кошельков готов и закоммичен (ada52d4), сервер запущен.",
              "2026-10-30T08:20:00Z"),
        # another hold on a yes that never came
        _turn(7, "user", "Миграцию базы запускай только после моего «да».", "2026-10-30T09:00:00Z", "s2"),
        _turn(8, "assistant", "Скрипт миграции готов, не запускал.", "2026-10-30T09:05:00Z", "s2"),
    ])
    texts = [it["text"] for it in m.later()]
    assert not any(t.startswith("Реализацию и демо") for t in texts)
    assert any(t.startswith("Миграцию базы") for t in texts)
    z = next(r for r in m.decisions() if r["decision"].startswith("Реализацию и демо"))["resolved"]
    assert z and z["confirmed"] == "2026-10-30" and z["commit"] == "ada52d4"


def test_hold_with_a_yes_but_no_report_stays_open(tmp_path):
    m = _mem(tmp_path)
    m.import_turns([
        _turn(1, "user", "Публикацию делай только после моего «да».", "2026-10-30T07:37:00Z"),
        _turn(2, "assistant", "Хорошо, жду.", "2026-10-30T07:40:00Z"),
        _turn(3, "user", "Да", "2026-10-30T07:56:00Z"),
    ])
    assert any(it["text"].startswith("Публикацию делай") for it in m.later())


def test_mcpb_manifest(tmp_path):
    import subprocess
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    out = tmp_path / "x.mcpb"
    subprocess.run([sys.executable, str(root / "scripts" / "build_mcpb.py"), "--out", str(out)], check=True)
    with zipfile.ZipFile(out) as z:
        man = json.loads(z.read("manifest.json"))
        assert "icon.png" in z.namelist()
    for k in ("manifest_version", "name", "version", "description", "author", "server"):
        assert k in man
    assert man["user_config"]["project"]["type"] == "directory" and man["user_config"]["project"]["required"]
    cfg = man["server"]["mcp_config"]
    assert cfg["env"]["CTXGRAPH_PROJECT"] == "${user_config.project}"
    assert cfg["platform_overrides"]["win32"]["command"].endswith("ctxgraph-mcpw.exe")  # no console
    names = {t["name"] for t in man["tools"]}
    assert {"recall", "save_chat", "import_claude_ai"} <= names
