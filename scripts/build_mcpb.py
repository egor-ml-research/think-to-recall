"""Build the Claude Desktop extension `dist/cotrail-<version>.mcpb` (MCPB manifest spec 0.3).

The extension holds no code: Claude Desktop runs `cotrail-mcp` (`cotrail-mcpw.exe` on Windows: a GUI launcher, no
console window) from the user's own install of the PyPI package (`uv tool install cotrail==<version>` or
`pipx install ...`; both put it in ~/.local/bin). The user picks the project folder once
at install time; it is passed as COTRAIL_PROJECT. The memory stays on the user's computer (~/.cotrail).

    python scripts/build_mcpb.py [--out dist/cotrail.mcpb] [--version 0.6.0]
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
        "name": "cotrail",
        "display_name": "cotrail",
        "version": version,
        "description": "Local decision memory: recalls what was decided, rejected or put off in this project's chats.",
        "long_description": (
            "cotrail keeps a local memory of a project's conversations: decisions, refusals, deferrals, reports of "
            "done work. Ask \"add this chat to memory\" to save the current chat; later questions find what was "
            "decided and why. Everything stays on your computer (~/.cotrail); nothing is sent anywhere.\n\n"
            "**Prerequisite:** install the package once in a terminal: `uv tool install cotrail==" + version
            + "` (or `pipx install cotrail==" + version + "`). The extension runs that install's "
            "`cotrail-mcp` (`cotrail-mcpw.exe` on Windows, no console window) from ~/.local/bin."
        ),
        "author": {"name": "egor-ml-research", "url": "https://github.com/egor-ml-research"},
        "repository": {"type": "git", "url": "https://github.com/egor-ml-research/cotrail"},
        "homepage": "https://github.com/egor-ml-research/cotrail",
        "documentation": "https://github.com/egor-ml-research/cotrail#readme",
        "support": "https://github.com/egor-ml-research/cotrail/issues",
        "icon": "icon.png",
        "license": "Apache-2.0",
        "keywords": ["memory", "decisions", "local", "project", "history"],
        "server": {
            "type": "binary",
            "entry_point": "cotrail-mcp",
            "mcp_config": {
                "command": "${HOME}/.local/bin/cotrail-mcp",
                "args": [],
                "env": {"COTRAIL_PROJECT": "${user_config.project}", "PYTHONIOENCODING": "utf-8"},
                "platform_overrides": {"win32": {"command": "${HOME}/.local/bin/cotrail-mcpw.exe"}},  # no console window
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
    p = build(Path(a.out) if a.out else ROOT / "dist" / f"cotrail-{v}.mcpb", v)
    print(p)


if __name__ == "__main__":
    main()
