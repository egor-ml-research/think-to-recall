"""Fully automatic team sync (the autosync rule): nothing to run by hand after `team join`.

- SessionStart hook: a detached `sync` (pull + push) - the session start waits for nothing; the Stop hook does the same
  after each reply. A failed background sync is counted; the next session start shows one line about it.
- git hooks post-commit / post-merge / post-checkout in the member's clone: a detached `graph-refresh` - when code files
  changed, Graphify rebuilds `graphify-out/graph.json` (only with the consent recorded at `team join`), then a sync
  pushes the compact graph. The hooks are a marked block appended to existing hooks; `team leave` removes it.
- status/<device>.json in the memory repo: member, version, last pull / push / graph push, failures - no paths.
- Once a day the background sync looks for a newer cotrail (the team repo's tools/, then PyPI); the session start
  shows one line suggesting «обнови cotrail».
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from cotrail import sync as S

HOOKS = ("post-commit", "post-merge", "post-checkout")
BEGIN, END = "# >>> cotrail team memory (code graph) >>>", "# <<< cotrail team memory <<<"
OLD_BEGIN, OLD_END = "# >>> ctxgraph team memory (code graph) >>>", "# <<< ctxgraph team memory <<<"  # before v0.7.0
CODE_EXT = re.compile(r"\.(py|pyi|js|jsx|ts|tsx|mjs|cjs|go|rs|java|kt|kts|swift|c|cc|cpp|cxx|h|hh|hpp|cs|rb|php|scala|"
                      r"lua|dart|m|mm|sh|ps1|sql|vue|svelte)$", re.I)  # fmt: skip
STATUS_EVERY_H = 6


def _now() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds")


def version() -> str:
    from importlib.metadata import PackageNotFoundError
    from importlib.metadata import version as v

    try:
        return v("cotrail")
    except PackageNotFoundError:
        return ""


# ── failures of the background sync ───────────────────────────────────────────────────────────────────────────────
def record_failure(project, home, err: str) -> None:
    from cotrail.privacy import redact
    from cotrail.repo_check import strip_home

    cfg = S.load_config(project, home)
    msg = strip_home(redact(re.sub(r"\s+", " ", err)).text)[:160]
    S.save_config(project, home, cfg | {"fail_count": int(cfg.get("fail_count") or 0) + 1, "last_error": msg,
                                        "last_fail": _now()})  # fmt: skip


def start_lines(project, home, lang: str = "ru") -> list[str]:
    """The SessionStart lines of the team memory: failed background syncs, an available update."""
    cfg = S.load_config(project, home)
    out = []
    n = int(cfg.get("fail_count") or 0)
    if cfg.get("remote") and n:
        err = cfg.get("last_error") or "?"
        out.append(f"Синхронизация командной памяти не прошла {n} раз(а), последняя ошибка: {err} — повторю "
                   "автоматически." if lang == "ru" else
                   f"Team memory sync failed {n} time(s), last error: {err} - retrying automatically.")  # fmt: skip
    up = _read_home(home).get("update") or {}
    if up.get("new") and _newer(up["new"], version()):
        out.append(f"Есть новая версия cotrail {up['new']} (у вас {version()}): скажите ассистенту «обнови cotrail»."
                   if lang == "ru" else
                   f"A newer cotrail {up['new']} is available (you have {version()}): tell the assistant "
                   "\"update cotrail\".")  # fmt: skip
    return out


# ── update check (once a day, in the background sync) ─────────────────────────────────────────────────────────────
def _read_home(home) -> dict:
    try:
        return json.loads((S.home_dir(home) / "config.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def _write_home(home, data: dict) -> None:
    p = S.home_dir(home) / "config.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1), "utf-8")


def _newer(a: str, b: str) -> bool:
    from cotrail.team import _ver

    try:
        return bool(a) and bool(b) and _ver(a) > _ver(b)
    except TypeError:
        return False


def check_update(repo: Path | None, home, log=print, pypi=None) -> dict:
    """At most once a day: the newest of the team repo's tools/ wheel and PyPI, if newer than the installed one."""
    cfg = _read_home(home)
    up = cfg.get("update") or {}
    today = _now()[:10]
    if up.get("checked") == today or (pypi is None and os.environ.get("COTRAIL_NO_UPDATE_CHECK")):
        return up
    have, best, src = version(), "", ""
    for w in sorted((repo / "tools").glob("cotrail-*.whl")) if repo and (repo / "tools").is_dir() else []:
        v = w.name.split("-")[1]
        if not best or _newer(v, best):
            best, src = v, str(w)
    try:
        v = (pypi or _pypi_latest)()
        if v and (not best or _newer(v, best)) and not (have and ".dev" in have and not _newer(v, have)):
            best, src = v, "cotrail==" + v
    except Exception:  # noqa: BLE001 - offline: the next day again
        pass
    up = {"checked": today, "new": best if _newer(best, have) else "", "src": src if _newer(best, have) else ""}
    _write_home(home, cfg | {"update": up})
    if up["new"]:
        log(f"update available: {up['new']} ({up['src']})")
    return up


