"""v0.6.6: no-store hint for read commands, `ctxgraph projects`, global rules. Synthetic temp homes only."""

import json
import os
import subprocess
import sys
from pathlib import Path

from ctxgraph import memory as M
from ctxgraph.memory import ProjectMemory


def _t(i, role, text, ts, session="s1"):
    return {"id": f"g{i}", "session": session, "role": role, "ts": ts, "text": text, "source": "transcript"}


TURNS = [_t(1, "user", "Use Postgres for the booking service.", "2026-11-10T10:00:00Z"),
         _t(2, "assistant", "Done: Postgres it is.", "2026-11-10T10:01:00Z")]


def _store(tmp_path, monkeypatch, name="proj", turns=TURNS):
    monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    monkeypatch.setenv("CTXGRAPH_LANG", "en")
    proj = tmp_path / name
    proj.mkdir(exist_ok=True)
    m = ProjectMemory(proj, home=tmp_path / "home")
    m.import_turns(turns)
    m.s.db.close()
    return proj


def _cli(tmp_path, *args, cwd=None, stdin=None, lang="en"):
    root = str(Path(__file__).resolve().parents[1])
    env = {**os.environ, "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", ""), "CTXGRAPH_LANG": lang, "PYTHONIOENCODING": "utf-8", "HOME": str(tmp_path), "USERPROFILE": str(tmp_path)}
    env.pop("CTXGRAPH_PROJECT", None)
    env.pop("CTXGRAPH_QUALITY", None)
    argv = [sys.executable, "-m", "ctxgraph.cli", "--home", str(tmp_path / "home"), *args]
    return subprocess.run(argv, cwd=cwd or tmp_path, input=stdin, capture_output=True, text=True, encoding="utf-8",
                          timeout=180, env=env)


def test_store_remembers_its_project_path(tmp_path, monkeypatch):
    proj = _store(tmp_path, monkeypatch)
    [k] = M.known_projects(tmp_path / "home")
    assert k["path"] == str(proj.resolve()) and k["exact"] and k["records"] == 2 and k["last"] == "2026-11-10"


def test_old_store_path_from_transcripts_else_slug(tmp_path, monkeypatch):
    home = tmp_path / "home"
    proj = tmp_path / "old"
    slug = M.project_slug(proj)
    (home / slug).mkdir(parents=True)
    import sqlite3

    sqlite3.connect(str(home / slug / "graph.sqlite")).close()  # a store without memory_meta
    monkeypatch.setattr(M.Path, "home", classmethod(lambda cls: tmp_path))
    [k] = M.known_projects(home)
    assert k["path"] == slug and not k["exact"]
    tr = tmp_path / ".claude" / "projects" / slug
    tr.mkdir(parents=True)
    (tr / "a.jsonl").write_text(json.dumps({"type": "user", "cwd": str(proj.resolve())}) + "\n", "utf-8")
    [k] = M.known_projects(home)
    assert k["path"] == str(proj.resolve()) and k["exact"]


def test_no_store_lists_known_projects_and_creates_nothing(tmp_path, monkeypatch):
    a, b = _store(tmp_path, monkeypatch, "alpha"), _store(tmp_path, monkeypatch, "beta")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    for cmd in (["rules"], ["recall", "postgres"], ["decisions"], ["later"], ["status"], ["expand", "abc"]):
        r = _cli(tmp_path, *cmd, cwd=elsewhere)
        assert r.returncode != 0 and "No ctxgraph memory in this folder" in r.stderr, (cmd, r.stderr)
        assert str(a.resolve()) in r.stderr and str(b.resolve()) in r.stderr and "--project <path>" in r.stderr
    r = _cli(tmp_path, "rules", cwd=elsewhere, lang="ru")
    assert "В этой папке нет памяти ctxgraph. Известные проекты:" in r.stderr and "--project <путь>" in r.stderr
    assert len(M.known_projects(tmp_path / "home")) == 2  # no empty store made for "elsewhere"
    r = _cli(tmp_path, "--project", str(a), "status")
    assert r.returncode == 0 and json.loads(r.stdout)["episodes"] == 2


def test_no_store_single_project_is_used(tmp_path, monkeypatch):
    proj = _store(tmp_path, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = _cli(tmp_path, "status", cwd=elsewhere)
    assert r.returncode == 0 and "using the only project with one: " + str(proj.resolve()) in r.stderr
    assert json.loads(r.stdout)["project"] == str(proj.resolve())


def test_projects_command(tmp_path, monkeypatch):
    r = _cli(tmp_path, "projects")
    assert r.returncode == 0 and "No project" in r.stdout
    proj = _store(tmp_path, monkeypatch)
    r = _cli(tmp_path, "projects")
    assert r.returncode == 0 and "2026-11-10" in r.stdout and str(proj.resolve()) in r.stdout and " 2 " in r.stdout


def test_global_rules_everywhere(tmp_path, monkeypatch):
    proj = _store(tmp_path, monkeypatch)
    home = tmp_path / "home"
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    r = _cli(tmp_path, "pin-rule", "--global", "Answer the user in Russian.", cwd=elsewhere)
    assert r.returncode == 0 and "(global)" in r.stdout
    [g] = M.global_rules(home)
    assert (home / "global_rules").exists() and g["origin"] == "global" and len(g["id"]) == 6
    r = _cli(tmp_path, "rules", "--global", cwd=elsewhere)
    assert f"#{g['id']}" in r.stdout and "(global)" in r.stdout
    # the project's own rules, the recall header and the SessionStart line all carry it
    r = _cli(tmp_path, "rules", cwd=proj)
    assert r.returncode == 0 and "(global): Answer the user in Russian." in r.stdout
    m = ProjectMemory(proj, home=home)
    out = m.render(m.recall("postgres", k=4))
    assert f"#{g['id']}: Answer the user in Russian. (global)" in out
    m.s.db.close()
    for cwd in (proj, elsewhere):  # any project, with or without a store
        r = _cli(tmp_path, "hook-start", stdin=json.dumps({"cwd": str(cwd)}))
        assert r.returncode == 0 and r.stdout.startswith("Global rules: #") and "(global)" in r.stdout
    # removing by id works from any folder, also without a store
    r = _cli(tmp_path, "rules", "--remove", g["id"], cwd=elsewhere)
    assert r.returncode == 0 and "removed (global)" in r.stdout and M.global_rules(home) == []
    r = _cli(tmp_path, "hook-start", stdin=json.dumps({"cwd": str(elsewhere)}))
    assert r.stdout.strip() == ""


def test_global_and_project_pin_ids(tmp_path):
    home = tmp_path / "home"
    rid = M.pin_global_rule("Keys only in .env", home)
    assert M.pin_global_rule("keys only in .ENV!", home) == rid and len(M.global_rules(home)) == 1
    assert M.unpin_global_rule("#" + rid[:4], home) and not M.unpin_global_rule(rid, home)
    assert M.pin_global_rule("Keys only in .env", home) == rid and M.global_rules(home)[0]["id"] == rid
