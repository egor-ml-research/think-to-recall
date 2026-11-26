"""Launch pieces: `cotrail setup` config writing, model consent guard, Graphify import, 2D/3D viewer with code layer."""

import json
import sys
from pathlib import Path

import pytest

from cotrail import graphify as GF
from cotrail import model as M
from cotrail import setup as S
from cotrail.embed import HashingEncoder
from cotrail.memory import ProjectMemory


def test_setup_merges_mcp_json_and_hook(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "WINDOWS", False)
    proj = tmp_path / "proj"
    (proj / ".claude").mkdir(parents=True)
    (proj / ".mcp.json").write_text(json.dumps({"mcpServers": {"other": {"command": "x"}}}), "utf-8")
    old = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "python -m cotrail.cli hook-stop"}]},
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
    assert d["mcpServers"]["cotrail"] == {"type": "stdio", "command": "cotrail-mcp", "args": []}
    assert str(tmp_path) not in raw and tmp_path.as_posix() not in raw and "python" not in raw.lower()
    p, st = S.write_hook(proj, str(tmp_path / "home"))
    assert st == "updated"
    d = json.loads(p.read_text("utf-8"))
    cmds = [h["command"] for g in d["hooks"]["Stop"] for h in g["hooks"]]
    assert "echo other" in cmds and sum("hook-stop" in c for c in cmds) == 1
    assert d["permissions"] == old["permissions"]
    ours = next(c for c in cmds if "hook-stop" in c)
    assert ours.startswith("cotrail --home ") and ours.endswith(" hook-stop") and "--project" not in ours
    assert "python" not in ours.lower()
    assert S.write_hook(proj, str(tmp_path / "home"))[1] == "unchanged"


def test_hook_command_runs_with_home(tmp_path, monkeypatch):
    """The hook command line written by setup works: `--home` routes the queue to that store."""
    import subprocess

    proj = tmp_path / "proj"
    proj.mkdir()
    cmd = S.hook_command(proj, str(tmp_path / "home"))
    payload = json.dumps({"transcript_path": "C:/t/x.jsonl", "cwd": str(proj)})
    # the hook as written (`cotrail --home H hook-stop`), run through this Python; the project comes from `cwd`
    argv = [sys.executable, "-m", "cotrail.cli", "--home", str(tmp_path / "home"), "hook-stop"]
    assert cmd.endswith("hook-stop")
    subprocess.run(argv, input=payload, text=True, check=True, timeout=60)
    q = list((tmp_path / "home").glob("*/pending.txt"))
    assert len(q) == 1 and "x.jsonl" in q[0].read_text("utf-8")


def test_model_guard_refuses_silent_download(tmp_path, monkeypatch):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    monkeypatch.delenv("COTRAIL_ALLOW_DOWNLOAD", raising=False)
    assert not M.is_cached()
    with pytest.raises(M.ModelMissing, match="cotrail setup"):
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
    from cotrail import memory_mcp as MM

    def missing(memory=None):
        raise M.ModelMissing("not downloaded; run `cotrail setup`")

    monkeypatch.setattr(MM, "mem", missing)
    assert "cotrail setup" in MM.memory_status() and "cotrail setup" in MM.decisions(3)


