"""Read-only source of deferred items: Beads issues (github.com/gastownhall/beads, MIT) in `<project>/.beads/*.jsonl`.

Beads keeps its truth in Dolt; `.beads/issues.jsonl` is an export, rewritten whole. We only read it, never write, and
use none of Beads' code. An issue counts as deferred ("later") when its status is `deferred`, or it has a non-empty
`defer_until`, or a `later` label; `closed` issues never count. Lines of other types (`_type` other than "issue"),
unknown fields and broken lines are skipped (rules written before the code).
"""

from __future__ import annotations

import json
from pathlib import Path


def deferred(project: str | Path) -> list[dict]:
    """[{"id", "date", "text", "status"}] of deferred Beads issues, newest first; [] without a `.beads` folder."""
    d = Path(project) / ".beads"
    if not d.is_dir():
        return []
    seen, out = set(), []
    for f in sorted(d.glob("*.jsonl")):
        try:
            lines = f.read_text("utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for ln in lines:
            try:
                r = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if not isinstance(r, dict) or r.get("_type", "issue") != "issue" or not r.get("id") or not r.get("title"):
                continue
            status = str(r.get("status") or "")
            labels = r.get("labels") or []
            later = status == "deferred" or bool(r.get("defer_until")) or "later" in labels
            if status == "closed" or not later or r["id"] in seen:
                continue
            seen.add(r["id"])
            date = str(r.get("updated_at") or r.get("created_at") or "")[:10]
            out.append({"id": str(r["id"]), "date": date, "text": str(r["title"]).strip(), "status": status})
    return sorted(out, key=lambda x: x["date"], reverse=True)
