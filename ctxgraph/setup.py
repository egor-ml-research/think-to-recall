"""`ctxgraph setup`: connect the memory to the project in the current directory, in one command.

1. `.mcp.json` of the project: the `ctxgraph` MCP server (this Python, absolute path; merged into an existing file).
2. `.claude/settings.local.json`: the Claude Code Stop hook that queues each finished turn (merged; an earlier
   ctxgraph hook is replaced, other hooks are kept). `settings.local.json` is per-user and not committed.
3. The encoder model (multilingual-e5-base, ~1.1 GB): downloaded once, after the user agrees; then offline.
4. On first connection: import of this project's earlier Claude Code sessions (asks first), and the decision
   chronology as the first result.
"""

from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path

YES = ("y", "yes", "д", "да")


def _ask(question: str, assume: bool | None) -> bool:
    if assume is not None:
        print(f"{question} [{'y' if assume else 'n'}]")
        return assume
    if not sys.stdin or not sys.stdin.isatty():
        print(f"{question} [n] (no terminal to ask; rerun with --yes to agree)")
        return False
    return input(f"{question} [y/N] ").strip().lower() in YES


def _q(s: str) -> str:
    """Quote a path for the hook command (Claude Code runs hooks through a POSIX-style shell, Git Bash on Windows)."""
    return shlex.quote(s) if os.name != "nt" else f'"{s}"'


def _read_json(p: Path) -> dict:
    if not p.exists() or not p.read_text("utf-8").strip():
        return {}
    data = json.loads(p.read_text("utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{p}: expected a JSON object")
    return data


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


def mcp_entry(project: Path, home: str | None) -> dict:
    env = {"PYTHONUTF8": "1", "CTXGRAPH_PROJECT": project.as_posix()}
    if home:
        env["CTXGRAPH_HOME"] = Path(home).as_posix()
    return {"type": "stdio", "command": Path(sys.executable).as_posix(), "args": ["-m", "ctxgraph.memory_mcp"], "env": env}


def hook_command(project: Path, home: str | None) -> str:
    cmd = f"{_q(Path(sys.executable).as_posix())} -m ctxgraph.cli --project {_q(project.as_posix())}"
    if home:
        cmd += f" --home {_q(Path(home).as_posix())}"
    return cmd + " hook-stop"


def write_mcp(project: Path, home: str | None) -> tuple[Path, str]:
    p = project / ".mcp.json"
    data = _read_json(p)
    servers = data.setdefault("mcpServers", {})
    new = mcp_entry(project, home)
    state = "unchanged" if servers.get("ctxgraph") == new else "updated" if "ctxgraph" in servers else "added"
    servers["ctxgraph"] = new
    _write_json(p, data)
    return p, state


def _is_ours(h: dict) -> bool:
    c = str(h.get("command", ""))
    return "hook-stop" in c and "ctxgraph" in c


def write_hook(project: Path, home: str | None) -> tuple[Path, str]:
    p = project / ".claude" / "settings.local.json"
    data = _read_json(p)
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    cmd = hook_command(project, home)
    had = any(_is_ours(h) for g in stop for h in g.get("hooks", []))
    same = any(h.get("command") == cmd for g in stop for h in g.get("hooks", []))
    for g in stop:
        g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
    stop[:] = [g for g in stop if g.get("hooks")]
    stop.append({"hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
    _write_json(p, data)
    return p, "unchanged" if same else "updated" if had else "added"


def ensure_model(assume: bool | None) -> bool:
    from ctxgraph import model as M

    if M.is_cached():
        print(f"Model: {M.REPO} is already downloaded ({M.snapshot_dir()}); the memory runs offline.")
        return True
    print(f"Model: the memory needs the sentence encoder {M.REPO} (MIT), about {M.SIZE_MB / 1000:.1f} GB, "
          "downloaded once from huggingface.co into the Hugging Face cache. After that nothing goes to the network.")  # fmt: skip
    if not _ask("Download it now?", assume):
        print("  Skipped. The memory will not work until the model is downloaded: rerun `ctxgraph setup`.")
        return False
    p = M.download()
    print(f"  Downloaded to {p}")
    return True


def check_spacy() -> None:
    from ctxgraph.v2 import english

    if not english.available():
        print("Note: the spaCy model en_core_web_sm is not installed; English sentences use the rules fallback "
              "(install with the `memory` extra to get it).")  # fmt: skip


def first_import(project: Path, assume: bool | None, limit: int = 15) -> None:
    from ctxgraph.memory import ProjectMemory, claude_project_dir, format_decisions

    src = claude_project_dir(project)
    files = sorted(src.glob("*.jsonl")) if src.is_dir() else []
    m = ProjectMemory(project)
    n = m.s.q("SELECT COUNT(*) FROM turn_meta")[0][0]
    if n:
        print(f"Memory: {n} turns already stored ({m.db_path}); nothing to import on first connection "
              "(`ctxgraph import` adds new sessions).")  # fmt: skip
    elif not files:
        print("Memory: empty; no earlier Claude Code sessions of this project found. New turns are recorded by the hook.")
        return
    else:
        print(f"History: {len(files)} earlier Claude Code session file(s) of this project in {src}.\n"
              "  Only your prompts and the assistant's visible replies are stored (no tool calls, no thinking); "
              "secrets are filtered before storage. Everything stays on this machine.")  # fmt: skip
        if not _ask("Import them into the project memory?", assume):
            print("  Skipped. Import later with `ctxgraph import`.")
            return
        r = m.import_claude_code(src, progress=lambda i, k: print(f"\r  {i}/{k}", end="", flush=True))
        print(f"\n  Imported {r['new']} turns of {r['turns']} found.")
    rows = m.decisions(limit)
    print(f"\nDecision chronology (newest first, {len(rows)} shown; `ctxgraph decisions --limit N` for more):\n")
    print(format_decisions(rows))


def run(project: Path, home: str | None, assume: bool | None, model: bool = True, history: bool = True) -> None:
    project = project.resolve()
    print(f"Project: {project}\n")
    p, st = write_mcp(project, home)
    print(f"MCP server: {st} in {p}")
    p, st = write_hook(project, home)
    print(f"Stop hook: {st} in {p}")
    print("  Restart Claude Code in this folder and approve the `ctxgraph` server when it asks.\n")
    if not model:
        return
    ok = ensure_model(assume)
    check_spacy()
    if ok and history:
        print()
        first_import(project, assume)
    print("\nGraph view: `ctxgraph view` (add `--3d` for the 3D view).")
