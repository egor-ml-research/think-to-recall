"""Check a memory (sync) repository before or after a push: no keys or secrets, no personal e-mails, no home folders.

The secret patterns are the privacy filter's (`cotrail.privacy`); on top of them, absolute home folders
(`C:\\Users\\<name>\\...`, `/home/<name>/...`, `/Users/<name>/...`) - they name the person and the machine layout.
`sync` scrubs these before writing (`strip_home`) and refuses to push a line this check would flag.

    python -m cotrail.repo_check <clone-of-the-memory-repo>      # or: cotrail team check
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HOME_PATTERNS = [
    re.compile(r"(?i)\b[A-Z]:(?:\\\\|\\|/){1,2}(?:Users|Documents and Settings)(?:\\\\|\\|/){1,2}[^\\/\s\"'<>|:*?]+"),
    re.compile(r"(?<![\w.~-])/(?:home|Users)/[^/\s\"'<>]+"),
]
ALLOWED = {"README.md", ".gitattributes"}


def strip_home(text: str) -> str:
    for p in HOME_PATTERNS:
        text = p.sub("~", text)
    return text


def findings(text: str) -> list[str]:
    from cotrail.privacy import _PATTERNS

    # a match that is (or holds) the filter's own placeholder is already redacted: "api_key=[REDACTED:...]"
    out = [kind for kind, p in _PATTERNS if any("[REDACTED:" not in m.group(0) for m in p.finditer(text))]
    out += ["home_path" for p in HOME_PATTERNS if p.search(text)]
    return out


def check_rows(rows: list[dict], where: str = "") -> list[dict]:
    """Every text field of the log lines: text, ask, author (a name, never an e-mail), session."""
    bad = []
    for r in rows:
        for field in ("text", "ask", "pasted", "author", "session", "title"):
            v = r.get(field)
            if not isinstance(v, str) or not v:
                continue
            kinds = findings(v)
            if field in ("session", "title"):  # session ids are uuids or titles: only e-mails and home folders matter there
                kinds = [k for k in kinds if k in ("email", "home_path")]
            for k in dict.fromkeys(kinds):
                bad.append({"where": where, "id": r.get("id", "?"), "field": field, "kind": k})
    return bad


ABS_PATH = re.compile(r"^([A-Za-z]:[\\/]|/|~)")


def check_graph_data(g: dict, where: str = "") -> list[dict]:
    """A member's code graph: labels and files with no secrets / e-mails / home folders, files relative."""
    bad = []
    for n in g.get("nodes", []):
        if not isinstance(n, list) or len(n) < 3:
            bad.append({"where": where, "id": "-", "field": "node", "kind": "malformed"})
            continue
        for field, v in (("label", n[1]), ("file", n[2])):
            kinds = [k for k in findings(str(v)) if k not in ("phone", "card", "hex", "base64")]
            if field == "file" and ABS_PATH.match(str(v)):
                kinds.append("absolute_path")
            bad += [{"where": where, "id": str(n[0])[:40], "field": field, "kind": k} for k in dict.fromkeys(kinds)]
    return bad


def check_graph(f: Path, rel: str) -> list[dict]:
    try:
        g = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        return [{"where": rel, "id": "-", "field": "file", "kind": "not JSON"}]
    return check_graph_data(g if isinstance(g, dict) else {}, rel)


TOOL_KINDS = {"private_key", "jwt", "api_key", "bearer", "url_credentials", "email", "home_path"}


def check_tool(f: Path, rel: str) -> list[dict]:
    """tools/: a wheel (every text member) or a text file - keys, e-mails, home folders. Code inside a wheel names
    variables like `token = ...`, so the assignment / long-number patterns are not applied there."""
    import zipfile

    texts: list[tuple[str, str]] = []
    if rel.endswith(".whl"):
        try:
            with zipfile.ZipFile(f) as z:
                texts = [(f"{rel}!{n}", z.read(n).decode("utf-8", "replace")) for n in z.namelist() if not n.endswith("/")]
        except zipfile.BadZipFile:
            return [{"where": rel, "id": "-", "field": "file", "kind": "bad wheel"}]
    elif rel.endswith((".md", ".txt", ".json", ".ps1", ".sh")):
        texts = [(rel, f.read_text("utf-8", errors="replace"))]
    else:
        return [{"where": rel, "id": "-", "field": "file", "kind": "unexpected file"}]
    return [{"where": w, "id": "-", "field": "text", "kind": k} for w, t in texts for k in dict.fromkeys(findings(t))
            if k in TOOL_KINDS]


def check_repo(repo: str | Path) -> list[dict]:
    repo = Path(repo)
    bad: list[dict] = []
    for f in sorted(p for p in repo.rglob("*") if p.is_file() and ".git" not in p.relative_to(repo).parts):
        rel = f.relative_to(repo).as_posix()
        if rel in ALLOWED:
            continue
        if rel.startswith("graphs/") and rel.endswith(".json"):
            bad += check_graph(f, rel)
            continue
        if rel.startswith("status/") and rel.endswith(".json"):  # device status: short fields, scanned as text
            bad += [{"where": rel, "id": "-", "field": "text", "kind": k}
                    for k in dict.fromkeys(findings(f.read_text("utf-8", errors="replace"))) if k in TOOL_KINDS]
            continue
        if rel.startswith("tools/"):  # the team's private build and its instructions (sync never reads tools/)
            bad += check_tool(f, rel)
            continue
        if not (rel.startswith("episodes/") and rel.endswith(".jsonl")):
            bad.append({"where": rel, "id": "-", "field": "file", "kind": "unexpected file"})
            continue
        rows = []
        for i, line in enumerate(f.read_text("utf-8", errors="replace").splitlines(), 1):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                if line.strip():
                    bad.append({"where": f"{rel}:{i}", "id": "-", "field": "line", "kind": "not JSON"})
        bad += check_rows([r for r in rows if isinstance(r, dict)], rel)
    return bad


def report(bad: list[dict]) -> str:
    if not bad:
        return "Memory repo check: clean (no secrets, e-mails or home folders)."
    lines = [f"Memory repo check: {len(bad)} finding(s):"]
    lines += [f"  {b['where']} {b['id']} {b['field']}: {b['kind']}" for b in bad[:50]]
    return "\n".join(lines + (["  ..."] if len(bad) > 50 else []))


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("usage: python -m cotrail.repo_check <memory-repo-folder>", file=sys.stderr)
        return 2
    bad = check_repo(argv[0])
    print(report(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
