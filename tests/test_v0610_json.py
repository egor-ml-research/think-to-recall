"""v0.6.10: `--json` for recall / decisions / later / rules / projects: parses, has the documented keys. Synthetic."""

import json
import os
import subprocess
import sys
from pathlib import Path

from cotrail.memory import ProjectMemory

COMMON = {"id", "date", "status", "topic", "text"}


def _t(i, role, text, ts, session="s1"):
    return {"id": f"j{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


TURNS = [_t(1, "user", "Переходим на Postgres для сервиса бронирования.", "2026-11-10T10:00:00Z"),
         _t(2, "assistant", "Готово: сервис бронирования переведён на Postgres, коммит 1a2b3c4.", "2026-11-10T10:05:00Z"),
         _t(3, "user", "Никогда не пушить в main без вопроса.", "2026-11-11T10:00:00Z"),
         _t(4, "assistant", "Принято.", "2026-11-11T10:01:00Z"),
         _t(5, "user", "Кэширование ответов через Redis оставим на потом.", "2026-11-12T10:00:00Z"),
         _t(6, "assistant", "Хорошо, кэш пока не делаю.", "2026-11-12T10:01:00Z")]


def _cli(tmp_path, *args):
    root = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", ""), "COTRAIL_LANG": "en",
           "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    for k in ("COTRAIL_PROJECT", "COTRAIL_QUALITY", "PYTHONIOENCODING"):
        env.pop(k, None)  # the JSON is UTF-8 bytes whatever the console code page
    r = subprocess.run([sys.executable, "-m", "cotrail.cli", "--home", str(tmp_path / "home"), *args],
                       cwd=tmp_path / "proj", capture_output=True, timeout=180, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    return json.loads(r.stdout.decode("utf-8"))


def test_json_outputs(tmp_path, monkeypatch):
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    (tmp_path / "proj").mkdir()
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(TURNS)
    m.s.db.close()
    rec = _cli(tmp_path, "recall", "Postgres бронирование", "--json")
    assert rec and all(COMMON | {"kind", "role", "ts", "line", "score", "source", "report", "gist"} <= set(r) for r in rec)
    assert any("Postgres" in r["text"] for r in rec)
    dec = _cli(tmp_path, "decisions", "--json")
    assert dec and all(COMMON | {"kind", "commit", "done", "resolved", "ts"} <= set(r) for r in dec)
    assert any("Postgres" in r["text"] and r["status"] == "decision" for r in dec)
    lat = _cli(tmp_path, "later", "--json")
    assert lat and all(COMMON | {"kind", "source"} <= set(r) for r in lat) and lat[0]["source"] == "chat"
    assert "Redis" in lat[0]["text"]
    rules = _cli(tmp_path, "rules", "--json")
    assert rules and all(COMMON | {"origin"} <= set(r) for r in rules)
    assert rules[0]["text"] == "Никогда не пушить в main без вопроса." and rules[0]["status"] == "rule"
    assert _cli(tmp_path, "rules", "--global", "--json") == []
    pr = _cli(tmp_path, "projects", "--json")
    assert len(pr) == 1 and COMMON | {"path", "records", "store"} <= set(pr[0])
    assert pr[0]["path"] == str((tmp_path / "proj").resolve()) and pr[0]["records"] == 6
