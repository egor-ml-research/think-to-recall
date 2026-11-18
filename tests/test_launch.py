"""Launch pieces: `ctxgraph setup` config writing, model consent guard, Graphify import, 2D/3D viewer with code layer."""

import json
import sys

import pytest

from ctxgraph import graphify as GF
from ctxgraph import model as M
from ctxgraph import setup as S
from ctxgraph.embed import HashingEncoder
from ctxgraph.memory import ProjectMemory


def test_setup_merges_mcp_json_and_hook(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), "utf-8")
    old = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python -m ctxgraph.cli hook-stop"}]},
                              {"hooks": [{"type": "command", "command": "echo other"}]}]},
           "permissions": {"allow": ["Bash(ls)"]}}  # fmt: skip
    (proj / ".claude" / "settings.local.json").write_text(json.dumps(old), "utf-8")
    S.shutil.which = lambda name, _w=S.shutil.which: None if name == "claude" else _w(name)  # no claude CLI here
    try:
        p, st = S.write_mcp(proj, str(tmp_path / "home"))
        assert S.write_mcp(proj, str(tmp_path / "home"))[1] == "unchanged"
    finally:
        import shutil as _sh

        S.shutil.which = _sh.which
    assert st == "added"
    raw = p.read_text("utf-8")
    d = json.loads(raw)
    assert d["mcpServers"]["other"] == {"command": "x"}
    # a shared, committable file: a command name only - no home folder, no Python path, no project path
    assert d["mcpServers"]["ctxgraph"] == {"type": "stdio", "command": "ctxgraph-mcp", "args": []}
    assert str(tmp_path) not in raw and tmp_path.as_posix() not in raw and "python" not in raw.lower()
    p, st = S.write_hook(proj, str(tmp_path / "home"))
    assert st == "updated"
    d = json.loads(p.read_text("utf-8"))
    cmds = [h["command"] for g in d["hooks"]["Stop"] for h in g["hooks"]]
    assert "echo other" in cmds and sum("hook-stop" in c for c in cmds) == 1
    assert d["permissions"] == old["permissions"]
    ours = next(c for c in cmds if "hook-stop" in c)
    assert ours.startswith("ctxgraph --home ") and ours.endswith(" hook-stop") and "--project" not in ours
    assert "python" not in ours.lower()
    assert S.write_hook(proj, str(tmp_path / "home"))[1] == "unchanged"


def test_hook_command_runs_with_home(tmp_path, monkeypatch):
    """The hook command line written by setup works: `--home` routes the queue to that store."""
    import subprocess

    proj = tmp_path / "proj"
    proj.mkdir()
    cmd = S.hook_command(proj, str(tmp_path / "home"))
    payload = json.dumps({"transcript_path": "C:/t/x.jsonl", "cwd": str(proj)})
    # the hook as written (`ctxgraph --home H hook-stop`), run through this Python; the project comes from `cwd`
    argv = [sys.executable, "-m", "ctxgraph.cli", "--home", str(tmp_path / "home"), "hook-stop"]
    assert cmd.endswith("hook-stop")
    subprocess.run(argv, input=payload, text=True, check=True, timeout=60)
    q = list((tmp_path / "home").glob("*/pending.txt"))
    assert len(q) == 1 and "x.jsonl" in q[0].read_text("utf-8")


