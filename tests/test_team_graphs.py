"""Team memory: members' code graphs through the memory repo, chat trees per member with titles
(the team graphs rule). Synthetic: two members, a local bare repo, a small code graph each."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cotrail import graphify as GF
from cotrail import repo_check as RC
from cotrail import sync as S
from cotrail import team as T
from cotrail.embed import HashingEncoder
from cotrail.flow import trees
from cotrail.memory import ProjectMemory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _clone(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "remote", "add", "origin", "https://github.com/example-org/vpn-demo.git"], check=True)
    return d


def _graph(root: Path, nodes: list[tuple], edges: list[tuple]) -> Path:
    g = {"directed": False, "graph": {"graphify_version": "0.9"},
         "nodes": [{"id": i, "label": lab, "source_file": f, "source_location": loc, "file_type": "code", "community": c}
                   for i, lab, f, loc, c in nodes],
         "links": [{"source": a, "target": b, "relation": r, "confidence": "EXTRACTED"} for a, b, r in edges]}  # fmt: skip
    p = root / "graphify-out" / "graph.json"
    p.parent.mkdir()
    p.write_text(json.dumps(g), "utf-8")
    return p


def _turn(i, who, role, text, ts, session, **kw):
    return {"id": f"{who}{i}", "role": role, "text": text, "ts": ts, "session": session, "source": "transcript", **kw}


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)


def test_backend_decision_and_its_code_reach_the_frontend_member(tmp_path: Path) -> None:
    bare = tmp_path / "mem.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    back, front = _clone(tmp_path, "back"), _clone(tmp_path, "front")
    hb, hf = tmp_path / "hb", tmp_path / "hf"
    # backend: a code graph (one absolute path inside the clone) and a decision naming that code
    _graph(back, [("f_sess", "session.py", "api/session.py", "L1", 0),
                  ("s_create", "createSession()", str(back / "api" / "session.py"), "L12", 0),
                  ("f_auth", "auth.py", "api/auth.py", "L1", 1)],
           [("f_sess", "s_create", "contains"), ("s_create", "f_auth", "calls")])  # fmt: skip
    mb = ProjectMemory(back, encoder=HashingEncoder(), home=hb)
    mb._author = "Backend Dev"
    mb.import_turns([
        _turn(1, "b", "user", "Решили: эндпоинт сессии в api/session.py, createSession() выдаёт токен на 15 минут",
              "2026-11-23T10:00:00Z", "sb", title="API сессий"),
        _turn(2, "b", "assistant", "Сделал createSession() в api/session.py, коммит 1a2b3c4.", "2026-11-23T10:05:00Z", "sb")])
    T.join(back, str(bare), hb, name="Backend Dev", import_history=False, check=lambda r: "local", log=lambda m: None)
    repo_b = S.repo_dir(back, hb)
    gfiles = list((repo_b / "graphs").glob("*.json"))
    assert len(gfiles) == 1
    g = json.loads(gfiles[0].read_text("utf-8"))
    assert g["member"] == "Backend Dev" and {n[2] for n in g["nodes"]} == {"api/session.py", "api/auth.py"}
    assert str(tmp_path) not in gfiles[0].read_text("utf-8") and RC.check_repo(repo_b) == []
    # frontend: its own graph imported locally (import-graphify), joins, sees the backend layer
    _graph(front, [("f_btn", "LoginButton.tsx", "web/src/LoginButton.tsx", "L1", 0)], [])
    mf = ProjectMemory(front, encoder=HashingEncoder(), home=hf)
    mf._author = "Frontend Dev"
    GF.import_graph(mf.db_path, front / "graphify-out" / "graph.json")
    mf.import_turns([_turn(1, "f", "user", "Решили: кнопка LoginButton.tsx показывает статус сессии",
                           "2026-11-23T11:00:00Z", "sf", title="Кнопка входа")])  # fmt: skip
    r = T.join(front, str(bare), hf, name="Frontend Dev", import_history=False, check=lambda r: "local",
               log=lambda m: None)  # fmt: skip
    assert r["code_layers"] == 3
    mf = ProjectMemory(front, encoder=HashingEncoder(), home=hf)
    mf._author = "Frontend Dev"
    out = mf.render(mf.recall("что решили про эндпоинт сессии и createSession"))
    assert "decided by Backend Dev" in out or "решил Backend Dev" in out
    assert "api/session.py" in out and "(Backend Dev)" in out  # the backend code linked to the decision
    tr = trees(mf)
    assert set(tr["members"]) == {"Backend Dev", "Frontend Dev"}
    assert {s["label"] for s in tr["sessions"]} == {"API сессий", "Кнопка входа"}
    assert {s["author"] for s in tr["sessions"]} == {"Backend Dev", "Frontend Dev"}
    assert {c["member"] for c in tr["codes"]} == {"Backend Dev", "Frontend Dev"}
    # the backend reimports nothing new when nothing changed; the frontend's graph reaches the backend
    S.sync(back, None, hb, memory=mb, log=lambda m: None)
    assert "Frontend Dev" in {c["member"] for c in trees(mb)["codes"]}


def test_a_graph_with_a_leak_is_not_pushed(tmp_path: Path) -> None:
    bare = tmp_path / "mem.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    p = _clone(tmp_path, "p")
    _graph(p, [("n1", "notify admin@example.com", "src/mail.py", "L1", 0)], [])
    logs: list[str] = []
    T.join(p, str(bare), tmp_path / "h", name="Dev", import_history=False, check=lambda r: "local", log=lambda m: None)
    m = ProjectMemory(p, encoder=HashingEncoder(), home=tmp_path / "h")
    S.sync(p, None, tmp_path / "h", memory=m, log=logs.append)
    assert not (S.repo_dir(p, tmp_path / "h") / "graphs").exists()
    assert any("code graph not shared (repo check)" in x and "email" in x for x in logs)


def test_compact_paths_are_relative_and_outside_ones_keep_the_name(tmp_path: Path) -> None:
    root = tmp_path / "clone"
    root.mkdir()
    src = _graph(root, [("a", "x.py", str(root / "pkg" / "x.py"), "L1", 0), ("b", "y.py", "C:/Users/someone/other/y.py", "L1", 0)], [])
    g = GF.compact(src, root, "M")
    assert [n[2] for n in g["nodes"]] == ["pkg/x.py", "y.py"] and RC.check_graph_data(g) == []
    assert RC.check_graph_data({"nodes": [["a", "x", "/home/me/x.py", "", 0]]})[0]["kind"] in ("home_path", "absolute_path")


def test_chat_titles_from_claude_code_summary_and_claude_ai(tmp_path: Path) -> None:
    from cotrail.cc_transcripts import turns

    f = tmp_path / "s.jsonl"
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"type": "summary", "summary": "Настройка WireGuard", "leafUuid": "x"},
        {"type": "user", "uuid": "u1", "sessionId": "s1", "timestamp": "2026-11-23T09:00:00Z",
         "message": {"role": "user", "content": "Решили: туннель на WireGuard, порт 51820"}}]), "utf-8")  # fmt: skip
    ts = list(turns(f))
    assert ts[0]["title"] == "Настройка WireGuard"
    m = ProjectMemory(tmp_path / "p", encoder=HashingEncoder(), home=tmp_path / "h")
    m.import_turns(ts)
    assert trees(m)["sessions"][0]["label"] == "Настройка WireGuard"


def test_tools_folder_is_checked_and_a_newer_build_is_announced(tmp_path: Path, monkeypatch) -> None:
    import zipfile

    repo = tmp_path / "repo"
    (repo / "tools").mkdir(parents=True)
    (repo / "tools" / "README.md").write_text("Install: uv tool install --force tools/cotrail-9.0.0-py3-none-any.whl", "utf-8")
    with zipfile.ZipFile(repo / "tools" / "cotrail-9.0.0-py3-none-any.whl", "w") as z:
        z.writestr("cotrail/x.py", "token = load()  # a variable name is not a secret\n")
    assert RC.check_repo(repo) == []
    with zipfile.ZipFile(repo / "tools" / "cotrail-9.0.1-py3-none-any.whl", "w") as z:
        z.writestr("cotrail/y.py", "KEY = 'AKIAABCDEFGHIJKLMNOP'  # C:\\Users\\someone\\x\n")
    (repo / "tools" / "notes.bin").write_bytes(b"\x00")
    kinds = {b["kind"] for b in RC.check_repo(repo)}
    assert {"api_key", "home_path", "unexpected file"} <= kinds
    import importlib.metadata as IM

    monkeypatch.setattr(IM, "version", lambda name: "0.6.13.dev6")
    msg = T.newer_build(repo)
    assert "cotrail-9.0.1" in msg and "installed 0.6.13.dev6" in msg
    monkeypatch.setattr(IM, "version", lambda name: "9.0.1")
    assert T.newer_build(repo) == ""
