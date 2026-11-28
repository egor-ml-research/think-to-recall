"""Memory sync through a private git repository: an append-only JSONL episode log per device.

Layout of the sync repository (a local clone lives in the cotrail home, outside the project):

    README.md
    episodes/<device-id>.jsonl     # one episode per line; only that device ever writes the file

An episode line is what the importer stores: id, hash, role, text (already through the secret filter), ts, session,
source, author (git user.name of the device that wrote it; + the optional after_summary / ask flags). The SQLite store is never put in the repository: every device builds
its own from the logs through `ProjectMemory.import_turns` (idempotent by id); lines are also deduplicated by `hash`.

`sync()`: pull -> import the other devices' new episodes -> append this device's new episodes to its own file ->
commit and push that file alone. Each device writes only its own file, so there are no merge conflicts; a rejected
push (another device pushed meanwhile) is retried after `pull --rebase`.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from cotrail.episodes import (  # noqa: F401 - the shared helpers, kept importable as sync.<name>
    SyncError,
    add_episodes,
    config_path,
    device_id,
    episode_hash,
    home_dir,
    load_config,
    local_episodes,
    make_episode,
    read_jsonl,
    save_config,
    store_dir,
)

BRANCH = "main"
README = """# cotrail memory (PRIVATE)

This repository is the shared decision memory of a project, synced by `cotrail sync`.

**It contains conversations** (the user's prompts and the assistant's visible replies, after a secret filter).
Keep it private. Do not make it public, do not fork it into a public place.

