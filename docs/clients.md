# MCP clients: what `cotrail setup --client <name>` writes, and the sources

Checked against the official docs on 2026-11-26. "Verified" = installation by the one phrase was run in that client
(see the README "Works with" line); the rest follow the docs and are covered by synthetic tests (`tests/test_clients.py`).

| client | server entry | auto-recording | rules / instructions | source |
|---|---|---|---|---|
| Claude Code | `claude mcp add --scope local` or `.mcp.json` | Stop hook (transcript) + SessionStart | MCP server instructions | code.claude.com/docs (hooks, MCP) |
| Cursor | `.cursor/mcp.json`, `env.COTRAIL_PROJECT = ${workspaceFolder}` | `.cursor/hooks.json` v1: `beforeSubmitPrompt` (`prompt`) + `afterAgentResponse` (`text`), paired by `conversation_id` | `.cursor/rules/cotrail.mdc`, `alwaysApply: true` | https://cursor.com/docs/context/mcp, https://cursor.com/docs/agent/hooks, https://cursor.com/docs/context/rules |
| Codex CLI | `.codex/config.toml` `[mcp_servers.cotrail]` (project scope: trusted projects only) | `.codex/hooks.json`: `UserPromptSubmit` (`prompt`) + `Stop` (`last_assistant_message`); needs `[features] hooks = true`; the user reviews and trusts the hooks | `AGENTS.md` block | https://learn.chatgpt.com/docs/extend/mcp?surface=cli, https://learn.chatgpt.com/docs/config-file/config-reference, https://learn.chatgpt.com/codex/hooks, https://learn.chatgpt.com/codex/agent-configuration/agents-md |
| Gemini CLI | `.gemini/settings.json` `mcpServers` | `hooks.AfterAgent` (`prompt` + `prompt_response` in one event) | `GEMINI.md` block | https://geminicli.com/docs/tools/mcp-server/, https://geminicli.com/docs/hooks/reference/ |
| Claude Desktop | `claude_desktop_config.json` (global; MSIX build: the `LocalCache\Roaming\Claude` copy when present), `env.COTRAIL_PROJECT` | none - "save this chat" (`save_chat`) | - | https://modelcontextprotocol.io/docs/develop/connect-local-servers |
| Windsurf | `~/.codeium/windsurf/mcp_config.json` (global) | none - "save this chat" | `AGENTS.md` block | docs.windsurf.com now redirects to docs.devin.ai; the Windsurf MCP path was NOT confirmed there (the Devin page lists `.devin/mcp_config.json`) |
| Cline | `~/.cline/data/settings/cline_mcp_settings.json` (CLI, `CLINE_MCP_SETTINGS_PATH`) + the VS Code extension's `globalStorage/saoudrizwan.claude-dev/settings/cline_mcp_settings.json` when present | none (Cline hooks are SDK plugins, not shell commands) - "save this chat" | `.clinerules/cotrail.md` | https://docs.cline.bot/mcp/configuring-mcp-servers, https://docs.cline.bot/sdk/plugins |
| OpenCode | `opencode.json` `mcp.servers.cotrail` (`type: local`, `command: [...]`; V2 schema) | none yet (plugins are JS; not written) - "save this chat" | `AGENTS.md` block | https://opencode.ai/docs/mcp-servers/, https://opencode.ai/docs/config/, https://opencode.ai/docs/rules/ |

Notes
- Project files hold no absolute paths. Global configs (Claude Desktop, Windsurf, Cline) hold the project path in
  `COTRAIL_PROJECT`: one project per entry; running setup for another project replaces it.
- `hook-turn` returns at once: a prompt waits in `<store>/hook_pending.json`; the reply writes the pair to
  `<store>/hook_turns/*.jsonl` and a detached `cotrail add-episode --file` imports it (secret filter applied). A
  project that was never set up gets no store from a hook.
- Gemini CLI: its docs say it was replaced by Antigravity CLI on 2026-06-18; the writer follows the Gemini CLI docs.
- Unverified details: the Codex `hooks.json` grouping (written in the Claude-Code-like `{matcher?, hooks: [...]}`
  shape), the Cursor per-event fields (from the docs page's event sections), the Windsurf path.
