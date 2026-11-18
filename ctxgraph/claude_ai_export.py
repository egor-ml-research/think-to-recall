"""Reader for a claude.ai data export (Settings -> Privacy -> Export data): a .zip with `conversations.json`
(and `projects.json`, `users.json`). ARCHITECTURE_V2.md §3.15: import = replaying turns in order with their original
times through the normal append path; the privacy scrub runs before storage, as for any turn.

Only what people wrote is kept: the user's messages and the assistant's visible text. Thinking, tool calls and tool
results, attachments' extracted text and uploaded files are skipped (counted in the report, without values).

The export holds every chat of the account, most of them unrelated to a project: `select()` filters conversations by
a regex over the title and the first messages, by claude.ai project name, by date, or by explicit ids; `--list` in the
CLI shows titles first so the user chooses. Everything stays local.
"""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from pathlib import Path

from ctxgraph.cc_transcripts import SERVICE, clean, is_short


def load(path: str | Path) -> tuple[list[dict], dict[str, str]]:
    """(conversations, project uuid -> name) from the export .zip, its unpacked folder, or conversations.json."""
    p = Path(path)
    if p.is_dir():
        conv = json.loads((p / "conversations.json").read_text("utf-8"))
        proj = json.loads((p / "projects.json").read_text("utf-8")) if (p / "projects.json").exists() else []
    elif zipfile.is_zipfile(p):
        with zipfile.ZipFile(p) as z:
            names = {Path(n).name: n for n in z.namelist()}
            conv = json.loads(z.read(names["conversations.json"]).decode("utf-8"))
            proj = json.loads(z.read(names["projects.json"]).decode("utf-8")) if "projects.json" in names else []
    else:
        conv, proj = json.loads(p.read_text("utf-8")), []
    return conv, {x.get("uuid", ""): x.get("name", "") for x in proj if isinstance(x, dict)}


def _project_of(c: dict) -> str:
    pr = c.get("project")
    return c.get("project_uuid") or (pr.get("uuid", "") if isinstance(pr, dict) else "") or ""


def _text(msg: dict, skipped: dict) -> str:
    """Visible text of a message. New exports: `content` blocks; older ones: `text` only."""
    blocks = msg.get("content")
    if isinstance(blocks, list) and blocks:
        parts = []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            kind = b.get("type", "")
            if kind == "text":
                parts.append(b.get("text") or "")
            else:  # thinking, tool_use, tool_result, ...
                skipped[kind or "other"] = skipped.get(kind or "other", 0) + 1
        text = "\n".join(parts)
    else:
        text = msg.get("text") or ""
    n_att = len(msg.get("attachments") or []) + len(msg.get("files") or [])
    if n_att:
        skipped["attachments"] = skipped.get("attachments", 0) + n_att
    return text


def summary(conv: list[dict], projects: dict[str, str]) -> list[dict]:
    """One row per conversation for choosing what to import: id, date, messages, title, claude.ai project."""
    rows = []
    for c in conv:
        msgs = c.get("chat_messages") or []
        rows.append({"id": c.get("uuid", ""), "date": (c.get("created_at") or "")[:10], "messages": len(msgs),
                     "title": c.get("name") or "(untitled)", "project": projects.get(_project_of(c), "")})  # fmt: skip
    return sorted(rows, key=lambda r: r["date"])


def select(conv: list[dict], projects: dict[str, str], match: str | None = None, project: str | None = None,
           since: str | None = None, ids: list[str] | None = None) -> list[dict]:  # fmt: skip
    """Conversations to import. `match` - regex over the title and the first 3 messages; `project` - claude.ai
    project name (substring, case-insensitive); `since` - YYYY-MM-DD; `ids` - conversation uuids (prefixes)."""
    rx = re.compile(match, re.I) if match else None
    out = []
    for c in conv:
        if ids and not any((c.get("uuid") or "").startswith(i) for i in ids):
            continue
        if since and (c.get("created_at") or "")[:10] < since:
            continue
        if project and project.lower() not in projects.get(_project_of(c), "").lower():
            continue
        if rx:
            head = " ".join([c.get("name") or ""] + [_text(m, {}) for m in (c.get("chat_messages") or [])[:3]])
            if not rx.search(head):
                continue
        out.append(c)
    return out


def turns(conv: list[dict]) -> tuple[list[dict], dict]:
    """Turns in the importer's format (id, session, role, ts, text, source) and a report of what was skipped."""
    out, skipped = [], {}
    for c in conv:
        cid = c.get("uuid") or hashlib.sha1((c.get("name") or "").encode()).hexdigest()
        for m in c.get("chat_messages") or []:
            sender = m.get("sender")
            if sender not in ("human", "assistant"):
                skipped["other_sender"] = skipped.get("other_sender", 0) + 1
                continue
            text = clean(_text(m, skipped))
            if not (sender == "human" and is_short(text)) and (len(text) < 12 or SERVICE.match(text)):
                skipped["short_or_service"] = skipped.get("short_or_service", 0) + 1
                continue
            ts = m.get("created_at") or c.get("created_at") or ""
            mid = m.get("uuid") or hashlib.sha1(f"{cid}|{ts}|{text[:200]}".encode()).hexdigest()
            out.append({"id": mid, "session": f"claude.ai:{cid}", "role": "user" if sender == "human" else "assistant",
                        "ts": ts, "text": text, "source": "claude.ai"})  # fmt: skip
    return out, skipped
