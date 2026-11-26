"""Local log of the memory's MCP tool calls: `~/.cotrail/<project>/calls.jsonl`, for the «Живая память» view.

One JSON line per tool call: {"t": UTC ISO time, "tool": tool name, "ids": record ids (#...) in the result, "ms":
duration}. NEVER the query text or any record text: only ids, which are already local labels of the store.
Bounded (rule fixed before the code): when calls.jsonl reaches MAX_BYTES it is renamed to calls.1.jsonl (the older
part is dropped) and a new file starts - at most ~2 x MAX_BYTES on disk. A failure to log never fails a tool call.
"""

from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

NAME, OLD = "calls.jsonl", "calls.1.jsonl"
MAX_BYTES = 1_000_000  # ~8-10 thousand calls per file
MAX_IDS = 40
# record ids as recall / expand / decisions print them: "#" + 4-8 hex characters of the episode id
ID = re.compile(r"#([0-9a-f]{4,8})\b")


def ids_of(text) -> list[str]:
    """Record ids in a tool result, in order, without repeats."""
    out: list[str] = []
    for x in ID.findall(text if isinstance(text, str) else ""):
        if x not in out:
            out.append(x)
    return out[:MAX_IDS]


def log_call(folder: Path, tool: str, result, ms: float, now: dt.datetime | None = None) -> None:
    """Append one line; any error (read-only disk, a locked file) is swallowed."""
    try:
        folder = Path(folder)
        p = folder / NAME
        if p.exists() and p.stat().st_size >= MAX_BYTES:
            p.replace(folder / OLD)
        t = (now or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        line = json.dumps({"t": t, "tool": str(tool), "ids": ids_of(result), "ms": int(round(ms))}, ensure_ascii=False)
        folder.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:  # noqa: BLE001 - logging must never fail a tool call
        pass


def _lines(p: Path) -> list[dict]:
    out = []
    try:
        raw = p.read_text("utf-8", errors="replace")
    except OSError:
        return out
    for ln in raw.splitlines():
        try:
            c = json.loads(ln)
        except ValueError:
            continue  # a line cut by a crash
        if isinstance(c, dict) and isinstance(c.get("t"), str) and isinstance(c.get("tool"), str):
            out.append({"t": c["t"], "tool": c["tool"], "ids": [str(x) for x in c.get("ids") or []][:MAX_IDS],
                        "ms": int(c.get("ms") or 0)})  # fmt: skip
    return out


def read_calls(folder: Path, limit: int = 3000) -> list[dict]:
    """The latest `limit` calls, oldest first (the rotated part, then the current file)."""
    folder = Path(folder)
    return (_lines(folder / OLD) + _lines(folder / NAME))[-limit:]


def size(folder: Path) -> int:
    """The current file's size: the offset from which a live page polls."""
    try:
        return (Path(folder) / NAME).stat().st_size
    except OSError:
        return 0


def read_from(folder: Path, offset: int) -> tuple[int, list[dict]]:
    """Calls appended after byte `offset` of the current file -> (new offset, calls). A file shorter than the offset
    was rotated: read it from the start."""
    p = Path(folder) / NAME
    try:
        size = p.stat().st_size
    except OSError:
        return 0, []
    if offset > size or offset < 0:
        offset = 0
    with p.open("rb") as f:
        f.seek(offset)
        raw = f.read()
    cut = raw.rfind(b"\n") + 1  # a half-written last line waits for the next poll
    out = []
    for ln in raw[:cut].decode("utf-8", errors="replace").splitlines():
        try:
            c = json.loads(ln)
            out.append({"t": c["t"], "tool": c["tool"], "ids": list(c.get("ids") or [])[:MAX_IDS], "ms": int(c.get("ms") or 0)})
        except (ValueError, KeyError, TypeError):
            continue
    return offset + cut, out