def _pypi_latest() -> str:
    import requests

    r = requests.get("https://pypi.org/pypi/cotrail/json", timeout=6)
    return str(r.json()["info"]["version"]) if r.ok else ""


def update_text(home=None) -> str:
    """What «обнови cotrail» does: the exact command; the memory servers must be stopped first on Windows."""
    up = _read_home(home).get("update") or {}
    src = up.get("src") or "cotrail"
    uv = "uv" if _which("uv") else "python -m uv"
    cmd = f'{uv} tool install --force "{src}"' if src.endswith(".whl") else f"{uv} tool install --force {src}"
    have = version()
    head = (f"cotrail {have} -> {up['new']}." if up.get("new") else f"cotrail {have}: no newer build found today.")
    return (f"{head}\nThe running memory servers lock cotrail's files: quit Claude Desktop (tray -> Quit) and Claude "
            f"Code, then run in a terminal:\n  {cmd}\nthen start Claude again.")  # fmt: skip


def _which(x: str) -> bool:
    import shutil

    return shutil.which(x) is not None


# ── status/<device>.json ─────────────────────────────────────────────────────────────────────────────────────────
def write_status(repo: Path, did: str, member: str, cfg: dict, force: bool = False, graph: bool = False) -> bool:
    """This device's status file (no paths, no e-mails); rewritten when something was pushed, the version changed, or
    every STATUS_EVERY_H hours. True when it changed (staged)."""
    p = repo / "status" / f"{did}.json"
    try:
        old = json.loads(p.read_text("utf-8")) if p.exists() else {}
    except ValueError:
        old = {}
    st = {"device": did, "member": member, "version": version(), "last_pull": _now(),
          "last_push": cfg.get("last_push", ""), "last_graph_push": cfg.get("last_graph_push", ""),
          "fails": int(cfg.get("fail_count") or 0)}  # fmt: skip
    if force:
        st["last_push"] = _now()
    if graph:
        st["last_graph_push"] = _now()
    try:
        age = (dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(old.get("last_pull", "2000-01-01T00:00:00+00:00"))
               ).total_seconds() / 3600  # fmt: skip
    except ValueError:
        age = 999
    if not force and old and old.get("version") == st["version"] and old.get("member") == member and age < STATUS_EVERY_H:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, sort_keys=True), "utf-8", newline="\n")
    S._git(repo, "add", f"status/{did}.json")
    return True


def read_statuses(repo: Path, ref: str | None = None) -> list[dict]:
    """status/*.json from the working tree, or from `ref` (origin/main after a fetch)."""
    out = []
    if ref:
        r = S._git(repo, "ls-tree", "--name-only", ref, "status/", check=False)
        names = [n for n in r.stdout.split() if n.endswith(".json")] if r.returncode == 0 else []
        blobs = [S._git(repo, "show", f"{ref}:{n}", check=False).stdout for n in names]
    else:
        blobs = [p.read_text("utf-8") for p in sorted((repo / "status").glob("*.json"))] if (repo / "status").is_dir() else []
    for b in blobs:
        try:
            x = json.loads(b)
        except ValueError:
            continue
        if isinstance(x, dict):
            out.append(x)
    return out


