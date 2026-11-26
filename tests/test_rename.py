"""The rename ctxgraph -> cotrail (v0.7.0): old commands, CTXGRAPH_* variables, ~/.ctxgraph in place, setup
replacing what an older version wrote. Also: no document tells anyone to `pip install` the old name (that PyPI name
belongs to someone else's package)."""

import json
import re
import sqlite3
import tomllib
from pathlib import Path

from cotrail import legacy as L

ROOT = Path(__file__).resolve().parent.parent


def test_env_fallback_new_name_wins():
    env = {"CTXGRAPH_LANG": "en", "CTXGRAPH_HOME": "/old", "COTRAIL_HOME": "/new"}
    L.mirror_env(env)
    assert env["COTRAIL_LANG"] == "en" and env["COTRAIL_HOME"] == "/new"


def test_default_home_old_folder_in_place(tmp_path, monkeypatch):
    monkeypatch.delenv("COTRAIL_HOME", raising=False)
    monkeypatch.delenv("CTXGRAPH_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    assert L.default_home() == tmp_path / ".cotrail"
    (tmp_path / ".ctxgraph").mkdir()
    assert L.default_home() == tmp_path / ".ctxgraph"  # used in place, nothing moved
    (tmp_path / ".cotrail").mkdir()
    assert L.default_home() == tmp_path / ".cotrail"
    monkeypatch.setenv("CTXGRAPH_HOME", str(tmp_path / "x"))
    assert L.default_home() == tmp_path / "x"


def test_old_commands_hint_on_stderr_only(monkeypatch, capsys):
    import cotrail.cli
    import cotrail.memory_mcp

    monkeypatch.setattr(cotrail.cli, "main", lambda: None)
    monkeypatch.setattr(cotrail.memory_mcp, "main", lambda: None)
    for f in (L.cli_main, L.mcp_main, L.mcpw_main):
        f()
        out = capsys.readouterr()
        assert out.out == "" and "cotrail" in out.err


def test_pyproject_commands_and_no_old_module():
    p = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))
    sc = {**p["project"]["scripts"], **p["project"]["gui-scripts"]}
    assert sc["cotrail"] == "cotrail.cli:main" and sc["cotrail-mcp"] == sc["cotrail-mcpw"] == "cotrail.memory_mcp:main"
    assert sc["ctxgraph"].startswith("cotrail.legacy:") and sc["ctxgraph-mcpw"].startswith("cotrail.legacy:")
    assert p["tool"]["setuptools"]["packages"]["find"]["include"] == ["cotrail*"]
    assert not (ROOT / "ctxgraph" / "__init__.py").exists()


def test_no_doc_installs_the_old_pypi_name():
    files = [*ROOT.glob("*.md"), *ROOT.glob("*.txt"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "packaging").rglob("*"),
             *(ROOT / "plugins").rglob("*"), *(ROOT / "cotrail").rglob("*.py")]
    bad = re.compile(r"(pip|pipx|uv pip|uv tool|uvx)\s+(install\s+)?(-U\s+|--upgrade\s+|--from\s+)?ctxgraph\b")
    hits = [str(f) for f in files if f.is_file() and f.suffix in {".md", ".txt", ".json", ".py", ".toml", ""}
            and bad.search(f.read_text("utf-8", errors="replace"))]
    assert not hits


def test_setup_replaces_old_entries(tmp_path, monkeypatch):
    from cotrail import setup as S

    monkeypatch.setattr(S.shutil, "which", lambda x: None)
    (tmp_path / ".mcp.json").write_text(json.dumps({"mcpServers": {
        "ctxgraph": {"type": "stdio", "command": "ctxgraph-mcp", "args": []}, "other": {"command": "x"}}}), "utf-8")
    S.write_mcp(tmp_path, None)
    servers = json.loads((tmp_path / ".mcp.json").read_text("utf-8"))["mcpServers"]
    assert "ctxgraph" not in servers and "cotrail" in servers and "other" in servers
    st = tmp_path / ".claude" / "settings.local.json"
    st.parent.mkdir()
    st.write_text(json.dumps({"hooks": {
        "Stop": [{"hooks": [{"type": "command", "command": "ctxgraph hook-stop"}]}],
        "SessionStart": [{"hooks": [{"type": "command", "command": "ctxgraph hook-start"}]}]}}), "utf-8")
    S.write_hook(tmp_path, None)
    cmds = [h["command"] for g in json.loads(st.read_text("utf-8"))["hooks"].values() for x in g for h in x["hooks"]]
    assert sorted(cmds) == ["cotrail hook-start", "cotrail hook-stop"]


def test_clients_replace_old_blocks(tmp_path):
    from cotrail import clients as C

    md = tmp_path / "AGENTS.md"
    md.write_text("# mine\n\n<!-- ctxgraph:begin -->\nold\n<!-- ctxgraph:end -->\n", "utf-8")
    C.write_block(md)
    t = md.read_text("utf-8")
    assert "# mine" in t and "ctxgraph:begin" not in t and t.count(C.BEGIN) == 1
    js = tmp_path / "mcp.json"
    js.write_text(json.dumps({"mcpServers": {"ctxgraph": {"command": "ctxgraph-mcp"}}}), "utf-8")
    C._put(js, ("mcpServers", "cotrail"), {"command": "cotrail-mcp"})
    assert list(json.loads(js.read_text("utf-8"))["mcpServers"]) == ["cotrail"]
    toml = tmp_path / "config.toml"
    toml.write_text("a = 1\n\n# >>> ctxgraph (written by `ctxgraph setup`)\n[mcp_servers.ctxgraph]\n# <<< ctxgraph\n", "utf-8")
    C._toml_block(toml, "[mcp_servers.cotrail]")
    t = toml.read_text("utf-8")
    assert "ctxgraph" not in t and "[mcp_servers.cotrail]" in t and t.startswith("a = 1")


def test_git_hook_old_block_stripped():
    import pytest

    A = pytest.importorskip("cotrail.autosync")  # team memory: private build only

    old = f"#!/bin/sh\necho mine\n{A.OLD_BEGIN}\npython -m ctxgraph.cli x\n{A.OLD_END}\n"
    assert A._strip(old) == "#!/bin/sh\necho mine\n"


def test_migrate_home_copies_and_keeps_old(tmp_path):
    old, new = tmp_path / ".ctxgraph", tmp_path / ".cotrail"
    (old / "proj").mkdir(parents=True)
    con = sqlite3.connect(old / "proj" / "graph.sqlite")
    con.execute("CREATE TABLE episode (id INTEGER)")
    con.executemany("INSERT INTO episode VALUES (?)", [(i,) for i in range(5)])
    con.commit()
    con.close()
    (old / "config.json").write_text("{}", "utf-8")
    assert L.migrate_home(old, new, log=lambda *a: None) == 0
    assert (old / "proj" / "graph.sqlite").exists() and (new / "config.json").exists()
    assert L._counts(new / "proj" / "graph.sqlite") == {"episode": 5}
    assert L.migrate_home(old, new, log=lambda *a: None) == 1  # never over an existing folder
