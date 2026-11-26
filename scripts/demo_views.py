"""A synthetic project for the «Волны» / «Живая память» demo: a fictional habit-tracker app, six weeks of chat
(decisions, changes of decision, reports, "later" items) and a synthetic MCP call log. No real data.

    python scripts/demo_views.py OUT_DIR [--mode waves|live]  -> OUT_DIR/home (store), OUT_DIR/views.html
"""

from __future__ import annotations

import argparse
import datetime as dt
import random
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cotrail.calls import log_call  # noqa: E402
from cotrail.embed import HashingEncoder  # noqa: E402
from cotrail.memory import ProjectMemory  # noqa: E402

# (day, user turn, assistant report or "") - a fictional habit tracker; Russian, as the change-of-decision detector is
CHAT = [
    (0, "Решили: данные привычек храним в SQLite на устройстве, офлайн, без сервера синхронизации.",
     "Готово: схема SQLite для привычек и отметок, миграции в db/schema.sql, коммит 3f2a9c1. Тесты проходят."),
    (1, "Регистрация по magic link, без паролей в онбординге.",
     "Готово: регистрация по magic link на почту, экраны онбординга 1-3, коммит 8b41d07."),
    (2, "Как серия должна считать пропущенный день на графике серий?", ""),
    (2, "Делаем так: серия переживает один пропуск в неделю, на графике серий это серая точка.",
     "Готово: правило серии в streaks.py, один льготный день в неделю, точки на графике, коммит 51c0e8a."),
    (3, "График серий: подпись льготного дня под графиком.",
     "Готово: легенда льготного дня под графиком серий, коммит 1e5f0d3."),
    (4, "Firebase для синхронизации не используем, файл SQLite остаётся на устройстве.",
     "Принято: заглушка Firebase убрана, синхронизация остаётся локальной в SQLite, коммит 2d7b3e4."),
    (5, "Напоминания: одно пуш-напоминание на привычку, тихие часы с 22 до 8.",
     "Готово: пуш-напоминания по привычкам с тихими часами, reminders.py, коммит 0c9f6aa."),
    (6, "Виджет на главный экран с привычками на сегодня — отложим на потом.", ""),
    (7, "Пейвол ставим после третьей привычки, пробный период подписки 7 дней.",
     "Готово: пейвол после третьей привычки, пробный период 7 дней в подписке, коммит e47d2b9."),
    (8, "Добавь тепловую карту отметок за 12 недель.",
     "Готово: тепловая карта отметок за 12 недель, charts/heatmap.py, коммит 9a1c3f0."),
    (9, "Онбординг: шаг с почтой убираем, magic link приходит после первой привычки.",
     "Готово: онбординг без шага с почтой, magic link после первой привычки, коммит 4be8d12."),
    (10, "Конфликты синхронизации: побеждает последняя отметка, без диалога слияния.",
     "Готово: last-write-wins для конфликтов отметок в sync.py, коммит 77e0b5c."),
    (11, "Тепловая карта: недели начинаются с понедельника.", "Готово: недели тепловой карты с понедельника, коммит 3a7e9b0."),
    (12, "Напоминания: вечернюю сводку пушем убираем, остаётся напоминание по привычке.",
     "Готово: вечерняя пуш-сводка удалена, напоминания по привычкам без изменений, коммит c3a84f1."),
    (13, "Экспорт данных привычек в CSV — потом.", ""),
    (14, "Переходим с SQLite на устройстве на сервер синхронизации с Postgres для данных привычек.",
     "Готово: сервер синхронизации с Postgres, данные привычек по HTTPS, SQLite теперь кэш, коммит 6f12d9e."),
    (15, "Цена подписки: 3 доллара в месяц, годовой план 24 доллара.",
     "Готово: цены подписки в пейволе, месяц 3, год 24, коммит a90b7c2."),
    (16, "Сервер синхронизации: лимит 60 запросов в минуту на устройство.",
     "Готово: лимит 60 в минуту на устройство на сервере синхронизации, коммит d48f1a3."),
    (17, "Что делать с отметками, сделанными офлайн, пока сервер синхронизации недоступен?", ""),
    (18, "Решили: офлайн-отметки копятся в очереди и отправляются на сервер синхронизации при подключении.",
     "Готово: офлайн-очередь отметок, отправка при переподключении в sync.py, коммит 5d3c2a7."),
    (19, "Онбординг: текст короче, максимум три экрана.",
     "Готово: текст онбординга сокращён до трёх экранов, коммит b2e9f41."),
    (20, "Импорт шагов из Apple Health как привычки — на потом.", ""),
    (21, "Пейвол: вместо третьей привычки показываем пейвол в конце первой недели пробного периода.",
     "Готово: пейвол перенесён в конец первой недели пробного периода, коммит 0f7a6c8."),
    (22, "Пуш-напоминания: кнопка отложить на 1 час.",
     "Готово: отложить напоминание на 1 час, действие уведомления в reminders.py, коммит 8c1d5e2."),
    (23, "Тепловая карта: цвета из палитры бренда.", "Готово: тепловая карта в палитре бренда, коммит 2c8f6a1."),
    (25, "Виджет не делаем в релизе 1.0, оставляем на потом.", ""),
    (26, "Подписка: пожизненного плана не будет.", "Принято: пожизненного плана в пейволе нет, коммит 72b0c9e."),
    (27, "Ошибка в sync при переподключении с пустой очередью, исправь.",
     "Исправлено: пустая офлайн-очередь больше не роняет sync при переподключении, тест добавлен, коммит 1b7e4d9."),
    (28, "Серии: вместо одного пропуска в неделю льготных дней два в месяц.",
     "Готово: льготные дни серии — два в месяц, streaks.py и легенда графика, коммит e1d6a07."),
    (29, "Тихие часы напоминаний настраиваются в настройках.", "Готово: настройка тихих часов напоминаний, коммит 4c9b2f5."),
    (30, "Онбординг: письмо с magic link с иконкой приложения и одной строкой текста.",
     "Готово: шаблон письма magic link с иконкой, коммит 9e3f7d1."),
    (31, "Чек-лист релиза 1.0: синхронизация, пейвол, напоминания, графики.",
     "Готово: чек-лист релиза в docs/release.md, все четыре области зелёные, коммит 6b2a0e4."),
    (32, "График серий: показывать лучшую серию за всё время.", "Готово: лучшая серия на графике серий, коммит 7d1e0c4."),
    (33, "Тёмная тема для графиков — потом.", ""),
    (34, "Решили: выпускаем 1.0 в понедельник с сервером синхронизации и пейволом после пробной недели.",
     "Готово: сборка 1.0 с тегом v1.0.0, тексты для магазина готовы, коммит f05c8a2."),
    (35, "Пейвол: годовой план показываем первым.", "Готово: годовой план первым в пейволе, коммит 3e8b1f6."),
    (36, "Синхронизация: сжатие запросов к серверу синхронизации.", "Готово: gzip для запросов sync, коммит 0a4d7c3."),
    (38, "Онбординг: пропуск онбординга для вернувшихся пользователей.",
     "Готово: вернувшиеся пользователи пропускают онбординг, коммит 6c2f9a8."),
    (40, "Напоминания: отложить на 30 минут вместо 1 часа.",
     "Готово: отложить напоминание теперь на 30 минут, коммит 8a0d3e7."),
    (41, "Экспорт в CSV всё-таки делаем в релизе 1.1.", "Готово: экспорт привычек и отметок в CSV, коммит 5f3a2e9."),
]


