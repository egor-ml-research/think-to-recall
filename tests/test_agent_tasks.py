"""Agent tasks (rules written before the code): records typed by another session or the app are not the
user's turns. Synthetic transcripts: a parent session starts a child and later messages it."""

import json

from ctxgraph import cc_transcripts as CC
from ctxgraph.memory import ProjectMemory, format_decisions

BRIEF = "Implement the export feature: use Redis for the job queue and always write CSV files in UTF-8."
PEER = "Later: postpone the PDF export until next month, keep CSV only."


def _rec(uuid, sess, ts, role, content, **meta):
    r = {"type": role, "uuid": uuid, "sessionId": sess, "timestamp": ts, "isSidechain": False,
         "message": {"role": role, "content": content}}
    r.update(meta)
    return json.dumps(r)


def _write(d):
    parent = [
        _rec("p1", "parent", "2026-11-20T09:00:00Z", "user", "Let's build the export feature in a separate session.",
             turnOrigin="human", promptSource="sdk"),
        _rec("p2", "parent", "2026-11-20T09:01:00Z", "assistant",
             [{"type": "text", "text": "Starting a session for the export feature now."},
              {"type": "tool_use", "name": "mcp__ccd_session__start_session", "input": {"prompt": BRIEF}}]),
        _rec("p3", "parent", "2026-11-20T10:00:00Z", "assistant",
             [{"type": "text", "text": "Sending the deferral to the export session."},
              {"type": "tool_use", "name": "SendMessage", "input": {"to": "x", "message": PEER}}]),
    ]
    child = [
        _rec("c1", "child", "2026-11-20T09:02:00Z", "user",
             "<system-reminder>\nLinked sessions now: none.\n</system-reminder>\n" + BRIEF,
             turnOrigin="host_synthetic", promptSource="sdk"),
        _rec("c2", "child", "2026-11-20T09:40:00Z", "assistant",
             [{"type": "text", "text": "Export done: Redis queue and CSV writer added, commit 4d5e6f7."}]),
        _rec("c3", "child", "2026-11-20T10:01:00Z", "user",
             "Another Claude session sent a message: <cross-session-message>" + PEER + "</cross-session-message>",
             turnOrigin="peer", promptSource="system",
             origin={"kind": "peer", "from": "local_parent", "name": "Main", "body": PEER}),
        _rec("c4", "child", "2026-11-20T10:02:00Z", "user", "The app was quit while you were working. Please continue.",
             turnOrigin="sdk", promptSource="sdk"),
        _rec("c5", "child", "2026-11-20T10:03:00Z", "assistant",
             [{"type": "text", "text": "Noted: the PDF export is postponed, CSV only for now."}]),
    ]
    (d / "parent.jsonl").write_text("\n".join(parent) + "\n", "utf-8")
    (d / "child.jsonl").write_text("\n".join(child) + "\n", "utf-8")


def test_agent_tasks_are_found_by_metadata_and_linked_to_the_parent(tmp_path):
    _write(tmp_path)
    ts = {t["id"]: t for t in CC.project_turns(tmp_path)}
    assert ts["p1"]["agent"] is None
    assert ts["c1"]["agent"] == {"kind": "brief", "parent": "parent"} and ts["c1"]["text"] == BRIEF
    assert ts["c3"]["agent"] == {"kind": "peer", "parent": "parent"} and ts["c3"]["text"] == PEER
    assert ts["c4"]["agent"]["kind"] == "host"


def test_agent_tasks_are_no_decisions_rules_or_later_items(tmp_path, monkeypatch):
    monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    monkeypatch.setenv("CTXGRAPH_LANG", "en")
    (tmp_path / "t").mkdir()
    _write(tmp_path / "t")
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_claude_code(tmp_path / "t")
    d = format_decisions(m.decisions())
    assert "Redis" not in d and "PDF" not in d and "export feature in a separate session" in d
    assert not any("UTF-8" in r["text"] for r in m.rules())  # "always ..." in a brief is not the user's rule
    assert not any("PDF" in i["text"] for i in m.later())
    out = m.render(m.recall("Which queue does the export use?", k=6))
    assert "agent task (from session parent" in out and "commit 4d5e6f7" in out  # the child's report stays with it
    assert m.lang == "en"
