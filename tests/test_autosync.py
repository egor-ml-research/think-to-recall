"""Fully automatic team sync (the autosync rule): after `team join` nothing is run by hand - the
Claude Code hooks and the git hooks do it. Synthetic: two members, temp homes, a local bare remote."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cotrail import autosync as AS
from cotrail import cli
from cotrail import sync as S
from cotrail import team as T
from cotrail.memory import ProjectMemory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
OK = lambda r: "local"  # noqa: E731


def _clone(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir()
    for a in (["init", "-q"], ["remote", "add", "origin", "https://github.com/example-org/vpn-demo.git"],
              ["config", "user.name", "T"], ["config", "user.email", "t@example.invalid"]):  # fmt: skip
        subprocess.run(["git", "-C", str(d), *a], check=True)
    return d


@pytest.fixture
def team(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)
    monkeypatch.setenv("PYTHONPATH", str(Path(__file__).resolve().parents[1]))  # the detached children import cotrail
    bare = tmp_path / "mem.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    a, b = _clone(tmp_path, "back"), _clone(tmp_path, "front")
    (a / ".git" / "hooks").mkdir(exist_ok=True)
    (a / ".git" / "hooks" / "post-commit").write_text("#!/bin/sh\necho mine\n", "utf-8")  # the user's own hook stays
    return bare, a, b, tmp_path / "ha", tmp_path / "hb"


def _hook(cmd: str, project: Path, home: Path, monkeypatch, payload: dict) -> list:
    """Run a Claude Code hook in-process; wait for the background process it starts."""
    procs = []
    real = S.spawn_background
    monkeypatch.setattr(S, "spawn_background", lambda *x, **k: procs.append(real(*x, **k)) or procs[-1])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload | {"cwd": str(project)})))
    cli.main(["--home", str(home), cmd])
    for p in procs:
        if p is not None:
            p.wait(timeout=180)
    return procs


def test_after_join_no_manual_command(team, monkeypatch, capsys) -> None:
    bare, a, b, ha, hb = team
    ma = ProjectMemory(a, home=ha)
    ma.remember("Решили: эндпоинт /api/v1/session выдаёт токен на 15 минут")
    ma.s.db.close()
    T.join(a, str(bare), ha, name="Back", import_history=False, check=OK, log=lambda m: None, graphify=False)
    T.join(b, str(bare), hb, name="Front", import_history=False, check=OK, log=lambda m: None, graphify=False)
    hook = (a / ".git" / "hooks" / "post-commit").read_text("utf-8")
    assert "echo mine" in hook and AS.BEGIN in hook and "graph-refresh --background" in hook
    assert "graphify-out/" in (a / ".git" / "info" / "exclude").read_text("utf-8")
    # the backend dev works on: a new decision lands in the store, the Stop hook pushes it in the background
    ma = ProjectMemory(a, home=ha)
    ma.remember("Решили: refreshToken() продлевает сессию раз в минуту")
    ma.s.db.close()
    tr = a / "t.jsonl"
    tr.write_text("", "utf-8")
    _hook("hook-stop", a, ha, monkeypatch, {"transcript_path": str(tr)})
    # the frontend dev opens a session: SessionStart pulls in the background
    _hook("hook-start", b, hb, monkeypatch, {})
    mb = ProjectMemory(b, home=hb)
    texts = [r[0] for r in mb.s.q("SELECT text FROM episodes")]
    assert any("refreshToken" in t for t in texts) and any("/api/v1/session" in t for t in texts)
    # a commit with code: the git hook rebuilds nothing (no consent) but shares the existing graph
    (a / "graphify-out").mkdir()
    (a / "graphify-out" / "graph.json").write_text(json.dumps({"nodes": [
        {"id": "s", "label": "session.py", "source_file": "api/session.py", "community": 0}], "links": []}), "utf-8")
    (a / "api").mkdir()
    (a / "api" / "session.py").write_text("def create(): pass\n", "utf-8")
    subprocess.run(["git", "-C", str(a), "add", "api"], check=True)
    out = subprocess.run(["git", "-C", str(a), "commit", "-q", "-m", "api"], capture_output=True, text=True)
    assert "mine" in out.stdout + out.stderr  # the user's hook still runs
    for _ in range(120):  # the detached graph-refresh -> sync
        r = subprocess.run(["git", "--git-dir", str(bare), "ls-tree", "--name-only", "main", "graphs/"],
                           capture_output=True, text=True)  # fmt: skip
        if r.stdout.strip():
            break
        time.sleep(1)
    assert r.stdout.strip().startswith("graphs/")
    _hook("hook-start", b, hb, monkeypatch, {})
    st = T.status(b, hb)
    members = {x["member"]: x for x in st["statuses"]}
    assert set(members) == {"Back", "Front"} and members["Back"]["last_graph_push"]
    assert "members' devices" in T.format_status(st)
    T.leave(a, ha)
    hook = (a / ".git" / "hooks" / "post-commit").read_text("utf-8")
    assert AS.BEGIN not in hook and "echo mine" in hook
    assert not (a / ".git" / "hooks" / "post-merge").exists()


def test_a_failed_background_sync_is_shown_once_at_session_start_and_cleared(team, monkeypatch, capsys) -> None:
    bare, a, b, ha, hb = team
    T.join(a, str(bare), ha, name="Back", import_history=False, check=OK, log=lambda m: None, graphify=False)
    real = S._run
    monkeypatch.setattr(S, "_run", lambda cmd, env: subprocess.CompletedProcess(cmd, 128, "", "fatal: unable to access "
                        "'https://github.com/x/': schannel: failed to receive handshake") if "fetch" in cmd or "ls-remote"
                        in cmd or "pull" in cmd else real(cmd, env))  # fmt: skip
    for _ in range(2):
        cli.main(["--project", str(a), "--home", str(ha), "sync", "--quiet"])
    assert S.load_config(a, ha)["fail_count"] == 2
    lines = AS.start_lines(a, ha, "ru")
    assert lines and lines[0].startswith("Синхронизация командной памяти не прошла 2 раз(а)") and "schannel" in lines[0]
    assert "повторю автоматически" in lines[0]
    monkeypatch.setattr(S, "_run", real)
    cli.main(["--project", str(a), "--home", str(ha), "sync", "--quiet"])
    assert AS.start_lines(a, ha, "ru") == []


def test_graph_refresh_rebuilds_only_when_code_changed(team, monkeypatch) -> None:
    bare, a, b, ha, hb = team
    T.join(a, str(bare), ha, name="Back", import_history=False, check=OK, log=lambda m: None, graphify=True)
    builds = []

    def build(clone):
        builds.append(clone)
        out = clone / "graphify-out" / "graph.json"
        out.parent.mkdir(exist_ok=True)
        out.write_text(json.dumps({"nodes": [{"id": "n", "label": "x.py", "source_file": "x.py"}], "links": []}), "utf-8")
        return out

    (a / "x.py").write_text("x = 1\n", "utf-8")
    subprocess.run(["git", "-C", str(a), "add", "x.py"], check=True)
    subprocess.run(["git", "-C", str(a), "commit", "-q", "--no-verify", "-m", "x"], check=True)
    assert AS.graph_refresh(a, ha, build=build, log=lambda m: None)["built"]
    assert not AS.graph_refresh(a, ha, build=build, log=lambda m: None)["built"]  # nothing changed since
    (a / "README.md").write_text("docs\n", "utf-8")
    subprocess.run(["git", "-C", str(a), "add", "README.md"], check=True)
    subprocess.run(["git", "-C", str(a), "commit", "-q", "--no-verify", "-m", "docs"], check=True)
    assert AS.graph_refresh(a, ha, build=build, log=lambda m: None)["changed"] == 0 and len(builds) == 1


def test_update_check_once_a_day_and_the_line(tmp_path: Path, monkeypatch) -> None:
    import importlib.metadata as IM

    monkeypatch.setattr(IM, "version", lambda name: "0.6.13.dev6")
    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "cotrail-0.6.13.dev9-py3-none-any.whl").write_bytes(b"PK")
    calls = []
    up = AS.check_update(repo, tmp_path / "h", log=lambda m: None, pypi=lambda: calls.append(1) or "0.6.12")
    assert up["new"] == "0.6.13.dev9" and up["src"].endswith("dev9-py3-none-any.whl")
    AS.check_update(repo, tmp_path / "h", log=lambda m: None, pypi=lambda: calls.append(1) or "0.6.12")
    assert len(calls) == 1  # once a day
    proj = tmp_path / "p"
    proj.mkdir()
    S.save_config(proj, tmp_path / "h", {"remote": "x"})
    assert any("обнови cotrail" in x for x in AS.start_lines(proj, tmp_path / "h", "ru"))
    assert "uv tool install --force" in AS.update_text(tmp_path / "h") and "quit Claude Desktop" in AS.update_text(tmp_path / "h")


def test_server_sync_pulls_at_start_pushes_after_new_records_and_pulls_periodically(tmp_path: Path) -> None:
    from cotrail.memory import ProjectMemory as PM

    team_p, solo_p = tmp_path / "team", tmp_path / "solo"
    team_p.mkdir()
    solo_p.mkdir()
    h = tmp_path / "h"
    mt, ms = PM(team_p, home=h), PM(solo_p, home=h)
    S.save_config(team_p, h, {"remote": "x"})
    now = [1000.0]
    started = []

    class Done:
        def poll(self):
            return 0

    sync = AS.ServerSync(lambda: [(mt.project, mt.dir, h), (ms.project, ms.dir, h)],
                         spawn=lambda p, home: started.append(p) or Done(), clock=lambda: now[0])  # fmt: skip
    assert sync.tick() == [str(mt.dir)]  # the start: pull; the memory without a team is left alone
    now[0] += 30
    assert sync.tick() == []
    mt.remember("Решили: новое решение для команды")
    now[0] += 10
    assert sync.tick() == []  # new record, but the last sync was < 1 min ago
    now[0] += 25
    assert sync.tick() == [str(mt.dir)]  # pushed once a minute after the start
    now[0] += 100
    assert sync.tick() == []  # nothing new
    now[0] += 600
    assert sync.tick() == [str(mt.dir)]  # the periodic pull
    (mt.dir / "hook_turns").mkdir()
    (mt.dir / "hook_turns" / "t.jsonl").write_text("{}\n", "utf-8")
    now[0] += 61
    assert sync.tick() == [str(mt.dir)]  # turns a client hook queued count as new


def test_server_sync_skips_while_a_sync_runs(tmp_path: Path) -> None:
    from cotrail.memory import ProjectMemory as PM

    p = tmp_path / "p"
    p.mkdir()
    m = PM(p, home=tmp_path / "h")
    S.save_config(p, tmp_path / "h", {"remote": "x"})
    now = [0.0]

    class Running:
        def poll(self):
            return None

    sync = AS.ServerSync(lambda: [(m.project, m.dir, tmp_path / "h")], spawn=lambda *a: Running(), clock=lambda: now[0])
    assert sync.tick() and not (now.__setitem__(0, 700) or sync.tick())


def test_hook_import_syncs_at_most_once_a_minute(team, monkeypatch) -> None:
    bare, a, b, ha, hb = team
    T.join(a, str(bare), ha, name="Back", import_history=False, check=OK, log=lambda m: None, graphify=False)
    assert AS.maybe_sync(a, ha) == "recent"  # join just synced
    cfg = S.load_config(a, ha)
    S.save_config(a, ha, cfg | {"last_sync": "2026-01-01T00:00:00+00:00"})
    from cotrail import clients as C

    f = a / "turns.jsonl"
    f.write_text(json.dumps({"role": "user", "text": "Решили: Cursor пишет в общую память", "ts": "2026-11-28T10:00:00Z",
                             "session": "cursor-1", "source": "cursor"}, ensure_ascii=False) + "\n", "utf-8")  # fmt: skip
    res = C.import_file(a, f, str(ha))
    assert res["sync"] == "synced"
    out = subprocess.run(["git", "--git-dir", str(bare), "log", "main", "-p", "--format="], capture_output=True,
                         text=True, encoding="utf-8").stdout  # fmt: skip
    assert "Cursor пишет в общую память" in out