# each turn names its area in the same words, so the few dozen turns still form clear topics
AREAS = [("синхронизация данных", ("sqlite", "синхрониз", "sync", "firebase", "офлайн", "postgres"),
          ("модуль SyncEngine", "очередь отметок", "сервер hb-sync", "кэш устройства", "журнал конфликтов", "токен устройства")),
         ("пейвол и подписка", ("пейвол", "подписк", "план"), ("экран PaywallView", "тариф Plus", "пробная неделя", "StoreKit", "чек покупки", "промокод")),
         ("пуш-напоминания", ("напомина", "пуш", "тихие часы"), ("сервис Nudger", "канал APNs", "расписание пушей", "экран уведомлений", "звук напоминания", "бейдж иконки")),
         ("графики серий", ("серия", "серии", "серий", "тепловая карт", "тепловую карт", "график"),
          ("компонент StreakChart", "HeatGrid", "льготный день", "экран статистики", "лучшая серия", "легенда графика")),
         ("онбординг и magic link", ("онбординг", "magic link", "регистрац"),
          ("экран Welcome", "письмо входа", "сервис LinkSender", "первая привычка", "deep link", "шаблон письма")),
         ("релиз 1.0", ("релиз", "виджет", "экспорт", "apple health", "тёмная тема"),
          ("план релиза", "TestFlight", "ветка release", "страница магазина", "скриншоты магазина", "release notes"))]


def area(text: str):
    t = text.lower()
    return next((x for x in AREAS if any(k in t for k in x[1])), None)


