"""Team memory: several people share one project memory through a PRIVATE git repo (the episode logs of `sync`).

- Identity: the project is its git remote (memory.store_dir), so every member's clone, branch and folder lands in the
  same store; search is shared across members.
- Author: every record carries a name (git user.name, or `--name`), carried through the log; recall shows
  "decided by <name>" in a team store.
- Topics stay content-based (concept communities over the whole store): a backend decision and a frontend one fall into
  different topics because they share no concepts, while the API contract between them - the thing both sides ask
  about - stays one topic. Splitting topics per author would cut exactly that shared thread apart.

`join`: privacy warning -> visibility check (gh) -> name -> this project's Claude Code sessions imported -> sync (hook-driven
afterwards: the Stop hook starts it in the background, as for one person's devices).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from cotrail import sync as S

WARNING = """PRIVACY: the memory repository will hold the TEXT of your conversations in this project (your prompts and the
assistant's replies, after a secret filter) and your name (git user.name). Every member of the repository can read
it. The repository MUST be private; never make it public or fork it to a public place."""


class TeamError(RuntimeError):
    pass


def github_repo(remote: str) -> str:
    """`owner/repo` of a GitHub remote, else ""."""
    from cotrail.memory import normalize_remote

    n = normalize_remote(remote)
    parts = n.split("/")
    return "/".join(parts[1:3]) if parts[0] == "github.com" and len(parts) >= 3 else ""


def visibility(remote: str) -> str:
    """PRIVATE / PUBLIC / INTERNAL from `gh repo view`; "local" for a path; "" when it cannot be checked."""
    if not github_repo(remote):
        return "local" if Path(remote).exists() or remote.startswith("file:") else ""
    if not shutil.which("gh"):
        return ""
    try:
        r = subprocess.run(["gh", "repo", "view", github_repo(remote), "--json", "visibility", "-q", ".visibility"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30)  # fmt: skip
    except (OSError, subprocess.SubprocessError):
        return ""
    return r.stdout.strip().upper() if r.returncode == 0 else ""


def session_dirs(mem, home) -> list[Path]:
    """Claude Code transcript folders of this project: its own folder plus any other folder (a subfolder, another
    clone or worktree) whose transcripts' cwd resolves to the same store."""
    from cotrail.memory import _path_from_transcripts, claude_project_dir, store_dir

    own = claude_project_dir(mem.project)
    out = [own] if own.is_dir() else []
    root = own.parent
    for d in sorted(root.iterdir()) if root.is_dir() else []:
        if d == own or not d.is_dir():
            continue
        cwd = _path_from_transcripts(d.name)
        if cwd and Path(cwd).is_dir() and store_dir(cwd, home) == mem.dir:
            out.append(d)
    return out


def _ver(v: str):
    try:
        from packaging.version import Version

        return Version(v)
    except Exception:  # noqa: BLE001 - no packaging: release numbers, then a .devN build before its release
        m = re.match(r"\s*(\d+(?:\.\d+)*)(?:\.?dev(\d+))?", v)
        if not m:
            raise TypeError(v) from None
        nums = [int(x) for x in m.group(1).split(".")] + [0] * 3
        return (*nums[:4], *((-1, int(m.group(2))) if m.group(2) else (0, 0)))


def newer_build(repo: Path) -> str:
    """«A newer build is in tools/» when the memory repo holds a wheel newer than the installed cotrail, else ""."""
    from importlib.metadata import PackageNotFoundError, version

    wheels = sorted((repo / "tools").glob("cotrail-*.whl")) if (repo / "tools").is_dir() else []
    if not wheels:
        return ""
    try:
        have = version("cotrail")
    except PackageNotFoundError:
        return ""
    best = max(wheels, key=lambda p: _ver(p.name.split("-")[1]))
    new = best.name.split("-")[1]
    try:
        if _ver(new) <= _ver(have):
            return ""
    except TypeError:
        return ""
    return (f"A newer build is in the memory repo: tools/{best.name} (installed {have}). Quit Claude Desktop / Claude "
            f"Code, then: uv tool install --force \"{best}\"")


def folder_problem(project: Path, home=None) -> str:
    """Why this folder is not a project to join with (the home folder, a drive root, no git remote), or ""."""
    from cotrail.memory import git_remote, known_projects

    project = Path(project).resolve()
    why = ("your home folder" if project == Path.home().resolve() else "a drive root" if project.parent == project
           else "a folder without a git remote" if not git_remote(project) else "")  # fmt: skip
    if not why:
        return ""
    clones = [k["path"] for k in known_projects(S.home_dir(home)) if k["slug"].startswith("git-") and k["exact"]]
    eg = clones[0] if clones else "<path-to-your-project-clone>"
    return (f"{project} is {why}, not a project clone. Run it inside your project's clone, e.g. `cd {eg}`, then "
            "`cotrail team join <repo>` again" + (f". Known project clones: {', '.join(clones[:5])}" if clones else "")
            + ". (`--force` joins this folder anyway.)")  # fmt: skip


def leave(project: str | Path, home=None) -> dict:
    """Turn team sync off for this project: the remote is forgotten, the local memory and the clone stay; what was
    already pushed stays in the team repository."""
    project = Path(project).resolve()
    cfg = S.load_config(project, home)
    if not cfg.get("remote"):
        return {"left": False, "remote": ""}
    S.save_config(project, home, {k: v for k, v in cfg.items() if k not in ("remote", "team", "last_sync")}
                  | {"left": cfg["remote"]})  # fmt: skip
    from cotrail import autosync as AS

    AS.remove_hooks(S._clone_root(project))
    return {"left": True, "remote": re.sub(r"//[^/@]+@", "//", cfg["remote"]), "store": str(S.store_dir(project, home))}


def join(project: str | Path, remote: str, home=None, *, name: str | None = None, import_history: bool = True,
         check=visibility, log=print, force: bool = False, graphify: bool | None = None, hooks: bool = True) -> dict:  # fmt: skip
    from cotrail.memory import ProjectMemory, default_author, project_identity

    project = Path(project).resolve()
    bad = "" if force else folder_problem(project, home)
    if bad:
        raise TeamError(bad)
    log(WARNING)
    vis = check(remote)
    if vis == "PUBLIC":
        raise TeamError(f"{remote} is PUBLIC: refusing to put conversations there. Make it private and run again.")
    if vis in ("PRIVATE", "INTERNAL", "local"):
        log(f"Repository visibility: {vis.lower()}.")
    else:
        log("Could not check the repository's visibility (no `gh`, or no access): make sure it is PRIVATE.")
    who = (name or "").strip() or default_author(project)
    if not who:
        raise TeamError("no name: set `git config user.name` or pass --name")
    if "@" in who:
        raise TeamError("the name must not be an e-mail (it goes into the shared repository)")
    home = S.home_dir(home)
    if graphify is None:  # consent to install Graphify and rebuild the code graph after commits
        import sys as _sys

        if _sys.stdin is not None and _sys.stdin.isatty():
            graphify = input("Share your code graph (Graphify, installed into cotrail's environment when first "
                             "needed; names and relative paths only, no source code)? [y/N] ").strip().lower() in ("y", "yes", "д", "да")
        else:
            graphify = bool(S.load_config(project, home).get("graphify"))
    S.save_config(project, home, S.load_config(project, home) | {"remote": remote, "author": who, "team": True,
                                                                 "graphify": bool(graphify)})  # fmt: skip
    mem = ProjectMemory(project, home=home)
    mem._author = who
    rs = [mem.import_claude_code(d) for d in session_dirs(mem, home)] if import_history else []
    imported, found = sum(r["new"] for r in rs), sum(r["turns"] for r in rs)
    hist = (f"imported {imported} turn(s) of this project's Claude Code sessions" if imported or not found
            else f"this project's Claude Code sessions: already imported {found} turn(s) earlier; 0 new")  # fmt: skip
    res = S.sync(project, remote, home, memory=mem, log=lambda m: None)
    ident = project_identity(project) or "(no git remote: this folder's path)"
    log(f"Joined as {who}: project {ident}; {hist}; "
        f"{res['imported']} record(s) from the other members, {res['pushed']} pushed.")
    if res.get("held"):
        log(f"Held back by the secret check (stay local, not pushed): {res['held']} record(s); see `cotrail team check`.")
    if hooks:
        from cotrail import autosync as AS

        clone = S._clone_root(project)
        done = AS.install_hooks(clone, home) if (clone / ".git").exists() else []
        if done:
            log(f"git hooks ({', '.join(done)}): the code graph is " + ("rebuilt and shared after commits, merges and "
                "checkouts" if graphify else "shared when graphify-out/graph.json exists (no rebuild: --graphify no)") + ".")
    nb = newer_build(S.repo_dir(project, home))
    if nb:
        log(nb)
    log("From now on the Stop hook syncs in the background after each reply (`cotrail sync` by hand any time).")
    return res | {"author": who, "history": imported, "identity": ident}


def remote_logs(repo: Path) -> dict[str, list[dict]]:
    """The episode logs as the remote has them (origin/main after a fetch), without touching the working tree."""
    r = S._git(repo, "ls-tree", "--name-only", f"origin/{S.BRANCH}", "episodes/", check=False)
    out: dict[str, list[dict]] = {}
    for name in r.stdout.split() if r.returncode == 0 else []:
        if not name.endswith(".jsonl"):
            continue
        blob = S._git(repo, "show", f"origin/{S.BRANCH}:{name}", check=False).stdout
        rows = []
        for line in blob.splitlines():
            try:
                x = json.loads(line)
            except ValueError:
                continue
            if isinstance(x, dict) and x.get("id"):
                rows.append(x)
        out[Path(name).stem] = rows
    return out


def _ago(ts: str) -> str:
    import datetime as dt

    try:
        d = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return ""
    m = int(d.total_seconds() // 60)
    return f"{m} min ago" if m < 120 else f"{m // 60} h ago" if m < 48 * 60 else f"{m // 1440} days ago"


def _per_member(logs: dict[str, list[dict]]) -> dict[str, int]:
    per: dict[str, int] = {}
    for rows in logs.values():
        for r in rows:
            k = r.get("author") or "?"
            per[k] = per.get(k, 0) + 1
    return dict(sorted(per.items(), key=lambda kv: -kv[1]))


def status(project: str | Path, home=None, fetch: bool = True) -> dict:
    """Members, last sync, records per member: the local clone, and - after a quick fetch (with the network retries;
    offline is reported, not an error) - what the remote has that this device has not synced yet."""
    project = Path(project).resolve()
    cfg = S.load_config(project, home)
    repo = S.repo_dir(project, home)
    have = (repo / ".git").exists()
    logs = S.read_logs(repo) if have else {}
    st = {"remote": cfg.get("remote", ""), "author": cfg.get("author", ""), "last_sync": cfg.get("last_sync", ""),
          "devices": len(logs), "members": _per_member(logs), "remote_checked": False, "offline": "",
          "remote_devices": 0, "remote_members": {}, "remote_new": 0}  # fmt: skip
    if have and fetch and st["remote"]:
        try:
            S._git(repo, "fetch", "-q", "origin", S.BRANCH)
            rl = remote_logs(repo)
            from cotrail import autosync as AS

            st["statuses"] = AS.read_statuses(repo, f"origin/{S.BRANCH}")
            ids = {r["id"] for rows in logs.values() for r in rows}
            st.update(remote_checked=True, remote_devices=len(rl), remote_members=_per_member(rl),
                      remote_new=sum(1 for rows in rl.values() for r in rows if r["id"] not in ids))  # fmt: skip
        except S.SyncError as e:
            st["offline"] = str(e)[:200]
    st["newer"] = newer_build(repo) if have else ""
    return st


def format_status(st: dict) -> str:
    if not st["remote"]:
        return "Not in a team: `cotrail team join <private-git-url>`."
    ago = _ago(st["last_sync"]) if st["last_sync"] else ""
    lines = [f"Team memory: {re.sub(r'//[^/@]+@', '//', st['remote'])}", f"  you: {st['author'] or '?'}",
             f"  last sync: {st['last_sync'] or 'never'}" + (f" ({ago})" if ago else "") + f"; devices: {st['devices']}",
             "  records per member (synced here):"]  # fmt: skip
    lines += [f"    {k}: {v}" for k, v in st["members"].items()] or ["    (none yet)"]
    if st.get("offline"):
        lines.append("  remote: not reachable now (offline?) - showing this device's copy only")
    elif st.get("remote_checked"):
        if st["remote_new"]:
            lines.append(f"  remote ({st['remote_devices']} devices): {st['remote_new']} new record(s) not synced here - "
                         "run `cotrail sync`")  # fmt: skip
            lines += [f"    {k}: {v}" for k, v in st["remote_members"].items()]
        else:
            lines.append(f"  remote: up to date ({st['remote_devices']} devices)")
    if st.get("statuses"):
        lines.append("  members' devices (from the repo):")
        for x in st["statuses"]:
            lines.append(f"    {x.get('member') or '?'} · {x.get('device')} · cotrail {x.get('version') or '?'} · pull "
                         f"{_ago(x.get('last_pull', '')) or '-'} · push {_ago(x.get('last_push', '')) or '-'} · graph "
                         f"{_ago(x.get('last_graph_push', '')) or '-'}" + (f" · {x['fails']} failed syncs" if x.get("fails") else ""))
    if st.get("newer"):
        lines.append("  " + st["newer"])
    return "\n".join(lines)


def status_json(st: dict) -> str:
    return json.dumps(st, ensure_ascii=False, indent=1)
