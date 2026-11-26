"""The old name (ctxgraph -> cotrail, v0.7.0, 2026-11).

- every `CTXGRAPH_*` variable is still read: it fills `COTRAIL_*` when that one is not set (a new name wins);
- the data home is `~/.cotrail`; while it does not exist and `~/.ctxgraph` does, the old folder is used in place
  (nothing is moved; `cotrail migrate-home` copies it, checks the record counts, never deletes the old one);
- the old commands `ctxgraph`, `ctxgraph-mcp`, `ctxgraph-mcpw` run the new ones after a one-line hint on stderr
  (never stdout: the MCP server speaks JSON-RPC there). Planned removal of the aliases: 2027-02.

Imports nothing from the package: `cotrail/__init__.py` runs it first.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

OLD_ENV, NEW_ENV = "CTXGRAPH_", "COTRAIL_"
OLD_HOME, NEW_HOME = ".ctxgraph", ".cotrail"
#: names an older version wrote into client configs and hooks; `cotrail setup` replaces them
OLD_SERVER_KEYS = ("ctxgraph",)
OLD_COMMANDS = ("ctxgraph", "ctxgraph-mcp", "ctxgraph-mcpw")


def mirror_env(environ=None) -> None:
    environ = os.environ if environ is None else environ
    for k, v in list(environ.items()):
        if k.startswith(OLD_ENV):
            environ.setdefault(NEW_ENV + k[len(OLD_ENV):], v)


def default_home() -> Path:
    """COTRAIL_HOME (or the old CTXGRAPH_HOME), else ~/.cotrail, else an existing ~/.ctxgraph in place."""
    env = os.environ.get("COTRAIL_HOME") or os.environ.get("CTXGRAPH_HOME")
    if env:
        return Path(env)
    new, old = Path.home() / NEW_HOME, Path.home() / OLD_HOME
    if not new.exists() and old.exists():
        return old
    return new


def hint(new: str) -> None:
    try:
        if sys.stderr is not None:
            print(f"ctxgraph is now cotrail: please use `{new}` (the old name keeps working until 2027-02).",
                  file=sys.stderr)
    except Exception:  # noqa: BLE001 - a GUI launcher may have no usable stderr
        pass


def cli_main() -> None:
    hint("cotrail")
    from cotrail.cli import main

    main()


def mcp_main() -> None:
    hint("cotrail-mcp")
    from cotrail.memory_mcp import main

    main()


def mcpw_main() -> None:
    hint("cotrail-mcpw")
    from cotrail.memory_mcp import main

    main()


# ── cotrail migrate-home ─────────────────────────────────────────────────────────────────────────────────────────
def _is_sqlite(p: Path) -> bool:
    try:
        with open(p, "rb") as f:
            return f.read(16) == b"SQLite format 3\x00"
    except OSError:
        return False


def _counts(db: Path) -> dict:
    import sqlite3

    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    try:
        names = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        return {n: con.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0] for n in names}
    finally:
        con.close()


def migrate_home(src: Path | None = None, dst: Path | None = None, log=print) -> int:
    """Copy the old home to ~/.cotrail (SQLite through the backup API), check the record counts of every store, then
    the new folder is used (it exists). The old folder is never deleted. Returns 0 on success."""
    import shutil
    import sqlite3

    src = Path(src or Path.home() / OLD_HOME)
    dst = Path(dst or Path.home() / NEW_HOME)
    if not src.is_dir():
        log(f"Nothing to migrate: {src} does not exist.")
        return 0
    if dst.exists():
        log(f"{dst} already exists: nothing copied (remove it by hand to migrate again).")
        return 1
    tmp = dst.with_name(dst.name + ".migrating")
    if tmp.exists():
        shutil.rmtree(tmp)
    dbs = []
    for p in src.rglob("*"):
        rel = p.relative_to(src)
        q = tmp / rel
        if p.is_dir():
            q.mkdir(parents=True, exist_ok=True)
            continue
        q.parent.mkdir(parents=True, exist_ok=True)
        if p.name.endswith(("-wal", "-shm", "-journal")):
            continue  # the backup API copies the committed database, the WAL included
        if _is_sqlite(p):
            a = sqlite3.connect(p.as_posix())
            b = sqlite3.connect(q.as_posix())
            try:
                a.backup(b)
            finally:
                b.close()
                a.close()
            dbs.append(rel)
        else:
            shutil.copy2(p, q)
    bad = [str(r) for r in dbs if _counts(src / r) != _counts(tmp / r)]
    if bad:
        log("Record counts differ (is a memory server still running? quit Claude and retry): " + ", ".join(bad))
        shutil.rmtree(tmp, ignore_errors=True)
        return 2
    tmp.rename(dst)
    log(f"Copied {src} -> {dst}: {len(dbs)} database(s), record counts match. {src} is kept (delete it by hand later).")
    log("Configs that name the old folder explicitly (COTRAIL_HOME / CTXGRAPH_HOME, git hooks of team memory) still "
        "point there: run `cotrail setup` (and `cotrail team join <url>` again in a team project).")
    return 0
