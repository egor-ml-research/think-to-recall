"""v0.6.7: cotrail's own output pasted back into a chat is never a rule / decision / "later" item; a rule is not
pinned twice. Synthetic projects only."""

from cotrail import memory as M
from cotrail import pasted as PS
from cotrail.memory import ProjectMemory


def _t(i, role, text, ts, session="c1"):
    return {"id": f"p{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "claude-ai"}


PASTED = """Вот что выдаёт cotrail rules:
- #7c9b63 2026-10-28 (auto): Никогда не пушить в main без вопроса.
- #a1b2c3 2026-10-29 (manual): Always keep API keys only in .env.
- #d4e5f6 2026-11-01 (global): Answer the user in Russian.
и decisions:
- 2026-11-02 [делать]: Перейти на Postgres для сервиса бронирования.
- 2026-11-03 [do]: Use SQLite for the cache, later.
    for reference - the report 2026-11-03: done
- 2026-11-04 · чат · #e7f8a9: Кэш Redis оставим на потом.
- 2026-11-05 · decision · topic: db · #0a1b2c3d: Always run migrations before tests."""


def _mem(tmp_path, monkeypatch):
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    monkeypatch.setenv("COTRAIL_LANG", "en")
    return ProjectMemory(tmp_path / "proj", home=tmp_path / "home")


def test_ctx_output_lines():
    runs = PS.ctx_output(PASTED)
    assert len(runs) == 2 and "никогда не пушить в main" in runs[0] and "for reference" in runs[1]
    assert PS.ctx_output("Never push to main without asking.\n- buy milk") == []
    assert not PS.in_ctx_output("Never push to main without asking.", PS.ctx_output("- #7c9b63 2026-10-28 (auto): x"))


def test_pasted_cotrail_output_adds_nothing(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch)
    m.import_turns([_t(1, "user", PASTED, "2026-11-20T10:00:00Z"),
                    _t(2, "assistant", "Понял, это вывод cotrail.", "2026-11-20T10:01:00Z")])
    assert m.rules() == []
    assert m.decisions(50) == []
    assert [it for it in m.later() if it["source"] == "chat"] == []
    # the user's own rule in a later turn is still pinned
    m.import_turns([_t(3, "user", "Никогда не коммить секреты в репозиторий.", "2026-11-21T10:00:00Z")])
    assert [r["text"] for r in m.rules()] == ["Никогда не коммить секреты в репозиторий."]


def test_duplicate_pins_are_one_rule(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch)
    m.import_turns([_t(1, "user", "Никогда не пушить в main без вопроса.", "2026-11-20T10:00:00Z")])
    [auto] = m.rules()
    assert auto["origin"] == "auto"
    for text in ("никогда  не пушить в MAIN без вопроса", f"- #{auto['id']} 2026-11-20 (auto): Никогда не пушить в main без вопроса.",
                 f"- 2026-11-20 · #{auto['id']}: Никогда не пушить в main без вопроса."):
        assert m.pin_rule(text) == auto["id"]
    [r] = m.rules()
    assert r["origin"] == "manual" and r["text"] == "Никогда не пушить в main без вопроса."
    home = tmp_path / "home"
    g = M.pin_global_rule("Answer the user in Russian.", home)
    assert M.pin_global_rule("- #abc123 2026-11-01 (global): answer the user in russian (global)", home) == g
    assert len(M.global_rules(home)) == 1
    # an auto rule identical to a global one is not pinned in the project again
    M.pin_global_rule("Always run the tests before a commit.", home)
    m.import_turns([_t(2, "user", "Always run the tests before a commit.", "2026-11-21T10:00:00Z")])
    texts = [x["text"] for x in m.rules()]
    assert texts.count("Always run the tests before a commit.") == 1
    assert [x["origin"] for x in m.rules() if x["text"].startswith("Always run")] == ["global"]
