"""Setup through the assistant (the MCP setup tools): list memories, connect a folder, join a team, find and import
chats. "Show before write": every call that changes something is a dry run unless `confirm=True`; the dry run says
exactly what would be written, and the assistant asks the user before calling again with confirm=True.

Nothing here leaves the machine except `join_team(confirm=True)`, which pushes to the user's private memory repo
after the repo check (lines the check flags are held back locally and listed).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from cotrail import memory as M

ASK = "Nothing written yet. Show this to the user; call again with confirm=true only after the user says yes."


def _home(home) -> Path:
    return Path(home or M.HOME)


def _identity(store: Path) -> str:
    import sqlite3

    try:
        con = sqlite3.connect(str(store / "graph.sqlite"))
        try:
            row = con.execute("SELECT value FROM memory_meta WHERE key='identity'").fetchone()
        finally:
            con.close()
        return row[0] if row else ""
    except sqlite3.Error:
        return ""


def list_memories(home=None) -> list[dict]:
    """Every memory with a short friendly name (the repo name of its git remote, else its folder's name)."""
    out = []
    for k in M.known_projects(_home(home)):
        d = Path(k["store"]).parent
        try:
            cfg = json.loads((d / "sync.json").read_text("utf-8"))
        except (OSError, ValueError):
            cfg = {}
        ident = _identity(d)
        name = (ident.rsplit("/", 1)[-1] if ident else Path(k["path"]).name or k["slug"]).lower()
        out.append({"name": name, "memory": k["slug"], "folder": k["path"], "records": k["records"], "last": k["last"],
                    "kind": "team" if cfg.get("remote") else "local",
                    "team": re.sub(r"//[^/@]+@", "//", cfg.get("remote", "")), "author": cfg.get("author", "")})  # fmt: skip
    return sorted(out, key=lambda r: r["last"], reverse=True)


def format_memories(rows: list[dict]) -> str:
    if not rows:
        return "No memories yet on this computer."
    dup = {r["name"] for r in rows if sum(x["name"] == r["name"] for x in rows) > 1}
    return "\n".join(f"- {r['memory'] if r['name'] in dup else r['name']} ({r['kind']}, {r['records']} records, "
                     f"last {r['last'] or '-'}) · {r['folder']}" for r in rows)  # fmt: skip


def workspace_problem(folder: str | Path, home=None) -> str:
    """The server's folder is a workspace (home, drive root, or a folder holding several projects) with no memory of
    its own: no default memory - the chat must pick one. "" when the folder is a project (or has its own memory)."""
    home = _home(home)
    folder = Path(folder).resolve()
    if (M.store_dir(folder, home) / "graph.sqlite").exists() or M.git_remote(folder):
        return ""
    inside = [r for r in list_memories(home) if r["folder"] and Path(r["folder"]).is_absolute()
              and folder in Path(r["folder"]).resolve().parents]  # fmt: skip
    kids = any((c / ".git").exists() for c in folder.iterdir() if c.is_dir()) if folder.is_dir() else False
    if not (folder == Path.home().resolve() or folder.parent == folder or inside or kids):
        return ""
    return ("No memory chosen for this chat (the server's folder " + str(folder) + " holds several projects). "
            "Memories:\n" + format_memories(list_memories(home)) + "\nAsk the user once which one for this chat (or "
            "take it from their words), then pass memory=<name> on every call.")  # fmt: skip


class UnknownMemory(ValueError):
    pass


def resolve_memory(memory: str, home=None) -> tuple[Path, Path]:
    """(store folder, project folder) of an EXISTING memory: a name from list_memories, a project folder that has a
    memory, or a git remote URL. Never creates anything; unknown -> UnknownMemory listing the memories."""
    home = _home(home)
    v = (memory or "").strip()
    cand: Path | None = None
    if v and (home / v / "graph.sqlite").exists():
        cand = home / v
    elif v and ("://" in v or re.match(r"^[\w.-]+@[\w.-]+:", v)):
        rid = M.remote_slug(v)
        al = M._aliases(home).get(rid)
        for d in (home / rid, home / al if al else None):
            if d is not None and (d / "graph.sqlite").exists():
                cand = d
                break
    elif v and Path(v).expanduser().is_dir():
        d = M.store_dir(Path(v).expanduser(), home)
        cand = d if (d / "graph.sqlite").exists() else None
    if cand is None and v:
        hits = [r for r in list_memories(home) if r["name"] == v.lower()]
        if len(hits) > 1:
            raise UnknownMemory(f"{memory!r} is ambiguous: " + ", ".join(f"{r['memory']} ({r['folder']})" for r in hits)
                                + ". Ask the user which one and pass its id as memory=.")  # fmt: skip
        if hits:
            cand = home / hits[0]["memory"]
    if cand is None:
        names = ", ".join(r["name"] for r in list_memories(home)) or "none yet"
        raise UnknownMemory(f"No memory {memory!r}. Available memories: {names}. Call list_memories and pass one "
                            "of these names as memory=.")  # fmt: skip
    rows = [k for k in M.known_projects(home) if Path(k["store"]).parent == cand]
    folder = Path(rows[0]["path"]) if rows and rows[0]["exact"] else cand
    return cand, folder


def _target(memory: str | None, home: Path) -> Path | None:
    """An existing memory by its name (store folder) or by a folder that has one; None = the folder's own."""
    if not memory or memory.lower() in ("auto", "new", "own"):
        return None
    if (home / memory / "graph.sqlite").exists():
        return home / memory
    p = Path(memory).expanduser()
    if p.is_dir() and (M.store_dir(p, home) / "graph.sqlite").exists():
        return M.store_dir(p, home)
    raise ValueError(f"no memory named {memory!r}: call list_memories")


def _sessions(folder: Path) -> int:
    d = M.claude_project_dir(folder)
    return len(list(d.glob("*.jsonl"))) if d.is_dir() else 0


def connect_folder(path: str, memory: str | None = None, home=None, confirm: bool = False) -> str:
    """Point a folder at a memory (its own, or an existing one) and import its Claude Code chats."""
    home = _home(home)
    folder = Path(path).expanduser().resolve()
    if not folder.is_dir():
        return f"No such folder: {folder}"
    own = M.store_dir(folder, home)
    target = _target(memory, home) or own
    remote = M.git_remote(folder)
    key = M.remote_slug(remote) if remote else M.project_slug(folder)
    n = _sessions(folder)
    if target != own and (own / "graph.sqlite").exists():
        return (f"{folder} already has its own memory ({own.name}); joining two memories is not supported. "
                "Use its own memory, or pick another folder.")
    plan = [f"Folder: {folder}" + (f" (git remote {M.normalize_remote(remote)}: every clone shares it)" if remote else ""),
            f"Memory: {target.name}" + (" (exists)" if (target / "graph.sqlite").exists() else " (new)"),
            f"Import: {n} Claude Code chat file(s) of this folder (read locally, nothing leaves the computer)"]  # fmt: skip
    if not confirm:
        return "\n".join(["Would connect:", *plan, ASK])
    if target != own:
        al = M._aliases(home) | {key: target.name}
        home.mkdir(parents=True, exist_ok=True)
        M._aliases_path(home).write_text(json.dumps(al, indent=1), "utf-8")
    m = M.ProjectMemory(folder, home=home)
    r = m.import_claude_code() if n else {"new": 0}
    return f"Connected {folder} to memory {m.dir.name}; imported {r['new']} new turn(s)."


def join_team(sync_repo: str, project: str | None = None, name: str | None = None, home=None, confirm: bool = False,
              check=None) -> str:  # fmt: skip
    from cotrail import repo_check as RC
    from cotrail import sync as S
    from cotrail import team as T

    home = _home(home)
    project = Path(project or os.environ.get("COTRAIL_PROJECT") or Path.cwd()).resolve()
    bad = T.folder_problem(project, home)
    if bad:  # the assistant passes memory= (a project with a git remote) instead
        return "Not joined: " + bad.replace("`--force` joins this folder anyway.", "Pass memory=<a project memory>.")
    vis = (check or T.visibility)(sync_repo)
    if vis == "PUBLIC":
        return f"Refused: {sync_repo} is PUBLIC. The memory repo must be private."
    who = (name or "").strip() or S.load_config(project, home).get("author") or M.default_author(project)
    db = M.store_dir(project, home) / "graph.sqlite"
    rows = [S._scrubbed(r) for r in S.local_episodes(db, who)]
    held = RC.check_rows(rows)
    plan = [T.WARNING, "", f"Repository: {sync_repo} (visibility: {vis.lower() or 'could not check - make sure it is PRIVATE'})",
            f"Project: {M.project_identity(project) or project}", f"Your name on the records: {who or '(none: give name)'}",
            f"Would push: {len(rows) - len({b['id'] for b in held})} record(s) already in this memory, plus this "
            "folder's Claude Code chats (imported first)",
            f"Held back by the secret check (stay local, never pushed): {len({b['id'] for b in held})}"
            + (": " + ", ".join(f"{b['id']} {b['field']}:{b['kind']}" for b in held[:10]) if held else "")]  # fmt: skip
    if not confirm:
        return "\n".join(["Would join the team memory:", *plan, ASK])
    if not who:
        return "No name: ask the user for the name to put on the records, then call again with name=..."
    logs: list[str] = []
    try:
        r = T.join(project, sync_repo, home, name=who, check=lambda _u: vis, log=logs.append, force=True)
    except (T.TeamError, S.SyncError) as e:
        return f"Not joined: {e}"
    tail = f" Held back by the secret check (not pushed): {r['held']}." if r.get("held") else ""
    joined = next((x for x in logs if x.startswith("Joined as")), "Joined.")
    return joined + tail + " " + logs[-1]


def _first_prompt(f: Path) -> tuple[str, str, str]:
    """cwd, first user text, first timestamp of a Claude Code transcript (first ~80 lines)."""
    from cotrail import cc_transcripts as CC

    cwd = text = ts = ""
    try:
        with f.open(encoding="utf-8", errors="replace") as fh:
            for _, ln in zip(range(80), fh):
                try:
                    r = json.loads(ln)
                except ValueError:
                    continue
                cwd = cwd or r.get("cwd") or ""
                ts = ts or r.get("timestamp") or ""
                if not text and r.get("type") == "user" and not r.get("isMeta"):
                    t = CC.clean(CC._text((r.get("message") or {}).get("content")))
                    if t and not t.startswith("<"):
                        text = t
                if cwd and text:
                    break
    except OSError:
        pass
    return cwd, text, ts


def find_chats(query: str = "", export: str | None = None, limit: int = 30) -> list[dict]:
    """Claude Code chats on this computer (folder or first prompt contains `query`), and with `export` the claude.ai
    conversations whose title contains it. Read only."""
    q = (query or "").lower()
    out = []
    root = Path.home() / ".claude" / "projects"
    for f in sorted(root.glob("*/*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if root.is_dir() else []:
        cwd, text, ts = _first_prompt(f)
        if q and q not in cwd.lower() and q not in text.lower():
            continue
        out.append({"id": "cc:" + f.stem[:8], "date": ts[:10], "where": cwd or f.parent.name, "title": text[:90]})
        if len(out) >= limit:
            break
    if export:
        from cotrail import claude_ai_export as CA

        conv, projects = CA.load(export)
        rows = [r for r in CA.summary(conv, projects) if not q or q in r["title"].lower() or q in r["project"].lower()]
        out += [{"id": "ai:" + r["id"][:8], "date": r["date"], "where": "claude.ai" + (f" [{r['project']}]" if r["project"]
                 else ""), "title": r["title"][:90]} for r in sorted(rows, key=lambda r: r["date"], reverse=True)[:limit]]  # fmt: skip
    return out


def format_chats(rows: list[dict]) -> str:
    if not rows:
        return "No chats found."
    return "\n".join(f"- {r['id']} · {r['date']} · {r['where']} · {r['title']}" for r in rows)


def import_chats(ids: list[str], memory: str | None = None, export: str | None = None, project: str | None = None,
                 home=None, confirm: bool = False) -> str:  # fmt: skip
    home = _home(home)
    cc = [i[3:] for i in ids if i.startswith("cc:")]
    ai = [i[3:] for i in ids if i.startswith("ai:")]
    if ai and not export:
        return "claude.ai chats need the export: give export=<path to the .zip>."
    root = Path.home() / ".claude" / "projects"
    files = [f for f in root.glob("*/*.jsonl") if any(f.stem.startswith(c) for c in cc)] if cc else []
    tgt = _target(memory, home)
    folder = Path(project or os.environ.get("COTRAIL_PROJECT") or Path.cwd()).resolve()
    if tgt is not None:
        rows = [k for k in M.known_projects(home) if Path(k["store"]).parent == tgt]
        folder = Path(rows[0]["path"]) if rows and Path(rows[0]["path"]).is_dir() else folder
    dest = tgt or M.store_dir(folder, home)
    plan = [f"Into memory: {dest.name}", f"Claude Code chats: {len(files)} of {len(cc)} asked",
            f"claude.ai chats: {len(ai)}" + (f" from {export}" if ai else "")]  # fmt: skip
    if not confirm:
        return "\n".join(["Would import:", *plan, ASK])
    if tgt is not None and M.store_dir(folder, home) != tgt:
        return f"Memory {tgt.name}: its folder is not on this computer; connect a folder to it first."
    m = M.ProjectMemory(folder, home=home)
    n = m.import_claude_code(files=files)["new"] if files else 0
    k = m.import_claude_ai(export, ids=ai)["new"] if ai else 0
    return f"Imported into {m.dir.name}: {n} turn(s) from Claude Code, {k} from claude.ai (each with your name)."