- `episodes/<device-id>.jsonl` - an append-only log per device or source; only that device writes its file.
- The SQLite store is not here: each device rebuilds it locally from these logs.
"""


def repo_dir(project, home=None) -> Path:
    """The local clone of the memory repo: `<store>/sync-repo` where one exists already (older versions), else a
    short path `<home>/sync/<hash of the store name>` - git on Windows fails on long paths of folder-named stores."""
    sd = store_dir(project, home)
    old = sd / "sync-repo"
    if (old / ".git").exists():
        return old
    return home_dir(home) / "sync" / hashlib.sha256(sd.name.encode()).hexdigest()[:12]


# ── git ──────────────────────────────────────────────────────────────────────────────────────────────────────────────


NETWORK = {"ls-remote", "fetch", "pull", "push", "clone"}
# a flaky network (TLS handshakes dropped, timeouts): these git calls are retried with a growing pause
NET_DELAYS = (2, 4, 6, 10)  # seconds between the 5 attempts
_NET_ERR = re.compile(r"(?i)handshake|schannel|ssl|tls|timed? ?out|could not resolve|unable to access|connection|"
                      r"early eof|rpc failed|remote end hung up|network|proxy|temporarily|reset by peer|503|502")  # fmt: skip
NET_HINT = "network error - run the same command again, it is safe to repeat"


def _run(cmd: list[str], env: dict) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                          timeout=300)  # fmt: skip


def _git_cfg(repo: Path, key: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), "config", "--local", key], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")  # fmt: skip
    return r.stdout.strip() if r.returncode == 0 else ""


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = os.environ | {"GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"}
    if args[0] == "commit":  # the device identity even when GIT_AUTHOR_* / GIT_COMMITTER_* are set (no personal e-mail)
        who = {k: _git_cfg(repo, k) for k in ("user.name", "user.email")}
        if who["user.name"] and who["user.email"]:
            env |= {"GIT_AUTHOR_NAME": who["user.name"], "GIT_AUTHOR_EMAIL": who["user.email"],
                    "GIT_COMMITTER_NAME": who["user.name"], "GIT_COMMITTER_EMAIL": who["user.email"]}
    net = args[0] in NETWORK
    ssl: list[str] = []
    for delay in (*NET_DELAYS, None) if net else (None,):
        try:
            r = _run(["git", "-C", str(repo), *ssl, *args], env)
        except subprocess.TimeoutExpired as e:
            r = subprocess.CompletedProcess(e.cmd, 1, "", "timed out")
        err = (r.stderr or r.stdout).strip()
        if r.returncode == 0 or not net or not _NET_ERR.search(err) or delay is None:
            break
        if "schannel" in err.lower() and not ssl:  # Windows TLS drops: the next attempts through OpenSSL (this call only)
            ssl = ["-c", "http.sslBackend=openssl"]
        time.sleep(delay)
    if check and r.returncode != 0:
        hint = f" ({NET_HINT})" if net and _NET_ERR.search(err) else ""
        raise SyncError(f"git {' '.join(args)}: {err}{hint}")
    return r


def _remote_has_branch(repo: Path) -> bool:
    r = _git(repo, "ls-remote", "--heads", "origin", BRANCH)
    return bool(r.stdout.strip())


def ensure_clone(repo: Path, remote: str, device: str) -> None:
    if not (repo / ".git").exists():
        repo.mkdir(parents=True, exist_ok=True)
        _git(repo, "init", "-q")
        _git(repo, "remote", "add", "origin", remote)
    elif _git(repo, "remote", "get-url", "origin").stdout.strip() != remote:
        _git(repo, "remote", "set-url", "origin", remote)
    # commits name the device, not the person: nothing personal goes into the history
    _git(repo, "config", "user.name", f"cotrail {device}")
    _git(repo, "config", "user.email", f"{device}@cotrail.invalid")
    _git(repo, "config", "core.autocrlf", "false")
    _git(repo, "config", "core.longpaths", "true")  # the clone sits under the project slug: long on Windows
    has_head = _git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode == 0
    if not has_head:
        _git(repo, "symbolic-ref", "HEAD", f"refs/heads/{BRANCH}")
        if _remote_has_branch(repo):
            _git(repo, "fetch", "-q", "origin", BRANCH)
            _git(repo, "reset", "-q", "--hard", f"origin/{BRANCH}")
        _git(repo, "branch", "--set-upstream-to", f"origin/{BRANCH}", check=False)


def _ahead(repo: Path) -> bool:
    """Local commits the remote does not have yet (or a first commit while the remote is empty)."""
    if _git(repo, "rev-parse", "--verify", "-q", "HEAD", check=False).returncode != 0:
        return False
    if _git(repo, "rev-parse", "--verify", "-q", f"origin/{BRANCH}", check=False).returncode != 0:
        return True
    r = _git(repo, "rev-list", "--count", f"origin/{BRANCH}..HEAD", check=False)
    return r.returncode == 0 and r.stdout.strip() not in ("", "0")


def _pull(repo: Path) -> None:
    if _remote_has_branch(repo):
        _git(repo, "pull", "-q", "--rebase", "origin", BRANCH)


# ── the log ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def read_logs(repo: Path) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for f in sorted((repo / "episodes").glob("*.jsonl")):
        rows = []
        for line in f.read_text("utf-8", errors="replace").splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue  # a torn last line (a crash mid-write) is skipped, not fatal
            if isinstance(r, dict) and r.get("id") and r.get("text") is not None:
                rows.append(r)
        out[f.stem] = rows
    return out


def _append(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def _scrubbed(r: dict) -> dict:
    """Belt and braces: the store's text went through the filter already; run it again before the text leaves, and
    shorten home folders (`C:\\Users\\<name>\\...`, `/home/<name>/...`) to `~` - they name the person."""
    from cotrail.privacy import redact
    from cotrail.repo_check import strip_home

    def clean(x: str) -> str:
        return strip_home(redact(x).text)

    return (r | {"text": clean(r["text"])} | ({"ask": clean(r["ask"])} if r.get("ask") else {})
            | ({"pasted": clean(r["pasted"])} if r.get("pasted") else {}))


# ── lock: one sync at a time per project (a hook may fire while a previous sync still runs) ───────────────────────────
class _Lock:
    def __init__(self, path: Path, stale: float = 900) -> None:
        self.path, self.stale, self.fd = path, stale, None

    def __enter__(self):
        for _ in range(2):
            try:
                self.fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self.stale:
                        self.path.unlink()
                        continue
                except FileNotFoundError:
                    continue
                raise SyncError("another sync is running") from None
        raise SyncError("another sync is running")

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


# ── sync ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
def sync(project: str | Path, remote: str | None = None, home: str | Path | None = None, *, memory=None,
         retries: int = 5, log=print) -> dict:  # fmt: skip
    """Pull, import the others' new episodes, append and push this device's own. Returns counts."""
    project = Path(project).resolve()
    home = home_dir(home)
    cfg = load_config(project, home)
    remote = remote or cfg.get("remote")
    if not remote:
        raise SyncError("no remote: run `cotrail sync --remote <git-url>` once")
    if remote != cfg.get("remote"):
        save_config(project, home, cfg | {"remote": remote})
    did = device_id(home)
    repo = repo_dir(project, home)
    sdir = store_dir(project, home)
    sdir.mkdir(parents=True, exist_ok=True)
    with _Lock(sdir / "sync.lock"):
        ensure_clone(repo, remote, did)
        _pull(repo)
        if memory is None:
            from cotrail.memory import ProjectMemory

            memory = ProjectMemory(project, home=home)
        if cfg.get("author"):
            memory._author = cfg["author"]
        memory.ingest_pending()  # turns the Stop hook queued: they go out in this same sync

        # 1. import the others' new episodes (dedupe by id, then by content hash)
        logs = read_logs(repo)
        mine = local_episodes(memory.db_path)
        have_ids = {r[0] for r in memory.s.q("SELECT id FROM episodes")}
        have_hash = {r["hash"] for r in mine}
        todo, seen = [], set()
        for _dev, rows in sorted(logs.items(), key=lambda kv: kv[0] != did):
            for r in rows:
                h = r.get("hash") or episode_hash(r["role"], r["session"], r["ts"], r["text"])
                if r["id"] in have_ids or h in have_hash or h in seen or r["id"] in seen:
                    continue
                seen.update((h, r["id"]))
                todo.append({"id": r["id"], "role": r["role"], "text": r["text"], "ts": r.get("ts", ""),
                             "session": r.get("session", "sync"), "source": r.get("source", "sync"),
                             "after_summary": bool(r.get("after_summary")), "ask": r.get("ask", ""),
                             "author": r.get("author", ""), "pasted": r.get("pasted", ""),
                             "title": r.get("title", "")})  # fmt: skip
        imported = memory.import_turns(todo)["new"] if todo else 0
        # code graphs (the team graphs rule): the others' as layers, this device's into graphs/
        layers = pull_graphs(repo, did, memory)
        graph_pushed = push_graph(project, repo, did, memory.author, log)

        # 2. this device's episodes that no log has yet -> its own file
        log_ids = {r["id"] for rows in logs.values() for r in rows}
        log_hash = {r.get("hash") for rows in logs.values() for r in rows}
        new = [_scrubbed(r) for r in local_episodes(memory.db_path, memory.author)
               if r["id"] not in log_ids and r["hash"] not in log_hash]  # fmt: skip
        from cotrail.repo_check import check_rows

        bad = check_rows(new)
        held = sorted({b["id"] for b in bad})
        if bad:  # never push what the repo check would flag: those lines stay local, the rest goes
            new = [r for r in new if r["id"] not in held]
            log("held back by the repo check (not pushed): "
                + "; ".join(f"{b['id']} {b['field']}:{b['kind']}" for b in bad[:10]))  # fmt: skip
        mine_file = repo / "episodes" / f"{did}.jsonl"
        if new:
            _append(mine_file, new)
        if not (repo / "README.md").exists():
            (repo / "README.md").write_text(README, "utf-8", newline="\n")
            _git(repo, "add", "README.md")
        pushed = 0
        from cotrail import autosync as A

        try:
            A.refresh_old_hooks(Path(project), home)
        except OSError:
            pass
        A.write_status(repo, did, memory.author, load_config(project, home), force=bool(new) or graph_pushed,
                       graph=graph_pushed)
        if new or _git(repo, "status", "--porcelain").stdout.strip():
            if mine_file.exists():  # also lines appended by a run that stopped before its commit
                _git(repo, "add", str(mine_file.relative_to(repo)).replace("\\", "/"))
            if _git(repo, "status", "--porcelain").stdout.strip():
                _git(repo, "commit", "-q", "-m", f"{did}: +{len(new)} episodes")
        if _ahead(repo):  # this run's commit, or one an interrupted run (network) left unpushed
            for attempt in range(retries):
                r = _git(repo, "push", "-q", "origin", f"HEAD:{BRANCH}", check=False)
                if r.returncode == 0:
                    pushed = len(new)
                    break
                if attempt == retries - 1:
                    err = (r.stderr or r.stdout).strip()
                    raise SyncError(f"push failed: {err}" + (f" ({NET_HINT})" if _NET_ERR.search(err) else ""))
                time.sleep(0.3 * (attempt + 1))
                _pull(repo)
        res = {"device": did, "imported": imported, "pushed": pushed, "held": len(held), "code_layers": layers,
               "total": sum(len(v) for v in read_logs(repo).values())}  # fmt: skip
        now = dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
        save_config(project, home, load_config(project, home) | {"last_sync": now, "last_pull": now, "fail_count": 0,
                    "last_error": ""} | ({"last_push": now} if pushed or graph_pushed else {})
                    | ({"last_graph_push": now} if graph_pushed else {}))  # fmt: skip
        A.check_update(repo, home, log)
        log(f"sync {dt.datetime.now().isoformat(timespec='seconds')}: {json.dumps(res)}")
        return res


# ── code graphs of the members (the team graphs rule) ──────────────────────────────────────────────────────────────────
def _clone_root(project: Path) -> Path:
    from cotrail.memory import _git_dir

    gd = _git_dir(project)
    return gd.parent if gd is not None and gd.name == ".git" else project


def push_graph(project: Path, repo: Path, did: str, member: str, log=print) -> bool:
    """This device's Graphify graph (graphify-out/graph.json of the clone) as graphs/<device>.json: compact, relative
    paths, checked first; unchanged -> nothing written. True when the file changed."""
    from cotrail import graphify as GF
    from cotrail.repo_check import check_graph_data

    root = _clone_root(project)
    src = next((p for p in (project / "graphify-out" / "graph.json", root / "graphify-out" / "graph.json") if p.exists()), None)
    if src is None:
        return False
    try:
        g = GF.compact(src, root, member or did)
    except (OSError, ValueError) as e:
        log(f"code graph not shared: {e}")
        return False
    bad = check_graph_data(g)
    if bad:
        log("code graph not shared (repo check): " + "; ".join(f"{b['id']} {b['field']}:{b['kind']}" for b in bad[:5]))
        return False
    out = repo / "graphs" / f"{did}.json"
    text = json.dumps(g, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    if out.exists() and out.read_text("utf-8") == text:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, "utf-8", newline="\n")
    _git(repo, "add", f"graphs/{did}.json")
    return True


def pull_graphs(repo: Path, did: str, memory) -> int:
    """The other devices' graphs/<device>.json as code layers of the local store (re-imported only when changed)."""
    files = sorted(p for p in (repo / "graphs").glob("*.json") if p.stem != did) if (repo / "graphs").is_dir() else []
    blob = "".join(f"{p.name}:{p.stat().st_size}:{hashlib.sha256(p.read_bytes()).hexdigest()[:12]};" for p in files)
    key = hashlib.sha256(blob.encode()).hexdigest()[:16]
    row = memory.s.q("SELECT value FROM memory_meta WHERE key='graphs_hash'")
    if row and row[0][0] == key:
        return 0
    graphs = []
    for p in files:
        try:
            g = json.loads(p.read_text("utf-8"))
        except ValueError:
            continue
        if isinstance(g, dict) and g.get("nodes"):
            graphs.append(g)
    from cotrail import graphify as GF

    memory.s.db.commit()
    n = GF.import_members(memory.db_path, graphs)
    memory.s.db.execute("INSERT OR REPLACE INTO memory_meta VALUES('graphs_hash', ?)", (key,))
    memory.s.db.commit()
    return n


