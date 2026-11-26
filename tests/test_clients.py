"""`cotrail setup --client <name>`: config writers per client (synthetic, temp dirs only) and the turn hook."""

import json
from pathlib import Path

import pytest

from cotrail import clients as C


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A fake user profile and a project folder; nothing outside tmp_path is touched."""
    home = tmp_path / "user"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setenv("APPDATA", str(home / "AppData" / "Roaming"))
    monkeypatch.setenv("LOCALAPPDATA", str(home / "AppData" / "Local"))
    monkeypatch.delenv("CLINE_MCP_SETTINGS_PATH", raising=False)
    proj = tmp_path / "proj"
    proj.mkdir()
    return home, proj


def _j(p: Path) -> dict:
    return json.loads(p.read_text("utf-8"))


def test_cursor_is_path_free_with_hooks_and_rule(env):
    home, proj = env
    (proj / ".cursor").mkdir()
    (proj / ".cursor" / "mcp.json").write_text('{"mcpServers": {"other": {"command": "x"}}}', "utf-8")
    lines = C.write("cursor", proj, None)
    m = _j(proj / ".cursor" / "mcp.json")["mcpServers"]
    assert m["other"] == {"command": "x"}  # the user's own entries are kept
    assert m["cotrail"]["command"] == C.server_name() and m["cotrail"]["env"]["COTRAIL_PROJECT"] == "${workspaceFolder}"
    assert str(proj) not in (proj / ".cursor" / "mcp.json").read_text("utf-8")
    h = _j(proj / ".cursor" / "hooks.json")
    assert h["version"] == 1
    assert [x["command"] for x in h["hooks"]["afterAgentResponse"]] == ["cotrail hook-turn --client cursor"]
    rule = (proj / ".cursor" / "rules" / "cotrail.mdc").read_text("utf-8")
    assert "alwaysApply: true" in rule and "recall" in rule
    assert any("hooks.json" in x for x in lines)
    C.write("cursor", proj, None)  # idempotent: one hook, one block
    h = _j(proj / ".cursor" / "hooks.json")
    assert len(h["hooks"]["beforeSubmitPrompt"]) == 1
    assert (proj / ".cursor" / "rules" / "cotrail.mdc").read_text("utf-8").count(C.BEGIN) == 1


def test_codex_project_toml_hooks_agents(env):
    home, proj = env
    (proj / "AGENTS.md").write_text("# House rules\n\nUse tabs.\n", "utf-8")
    C.write("codex", proj, None)
    toml = (proj / ".codex" / "config.toml").read_text("utf-8")
    assert "[mcp_servers.cotrail]" in toml and f'command = "{C.server_name()}"' in toml and "hooks = true" in toml
    import tomllib

    assert tomllib.loads(toml)["mcp_servers"]["cotrail"]["args"] == []
    h = _j(proj / ".codex" / "hooks.json")["hooks"]
    assert set(h) == {"UserPromptSubmit", "Stop"}
    agents = (proj / "AGENTS.md").read_text("utf-8")
    assert agents.startswith("# House rules") and "Use tabs." in agents and C.BEGIN in agents
    C.write("codex", proj, None)
    assert (proj / ".codex" / "config.toml").read_text("utf-8").count("[mcp_servers.cotrail]") == 1
    assert (proj / "AGENTS.md").read_text("utf-8").count(C.BEGIN) == 1


def test_codex_keeps_existing_features_table(env):
    home, proj = env
    (proj / ".codex").mkdir()
    (proj / ".codex" / "config.toml").write_text("[features]\nweb_search = true\n", "utf-8")
    lines = C.write("codex", proj, None)
    import tomllib

    data = tomllib.loads((proj / ".codex" / "config.toml").read_text("utf-8"))  # still valid: no second [features]
    assert data["features"] == {"web_search": True} and "cotrail" in data["mcp_servers"]
    assert any("hooks = true" in x for x in lines)


def test_gemini_settings_hook_and_context(env):
    home, proj = env
    C.write("gemini", proj, str(proj / "h"))
    s = _j(proj / ".gemini" / "settings.json")
    assert s["mcpServers"]["cotrail"]["command"] == C.server_name()
    assert s["mcpServers"]["cotrail"]["env"]["COTRAIL_HOME"].endswith("/h")
    assert "hook-turn --client gemini" in s["hooks"]["AfterAgent"][0]["hooks"][0]["command"]
    assert C.BEGIN in (proj / "GEMINI.md").read_text("utf-8")


def test_opencode_v2_schema(env):
    home, proj = env
    (proj / "opencode.json").write_text('{"$schema": "https://opencode.ai/config.json"}', "utf-8")
    C.write("opencode", proj, None)
    d = _j(proj / "opencode.json")
    assert d["$schema"] and d["mcp"]["servers"]["cotrail"] == {"type": "local", "command": [C.server_name()]}


@pytest.mark.parametrize("client", ["claude-desktop", "windsurf", "cline"])
def test_global_clients_hold_the_project_in_env(env, client):
    home, proj = env
    lines = C.write(client, proj, None)
    paths = {"claude-desktop": [C.claude_desktop_config()], "windsurf": [home / ".codeium" / "windsurf" / "mcp_config.json"],
             "cline": C.cline_configs()}[client]
    for p in paths:
        assert str(p).startswith(str(home))
        e = _j(p)["mcpServers"]["cotrail"]
        assert e["env"]["COTRAIL_PROJECT"] == proj.as_posix()
    assert any("save this chat" in x for x in lines)  # no hooks there: the one line for the user


def test_claude_desktop_prefers_the_msix_copy(env, monkeypatch):
    home, proj = env
    monkeypatch.setattr(C, "WINDOWS", True)
    v = home / "AppData" / "Local" / "Packages" / "Claude_abc" / "LocalCache" / "Roaming" / "Claude"
    v.mkdir(parents=True)
    (v / "claude_desktop_config.json").write_text("{}", "utf-8")
    assert C.claude_desktop_config() == v / "claude_desktop_config.json"


def test_parse_and_detect(monkeypatch):
    for k in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CURSOR_TRACE_ID", "CURSOR_AGENT", "GEMINI_CLI", "OPENCODE",
              "OPENCODE_BIN_PATH"):
        monkeypatch.delenv(k, raising=False)
    import os

    for k in [k for k in os.environ if k.startswith("CODEX_")]:
        monkeypatch.delenv(k)
    assert C.parse(None) == ["claude-code"]
    assert C.parse("cursor,codex,cursor") == ["cursor", "codex"]
    monkeypatch.setenv("GEMINI_CLI", "1")
    assert C.parse("auto") == ["gemini"]
    with pytest.raises(SystemExit):
        C.parse("vim")


def _store(proj: Path):
    from cotrail.memory import ProjectMemory

    ProjectMemory(proj)  # setup creates the store; hooks never do


def test_hook_turn_pairs_prompt_and_reply(env):
    home, proj = env
    assert C.hook_turn("cursor", json.dumps({"hook_event_name": "beforeSubmitPrompt", "prompt": "hi",
                                             "workspace_roots": [str(proj)]}), None, None, spawn=False) is None
    _store(proj)
    r = C.hook_turn("cursor", json.dumps({"hook_event_name": "beforeSubmitPrompt", "prompt": "Use SQLite or Postgres?",
                                          "conversation_id": "c1", "workspace_roots": [str(proj)]}), None, None, spawn=False)
    assert r == {"pending": "cursor:c1"}
    r = C.hook_turn("cursor", json.dumps({"hook_event_name": "afterAgentResponse", "text": "Go with SQLite.",
                                          "conversation_id": "c1", "workspace_roots": [str(proj)]}), None, None, spawn=False)
    assert [x["role"] for x in r["rows"]] == ["user", "assistant"] and r["session"] == "cursor-c1"
    assert r["file"].read_text("utf-8").count("\n") == 2


def test_hook_turn_codex_and_gemini(env):
    home, proj = env
    _store(proj)
    C.hook_turn("codex", json.dumps({"hook_event_name": "UserPromptSubmit", "prompt": "rename the module",
                                     "session_id": "s", "cwd": str(proj)}), None, None, spawn=False)
    r = C.hook_turn("codex", json.dumps({"hook_event_name": "Stop", "last_assistant_message": "Renamed.",
                                         "session_id": "s", "cwd": str(proj)}), None, None, spawn=False)
    assert [x["text"] for x in r["rows"]] == ["rename the module", "Renamed."]
    r = C.hook_turn("gemini", json.dumps({"hook_event_name": "AfterAgent", "prompt": "q", "prompt_response": "a",
                                          "session_id": "g", "cwd": str(proj)}), None, None, spawn=False)
    assert [x["role"] for x in r["rows"]] == ["user", "assistant"]
    assert C.hook_turn("codex", "not json", None, None, spawn=False) is None


def test_hook_rows_import_through_add_episode(env):
    """The file the hook writes is what `cotrail hook-import --file` reads (run inline here instead of detached)."""
    home, proj = env
    _store(proj)
    C.hook_turn("gemini", json.dumps({"prompt": "Decision: we store dates in UTC.", "prompt_response": "Noted, UTC.",
                                      "session_id": "g", "cwd": str(proj)}), None, None, spawn=False)
    from cotrail.memory import store_dir

    f = next((store_dir(proj) / "hook_turns").glob("*.jsonl"))
    from cotrail.cli import main

    main(["--project", str(proj), "hook-import", "--file", str(f)])
    assert not f.exists()
    from cotrail.memory import ProjectMemory

    assert ProjectMemory(proj).s.q("SELECT COUNT(*) FROM turn_meta")[0][0] == 2


def test_setup_client_cli_and_history_show(env, capsys):
    home, proj = env
    from cotrail.cli import main

    main(["--project", str(proj), "setup", "--client", "cursor,opencode", "--no-model"])
    out = capsys.readouterr().out
    assert "[cursor]" in out and "[opencode]" in out and "not a git repository" in out
    assert (proj / ".cursor" / "mcp.json").exists() and not (proj / ".mcp.json").exists()
    (proj / ".git").mkdir()
    sub = proj / "src"
    sub.mkdir()
    main(["--project", str(sub), "setup", "--client", "gemini", "--no-model"])
    assert (proj / ".gemini" / "settings.json").exists()  # the git root, not the subfolder
    from cotrail import setup as S

    assert "nothing to import" in S.history_preview(proj)