def test_model_guard_refuses_silent_download(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.delenv("CTXGRAPH_ALLOW_DOWNLOAD", raising=False)
    assert not M.is_cached()
    with pytest.raises(M.ModelMissing, match="ctxgraph setup"):
        M.prepare()
    snap = M.snapshot_dir()
    snap.mkdir(parents=True)
    for f in M.FILES:
        (snap / f).parent.mkdir(parents=True, exist_ok=True)
        (snap / f).write_text("x")
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    M.prepare()
    import os

    assert M.is_cached() and os.environ["HF_HUB_OFFLINE"] == "1"


def test_mcp_tools_explain_missing_model(monkeypatch):
    from ctxgraph import memory_mcp as MM

    def missing():
        raise M.ModelMissing("not downloaded; run `ctxgraph setup`")

    monkeypatch.setattr(MM, "mem", missing)
    assert "ctxgraph setup" in MM.memory_status() and "ctxgraph setup" in MM.decisions(3)


GRAPH = {
    "directed": False, "multigraph": False, "graph": {"schema_version": 1, "graphify_version": "0.9"},
    "nodes": [
        {"id": "f_mem", "label": "memory.py", "source_file": "ctxgraph/memory.py", "source_location": "L1", "file_type": "code", "community": 0},
        {"id": "c_pm", "label": "ProjectMemory", "source_file": "ctxgraph/memory.py", "source_location": "L201", "file_type": "code", "community": 0},
        {"id": "m_recall", "label": ".recall()", "source_file": "ctxgraph/memory.py", "source_location": "L597", "file_type": "code", "community": 0},
        {"id": "f_cli", "label": "cli.py", "source_file": "ctxgraph/cli.py", "source_location": "L1", "file_type": "code", "community": 1},
        {"id": "fn_main", "label": "main()", "source_file": "ctxgraph/cli.py", "source_location": "L150", "file_type": "code", "community": 1},
    ],
    "links": [
        {"source": "f_mem", "target": "c_pm", "relation": "contains", "confidence": "EXTRACTED", "confidence_score": 1.0},
        {"source": "c_pm", "target": "m_recall", "relation": "method", "confidence": "EXTRACTED"},
        {"source": "f_cli", "target": "f_mem", "relation": "imports", "confidence": "EXTRACTED"},
        {"source": "fn_main", "target": "m_recall", "relation": "calls", "confidence": "INFERRED", "confidence_score": 0.75},
        {"source": "fn_main", "target": "missing", "relation": "calls", "confidence": "EXTRACTED"},
    ],
}


def _mem_with_chat(tmp_path):
    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    turns = []
    for i, t in enumerate([
        "Решили: логику в ctxgraph/memory.py не трогаем, ProjectMemory остаётся как есть.",
        "В ProjectMemory метод recall отдаёт основную линию и периферию; ctxgraph/memory.py заморожен.",
        "Файл ctxgraph/memory.py и класс ProjectMemory — главное место памяти, main не трогаем.",
        "Ещё раз: ProjectMemory и ctxgraph/memory.py — без изменений, правим только cli.",
    ]):
        turns.append({"id": f"u{i}", "session": "s1", "role": "user", "ts": f"2026-11-0{i + 1}T10:00:00Z", "text": t,
                      "source": "cc"})  # fmt: skip
    m.import_turns(turns)
    return m


def test_graphify_import_labels_origins_and_links_by_name(tmp_path):
    m = _mem_with_chat(tmp_path)
    g = tmp_path / "graphify-out"
    g.mkdir()
    (g / "graph.json").write_text(json.dumps(GRAPH), "utf-8")
    r = GF.import_graph(m.db_path, tmp_path)  # repo root: finds graphify-out/graph.json
    assert (r["nodes"], r["edges"], r["code"], r["inferred"]) == (5, 4, 3, 1)
    db = GF.connect(m.db_path)
    links = db.execute("SELECT c.label, l.code, l.how, l.origin FROM code_links l JOIN concepts c ON c.id=l.concept").fetchall()
    got = {(lab.lower(), code, how) for lab, code, how, o in links if o == "inferred"}
    assert ("ctxgraph/memory.py", "f_mem", "path") in got
    assert any(code == "c_pm" and how == "name" for _, code, how in got)
    assert not any(code == "fn_main" for _, code, _ in got)  # "main" is too generic to link
    # re-import replaces, no duplicates
    r2 = GF.import_graph(m.db_path, g / "graph.json")
    assert r2["links"] == r["links"] and db.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0] == 5
    lay = GF.layer(m.db_path, {c for (c,) in db.execute("SELECT concept FROM code_links")})
    assert {n["origin"] for n in lay["nodes"]} == {"code"}
    assert {lk["origin"] for lk in lay["links"]} == {"code", "inferred"}
    assert lay["meta"]["graphify_version"] == "0.9"