# ── add-episode: turns of an external chat (claude.ai etc.) ─────────────────────────────────────────────────────────


# ── the Stop hook: sync in the background ────────────────────────────────────────────────────────────────────────────
def spawn_background(project: str | Path, home: str | Path | None = None, command: tuple = ("sync", "--quiet")
                     ) -> subprocess.Popen | None:  # fmt: skip
    """Start `cotrail sync` detached and return at once; output (and any network error) goes to sync.log, and the
    next run retries. Nothing happens when sync was never configured for this project."""
    project = Path(project).resolve()
    home = home_dir(home)
    if not load_config(project, home).get("remote"):
        return None
    sdir = store_dir(project, home)
    sdir.mkdir(parents=True, exist_ok=True)
    logf = open(sdir / "sync.log", "a", encoding="utf-8")  # noqa: SIM115 - handed to the child
    kw: dict = {"stdin": subprocess.DEVNULL, "stdout": logf, "stderr": subprocess.STDOUT, "close_fds": True}
    if sys.platform == "win32":
        kw["creationflags"] = 0x00000008 | 0x00000200 | 0x08000000  # DETACHED | NEW_PROCESS_GROUP | NO_WINDOW
    else:
        kw["start_new_session"] = True
    cmd = [sys.executable, "-m", "cotrail.cli", "--project", str(project), "--home", str(home), *command]
    try:
        return subprocess.Popen(cmd, **kw)
    finally:
        logf.close()


def trim_log(path: Path, keep: int = 400) -> None:
    try:
        lines = path.read_text("utf-8", errors="replace").splitlines()
        if len(lines) > keep * 2:
            path.write_text("\n".join(lines[-keep:]) + "\n", "utf-8")
    except OSError:
        pass

