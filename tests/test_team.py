"""Team memory: identity by git remote, authors through sync, `team join/status`, the memory-repo check.
Synthetic only: temp homes, a local bare repo as the memory remote, two simulated members."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cotrail import repo_check as RC
from cotrail import sync as S
from cotrail import team as T
from cotrail.embed import HashingEncoder
from cotrail.memory import ProjectMemory, normalize_remote, project_slug, remote_slug, store_dir

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
URL = "https://github.com/example-org/Demo-App.git"


def _git(d: Path, *a: str) -> None:
    subprocess.run(["git", "-C", str(d), *a], check=True, capture_output=True)


def _clone(tmp: Path, name: str, url: str = URL) -> Path:
    d = tmp / name
    d.mkdir(parents=True)
    _git(d, "init", "-q")
    _git(d, "remote", "add", "origin", url)
    return d


def _turn(i: int, who: str, text: str, session: str) -> dict:
    return {"id": f"{who}-{i}", "role": "user", "text": text, "ts": f"2026-11-20T10:{i:02d}:00+00:00",
            "session": session, "source": "transcript"}  # fmt: skip


@pytest.fixture
def bare(tmp_path: Path) -> str:
    b = tmp_path / "memory.git"
    subprocess.run(["git", "init", "-q", "--bare", str(b)], check=True)
    return str(b)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)
    monkeypatch.delenv("COTRAIL_AUTHOR", raising=False)


def test_remote_forms_normalize_to_one_identity() -> None:
    forms = ["https://github.com/Example-Org/demo-app.git", "git@github.com:example-org/demo-app.git",
             "ssh://git@github.com:22/example-org/demo-app", "https://user:tok123@github.com/example-org/demo-app/",
             "HTTPS://GITHUB.COM/example-org/Demo-App"]  # fmt: skip
    assert {normalize_remote(f) for f in forms} == {"github.com/example-org/demo-app"}
    assert remote_slug(forms[3]) == "git-github-com-example-org-demo-app"  # no credentials in the slug


def test_clones_share_a_store_and_a_folder_without_remote_keeps_its_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    a, b = _clone(tmp_path, "a"), _clone(tmp_path, "work/b-frontend", "git@github.com:example-org/demo-app.git")
    (a / "sub").mkdir()
    assert store_dir(a, home) == store_dir(b, home) == store_dir(a / "sub", home) == home / remote_slug(URL)
    plain = tmp_path / "plain"
    plain.mkdir()
    assert store_dir(plain, home) == home / project_slug(plain)
    m = ProjectMemory(a, encoder=HashingEncoder(), home=home)
    m.import_turns([_turn(1, "x", "решили: API отдаёт JSON с полем status", "s1")])
    m2 = ProjectMemory(b, encoder=HashingEncoder(), home=home)
    assert [r[0] for r in m2.s.q("SELECT id FROM episodes")] == ["x-1"]


def test_old_path_store_is_adopted_in_place_and_never_lost(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    a = _clone(tmp_path, "a")
    monkeypatch.setenv("COTRAIL_IDENTITY", "path")  # an older version: the store is named after the folder
    old = ProjectMemory(a, encoder=HashingEncoder(), home=home)
    old.import_turns([_turn(1, "old", "решили: хранить сессии в Redis", "s0")])
    old.s.db.close()
    monkeypatch.delenv("COTRAIL_IDENTITY")
    assert store_dir(a, home) == home / project_slug(a)  # adopted, not moved: an older cotrail still finds it
    assert json.loads((home / "identities.json").read_text("utf-8")) == {remote_slug(URL): project_slug(a)}
    b = _clone(tmp_path, "b")  # another clone of the same remote reaches the same records
    m = ProjectMemory(b, encoder=HashingEncoder(), home=home)
    assert "old-1" in {r[0] for r in m.s.q("SELECT id FROM episodes")}
    assert not (home / remote_slug(URL)).exists()


def test_old_path_store_is_merged_when_the_remote_store_came_first(tmp_path: Path, monkeypatch) -> None:
    home = tmp_path / "home"
    a, b = _clone(tmp_path, "a"), _clone(tmp_path, "b")
    monkeypatch.setenv("COTRAIL_IDENTITY", "path")
    old = ProjectMemory(a, encoder=HashingEncoder(), home=home)
    old.import_turns([_turn(1, "old", "решили: логи писать в stdout", "s0")])
    old.s.db.close()
    monkeypatch.delenv("COTRAIL_IDENTITY")
    # b made the remote store first (without the alias, as if a's old store were unknown)
    (home / remote_slug(URL)).mkdir(parents=True)
    ProjectMemory(home / "nowhere", encoder=HashingEncoder(), home=home)  # unrelated
    shutil.copy(home / project_slug(home / "nowhere") / "graph.sqlite", home / remote_slug(URL) / "graph.sqlite")
    m = ProjectMemory(a, encoder=HashingEncoder(), home=home)
    assert m.dir == home / remote_slug(URL)
    assert "old-1" in {r[0] for r in m.s.q("SELECT id FROM episodes")}
    assert (home / project_slug(a) / "graph.sqlite").exists()  # the old store stays
    assert (home / project_slug(a) / "merged_into").read_text("utf-8").strip() == remote_slug(URL)
    ProjectMemory(b, encoder=HashingEncoder(), home=home)  # merged once, not again
    assert m.s.q("SELECT COUNT(*) FROM episodes")[0][0] == 1


def test_two_members_share_memory_with_authors(tmp_path: Path, bare: str) -> None:
    back, front = _clone(tmp_path, "back"), _clone(tmp_path, "front")
    hb, hf = tmp_path / "home-back", tmp_path / "home-front"
    # the backend dev (already using cotrail) records decisions, then joins
    mb = ProjectMemory(back, encoder=HashingEncoder(), home=hb)
    mb._author = "Backend Dev"
    mb.import_turns([_turn(1, "b", "Решили: backend API отдаёт токены через эндпоинт /api/v1/session, срок жизни 15 минут",
                           "sb")])  # fmt: skip
    logs: list[str] = []
    T.join(back, bare, hb, name="Backend Dev", import_history=False, check=lambda r: "PRIVATE", log=logs.append)
    assert "PRIVACY" in logs[0] and "visibility: private" in logs[1]
    # the frontend dev joins from a fresh home and gets the backend decision with its author
    r = T.join(front, bare, hf, name="Frontend Dev", import_history=False, check=lambda r: "PRIVATE", log=lambda m: None)
    assert r["imported"] == 1
    mf = ProjectMemory(front, encoder=HashingEncoder(), home=hf)
    mf.import_turns([_turn(2, "f", "Решили: на фронтенде кнопка подключения VPN показывает статус сессии", "sf")])
    S.sync(front, None, hf, memory=mf, log=lambda m: None)
    S.sync(back, None, hb, memory=mb, log=lambda m: None)
    assert mb.authors()["f-2"] == "Frontend Dev" and mf.authors()["b-1"] == "Backend Dev"
    out = mf.render(mf.recall("что решили про backend API эндпоинт сессии"))
    assert "decided by Backend Dev" in out or "решил Backend Dev" in out
    assert any(d.get("author") == "Backend Dev" for d in mf.decisions())
    st = T.status(front, hf)
    assert st["members"] == {"Backend Dev": 1, "Frontend Dev": 1} and st["last_sync"] and st["devices"] == 2
    assert "Frontend Dev: 1" in T.format_status(st)
    assert RC.check_repo(S.repo_dir(front, hf)) == []


def test_single_author_store_shows_no_author_label(tmp_path: Path) -> None:
    a = _clone(tmp_path, "a")
    m = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    m._author = "Solo"
    m.import_turns([_turn(1, "s", "Решили: конфиг хранить в YAML", "s")])
    assert m.authors() == {"s-1": "Solo"}
    assert "Solo" not in m.render(m.recall("конфиг YAML"))
    m2 = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    m2._author = "Newcomer"  # a new member with no records yet sees whose record it is
    assert "Solo" in m2.render(m2.recall("конфиг YAML"))


def test_join_refuses_a_public_repo_and_an_email_name(tmp_path: Path, bare: str) -> None:
    a = _clone(tmp_path, "a")
    with pytest.raises(T.TeamError, match="PUBLIC"):
        T.join(a, "https://github.com/example-org/mem", tmp_path / "h", name="X", check=lambda r: "PUBLIC",
               log=lambda m: None)  # fmt: skip
    with pytest.raises(T.TeamError, match="e-mail"):
        T.join(a, bare, tmp_path / "h", name="x@example.com", check=lambda r: "local", log=lambda m: None)
    logs: list[str] = []
    T.join(a, bare, tmp_path / "h", name="X", import_history=False, check=lambda r: "", log=logs.append)
    assert any("make sure it is PRIVATE" in m for m in logs)
    assert T.github_repo("git@github.com:Example-Org/Mem.git") == "example-org/mem"


def test_sync_scrubs_home_folders_and_the_check_flags_leaks(tmp_path: Path, bare: str) -> None:
    a = _clone(tmp_path, "a")
    m = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    m._author = "Dev"
    m.import_turns([_turn(1, "p", r"Решили: конфиг лежит в C:\Users\somebody\proj\cfg.yaml и /home/somebody/x", "s")])
    S.sync(a, bare, tmp_path / "h", memory=m, log=lambda m: None)
    repo = S.repo_dir(a, tmp_path / "h")
    text = "".join(p.read_text("utf-8") for p in (repo / "episodes").glob("*.jsonl"))
    assert "somebody" not in text and r"~\\proj" in text
    assert RC.check_repo(repo) == []
    bad = repo / "episodes" / "leak.jsonl"
    bad.write_text(json.dumps({"id": "z", "role": "user", "text": "key AKIAABCDEFGHIJKLMNOP and C:/Users/someone/a",
                               "author": "a@b.co", "session": "s"}) + "\n", "utf-8")  # fmt: skip
    (repo / "graph.sqlite").write_text("x", "utf-8")
    kinds = {(b["field"], b["kind"]) for b in RC.check_repo(repo)}
    assert ("text", "home_path") in kinds and ("author", "email") in kinds and ("file", "unexpected file") in kinds
    assert any(f == "text" and k not in ("home_path",) for f, k in kinds)  # the key
    assert RC.main([str(repo)]) == 1


def test_save_chat_and_claude_ai_turns_carry_the_author(tmp_path: Path, monkeypatch) -> None:
    a = _clone(tmp_path, "a")
    monkeypatch.setenv("COTRAIL_AUTHOR", "Planner")
    m = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    r = m.save_chat("planning", [{"role": "user", "text": "Решили: сначала делаем авторизацию на бэкенде"}])
    assert r["new"] == 1 and set(m.authors().values()) == {"Planner"}
    S.save_config(a, tmp_path / "h", {"author": "Team Name"})  # the name `team join` saved wins over the env
    m2 = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    assert m2.author == "Team Name"


def test_join_finds_session_folders_of_other_clones_and_subfolders(tmp_path: Path, monkeypatch) -> None:
    fake = tmp_path / "userhome"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    a, b = _clone(tmp_path, "a"), _clone(tmp_path, "b", "git@github.com:example-org/demo-app.git")
    other = _clone(tmp_path, "other", "https://github.com/example-org/another.git")
    (a / "frontend").mkdir()
    for d in (a, a / "frontend", b, other):
        cp = fake / ".claude" / "projects" / project_slug(d)
        cp.mkdir(parents=True)
        (cp / "s.jsonl").write_text(json.dumps({"cwd": str(d)}) + "\n", "utf-8")
    m = ProjectMemory(a, encoder=HashingEncoder(), home=tmp_path / "h")
    got = {d.name for d in T.session_dirs(m, tmp_path / "h")}
    assert got == {project_slug(a), project_slug(a / "frontend"), project_slug(b)}