GRAPH = {
    "directed": False, "multigraph": False, "graph": {"schema_version": 1, "graphify_version": "0.9"},
    "nodes": [
        {"id": "f_mem", "label": "memory.py", "source_file": "cotrail/memory.py", "source_location": "L1", "file_type": "code", "community": 0},
        {"id": "c_pm", "label": "ProjectMemory", "source_file": "cotrail/memory.py", "source_location": "L201", "file_type": "code", "community": 0},
        {"id": "m_recall", "label": ".recall()", "source_file": "cotrail/memory.py", "source_location": "L597", "file_type": "code", "community": 0},
        {"id": "f_cli", "label": "cli.py", "source_file": "cotrail/cli.py", "source_location": "L1", "file_type": "code", "community": 1},
        {"id": "fn_main", "label": "main()", "source_file": "cotrail/cli.py", "source_location": "L150", "file_type": "code", "community": 1},
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
        "Решили: логику в cotrail/memory.py не трогаем, ProjectMemory остаётся как есть.",
        "В ProjectMemory метод recall отдаёт основную линию и периферию; cotrail/memory.py заморожен.",
        "Файл cotrail/memory.py и класс ProjectMemory — главное место памяти, main не трогаем.",
        "Ещё раз: ProjectMemory и cotrail/memory.py — без изменений, правим только cli.",
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
    assert ("cotrail/memory.py", "f_mem", "path") in got
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
    from cotrail.viewer import export_html

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



def test_viewer_cosmos_mode(tmp_path):
    """--cosmos: the cosmic mode script is inlined and the page opens in it; without a mode the page uses its last one."""
    pytest.importorskip("networkx")
    from cotrail.viewer import export_html

    m = _mem_with_chat(tmp_path)
    get = lambda h: json.loads(h.split("const DATA = ", 1)[1].split(";\nconst $", 1)[0].replace("<\\/", "</"))  # noqa: E731
    html = export_html(m, out=tmp_path / "c.html", mode="cosmos").read_text("utf-8")
    assert "/*__COSMOS__*/" not in html and "const COS = " in html and 'data-mode="cosmos"' in html
    data = get(html)
    assert data["mode"] == "cosmos" and isinstance(data["daily"], dict)
    assert get(export_html(m, out=tmp_path / "d.html").read_text("utf-8"))["mode"] == ""

def test_setup_registers_locally_with_the_claude_cli(tmp_path, monkeypatch):
    """With the `claude` CLI: `claude mcp add --scope local`, nothing in the repository; an old .mcp.json entry with
    absolute paths (written by an earlier version) is removed."""
    monkeypatch.setattr(S, "WINDOWS", False)
    proj = tmp_path / "proj"
    proj.mkdir()
    old = {"mcpServers": {"cotrail": {"command": "C:/x/python.exe", "args": ["-m", "cotrail.memory_mcp"]},
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
    assert add == ["/usr/bin/claude", "mcp", "add", "--scope", "local", "cotrail", "--", "cotrail-mcp"]
    assert all(cwd == proj for _, cwd in calls)
    assert json.loads((proj / ".mcp.json").read_text("utf-8")) == {"mcpServers": {"other": {"command": "y"}}}


def test_windows_uses_the_console_free_launcher(tmp_path, monkeypatch):
    """Windows: `cotrail-mcpw` (GUI launcher: no console window from Claude Desktop / Claude Code desktop) in
    `claude mcp add`, in the path-free `.mcp.json` and in the Cursor snippet; other systems keep `cotrail-mcp`.
    An entry of either name (or a hand-written pythonw command) is recognised as ours."""
    monkeypatch.setattr(S, "WINDOWS", True)
    assert S.mcp_entry() == {"type": "stdio", "command": "cotrail-mcpw", "args": []}
    calls = []

    class R:
        returncode, stdout, stderr = 0, "", ""

    found = {"claude": "C:/bin/claude.exe", "cotrail-mcpw": "C:/u/.local/bin/cotrail-mcpw.exe"}
    monkeypatch.setattr(S.shutil, "which", lambda name: found.get(name))
    monkeypatch.setattr(S.subprocess, "run", lambda argv, **kw: calls.append(argv) or R())
    proj = tmp_path / "proj"
    proj.mkdir()
    S.write_mcp(proj, None)
    assert next(a for a in calls if a[1:3] == ["mcp", "add"])[-1] == "C:/u/.local/bin/cotrail-mcpw.exe"
    found.pop("claude")  # no claude CLI: the path-free .mcp.json entry
    S.write_mcp(proj, None)
    assert json.loads((proj / ".mcp.json").read_text("utf-8"))["mcpServers"]["cotrail"]["command"] == "cotrail-mcpw"
    for c in ("cotrail-mcp", "cotrail-mcpw", "C:/x/Scripts/pythonw.exe -m cotrail.memory_mcp"):
        assert S._ours({"command": c})
    monkeypatch.setattr(S, "WINDOWS", False)
    assert S.mcp_entry()["command"] == "cotrail-mcp"


def test_gui_launcher_is_declared():
    """The package declares the GUI entry point next to the console one (same server)."""
    import tomllib

    meta = tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text("utf-8"))
    assert meta["project"]["gui-scripts"] == {"cotrail-mcpw": "cotrail.memory_mcp:main",
                                          "ctxgraph-mcpw": "cotrail.legacy:mcpw_main"}  # the old name
    assert meta["project"]["scripts"]["cotrail-mcp"] == "cotrail.memory_mcp:main"


def test_download_failure_is_a_message_not_a_traceback(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "hub"))
    import huggingface_hub

    def fail(*a, **k):
        raise ConnectionError("Failed to resolve 'huggingface.co' ([Errno 11001] getaddrinfo failed)")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", fail)
    with pytest.raises(M.DownloadFailed) as e:
        M.download()
    msg = str(e.value)
    assert M.REPO in msg and "huggingface.co" in msg and "cotrail setup" in msg and "getaddrinfo" in msg
    assert e.value.__cause__ is None and e.value.__suppress_context__  # no chained traceback
    assert S.ensure_model(True) is False  # setup prints the message and goes on
    out = capsys.readouterr().out
    assert "Could not download the encoder model" in out and "Traceback" not in out


def test_store_refuses_vectors_of_another_encoder(tmp_path):
    from cotrail.embed import HashingEncoder
    from cotrail.memory import EncoderMismatch, ProjectMemory

    m = ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")
    m.remember("Для базы данных используем PostgreSQL.")

    other = HashingEncoder()
    other.name = "other-encoder"
    with pytest.raises(EncoderMismatch, match="do not mix"):
        ProjectMemory(tmp_path / "proj", encoder=other, home=tmp_path / "home")
    ProjectMemory(tmp_path / "proj", encoder=HashingEncoder(), home=tmp_path / "home")  # the same encoder: fine


def test_default_mode_is_bm25_without_any_model(tmp_path, monkeypatch):
    """No encoder given, no quality config: BM25 recall, a hashing encoder for the graph only, no model needed."""
    monkeypatch.setenv("HF_HUB_CACHE", str(tmp_path / "empty-hub"))  # the model is surely not there
    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    from cotrail.memory import ProjectMemory, wants_quality

    assert not wants_quality(tmp_path / "home")
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    assert m.mode == "bm25" and m.s.q("SELECT value FROM memory_meta WHERE key='encoder'")[0][0].startswith("hashing")
    m.remember("Для базы данных используем PostgreSQL с репликацией.", ts="2026-11-01T10:00:00Z")
    m.remember("Деплой делаем на Fly.io, а не на Heroku.", ts="2026-11-02T10:00:00Z")
    hits = m.recall("какую базу данных используем", k=1)
    assert hits and "PostgreSQL" in hits[0].text  # lemmas: "базу" ~ "базы"
    m2 = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")  # reopened: keeps its mode
    assert m2.mode == "bm25"


def test_setup_quality_moves_a_default_store_aside_and_keeps_rules(tmp_path, monkeypatch):
    from cotrail.memory import ProjectMemory

    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    home, proj = tmp_path / "home", tmp_path / "proj"
    proj.mkdir()
    m = ProjectMemory(proj, home=home)
    rid = m.pin_rule("Ключи API — только в .env.")
    db = m.db_path
    m.s.db.close()  # Windows: an open SQLite file cannot be renamed
    del m
    monkeypatch.setattr(S, "ensure_model", lambda assume: True)
    import cotrail.memory as MM

    monkeypatch.setattr(MM, "HOME", home)
    assert S.enable_quality(proj, str(home), True)
    assert json.loads((home / "config.json").read_text("utf-8"))["quality"] is True
    assert list(db.parent.glob("graph.sqlite.bm25-*"))  # the old store is kept aside, not deleted
    import sqlite3

    assert sqlite3.connect(db).execute("SELECT id FROM pinned_rules").fetchall() == [(rid,)]


def test_import_without_a_terminal_says_to_use_y(tmp_path):
    import subprocess

    src = tmp_path / "transcripts"
    src.mkdir()
    (src / "s.jsonl").write_text(json.dumps({"type": "user", "uuid": "u1", "timestamp": "2026-11-01T10:00:00Z",
                                             "sessionId": "s", "message": {"role": "user", "content": "Берём Postgres."}}),
                                 "utf-8")  # fmt: skip
    r = subprocess.run([sys.executable, "-m", "cotrail.cli", "--home", str(tmp_path / "home"), "--project",
                        str(tmp_path / "proj"), "import", "--source", str(src)], input="", capture_output=True,
                       text=True, timeout=120)  # fmt: skip
    assert r.returncode != 0 and "-y" in r.stderr and "EOFError" not in r.stderr + r.stdout


def test_setup_question_without_input_is_no_not_a_crash(monkeypatch, capsys):
    class TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(S.sys, "stdin", TTY())

    def eof(prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert S._ask("Import them into the project memory?", None) is False
    assert "--yes" in capsys.readouterr().out


def test_setup_enter_takes_the_default(monkeypatch):
    class TTY:
        def isatty(self):
            return True

    monkeypatch.setattr(S.sys, "stdin", TTY())
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    assert S._ask("Download data for topic names?", None, default=True) is True
    assert S._ask("Import them?", None) is False


def test_wordnet_step_downloads_on_yes_and_hints_on_no(monkeypatch, capsys):
    from cotrail.sources import wordnet as W

    state = {"ready": False}
    monkeypatch.setattr(W, "ready", lambda: state["ready"])
    monkeypatch.setattr(W, "download", lambda: state.update(ready=True) or True)
    assert S.ensure_wordnet(False) is False and "rerun `cotrail setup`" in capsys.readouterr().out
    assert S.ensure_wordnet(True) is True and state["ready"]
    assert S.ensure_wordnet(None) is True  # already there: no question


def test_expand_without_wordnet_gives_a_hint_not_a_dash(tmp_path, monkeypatch):
    from cotrail.sources import wordnet as W
    from tests.test_english import TURNS

    monkeypatch.delenv("COTRAIL_QUALITY", raising=False)
    monkeypatch.delenv("COTRAIL_LANG", raising=False)
    monkeypatch.setattr(W, "ready", lambda: False)
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(TURNS)
    monkeypatch.setattr(m._topics(), "name", {})  # a record whose topic has no name
    x = m.expand("t2")
    assert "Topic: -" not in x and "`cotrail setup` downloads it" in x
    monkeypatch.setattr(W, "ready", lambda: True)  # the data is there: an unnamed topic is just unnamed
    assert "Topic: -" in m.expand("t2")


def _setup_env(tmp_path, monkeypatch, tty, answers=()):
    """A project with code and one earlier session; no `claude` CLI; WordNet missing; Graphify and the WordNet
    download recorded instead of run."""
    import cotrail.memory as MM
    from cotrail.sources import wordnet as W

    proj, src = tmp_path / "proj", tmp_path / "transcripts"
    (proj / "app").mkdir(parents=True)
    (proj / "app" / "main.py").write_text("def main():\n    pass\n", "utf-8")
    src.mkdir()
    rec = {"type": "user", "uuid": "u1", "timestamp": "2026-11-01T10:00:00Z", "sessionId": "s1",
           "message": {"role": "user", "content": "For the database we will use Postgres."}}
    (src / "s1.jsonl").write_text(json.dumps(rec) + "\n", "utf-8")
    monkeypatch.setattr(MM, "HOME", tmp_path / "home")
    monkeypatch.setattr(MM, "claude_project_dir", lambda p: src)
    monkeypatch.setattr(S.shutil, "which", lambda name: None)
    calls = []
    monkeypatch.setattr(W, "ready", lambda: "wordnet" in calls)
    monkeypatch.setattr(W, "download", lambda: calls.append("wordnet") or True)
    monkeypatch.setattr(S, "build_code_graph", lambda p: calls.append("graphify") or True)

    class In:
        def isatty(self):
            return tty

    monkeypatch.setattr(S.sys, "stdin", In())
    it = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(it))
    return proj, calls


def _turns(proj):
    return ProjectMemory(proj).s.q("SELECT COUNT(*) FROM turn_meta")[0][0]


def test_setup_without_terminal_only_registers_and_lists_the_skipped(tmp_path, monkeypatch, capsys):
    proj, calls = _setup_env(tmp_path, monkeypatch, tty=False)
    ans = S.run(proj, None, None)
    out = capsys.readouterr().out
    assert ans == {"import": False, "graphify": False, "wordnet": False} and calls == [] and _turns(proj) == 0
    assert (proj / ".mcp.json").exists() and (proj / ".claude" / "settings.local.json").exists()
    for cmd in ("--import-history yes", "--graphify yes", "--wordnet yes"):
        assert f"cotrail setup {cmd}" in out


def test_setup_flags_answer_without_a_terminal(tmp_path, monkeypatch):
    proj, calls = _setup_env(tmp_path, monkeypatch, tty=False)
    ans = S.run(proj, None, None, flags={"import": True, "graphify": True, "wordnet": False})
    assert ans == {"import": True, "graphify": True, "wordnet": False}
    assert calls == ["graphify"] and _turns(proj) == 1


def test_setup_yes_takes_the_defaults(tmp_path, monkeypatch):
    proj, calls = _setup_env(tmp_path, monkeypatch, tty=False)
    ans = S.run(proj, None, True)
    assert ans == {"import": True, "graphify": False, "wordnet": True} and calls == ["wordnet"] and _turns(proj) == 1


def test_setup_asks_everything_first_and_enter_takes_the_defaults(tmp_path, monkeypatch, capsys):
    proj, calls = _setup_env(tmp_path, monkeypatch, tty=True, answers=["", "", ""])
    ans = S.run(proj, None, None)
    out = capsys.readouterr().out
    assert ans == {"import": True, "graphify": False, "wordnet": True} and _turns(proj) == 1
    assert out.index("Setup plan:") < out.index("Imported")  # all questions before any work
    assert "import - yes (answer); graphify - no (answer); wordnet - yes (answer)" in out


def test_code_files_skips_dependencies_and_minified(tmp_path):
    (tmp_path / "node_modules" / "x").mkdir(parents=True)
    (tmp_path / "node_modules" / "x" / "a.js").write_text("x", "utf-8")
    (tmp_path / "static").mkdir()
    (tmp_path / "static" / "lib.min.js").write_text("x", "utf-8")
    assert S.code_files(tmp_path) == 0
    (tmp_path / "app.ts").write_text("x", "utf-8")
    assert S.code_files(tmp_path) == 1


def test_install_for_ai_flags_exist_in_setup_help():
    """INSTALL_FOR_AI.md (public repo root) must not name a flag the CLI does not have."""
    import re
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "INSTALL_FOR_AI.md"
    if not doc.exists():
        pytest.skip("INSTALL_FOR_AI.md lives in the public repository")
    from cotrail import cli

    text = doc.read_text("utf-8")
    flags = set(re.findall(r"(?<![\w-])(--[a-z][a-z-]+)", text))
    import contextlib
    import io

    buf = io.StringIO()
    for cmd in (["setup"], ["decisions"], ["recall"], []):  # the commands the document runs + the global flags
        with contextlib.redirect_stdout(buf), contextlib.suppress(SystemExit):
            cli.main([*cmd, "--help"])
    known = set(re.findall(r"--[a-z][a-z-]+", buf.getvalue())) | {"--lang", "--scope"}
    assert flags <= known, flags - known


def test_setup_lang_is_saved_for_every_store(tmp_path, monkeypatch):
    proj, _calls = _setup_env(tmp_path, monkeypatch, tty=False)
    monkeypatch.delenv("COTRAIL_LANG", raising=False)
    S.run(proj, str(tmp_path / "home"), None, lang="en")
    assert json.loads((tmp_path / "home" / "config.json").read_text("utf-8"))["lang"] == "en"
    m = ProjectMemory(proj, home=tmp_path / "home")
    assert m.lang == "en"


def test_explicit_graphify_yes_rebuilds_an_existing_code_graph(tmp_path, monkeypatch):
    proj, calls = _setup_env(tmp_path, monkeypatch, tty=False)
    monkeypatch.setattr(S, "_has_code_graph", lambda p: True)
    assert S.run(proj, None, None, flags={"import": False, "graphify": True, "wordnet": False})["graphify"] is True
    assert calls == ["graphify"]
    assert "graphify" not in S.run(proj, None, None)  # without the flag an existing graph is not rebuilt