def build(out: Path, mode: str = "live", lang: str = "ru") -> Path:
    """lang "ru": the Russian set above; "en": demo/habit_app.en.json (the same story in English, with side sessions)."""
    import json

    from cotrail.viewer import export_html

    home = out / "home"
    m = ProjectMemory(out / "habit-app", encoder=HashingEncoder(), home=home)
    t0 = dt.datetime(2026, 9, 1, 9, 0, tzinfo=dt.UTC)
    turns, rnd = [], random.Random(7)
    uid = lambda: str(uuid.UUID(int=rnd.getrandbits(128)))  # noqa: E731
    iso = lambda t: t.isoformat().replace("+00:00", "Z")  # noqa: E731
    if lang == "en":
        en = json.loads((Path(__file__).resolve().parents[1] / "demo" / "habit_app.en.json").read_text("utf-8"))
        chat, areas = [tuple(c) for c in en["chat"]], [(a, tuple(k), v) for a, k, v in en["areas"]]
        for j, (_, _, v) in enumerate(areas):  # small follow-ups of each area spread over the six weeks
            for k in range(6):
                fu, fr = en["followups"][(j + k) % len(en["followups"])], en["followup_reports"][(j * 6 + k) % len(en["followup_reports"])]
                chat.append((2 + (k * 7 + j * 3) % 40, fu.replace("{A}", v[k]).replace("{B}", v[(k + 2) % 6]),
                             fr.replace("{h}", f"{rnd.getrandbits(28):07x}")))  # fmt: skip
        side = en["side"]
    else:
        chat, side = list(CHAT), []
        for j, (_, _, v) in enumerate(AREAS):
            for k in range(6):
                chat.append((2 + (k * 7 + j * 3) % 40, f"Поправь {v[k]} вместе с {v[(k + 2) % 6]}.", f"Готово, коммит {rnd.getrandbits(28):07x}."))
    chat.sort(key=lambda c: c[0])
    if lang == "en":
        _en_turns(chat, en, areas, turns, t0, rnd, uid, iso)
        chat = []
    for i, (day, user, report) in enumerate(chat):
        if lang != "en":
            ar = area(user)
            if ar and not user.startswith("Поправь"):  # two of the area's names, in turn, so they co-occur
                v = ar[2]
                user = f"{user} Затрагивает {v[i % 6]} и {v[(i + 1) % 6]}."
        ts = t0 + dt.timedelta(days=day, hours=rnd.randint(0, 8), minutes=rnd.randint(0, 59))
        turns.append({"id": uid(), "session": f"s{day // 7}", "role": "user", "text": user, "source": "cc", "ts": iso(ts)})
        if report:
            turns.append({"id": uid(), "session": f"s{day // 7}", "role": "assistant", "text": report, "source": "cc",
                          "ts": iso(ts + dt.timedelta(minutes=4))})  # fmt: skip
    for k, (day, brief, rep, *par) in enumerate(side):  # side sessions started from a main chat: offshoots in the tree
        ts = t0 + dt.timedelta(days=day, hours=10)
        parent = f"{par[0].replace(' ', '-')}-{day // 14}" if par else f"s{day // 7}"
        turns.append({"id": uid(), "session": f"side{k}", "role": "user", "text": brief, "source": "cc", "ts": iso(ts),
                      "agent": {"kind": "brief", "parent": parent}})  # fmt: skip
        for j, part in enumerate([rep, "Notes saved to the report; nothing else to change.", "Closing this session."]):
            turns.append({"id": uid(), "session": f"side{k}", "role": "assistant", "text": part, "source": "cc",
                          "ts": iso(ts + dt.timedelta(minutes=6 + 5 * j))})  # fmt: skip
    m.import_turns(turns)
    # a synthetic Graphify graph of the app's code: the second tree and the code stars in Cosmos
    from cotrail import graphify as GF

    g = out / "graph.json"
    g.write_text(json.dumps(_code_graph(random.Random(3))), "utf-8")
    GF.import_graph(m.db_path, g)
    # a synthetic call log: an afternoon of recall / expand calls on the demo records (ids only, like the real one)
    ids = [e[:8] for (e,) in m.s.q("SELECT id FROM episodes WHERE role='user'")]
    (m.dir / "calls.jsonl").unlink(missing_ok=True)
    now = dt.datetime(2026, 10, 14, 14, 0, tzinfo=dt.UTC)
    for _ in range(40):
        now += dt.timedelta(seconds=rnd.randint(20, 240))
        tool = rnd.choice(["recall", "recall", "recall", "expand", "decisions"])
        got = rnd.sample(ids, 1 if tool == "expand" else rnd.randint(3, 6))
        log_call(m.dir, tool, " ".join("#" + x for x in got), rnd.randint(40, 900), now=now)
    return export_html(m, out=out / "views.html", mode=mode)


