"""team join from a wrong folder is refused (home, drive root, no git remote) unless --force; team leave; a flaky
network: git network calls are retried, a half-finished join is safe to rerun. Synthetic: temp homes, bare repos."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cotrail import cli
from cotrail import sync as S
from cotrail import team as T
from cotrail.memory import ProjectMemory

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
OK = lambda r: "local"  # noqa: E731 - the visibility check of a local bare repo


def _clone(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir()
    subprocess.run(["git", "-C", str(d), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(d), "remote", "add", "origin", "https://github.com/example-org/demo.git"], check=True)
    return d


@pytest.fixture
def bare(tmp_path: Path) -> str:
    b = tmp_path / "mem.git"
    subprocess.run(["git", "init", "-q", "--bare", str(b)], check=True)
    return str(b)


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    monkeypatch.setenv("COTRAIL_AUTHOR", "Dev")


def _remote_lines(bare: str, tmp: Path) -> list[dict]:
    d = tmp / f"check-{len(list(tmp.glob('check-*')))}"
    subprocess.run(["git", "clone", "-q", "-b", "main", bare, str(d)], check=True, capture_output=True)
    return [json.loads(x) for f in (d / "episodes").glob("*.jsonl") for x in f.read_text("utf-8").splitlines() if x]


def test_join_refuses_home_drive_root_and_folders_without_remote(tmp_path: Path, bare: str, monkeypatch, capsys) -> None:
    fake_home = tmp_path / "userhome"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))
    h = tmp_path / "h"
    _clone(tmp_path, "proj")
    ProjectMemory(tmp_path / "proj", home=h)  # a known clone, suggested in the message
    for folder, why in ((fake_home, "home folder"), (Path(tmp_path.anchor), "drive root"), (tmp_path, "without a git remote")):
        with pytest.raises(T.TeamError, match=why) as e:
            T.join(folder, bare, h, name="Dev", check=OK, log=lambda m: None)
        assert "cd " in str(e.value) and str(tmp_path / "proj") in str(e.value)
    assert not any(p.name.startswith("C--") and "userhome" in p.name for p in h.iterdir())
    with pytest.raises(SystemExit, match="Run it inside your project's clone"):
        cli.main(["--project", str(fake_home), "--home", str(h), "team", "join", bare])
    plain = tmp_path / "plain"
    plain.mkdir()
    r = T.join(plain, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None, force=True)
    assert r["identity"].startswith("(no git remote")
    from cotrail import assistant_setup as A

    assert A.join_team(bare, str(fake_home), home=h, check=OK).startswith("Not joined")


def test_leave_turns_sync_off_and_keeps_the_memory(tmp_path: Path, bare: str, capsys) -> None:
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    m = ProjectMemory(p, home=h)
    m.remember("Решили: держать конфиг в TOML")
    m.s.db.close()
    T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    cli.main(["--project", str(p), "--home", str(h), "team", "leave"])
    assert "sync is off" in capsys.readouterr().out
    assert not S.load_config(p, h).get("remote") and S.spawn_background(p, h) is None
    assert T.status(p, h)["remote"] == "" and "Not in a team" in T.format_status(T.status(p, h))
    assert ProjectMemory(p, home=h).s.q("SELECT COUNT(*) FROM episodes")[0][0] == 1
    cli.main(["--project", str(p), "--home", str(h), "team", "leave"])
    assert "not in a team" in capsys.readouterr().out


def _flaky(monkeypatch, fail_first: int, only: set[str] | None = None) -> dict:
    real, state = S._run, {"n": 0, "calls": 0}

    def run(cmd, env):
        sub = next(x for x in cmd[3:] if not x.startswith("-") and "=" not in x)
        if sub in S.NETWORK and (only is None or sub in only):
            state["calls"] += 1
            if state["n"] < fail_first:
                state["n"] += 1
                return subprocess.CompletedProcess(cmd, 128, "", "fatal: unable to access 'https://github.com/x/': "
                                                   "schannel: failed to receive handshake, SSL/TLS connection failed")
        return real(cmd, env)

    monkeypatch.setattr(S, "_run", run)
    return state


def test_a_few_dropped_handshakes_are_retried(tmp_path: Path, bare: str, monkeypatch) -> None:
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    ProjectMemory(p, home=h).remember("Решили: API отдаёт ошибки в формате problem+json")
    st = _flaky(monkeypatch, 3)
    r = T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    assert st["n"] == 3 and r["pushed"] == 1
    assert len(_remote_lines(bare, tmp_path)) == 1


def test_a_half_finished_join_is_safe_to_rerun(tmp_path: Path, bare: str, monkeypatch) -> None:
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    m = ProjectMemory(p, home=h)
    m.remember("Решили: сессии храним 15 минут")
    m.remember("Решили: логин через OAuth")
    m.s.db.close()
    _flaky(monkeypatch, 10**6, only={"push"})  # the network is gone for the push: the commit stays local
    with pytest.raises(S.SyncError, match="safe to repeat"):
        T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    monkeypatch.undo()
    monkeypatch.setattr(S, "NET_DELAYS", (0, 0, 0, 0))
    _flaky(monkeypatch, 4, only={"ls-remote"})  # still flaky at the start of the rerun: retried
    T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)  # and once more: no change
    lines = _remote_lines(bare, tmp_path)
    assert len(lines) == 2 and len({x["id"] for x in lines}) == 2


def test_network_error_message_says_rerun(tmp_path: Path, bare: str, monkeypatch, capsys) -> None:
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    _flaky(monkeypatch, 10**6)
    with pytest.raises(SystemExit, match="safe to repeat"):
        cli.main(["--project", str(p), "--home", str(h), "team", "join", bare, "--no-history"])


def test_commits_carry_the_device_identity_even_with_git_author_env(tmp_path: Path, bare: str, monkeypatch) -> None:
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Real Person")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "real.person@example.com")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "real.person@example.com")
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    ProjectMemory(p, home=h).remember("Решили: логи в JSON")
    T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    out = subprocess.run(["git", "--git-dir", bare, "log", "main", "--format=%an <%ae> | %cn <%ce>"], capture_output=True,
                         text=True).stdout  # fmt: skip
    assert "real.person" not in out and "@cotrail.invalid" in out


def test_status_fetches_and_shows_what_the_remote_has(tmp_path: Path, bare: str, monkeypatch) -> None:
    a, b = _clone(tmp_path, "a"), _clone(tmp_path, "b")
    ha, hb = tmp_path / "ha", tmp_path / "hb"
    ProjectMemory(a, home=ha).remember("Решили: API отдаёт JSON")
    T.join(a, bare, ha, name="Back", import_history=False, check=OK, log=lambda m: None)
    st = T.status(a, ha)
    assert st["remote_checked"] and st["remote_new"] == 0 and "up to date" in T.format_status(st)
    assert "min ago" in T.format_status(st)
    m = ProjectMemory(b, home=hb)  # the second member pushes after a's last sync
    m.remember("Решили: кнопка входа зелёная")
    m.remember("Решили: статус туннеля в трее")
    m.s.db.close()
    monkeypatch.setenv("COTRAIL_AUTHOR", "Front")
    T.join(b, bare, hb, name="Front", import_history=False, check=OK, log=lambda m: None)
    st = T.status(a, ha)
    assert st["remote_new"] == 2 and st["remote_members"] == {"Back": 1, "Front": 2} and st["members"] == {"Back": 1}
    assert "2 new record(s) not synced here - run `cotrail sync`" in T.format_status(st)
    S.sync(a, None, ha, log=lambda m: None)
    assert T.status(a, ha)["remote_new"] == 0
    st = T.status(a, ha) | {}
    monkeypatch.setattr(S, "_run", lambda cmd, env: subprocess.CompletedProcess(cmd, 128, "", "fatal: unable to access: "
                                                                                 "Could not resolve host"))  # fmt: skip
    st = T.status(a, ha)
    assert st["offline"] and "not reachable" in T.format_status(st) and st["members"] == {"Back": 1, "Front": 2}


def test_schannel_failure_falls_back_to_openssl_for_this_call_only(tmp_path: Path, bare: str, monkeypatch) -> None:
    real, seen = S._run, []

    def run(cmd, env):
        if "ls-remote" in cmd:
            seen.append(list(cmd))
            if "http.sslBackend=openssl" not in cmd:
                return subprocess.CompletedProcess(cmd, 128, "", "fatal: unable to access: schannel: failed to receive handshake")
        return real(cmd, env)

    monkeypatch.setattr(S, "_run", run)
    p, h = _clone(tmp_path, "proj"), tmp_path / "h"
    T.join(p, bare, h, name="Dev", import_history=False, check=OK, log=lambda m: None)
    assert seen and "http.sslBackend=openssl" not in seen[0] and "http.sslBackend=openssl" in seen[1]
    local = subprocess.run(["git", "-C", str(S.repo_dir(p, h)), "config", "--local", "--get", "http.sslBackend"],
                           capture_output=True, text=True).stdout  # fmt: skip
    assert local == ""  # a per-call option: no git config is written
