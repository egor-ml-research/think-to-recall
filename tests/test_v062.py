"""v0.6.2 (rules written before the code): the save_chat instruction in the tool descriptions, the time of the last
save and one reminder line in recall for MCP clients without automatic recording. Synthetic data, offline."""

import asyncio
import datetime as dt
import json
import os
import subprocess
import sys

from ctxgraph import memory_mcp as M
from ctxgraph.embed import HashingEncoder
from ctxgraph.memory import ProjectMemory


def _mem(tmp_path):
    return ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")


def test_descriptions_tell_the_model_to_save():
    ts = {t.name: t.description for t in asyncio.run(M.server.list_tools())}
    for name in ("recall", "save_chat"):
        assert "call save_chat at the end of your answer" in ts[name] and "not Claude Code" in ts[name]
        assert "SAVE_HINT" not in ts[name]


def test_reminder_once_for_clients_without_recording(tmp_path):
    m = _mem(tmp_path)
    M._reminded = False
    assert m.last_chat_save() is None
    assert M._save_reminder(m, "") == ""  # unknown client
    assert M._save_reminder(m, "claude-code") == ""  # Claude Code records by its hook
    line = M._save_reminder(m, "claude-ai")
    assert "has not been saved yet" in line and "save_chat" in line
    assert M._save_reminder(m, "claude-ai") == ""  # never twice in a row in one session
    M._mem = m
    try:
        M.save_chat("Заметки", [{"role": "user", "text": "Для заметок берём SQLite, без отдельного сервера базы."}], 0)
    finally:
        M._mem = None
    assert m.last_chat_save() and not M._reminded  # a save resets the once-per-session flag
    assert M._save_reminder(m, "cursor-vscode") == ""  # a fresh save: no reminder
    old = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=M.REMIND_HOURS + 1)).isoformat()
    m.s.db.execute("UPDATE memory_meta SET value=? WHERE key='last_save_chat'", (old,))
    assert "was last saved 13 h ago" in M._save_reminder(m, "cursor-vscode")
    M._reminded = False


def _call_recall(tmp_path, client):
    env = dict(os.environ, CTXGRAPH_PROJECT=str(tmp_path / "proj"), CTXGRAPH_HOME=str(tmp_path / "home"),
               PYTHONIOENCODING="utf-8")
    env.pop("CTXGRAPH_QUALITY", None)
    (tmp_path / "proj").mkdir(exist_ok=True)
    p = subprocess.Popen([sys.executable, "-m", "ctxgraph.memory_mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, env=env)

    def send(o):
        p.stdin.write((json.dumps(o) + "\n").encode())
        p.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18",
              "capabilities": {}, "clientInfo": {"name": client, "version": "1"}}})
        p.stdout.readline()
        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        out = []
        for i in (2, 3):
            send({"jsonrpc": "2.0", "id": i, "method": "tools/call",
                  "params": {"name": "recall", "arguments": {"question": "какую базу выбрали"}}})
            r = json.loads(p.stdout.readline())
            out.append(r["result"]["content"][0]["text"])
        return out
    finally:
        p.kill()


def test_reminder_reaches_the_client_by_its_name(tmp_path):
    first, second = _call_recall(tmp_path, "claude-ai")
    assert "save_chat" in first and "save_chat" not in second
    assert not any("save_chat" in x for x in _call_recall(tmp_path, "claude-code"))
