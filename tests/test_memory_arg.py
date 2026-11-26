"""Per-chat memory in one MCP server (Claude Desktop): every tool takes `memory=`; stores are opened once and cached;
an unknown name is an error listing the memories, nothing is created. Synthetic: two memories in a temp home."""

from __future__ import annotations

import subprocess
import threading
from pathlib import Path

import pytest

from cotrail import memory as M
from cotrail import memory_mcp as S
from cotrail.memory import ProjectMemory


@pytest.fixture
def two(tmp_path: Path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(M, "HOME", home)
    monkeypatch.setenv("COTRAIL_AUTHOR", "Tester")
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)
    vpn, game, default = tmp_path / "vpn", tmp_path / "game", tmp_path / "default"
    for d in (vpn, game, default):
        d.mkdir()
    subprocess.run(["git", "-C", str(vpn), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vpn), "remote", "add", "origin", "git@github.com:example-org/vpn-demo.git"], check=True)
    ProjectMemory(vpn, home=home).remember("Решили: сервер VPN поднимаем на WireGuard, порт 51820")
    ProjectMemory(game, home=home).remember("Решили: игровой движок Godot, рендер Forward+")
    ProjectMemory(default, home=home).remember("Решили: в проекте по умолчанию логи в JSON")
    monkeypatch.setenv("COTRAIL_PROJECT", str(default))
    monkeypatch.setattr(S, "_mem", None)
    monkeypatch.setattr(S, "_open", {})
    return home, vpn, game, default


def test_calls_with_and_without_memory(two) -> None:
    home, vpn, game, default = two
    assert "JSON" in S.recall("какие логи", detail="brief")
    out = S.recall("какой сервер VPN", memory="git-github-com-example-org-vpn-demo")
    assert "WireGuard" in out and "Godot" not in out
    assert "Godot" in S.recall("движок", memory=str(game))  # a project folder
    assert "WireGuard" in S.decisions(memory="https://github.com/Example-Org/vpn-demo")  # a git remote, other form
    assert "Turns: 1" in S.memory_status(memory=str(game))
    names = S.list_memories()
    assert "vpn-demo (local" in names and "game (local" in names


def test_save_chat_and_remember_write_into_the_named_memory(two) -> None:
    home, vpn, game, default = two
    S.save_chat("план", [{"role": "user", "text": "Решили: клиент VPN показывает статус туннеля в трее"}],
                memory=str(vpn))  # fmt: skip
    S.remember("Решили: уровни грузим из JSON", memory=M.project_slug(game))
    m = ProjectMemory(vpn, home=home)
    texts = [r[0] for r in m.s.q("SELECT text FROM episodes")]
    assert any("трее" in t for t in texts) and not any("уровни" in t for t in texts)
    assert set(m.authors().values()) == {"Tester"}
    assert ProjectMemory(default, home=home).s.q("SELECT COUNT(*) FROM episodes")[0][0] == 1


def test_unknown_memory_is_an_error_and_creates_nothing(two, tmp_path: Path) -> None:
    home = two[0]
    before = sorted(p.name for p in home.iterdir())
    for bad in ("no-such-memory", str(tmp_path / "missing"), "https://github.com/example-org/other"):
        out = S.recall("что угодно", memory=bad)
        assert out.startswith("No memory") and "vpn-demo" in out
    empty = tmp_path / "empty"
    empty.mkdir()
    assert S.rules(memory=str(empty)).startswith("No memory")  # a folder without a memory: not created
    assert sorted(p.name for p in home.iterdir()) == before


def test_concurrent_calls_share_one_open_store_per_memory(two) -> None:
    home, vpn, game, default = two
    errors, outs = [], []

    def run(i: int) -> None:
        try:
            mem = str(vpn) if i % 2 else str(game)
            outs.append(S.recall("сервер или движок", memory=mem, detail="brief"))
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=run, args=(i,)) for i in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors and len(outs) == 12
    assert len(S._open) == 2


def test_open_stores_are_bounded(two, tmp_path: Path, monkeypatch) -> None:
    home = two[0]
    monkeypatch.setattr(S, "MAX_OPEN", 2)
    extra = []
    for i in range(3):
        d = tmp_path / f"p{i}"
        d.mkdir()
        ProjectMemory(d, home=home).remember(f"Решили: вариант номер {i} для проверки кэша")
        extra.append(d)
    for d in extra:
        S.memory_status(memory=str(d))
    assert len(S._open) == 2 and str(M.store_dir(extra[0], home)) not in S._open


def test_workspace_folder_has_no_default_and_friendly_names_resolve(tmp_path: Path, monkeypatch) -> None:
    home, root = tmp_path / "home", tmp_path / "projects"
    monkeypatch.setattr(M, "HOME", home)
    monkeypatch.delenv("COTRAIL_IDENTITY", raising=False)
    vpn, game = root / "Vpn-Demo", root / "game"
    for d in (vpn, game):
        d.mkdir(parents=True)
    subprocess.run(["git", "-C", str(vpn), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(vpn), "remote", "add", "origin", "https://github.com/example-org/Vpn-Demo.git"],
                   check=True)  # fmt: skip
    ProjectMemory(vpn, home=home).remember("Решили: туннель на WireGuard")
    ProjectMemory(game, home=home).remember("Решили: движок Godot")
    monkeypatch.setenv("COTRAIL_PROJECT", str(root))
    monkeypatch.setattr(S, "_mem", None)
    monkeypatch.setattr(S, "_open", {})
    out = S.recall("что решили")
    assert out.startswith("No memory chosen") and "vpn-demo (local" in out and "game (local" in out
    assert not (home / M.project_slug(root)).exists()  # no store made for the workspace folder
    assert "WireGuard" in S.recall("туннель", memory="vpn-demo") and "Godot" in S.recall("движок", memory="GAME")
    other = tmp_path / "elsewhere" / "game"
    other.mkdir(parents=True)
    ProjectMemory(other, home=home).remember("Решили: другой проект с тем же именем")
    assert "ambiguous" in S.recall("x", memory="game")
