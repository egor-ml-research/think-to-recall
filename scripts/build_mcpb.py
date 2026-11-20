"""Build the Claude Desktop extension `dist/ctxgraph-<version>.mcpb` (MCPB manifest spec 0.3).

The extension holds no code: Claude Desktop runs `ctxgraph-mcp` from the user's own install
(`uv tool install ...` or `pipx install ...`, both put it in ~/.local/bin). The user picks the project folder once
at install time; it is passed as CTXGRAPH_PROJECT. The memory stays on the user's computer (~/.ctxgraph).

    python scripts/build_mcpb.py [--out dist/ctxgraph.mcpb] [--version 0.6.0]
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TOOLS = [
    ("recall", "Search this project's earlier conversations: decisions, constraints, rejected options."),
    ("expand", "Show one remembered record in full, with how its decision changed over time."),
    ("decisions", "The user's decisions in this project, newest first, with what was done about them."),
    ("later", "Open items the user put off for later."),
    ("overview", "A short map of the project: modules, topics, latest decisions."),
    ("rules", "The project's pinned permanent rules."),
    ("pin_rule", "Pin a permanent project rule when the user asks."),
    ("unpin_rule", "Remove a pinned rule when the user asks."),
    ("remember", "Save one statement explicitly when the user asks."),
    ("save_chat", "Save the current chat (its turns, verbatim) into the project memory; repeat-safe."),
    ("import_claude_ai", "Import chosen chats from a claude.ai data export (local file)."),
    ("import_history", "Import this project's earlier Claude Code sessions."),
    ("memory_status", "How much is in this project's memory."),
    ("forget", "Hide one remembered turn when the user asks."),
    ("show_graph", "Build a local HTML view of the project's conversation graph."),
]


def manifest(version: str) -> dict:
    return {
        "manifest_version": "0.3",
        "name": "ctxgraph",
        "display_name": "ctxgraph — project decision memory",
        "version": version,
        "description": "Local decision memory for your project: save chats, recall what was decided and why.",
        "long_description": (
            "ctxgraph keeps a local memory of a project's conversations: decisions, refusals, deferrals, reports of "
            "done work. Ask \"add this chat to memory\" to save the current chat; later questions find what was "
            "decided and why. Everything stays on your computer (~/.ctxgraph); nothing is sent anywhere.\n\n"
            "**Prerequisite:** install ctxgraph once in a terminal: "
            "`uv tool install git+https://github.com/egor-ml-research/think-to-recall@v" + version + "` "
            "(or the same with `pipx install`). The extension runs that install's `ctxgraph-mcp`."
        ),
        "author": {"name": "egor-ml-research", "url": "https://github.com/egor-ml-research"},
        "repository": {"type": "git", "url": "https://github.com/egor-ml-research/think-to-recall"},
        "homepage": "https://github.com/egor-ml-research/think-to-recall",
        "documentation": "https://github.com/egor-ml-research/think-to-recall#readme",
        "support": "https://github.com/egor-ml-research/think-to-recall/issues",
        "icon": "icon.png",
        "license": "MIT",
        "keywords": ["memory", "decisions", "local", "project", "history"],
        "server": {
            "type": "binary",
            "entry_point": "ctxgraph-mcp",
            "mcp_config": {
                "command": "${HOME}/.local/bin/ctxgraph-mcp",
                "args": [],
                "env": {"CTXGRAPH_PROJECT": "${user_config.project}", "PYTHONIOENCODING": "utf-8"},
                "platform_overrides": {"win32": {"command": "${HOME}/.local/bin/ctxgraph-mcp.exe"}},
            },
        },
        "tools": [{"name": n, "description": d} for n, d in TOOLS],
        "user_config": {
            "project": {
                "type": "directory",
                "title": "Project folder",
                "description": "The folder of the project whose memory this is (one memory per project folder).",
                "required": True,
            }
        },
        "compatibility": {"platforms": ["win32", "darwin", "linux"]},
    }


def version_of(root: Path) -> str:
    m = re.search(r'^version\s*=\s*"([^"]+)"', (root / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else "0.0.0"


def build(out: Path, version: str) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest(version), ensure_ascii=False, indent=2))
        z.write(ROOT / "packaging" / "mcpb" / "icon.png", "icon.png")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    v = a.version or version_of(ROOT)
    p = build(Path(a.out) if a.out else ROOT / "dist" / f"ctxgraph-{v}.mcpb", v)
    print(p)


if __name__ == "__main__":
    main()