STEPS = ["Reading {f} first.", "Looking at how {A} handles this today.", "Updating {f}.", "Running the test suite.",
         "Checking the edge cases around {B}.", "Two tests failed; fixing the fixture.", "Re-running the tests: green."]
FILES = {"data sync": "sync.py", "paywall": "paywall.py", "reminders": "reminders.py", "streak charts": "streaks.py",
         "onboarding": "onboarding.py", "release": "docs/release.md"}


def _en_turns(chat, en, areas, turns, t0, rnd, uid, iso) -> None:
    """English set: one chat per area and fortnight; between a message and its report the assistant's work steps."""
    def area_of(t):
        t = t.lower()
        return next((x for x in areas if any(k in t for k in x[1])), areas[-1])
    for day, user, report in chat:
        ar = area_of(user)
        ss = f"{ar[0].replace(' ', '-')}-{day // 14}"
        ts = t0 + dt.timedelta(days=day, hours=rnd.randint(0, 8), minutes=rnd.randint(0, 59))
        turns.append({"id": uid(), "session": ss, "role": "user", "text": user, "source": "cc", "ts": iso(ts)})
        if not report:
            continue
        k = rnd.randint(2, 5)
        for j, st in enumerate(rnd.sample(STEPS, k)):
            turns.append({"id": uid(), "session": ss, "role": "assistant", "source": "cc", "ts": iso(ts + dt.timedelta(minutes=1 + j)),
                          "text": st.format(f=FILES.get(ar[0], "app.py"), A=ar[2][0], B=ar[2][rnd.randint(1, 5)])})  # fmt: skip
        turns.append({"id": uid(), "session": ss, "role": "assistant", "text": report, "source": "cc", "ts": iso(ts + dt.timedelta(minutes=k + 2))})


def _code_graph(rnd) -> dict:
    """A plausible Graphify graph.json for the demo app: folders, files, symbols, contains / imports / calls edges."""
    mods = {"app/sync": ["sync_engine", "queue", "conflicts", "device_cache", "api_client", "tokens"],
            "app/paywall": ["paywall_view", "plans", "storekit", "receipts", "promo"],
            "app/reminders": ["nudge_worker", "apns", "schedule", "quiet_hours", "snooze"],
            "app/charts": ["streak_chart", "heat_grid", "streaks", "legend", "stats_screen"],
            "app/onboarding": ["welcome", "link_sender", "first_habit", "deep_links", "email_templates"],
            "server": ["hb_sync", "routes", "rate_limit", "db", "migrations"],
            "tests": ["test_sync", "test_paywall", "test_reminders", "test_streaks", "test_onboarding", "test_server"],
            "scripts": ["load_test", "release", "seed_data"]}
    verbs = ["load", "save", "apply", "render", "handle", "build", "check", "update", "parse", "send", "merge", "replay", "format", "validate"]
    nodes, links, syms = [], [], []
    for d, files in mods.items():
        for f in files:
            path = f"{d}/{f}.py"
            fid = path.replace("/", "_")
            nodes.append({"id": fid, "label": f"{f}.py", "source_file": path, "source_location": "L1", "file_type": "code"})
            cls = "".join(w.title() for w in f.split("_"))
            here = [fid]
            if not d.startswith(("tests", "scripts")):
                nodes.append({"id": fid + "_c", "label": cls, "source_file": path, "source_location": "L12", "file_type": "code"})
                links.append({"source": fid, "target": fid + "_c", "relation": "contains", "confidence": "EXTRACTED"})
                here.append(fid + "_c")
            for k in range(rnd.randint(6, 16)):
                v = rnd.choice(verbs)
                nid = f"{fid}_{k}"
                lab = f"test_{v}_{f.replace('test_', '')}_{k}()" if d == "tests" else f".{v}_{rnd.choice(f.split('_'))}()"
                nodes.append({"id": nid, "label": lab, "source_file": path, "source_location": f"L{20 + 9 * k}", "file_type": "code"})
                links.append({"source": here[-1], "target": nid, "relation": "contains" if d == "tests" else "method", "confidence": "EXTRACTED"})
                syms.append(nid)
    for _ in range(len(syms) // 2):
        a, b = rnd.sample(syms, 2)
        links.append({"source": a, "target": b, "relation": "calls", "confidence": rnd.choice(["EXTRACTED", "INFERRED"])})
    return {"directed": False, "multigraph": False, "graph": {"schema_version": 1, "graphify_version": "0.9"}, "nodes": nodes, "links": links}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--mode", default="live")
    ap.add_argument("--lang", default="ru", choices=["ru", "en"])
    a = ap.parse_args()
    print(build(Path(a.out), a.mode, a.lang))
