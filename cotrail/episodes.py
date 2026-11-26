"""Episodes of a store outside team memory: the store folder and its config, episode lines (id, hash, role, text,
ts, session, source, author, flags) read from a store, and external turns added by hand (`cotrail add-episode`).

Team memory (cotrail/sync.py, experimental) moves these lines through a git repository; everything here
works without it.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import uuid
from pathlib import Path


def home_dir(home: str | Path | None = None) -> Path:
    from cotrail.legacy import default_home

    return Path(home or default_home())


def device_id(home: str | Path | None = None) -> str:
    """Stable per machine: generated once, kept in the cotrail home."""
    p = home_dir(home) / "device_id"
    if p.exists() and p.read_text("utf-8").strip():
        return p.read_text("utf-8").strip()
    p.parent.mkdir(parents=True, exist_ok=True)
    did = "dev-" + uuid.uuid4().hex[:10]
    p.write_text(did + "\n", "utf-8")
    return did


def episode_hash(role: str, session: str, ts: str, text: str) -> str:
    return hashlib.sha256(f"{role}\x1f{session}\x1f{ts}\x1f{text}".encode()).hexdigest()[:24]


def store_dir(project: str | Path, home: str | Path | None = None) -> Path:
    """The project's store folder: by git remote when the folder has one (memory.store_dir)."""
    from cotrail.memory import store_dir as sd

    return sd(project, home_dir(home))


def config_path(project, home=None) -> Path:
    return store_dir(project, home) / "sync.json"


def load_config(project, home=None) -> dict:
    p = config_path(project, home)
    try:
        return json.loads(p.read_text("utf-8")) if p.exists() else {}
    except json.JSONDecodeError:
        return {}


def save_config(project, home, cfg: dict) -> None:
    p = config_path(project, home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=1), "utf-8")


class SyncError(RuntimeError):
    pass


def local_episodes(db: Path, author: str = "") -> list[dict]:
    """Episodes of the local store as log lines (text as stored: already through the secret filter). A record with
    no author row (imported before authors existed) is this device's: `author`."""
    if not db.exists():
        return []
    con = sqlite3.connect(db)
    try:
        tabs = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "episodes" not in tabs:
            return []
        meta = "turn_meta" in tabs
        q = ("SELECT e.id, e.role, e.text, e.session_id, e.source, e.t_created, "
             + ("m.ts, m.session, m.origin " if meta else "NULL, NULL, NULL ")
             + "FROM episodes e " + ("LEFT JOIN turn_meta m ON m.episode = e.id " if meta else "")
             + "WHERE e.t_expired IS NULL ORDER BY e.seq")  # fmt: skip
        rows = con.execute(q).fetchall()
        flags = {r[0] for r in con.execute("SELECT episode FROM turn_flags WHERE after_summary=1")} \
            if "turn_flags" in tabs else set()  # fmt: skip
        asks = dict(con.execute("SELECT episode, ask FROM turn_asks")) if "turn_asks" in tabs else {}
        who = dict(con.execute("SELECT episode, author FROM turn_author")) if "turn_author" in tabs else {}
        pasted = dict(con.execute("SELECT episode, text FROM turn_pasted")) if "turn_pasted" in tabs else {}
        titles = dict(con.execute("SELECT session, title FROM session_titles")) if "session_titles" in tabs else {}
    finally:
        con.close()
    out = []
    for eid, role, text, sess, src, t_created, ts, session, origin in rows:
        ts = ts or dt.datetime.fromtimestamp(t_created or 0, dt.UTC).isoformat(timespec="seconds")
        session = session or sess
        rec = {"id": eid, "hash": episode_hash(role, session, ts, text), "role": role, "text": text, "ts": ts,
               "session": session, "source": origin or src or "transcript"}  # fmt: skip
        if eid in flags:
            rec["after_summary"] = True
        if asks.get(eid):
            rec["ask"] = asks[eid]
        if who.get(eid, author):
            rec["author"] = who.get(eid, author)
        if pasted.get(eid):
            rec["pasted"] = pasted[eid]
        if titles.get(session):
            rec["title"] = titles[session]
        out.append(rec)
    return out


def make_episode(role: str, text: str, ts: str | None, source: str, session: str | None) -> dict:
    ts = ts or dt.datetime.now(dt.UTC).isoformat(timespec="seconds")
    session = session or f"{source}-{ts[:10]}"
    if role not in ("user", "assistant"):
        raise SyncError(f"role must be user or assistant, not {role!r}")
    from cotrail.privacy import redact

    clean = redact(text).text
    h = episode_hash(role, session, ts, clean)
    return {"id": "x" + h[:16], "hash": h, "role": role, "text": clean, "ts": ts, "session": session,
            "source": source}  # fmt: skip


def add_episodes(memory, rows: list[dict]) -> dict:
    """Into the local store through the normal import path (secret filter, statuses); the next sync logs them."""
    return memory.import_turns(rows)


def read_jsonl(path: str | Path, source: str, session: str | None = None) -> list[dict]:
    out = []
    for i, line in enumerate(Path(path).read_text("utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            raise SyncError(f"{path}:{i}: not JSON ({e})") from None
        if not r.get("text") or not r.get("role"):
            raise SyncError(f"{path}:{i}: needs role and text")
        out.append(make_episode(r["role"], r["text"], r.get("ts"), r.get("source", source),
                                r.get("session", session)))  # fmt: skip
    return out