# ── git hooks in the member's clone ──────────────────────────────────────────────────────────────────────────────
def hooks_dir(clone: Path) -> Path | None:
    from cotrail.memory import _git_dir

    r = subprocess.run(["git", "-C", str(clone), "config", "core.hooksPath"], capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.strip():
        hp = Path(r.stdout.strip())
        return hp if hp.is_absolute() else clone / hp
    gd = _git_dir(clone)
    return gd / "hooks" if gd else None


def _block(clone: Path, home) -> str:
    py = Path(sys.executable).as_posix()
    return (f'{BEGIN}\n"{py}" -m cotrail.cli --home "{S.home_dir(home).as_posix()}" --project "{clone.as_posix()}" '
            f"graph-refresh --background >/dev/null 2>&1 || true\n{END}\n")  # fmt: skip


def install_hooks(clone: Path, home=None) -> list[str]:
    """Append (or refresh) the marked block in post-commit / post-merge / post-checkout; other hook lines stay."""
    d = hooks_dir(clone)
    if d is None:
        return []
    d.mkdir(parents=True, exist_ok=True)
    done = []
    for h in HOOKS:
        p = d / h
        text = p.read_text("utf-8", errors="replace") if p.exists() else "#!/bin/sh\n"
        text = _strip(text)
        if not text.endswith("\n"):
            text += "\n"
        p.write_text(text + _block(clone, home), "utf-8", newline="\n")
        try:
            p.chmod(0o755)
        except OSError:
            pass
        done.append(h)
    _exclude_graph_dir(clone)
    return done


def _strip(text: str) -> str:
    for b, e in ((BEGIN, END), (OLD_BEGIN, OLD_END)):
        text = re.sub(rf"\n?{re.escape(b)}.*?{re.escape(e)}\n?", "\n", text, flags=re.S)
    return text.rstrip("\n") + "\n"


def refresh_old_hooks(clone: Path, home=None) -> list[str]:
    """Git hooks written under the old name run `python -m ctxgraph.cli` (gone since v0.7.0): rewrite them once."""
    d = hooks_dir(clone)
    old = [h for h in HOOKS if d and (d / h).exists() and OLD_BEGIN in (d / h).read_text("utf-8", errors="replace")]
    return install_hooks(clone, home) if old else []


def remove_hooks(clone: Path) -> list[str]:
    d = hooks_dir(clone)
    out = []
    for h in HOOKS if d else ():
        p = d / h
        if p.exists() and any(b in p.read_text("utf-8", errors="replace") for b in (BEGIN, OLD_BEGIN)):
            rest = _strip(p.read_text("utf-8", errors="replace"))
            if rest.strip() in ("", "#!/bin/sh"):
                p.unlink()
            else:
                p.write_text(rest, "utf-8", newline="\n")
            out.append(h)
    return out


def _exclude_graph_dir(clone: Path) -> None:
    """graphify-out/ never goes into the project's own repo: .git/info/exclude (local, not committed)."""
    from cotrail.memory import _git_dir

    gd = _git_dir(clone)
    if gd is None:
        return
    ex = gd / "info" / "exclude"
    ex.parent.mkdir(parents=True, exist_ok=True)
    cur = ex.read_text("utf-8", errors="replace") if ex.exists() else ""
    if "graphify-out/" not in cur.split():
        ex.write_text(cur + ("" if cur.endswith("\n") or not cur else "\n") + "graphify-out/\n", "utf-8")


# ── graph-refresh (run by the git hooks, detached) ───────────────────────────────────────────────────────────────
def changed_code(clone: Path, since: str) -> list[str]:
    if not since:
        return ["*"]
    r = subprocess.run(["git", "-C", str(clone), "diff", "--name-only", since, "HEAD"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")  # fmt: skip
    if r.returncode != 0:
        return ["*"]
    return [f for f in r.stdout.splitlines() if CODE_EXT.search(f)]


def graph_refresh(project, home=None, build=None, log=print) -> dict:
    """When code changed since the last graph: rebuild it (consent at join) and import it as this device's own layer;
    then a sync pushes it. `build(clone)` -> path of graph.json (tests); default: Graphify."""
    project = Path(project).resolve()
    cfg = S.load_config(project, home)
    if not cfg.get("remote"):
        return {"skipped": "not in a team"}
    clone = S._clone_root(project)
    head = subprocess.run(["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    changed = changed_code(clone, cfg.get("graph_commit", ""))
    out = clone / "graphify-out" / "graph.json"
    res = {"changed": len(changed), "built": False}
    if changed and cfg.get("graphify"):
        g = (build or _graphify_build)(clone)
        if g:
            from cotrail import graphify as GF

            GF.import_graph(S.store_dir(project, home) / "graph.sqlite", g)
            res["built"] = True
    elif changed and not out.exists():
        res["skipped"] = "no consent to install Graphify (team join --graphify yes)"
    S.save_config(project, home, S.load_config(project, home) | {"graph_commit": head})
    if res["built"] or (changed and out.exists()):
        S.sync(project, None, home, log=log)
    return res


def _graphify_build(clone: Path) -> Path | None:
    from cotrail import setup as SU

    cmd = SU._graphify_cmd()
    if cmd is None and SU._install_graphify():
        import importlib

        importlib.invalidate_caches()
        cmd = SU._graphify_cmd()
    if cmd is None:
        return None
    r = subprocess.run(cmd + ["extract", str(clone), "--code-only"], cwd=clone, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800, env=os.environ)  # fmt: skip
    out = clone / "graphify-out" / "graph.json"
    return out if r.returncode == 0 and out.exists() else None


# ── sync from the MCP server itself (any client: Cursor, Codex, Gemini CLI, OpenCode, ...) ─────────────────────────
PUSH_MIN_S = 60  # at most one push sync a minute after new records
PULL_EVERY_S = 600  # a pull while the server runs
TICK_S = 10


def _count(db: Path) -> int:
    """Episodes of a store, by a short read-only connection of its own (the server's connection stays untouched)."""
    import sqlite3

    try:
        con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True, timeout=2)
        try:
            return int(con.execute("SELECT COUNT(*) FROM episodes").fetchone()[0])
        finally:
            con.close()
    except sqlite3.Error:
        return -1


def _queued(store: Path) -> bool:
    """Turns a hook queued that the store has not imported yet (Claude Code pending.txt, client hook_turns/)."""
    q = store / "pending.txt"
    try:
        if q.exists() and q.stat().st_size > 0:
            return True
    except OSError:
        pass
    return any((store / "hook_turns").glob("*.jsonl")) if (store / "hook_turns").is_dir() else False


class ServerSync:
    """A daemon thread of the MCP server: for every opened memory that is in a team, a detached `cotrail sync` at the
    start, after new records (at most once a minute) and every PULL_EVERY_S. Never blocks a tool call; the sync
    process takes the store's lock (a running sync is skipped) and records failures for the next session start."""

    def __init__(self, memories, spawn=None, clock=None) -> None:
        import time

        self.memories = memories  # () -> [(project, store, home)]
        self.spawn = spawn or (lambda project, home: S.spawn_background(project, home))
        self.clock = clock or time.monotonic
        self.state: dict[str, dict] = {}  # store -> {base, last, proc}

    def _team(self, store: Path) -> bool:
        try:
            return bool(json.loads((store / "sync.json").read_text("utf-8")).get("remote"))
        except (OSError, ValueError):
            return False

    def tick(self) -> list[str]:
        """One pass; returns the stores a sync was started for (tests)."""
        started = []
        now = self.clock()
        for project, store, home in self.memories():
            store = Path(store)
            if not self._team(store):
                continue
            st = self.state.setdefault(str(store), {"base": None, "last": None, "proc": None})
            p = st["proc"]
            if p is not None and p.poll() is None:
                continue  # still running
            if p is not None:  # finished: what it imported is not "new" for the next push
                st["proc"], st["base"] = None, _count(store / "graph.sqlite")
            n = _count(store / "graph.sqlite")
            first = st["last"] is None
            dirty = (st["base"] is not None and n != st["base"]) or _queued(store)
            due = first or (now - st["last"] >= PULL_EVERY_S) or (dirty and now - st["last"] >= PUSH_MIN_S)
            if due:
                st["proc"], st["last"], st["base"] = self.spawn(project, home), now, n
                started.append(str(store))
            elif st["base"] is None:
                st["base"] = n
        return started

    def run(self, stop=None) -> None:
        import time

        while not (stop and stop.is_set()):
            try:
                self.tick()
            except Exception:  # noqa: BLE001 - the server keeps serving
                pass
            time.sleep(TICK_S)


def maybe_sync(project, home=None, min_gap_s: int = PUSH_MIN_S) -> str:
    """After a client hook imported turns (hook-import, already detached): sync now unless one ran in the last minute
    or another is running; a failure is recorded for the next session start."""
    import datetime as _dt

    cfg = S.load_config(project, home)
    if not cfg.get("remote"):
        return "not in a team"
    try:
        last = _dt.datetime.fromisoformat(cfg.get("last_sync", "2000-01-01T00:00:00+00:00"))
        if (_dt.datetime.now(_dt.UTC) - last).total_seconds() < min_gap_s:
            return "recent"
    except ValueError:
        pass
    try:
        S.sync(project, None, home, log=lambda m: None)
        return "synced"
    except S.SyncError as e:
        if "another sync is running" not in str(e):
            record_failure(project, home, str(e))
        return "failed"
