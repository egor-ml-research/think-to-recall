"""Setup through the assistant: dry run by default, connect a folder, join a team with the secret check, find and
import chats. Synthetic: temp homes, a fake user home with Claude Code transcripts, a local bare repo."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cotrail import assistant_setup as A
from cotrail.memory import ProjectMemory, project_slug, store_dir

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _transcript(fake_home: Path, folder: Path, sid: str, texts: list[str]) -> Path:
    d = fake_home / ".claude" / "projects" / project_slug(folder)
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{sid}.jsonl"
    rows = [{"type": "user" if i % 2 == 0 else "assistant", "uuid": f"{sid}-{i}", "sessionId": sid, "cwd": str(folder),
             "timestamp": f"2026-11-21T09:{i:02d}:00Z",
             "message": {"role": "user" if i % 2 == 0 else "assistant", "content": t}} for i, t in enumerate(texts)]  # fmt: skip
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", "utf-8")
    return f


@pytest.fixture
def env(tmp_path: Path, monkeypatch):
    fake = tmp_path / "userhome"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake))
    monkeypatch.setenv("COTRAIL_AUTHOR", "Front Dev")
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)
    return fake, tmp_path / "home"


def test_connect_folder_is_a_dry_run_until_confirmed(tmp_path: Path, env) -> None:
    fake, home = env
    proj = tmp_path / "app"
    proj.mkdir()
    _transcript(fake, proj, "11111111-aaaa", ["Решили: кэш держать в памяти процесса, не в Redis", "Хорошо, так и сделаю."])
    out = A.connect_folder(str(proj), home=home)
    assert "Would connect" in out and "1 Claude Code chat file" in out and "confirm=true" in out
    assert not home.exists() or not any(home.rglob("graph.sqlite"))
    out = A.connect_folder(str(proj), home=home, confirm=True)
    assert "imported 2 new turn" in out
    assert "app" in A.format_memories(A.list_memories(home))


def test_connect_a_second_folder_to_an_existing_memory(tmp_path: Path, env) -> None:
    _, home = env
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    ProjectMemory(a, home=home).save_chat("t", [{"role": "user", "text": "Решили: логи писать в JSON формате всегда"}])
    name = store_dir(a, home).name
    assert "Would connect" in A.connect_folder(str(b), name, home=home)
    A.connect_folder(str(b), name, home=home, confirm=True)
    assert store_dir(b, home) == store_dir(a, home)
    assert ProjectMemory(b, home=home).s.q("SELECT COUNT(*) FROM episodes")[0][0] == 1
    with pytest.raises(ValueError):
        A.connect_folder(str(b), "no-such-memory", home=home)


def test_join_team_shows_before_write_and_holds_flagged_lines(tmp_path: Path, env) -> None:
    import pytest

    SY = pytest.importorskip("cotrail.sync")  # team memory (experimental): not in every build
    _, home = env
    proj = tmp_path / "app"
    proj.mkdir()
    subprocess.run(["git", "-C", str(proj), "init", "-q"], check=True)  # a remote: a short store name (Windows paths)
    subprocess.run(["git", "-C", str(proj), "remote", "add", "origin", "https://github.com/example-org/app"], check=True)
    subprocess.run(["git", "init", "-q", "--bare", str(tmp_path / "mem.git")], check=True)
    m = ProjectMemory(proj, home=home)
    m.import_turns([SY.make_episode("user", "Решили: токены живут 15 минут", "2026-11-21T10:00:00Z", "transcript", "s1"),
                    SY.make_episode("user", "Решили: схема БД в миграциях", "2026-11-21T10:01:00Z", "transcript",
                                   r"C:\Users\someone\notes")])  # fmt: skip
    m.s.db.close()
    out = A.join_team(str(tmp_path / "mem.git"), str(proj), home=home, check=lambda u: "local")
    assert "PRIVACY" in out and "Would push: 1 record" in out and "Held back by the secret check" in out
    assert "home_path" in out and not SY.repo_dir(proj, home).exists()
    assert A.join_team("https://github.com/x/y", str(proj), home=home, check=lambda u: "PUBLIC").startswith("Refused")
    out = A.join_team(str(tmp_path / "mem.git"), str(proj), home=home, check=lambda u: "local", confirm=True)
    assert "Joined as Front Dev" in out and "Held back" in out
    text = "".join(p.read_text("utf-8") for p in (SY.repo_dir(proj, home) / "episodes").glob("*.jsonl"))
    assert "токены" in text and "someone" not in text and "миграциях" not in text


def test_find_and_import_chats(tmp_path: Path, env) -> None:
    fake, home = env
    back, front = tmp_path / "backend-api", tmp_path / "web"
    back.mkdir()
    front.mkdir()
    _transcript(fake, back, "22222222-bbbb", ["Решили: эндпоинт /api/v1/session отдаёт токен", "Принято, делаю эндпоинт так."])
    _transcript(fake, front, "33333333-cccc", ["Решили: кнопка подключения зелёная", "Ок."])
    rows = A.find_chats("api")
    assert [r["id"] for r in rows] == ["cc:22222222"] and "эндпоинт" in rows[0]["title"]
    assert len(A.find_chats("")) == 2
    out = A.import_chats(["cc:22222222"], project=str(front), home=home)
    assert "Would import" in out and "Claude Code chats: 1 of 1" in out
    out = A.import_chats(["cc:22222222"], project=str(front), home=home, confirm=True)
    assert "2 turn(s) from Claude Code" in out
    m = ProjectMemory(front, home=home)
    assert set(m.authors().values()) == {"Front Dev"}
    assert "claude.ai chats need the export" in A.import_chats(["ai:abc"], home=home)