def test_graphify_rejects_other_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("[1, 2]", "utf-8")
    with pytest.raises(ValueError):
        GF.load(p)


def test_viewer_embeds_both_libs_and_code_layer(tmp_path):
    pytest.importorskip("networkx")
    from ctxgraph.viewer import export_html

    m = _mem_with_chat(tmp_path)
    (tmp_path / "graph.json").write_text(json.dumps(GRAPH), "utf-8")
    GF.import_graph(m.db_path, tmp_path / "graph.json")
    out = export_html(m, out=tmp_path / "g.html", mode="3d")
    html = out.read_text("utf-8")
    assert "ForceGraph3D" in html and "force-graph - https://github.com/vasturiano/force-graph" in html
    assert "/*__DATA__*/" not in html and "/*__FORCE_GRAPH_3D__*/" not in html
    data = json.loads(html.split("const DATA = ", 1)[1].split(";\nconst $", 1)[0].replace("<\\/", "</"))
    assert data["mode"] == "3d"
    assert {n["origin"] for n in data["nodes"]} >= {"code"}
    assert all(lk["origin"] in ("conversation", "code", "inferred") for lk in data["links"])


def test_setup_registers_locally_with_the_claude_cli(tmp_path, monkeypatch):
    """With the `claude` CLI: `claude mcp add --scope local`, nothing in the repository; an old .mcp.json entry with
    absolute paths (written by an earlier version) is removed."""
    proj = tmp_path / "proj"
    proj.mkdir()
    old = {"mcpServers": {"ctxgraph": {"command": "C:/x/python.exe", "args": ["-m", "ctxgraph.memory_mcp"]},
                          "other": {"command": "y"}}}
    (proj / ".mcp.json").write_text(json.dumps(old), "utf-8")
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    monkeypatch.setattr(S.shutil, "which", lambda name: "/usr/bin/claude" if name == "claude" else None)
    monkeypatch.setattr(S.subprocess, "run", lambda argv, **kw: calls.append((argv, kw.get("cwd"))) or R())
    where, st = S.write_mcp(proj, None)
    assert st == "added" and "local" in where
    add = next(a for a, _ in calls if a[1:3] == ["mcp", "add"])
    assert add == ["/usr/bin/claude", "mcp", "add", "--scope", "local", "ctxgraph", "--", "ctxgraph-mcp"]
    assert all(cwd == proj for _, cwd in calls)
    assert json.loads((proj / ".mcp.json").read_text("utf-8")) == {"mcpServers": {"other": {"command": "y"}}}


def test_download_failure_is_a_message_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    import huggingface_hub

    def fail(*a, **k):
        raise ConnectionError("Failed to resolve 'huggingface.co' ([Errno 11001] getaddrinfo failed)")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fail)
    with pytest.raises(M.DownloadFailed) as e:
        M.download()
    msg = str(e.value)
    assert M.REPO in msg and "huggingface.co" in msg and "ctxgraph setup" in msg and "getaddrinfo" in msg
    assert e.value.__cause__ is None and e.value.__suppress_context__  # no chained traceback
    assert S.ensure_model(True) is False  # setup prints the message and goes on
    out = capsys.readouterr().out
    assert "Could not download the encoder model" in out and "Traceback" not in out


def test_store_refuses_vectors_of_another_encoder(tmp_path):
    from ctxgraph.embed import HashingEncoder
    from ctxgraph.memory import EncoderMismatch, ProjectMemory

    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    m.remember("Для базы данных используем PostgreSQL.")

    other = HashingEncoder()
    other.name = "other-encoder"
    with pytest.raises(EncoderMismatch, match="do not mix"):
        ProjectMemory(tmp_path / "proj", encoder=other, home=tmp_path / "home")
    ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")  # the same encoder: fine
