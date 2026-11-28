"""Memory sync through a git repo: two devices, a local bare repo as the remote."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from cotrail import sync as S
from cotrail.embed import HashingEncoder
from cotrail.memory import ProjectMemory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


def _mem(tmp: Path, dev: str) -> ProjectMemory:
    return ProjectMemory(tmp / "proj", encoder=HashingEncoder(), home=tmp / dev)


def _turns(dev: str, n: int) -> list[dict]:
    return [S.make_episode("user" if i % 2 == 0 else "assistant",
                           f"{dev}: решение номер {i} про модуль синхронизации памяти", f"2026-11-19T10:{i:02d}:00+00:00",
                           "transcript", f"sess-{dev}") for i in range(n)]  # fmt: skip


def _ids(m: ProjectMemory) -> list[str]:
    return [r[0] for r in m.s.q("SELECT id FROM episodes WHERE t_expired IS NULL")]


@pytest.fixture
def remote(tmp_path: Path) -> str:
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    return str(bare)


def test_two_devices_in_parallel_converge(tmp_path: Path, remote: str) -> None:
    errors: list[BaseException] = []

    def run(dev: str, n: int) -> None:
        try:
            m = _mem(tmp_path, dev)
            m.import_turns(_turns(dev, n))
            S.sync(tmp_path / "proj", remote, tmp_path / dev, memory=m, log=lambda *_: None)
        except BaseException as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=run, args=(d, n)) for d, n in (("a", 5), ("b", 7))]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors, errors
    # a second round: each pulls what the other pushed
    ma, mb = _mem(tmp_path, "a"), _mem(tmp_path, "b")
    S.sync(tmp_path / "proj", None, tmp_path / "a", memory=ma, log=lambda *_: None)  # remote remembered
    S.sync(tmp_path / "proj", None, tmp_path / "b", memory=mb, log=lambda *_: None)
    ia, ib = _ids(ma), _ids(mb)
    assert len(ia) == len(set(ia)) == 12
    assert sorted(ia) == sorted(ib)
    # each device wrote only its own file, and the logs hold every episode once
    repo = S.repo_dir(tmp_path / "proj", tmp_path / "a")
    S._pull(repo)
    logs = S.read_logs(repo)
    assert set(logs) == {S.device_id(tmp_path / "a"), S.device_id(tmp_path / "b")}
    all_ids = [r["id"] for rows in logs.values() for r in rows]
    assert len(all_ids) == len(set(all_ids)) == 12
    assert not any(p.suffix == ".sqlite" for p in repo.rglob("*"))


def test_resync_dedupes_by_hash(tmp_path: Path, remote: str) -> None:
    ma = _mem(tmp_path, "a")
    ma.import_turns(_turns("a", 3))
    r1 = S.sync(tmp_path / "proj", remote, tmp_path / "a", memory=ma, log=lambda *_: None)
    r2 = S.sync(tmp_path / "proj", remote, tmp_path / "a", memory=ma, log=lambda *_: None)
    assert (r1["pushed"], r2["pushed"], r2["imported"]) == (3, 0, 0)
    # the same content under another id on device b (e.g. the same claude.ai turn added on both) is not duplicated
    mb = _mem(tmp_path, "b")
    same = [t | {"id": "other-" + t["id"]} for t in _turns("a", 3)]
    mb.import_turns(same)
    rb = S.sync(tmp_path / "proj", remote, tmp_path / "b", memory=mb, log=lambda *_: None)
    assert (rb["imported"], rb["pushed"]) == (0, 0)
    assert len(_ids(mb)) == 3
    assert S.sync(tmp_path / "proj", remote, tmp_path / "a", memory=ma, log=lambda *_: None)["imported"] == 0


def test_log_carries_filtered_text_only(tmp_path: Path, remote: str) -> None:
    m = _mem(tmp_path, "a")
    m.import_turns([S.make_episode("user", "ключ api_key=sk-abcdefghijklmnopqrstuvwxyz123456 не коммитить",
                                   None, "claude-ai", "c1")])  # fmt: skip
    S.sync(tmp_path / "proj", remote, tmp_path / "a", memory=m, log=lambda *_: None)
    text = (S.repo_dir(tmp_path / "proj", tmp_path / "a") / "episodes" / f"{S.device_id(tmp_path / 'a')}.jsonl").read_text("utf-8")
    assert "sk-abcdef" not in text and "REDACTED" in text


def test_add_episode_cli(tmp_path: Path) -> None:
    from cotrail import cli

    home, proj = tmp_path / "home", tmp_path / "proj"
    proj.mkdir()
    cli.main(["--project", str(proj), "--home", str(home), "add-episode", "--role", "assistant", "--source", "claude-ai",
              "--text", "Решили хранить логи эпизодов в приватном git-репозитории", "--ts", "2026-11-19T12:00:00+00:00"])  # fmt: skip
    f = tmp_path / "chat.jsonl"
    f.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in [
        {"role": "user", "text": "А почему не синхронизировать сам sqlite?", "ts": "2026-11-19T12:01:00+00:00"},
        {"role": "assistant", "text": "Потому что бинарный файл даёт конфликты слияния", "ts": "2026-11-19T12:02:00+00:00"},
    ]), "utf-8")  # fmt: skip
    for _ in range(2):  # idempotent: the second add changes nothing
        cli.main(["--project", str(proj), "--home", str(home), "add-episode", "--file", str(f)])
    rows = S.local_episodes(S.store_dir(proj, home) / "graph.sqlite")
    assert len(rows) == 3
    assert {r["source"] for r in rows} == {"claude-ai"}
    assert [r["role"] for r in rows] == ["assistant", "user", "assistant"]


def test_hook_stop_does_not_block(tmp_path: Path, remote: str, monkeypatch) -> None:
    from cotrail import cli

    home, proj = tmp_path / "home", tmp_path / "proj"
    proj.mkdir()
    S.save_config(proj, home, {"remote": remote})
    started = []
    real = S.spawn_background

    def spy(project, h=None):
        p = real(project, h)
        started.append(p)
        return p

    monkeypatch.setattr(S, "spawn_background", spy)
    tr = tmp_path / "t.jsonl"
    tr.write_text("", "utf-8")
    monkeypatch.setattr(sys, "stdin", __import__("io").StringIO(json.dumps({"transcript_path": str(tr), "cwd": str(proj)})))
    t0 = time.perf_counter()
    cli.main(["--project", str(proj), "--home", str(home), "hook-stop"])
    took = time.perf_counter() - t0
    assert started and started[0] is not None
    assert started[0].poll() is None or took < 1.0  # returned while the child still ran, or the child was quick
    assert took < 1.0
    started[0].wait(timeout=120)
    log = (S.store_dir(proj, home) / "sync.log").read_text("utf-8", errors="replace")
    assert "Traceback" not in log
    assert (S.repo_dir(proj, home) / "README.md").exists()


def test_hook_without_sync_config_spawns_nothing(tmp_path: Path) -> None:
    assert S.spawn_background(tmp_path / "proj", tmp_path / "home") is None


def test_network_error_goes_to_log_quietly(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    from cotrail import cli

    home, proj = tmp_path / "home", tmp_path / "proj"
    proj.mkdir()
    S.save_config(proj, home, {"remote": str(tmp_path / "missing.git")})
    cli.main(["--project", str(proj), "--home", str(home), "sync", "--quiet"])  # does not raise
