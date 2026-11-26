"""`cotrail` command line: decision memory for AI assistants.

    cotrail setup                  # connect this project: .mcp.json, Stop hook, model, first import + decisions
    cotrail import                 # import this project's earlier Claude Code sessions (asks for consent)
    cotrail recall "question" [--step "..."]...
    cotrail decisions | rules | status
    cotrail projects               # every project with a memory: path, records, last record
    cotrail pin-rule [--global] "..."   # pin a rule for this project, or for all projects (--global)
    cotrail view [--3d|--cosmos]  # local HTML graph of the memory (2D, 3D or cosmic)
    cotrail import-graphify PATH   # add a Graphify code graph (graph.json) to the view
    cotrail mcp                    # MCP server (stdio) for Claude Code / Cursor
    cotrail hook-stop              # Claude Code Stop hook: queues the transcript (fast, no model load)
    cotrail hook-start             # Claude Code SessionStart hook: one line of open "later" items
    cotrail later                  # open "later" items (chat + .beads/*.jsonl, read-only)
    cotrail overview               # a map of the project: code areas + their newest decisions (<= ~600 tokens)

All commands work on the project in the current directory (or --project / COTRAIL_PROJECT).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _mem(project):
    from cotrail.memory import ProjectMemory

    return ProjectMemory(project)


def _project(a) -> Path:
    return Path(a.project or os.environ.get("COTRAIL_PROJECT") or Path.cwd()).resolve()


def _existing(a):
    """The memory of this folder's project for a read command; never creates a store. No store here: the only known
    project is used (said in one line), otherwise the known projects are listed and the command stops."""
    from cotrail.memory import known_projects, store_exists, ui_lang

    if store_exists(_project(a)):
        return _mem(a.project)
    known, ru = known_projects(), ui_lang() == "ru"
    if len(known) == 1 and known[0]["exact"]:
        path = known[0]["path"]
        print(f"В этой папке нет памяти cotrail; беру единственный проект: {path}" if ru
              else f"No cotrail memory in this folder; using the only project with one: {path}", file=sys.stderr)
        return _mem(path)
    if not known:
        sys.exit("Памяти cotrail пока нет ни у одного проекта: запустите `cotrail setup` в папке проекта." if ru
                 else "No project has a cotrail memory yet: run `cotrail setup` in the project folder.")
    names = "\n".join(f"  {k['path']}" for k in known)
    sys.exit(f"В этой папке нет памяти cotrail. Известные проекты:\n{names}\n"
             "Запустите из папки проекта или добавьте --project <путь>." if ru else
             f"No cotrail memory in this folder. Known projects:\n{names}\n"
             "Run from the project folder or add --project <path>.")


def _json(rows) -> None:
    """`--json`: UTF-8 whatever the console code page, no labels or colors."""
    sys.stdout.buffer.write((json.dumps(rows, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
    sys.stdout.flush()


def _rule_row(r: dict) -> str:
    return f"- #{r['id']} {r['date']} ({r['origin']}): {r['text']}"


def cmd_import(a) -> None:
    from cotrail.memory import claude_project_dir

    src = Path(a.source) if a.source else claude_project_dir(a.project or Path.cwd())
    files = sorted(src.glob("*.jsonl")) if src.is_dir() else []
    if not files:
        sys.exit(f"No Claude Code transcripts in {src}")
    print(f"Will read {len(files)} local transcript file(s) from {src}\n"
          "Only your prompts and the assistant's visible replies are stored (secrets are filtered before storage).")  # fmt: skip
    if not a.yes and not _consent("Import into local memory? [y/N] "):
        sys.exit("Cancelled.")
    m = _mem(a.project)
    r = m.import_claude_code(src, progress=lambda i, n: print(f"  {i}/{n}", flush=True))
    print(f"Imported {r['new']} new turns ({r['summaries']} from summaries) of {r['turns']}. Store: {m.db_path}")


def cmd_import_claude_ai(a) -> None:
    from cotrail import claude_ai_export as CA

    conv, projects = CA.load(a.export)
    filters = {"match": a.match, "project": a.project_name, "since": a.since, "ids": a.id}
    chosen = CA.select(conv, projects, **filters)
    rows = [r for r in CA.summary(chosen, projects)]
    for r in rows:
        print(f"  {r['date']}  {r['id'][:8]}  {r['messages']:4d} msg  {r['title'][:70]}"
              + (f"  [{r['project']}]" if r["project"] else ""))  # fmt: skip
    print(f"{len(rows)} of {len(conv)} conversations selected"
          + ("" if any(filters.values()) else " (no filter: the whole account)"))  # fmt: skip
    if a.list or not rows:
        return
    print("Only your messages and the assistant's visible text are stored (no thinking, tool calls, attachments); "
          "secrets are filtered before storage. Everything stays on this machine.")  # fmt: skip
    if not a.yes and not _consent("Import these into local memory? [y/N] "):
        sys.exit("Cancelled.")
    m = _mem(a.project)
    r = m.import_claude_ai(a.export, progress=lambda i, n: print(f"  {i}/{n}", flush=True), **filters)
    sk = ", ".join(f"{k} {v}" for k, v in sorted(r["skipped"].items())) or "nothing"
    print(f"Imported {r['new']} new turns of {r['turns']} from {r['conversations']} conversations; skipped: {sk}. "
          f"Store: {m.db_path}")


def _consent(question: str) -> bool:
    """Ask in a terminal; without one (a script, a hook, CI) do not wait for input: say how to agree instead."""
    if not sys.stdin or not sys.stdin.isatty():
        sys.exit("No terminal to ask for consent. Run the same command with -y to agree.")
    try:
        return input(question).strip().lower() in ("y", "yes", "д", "да")
    except EOFError:
        sys.exit("No answer. Run the same command with -y to agree.")


def cmd_recall(a) -> None:
    m = _existing(a)
    k = a.k or (12 if a.detail == "brief" else 6)
    hits = m.recall(a.question, a.step or None, k=k)
    if a.json:
        return _json(m.recall_json(hits))
    print(m.render(hits, detail=a.detail))


def cmd_expand(a) -> None:
    print(_existing(a).expand(a.id))


def cmd_decisions(a) -> None:
    from cotrail.memory import format_decisions

    m = _existing(a)
    if a.json:
        return _json(m.decisions_json(a.limit))
    print(format_decisions(m.decisions(a.limit)))


def cmd_rules(a) -> None:
    from cotrail import memory as M

    if a.global_:  # rules shared by all projects: no project store needed
        if a.add:
            print(f"Pinned as #{M.pin_global_rule(a.add)} (global)")
        for rid in a.remove or []:
            print(f"#{rid}: " + ("removed (global)" if M.unpin_global_rule(rid) else "not found"))
        if a.json:
            return _json([{"id": r["id"], "date": r["date"], "status": "rule", "topic": "", "text": r["text"],
                           "origin": "global"} for r in M.global_rules()])
        for r in M.global_rules():
            print(_rule_row(r))
        return
    remove = list(a.remove or [])
    if remove and not a.add and not M.store_exists(_project(a)):  # a global rule can be removed from any folder
        for rid in [r for r in remove if M.unpin_global_rule(r)]:
            print(f"#{rid}: removed (global)")
            remove.remove(rid)
        if not remove:
            return
    m = _existing(a)
    if a.add:
        print(f"Pinned as #{m.pin_rule(a.add)}")
    for rid in remove:
        if m.unpin_rule(rid):
            print(f"#{rid}: removed")
        else:
            print(f"#{rid}: " + ("removed (global)" if M.unpin_global_rule(rid) else "not found"))
    if a.json:
        return _json(m.rules_json())
    for r in m.rules():
        print(_rule_row(r))


def cmd_pin_rule(a) -> None:
    from cotrail import memory as M

    if a.global_:
        print(f"Pinned as #{M.pin_global_rule(a.text)} (global)")
    else:
        print(f"Pinned as #{_existing(a).pin_rule(a.text)}")


def cmd_projects(a) -> None:
    from cotrail.memory import known_projects, projects_json, ui_lang

    if a.json:
        return _json(projects_json())
    rows = sorted(known_projects(), key=lambda k: k["last"], reverse=True)
    ru = ui_lang() == "ru"
    if not rows:
        print("Памяти cotrail пока нет ни у одного проекта." if ru else "No project has a cotrail memory yet.")
        return
    print("последняя   записей  проект" if ru else "last        records  project")
    for k in rows:
        print(f"{k['last'] or '—':10}  {k['records']:7d}  {k['path']}")


def cmd_status(a) -> None:
    print(json.dumps(_existing(a).stats(), ensure_ascii=False, indent=1))


def cmd_view(a) -> None:
    import webbrowser

    from cotrail.viewer import export_html

    if a.live:  # the page and calls.jsonl on 127.0.0.1: pulses of the assistant's memory calls as they happen
        from cotrail.viewer import serve

        def ready(url):
            print(f"{url}  (Ctrl+C - stop)", flush=True)
            if not a.no_open:
                webbrowser.open(url)

        serve(_existing(a), port=a.port, on_ready=ready)
        return
    mode = "cosmos" if a.cosmos else "3d" if a.three_d else None
    p = export_html(_existing(a), out=a.out, mode=mode)
    print(p)
    if not a.no_open:
        webbrowser.open(p.as_uri())


def cmd_hook_stop(a) -> None:
    from cotrail.memory import queue_transcript

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if data.get("transcript_path"):
        queue_transcript(data.get("cwd") or a.project or Path.cwd(), data["transcript_path"])


def cmd_hook_turn(a) -> None:
    """A client hook (Cursor, Codex, Gemini CLI): queue the turn and return at once; a hook never fails the agent."""
    from cotrail import clients as C

    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
        C.hook_turn(a.client, raw, a.project, a.home)
    except Exception:  # noqa: BLE001
        pass
    out = C.HOOK_REPLY.get(a.client, "")
    if out:
        sys.stdout.write(out + "\n")
        sys.stdout.flush()


def cmd_hook_start(a) -> None:
    """Claude Code SessionStart hook: one line of open "later" items for the new session (nothing when none)."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        data = {}
    try:
        from cotrail.memory import ProjectMemory, global_rules, store_exists, ui_lang

        project = Path(data.get("cwd") or a.project or Path.cwd())
        lines, lang = [], None
        if store_exists(project):
            m = ProjectMemory(project)
            lines.append(m.later_line())
            lang = m.lang
        g = global_rules()  # rules for all projects: in the SessionStart line of every project, with or without a store
        if g:
            head = "Общие правила" if (lang or ui_lang()) == "ru" else "Global rules"
            lines.insert(0, f"{head}: " + "; ".join(f"#{r['id']} {r['text']} (global)" for r in g))
        out = "\n".join(x for x in lines if x)
        if out:  # Claude Code reads hook output as UTF-8 (a Windows pipe would get the console code page)
            sys.stdout.buffer.write((out + "\n").encode("utf-8"))
            sys.stdout.flush()
    except Exception:  # noqa: BLE001 - a hook never fails the session
        pass


def cmd_overview(a) -> None:
    from cotrail.overview import overview

    print(overview(_existing(a), max_chars=a.max_chars))


def cmd_later(a) -> None:
    from cotrail.memory import format_later

    m = _existing(a)
    if a.json:
        return _json(m.later_json(a.limit))
    print(format_later(m.later(a.limit)))


def cmd_setup(a) -> None:
    from cotrail import setup as S

    from cotrail import clients as C

    yn = {"yes": True, "no": False, "show": "show", None: None}
    flags = {"import": yn[a.import_history], "graphify": yn[a.graphify], "wordnet": yn[a.wordnet]}
    S.run(Path(a.project or Path.cwd()), a.home or os.environ.get("COTRAIL_HOME"), True if a.yes else None,
          model=not a.no_model, history=not a.no_import, quality=a.quality, flags=flags,
          lang=a.setup_lang or a.lang, clients=C.parse(a.client))
    if a.print_cursor:
        e = S.mcp_entry()
        print("\nCursor - .cursor/mcp.json of the project (no hooks there: turns are saved via the remember tool):\n"
              + json.dumps({"mcpServers": {"cotrail": {k: e[k] for k in ("command", "args")}}}, indent=2))


def cmd_import_graphify(a) -> None:
    from cotrail import graphify as GF
    from cotrail.memory import HOME, project_slug

    db = HOME / project_slug(Path(a.project or Path.cwd()).resolve()) / "graph.sqlite"
    if not db.exists():
        sys.exit(f"No memory for this project yet ({db}); run `cotrail setup` first.")
    r = GF.import_graph(db, a.path)
    print(f"Code graph from {r['source']}: {r['nodes']} nodes, {r['edges']} edges ({r['code']} code, "
          f"{r['inferred']} inferred by Graphify); {r['links']} inferred links to conversation concepts "
          "(exact file / symbol names). Shown in `cotrail view`.")


def cmd_migrate_home(a) -> None:
    from cotrail.legacy import migrate_home

    raise SystemExit(migrate_home())


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="cotrail", description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=None, help="project directory (default: current)")
    ap.add_argument("--lang", choices=["en", "ru"], default=None,
                    help="language of the labels in recall / decisions / expand (default: the project's language)")
    ap.add_argument("--home", default=None, help="memory store folder (default: ~/.cotrail or COTRAIL_HOME)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("import")
    p.add_argument("--source", help="directory with Claude Code .jsonl transcripts (default: this project's)")
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(f=cmd_import)
    p = sub.add_parser("import-claude-ai", help="import chats from a claude.ai data export (.zip)")
    p.add_argument("export", help="the export .zip, its unpacked folder, or conversations.json")
    p.add_argument("--list", action="store_true", help="only list the selected conversations")
    p.add_argument("--match", help="regex over the title and the first messages")
    p.add_argument("--project-name", help="claude.ai project name (substring)")
    p.add_argument("--since", help="YYYY-MM-DD")
    p.add_argument("--id", action="append", help="conversation uuid (prefix); repeatable")
    p.add_argument("-y", "--yes", action="store_true")
    p.set_defaults(f=cmd_import_claude_ai)
    p = sub.add_parser("recall")
    p.add_argument("question")
    p.add_argument("--step", action="append")
    p.add_argument("-k", type=int, default=None, help="records (default 6; 12 with --detail brief)")
    p.add_argument("--detail", choices=["full", "brief", "mixed"], default="full",
                   help="full: the records' text (default); brief: one line each with #id; mixed: the best in full")
    p.add_argument("--json", action="store_true", help="a JSON array (README: JSON output) instead of the text block")
    p.set_defaults(f=cmd_recall)
    p = sub.add_parser("expand", help="a record in full and the thread of its topic")
    p.add_argument("id", help="the record id shown by recall (#...)")
    p.set_defaults(f=cmd_expand)
    p = sub.add_parser("decisions")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--json", action="store_true", help="a JSON array (README: JSON output)")
    p.set_defaults(f=cmd_decisions)
    p = sub.add_parser("rules", help="pinned rules (this project's + global ones): list, --add, --remove")
    p.add_argument("--add", help="pin a rule (text)")
    p.add_argument("--remove", action="append", help="rule id; repeatable")
    p.add_argument("--global", dest="global_", action="store_true", help="the rules shared by all projects")
    p.add_argument("--json", action="store_true", help="a JSON array (README: JSON output)")
    p.set_defaults(f=cmd_rules)
    p = sub.add_parser("pin-rule", help="pin a standing rule for this project (or for all projects: --global)")
    p.add_argument("text")
    p.add_argument("--global", dest="global_", action="store_true", help="for all projects (~/.cotrail/global_rules)")
    p.set_defaults(f=cmd_pin_rule)
    p = sub.add_parser("projects", help="every project with a memory: path, records, date of the last record")
    p.add_argument("--json", action="store_true", help="a JSON array (README: JSON output)")
    p.set_defaults(f=cmd_projects)
    sub.add_parser("status").set_defaults(f=cmd_status)
    sub.add_parser("migrate-home", help="copy the old ~/.ctxgraph to ~/.cotrail, check record counts (old kept)").set_defaults(f=cmd_migrate_home)
    p = sub.add_parser("view")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--out", help="write the HTML here instead of the memory folder")
    p.add_argument("--3d", dest="three_d", action="store_true", help="open in the 3D view (2D/3D toggle in the page)")
    p.add_argument("--cosmos", action="store_true", help="open in the cosmic view (default: the mode last used in the page)")
    p.add_argument("--live", action="store_true", help="«Живая память»: serve the page on 127.0.0.1 with live pulses "
                   "of the memory's MCP calls (calls.jsonl)")
    p.add_argument("--port", type=int, default=8765, help="port for --live (the next free one if busy)")
    p.set_defaults(f=cmd_view)
    p = sub.add_parser("import-graphify", help="add a Graphify code graph (graphify-out/graph.json) to the view")
    p.add_argument("path", help="graph.json, or the folder with it (graphify-out/ or the repo root)")
    p.set_defaults(f=cmd_import_graphify)
    sub.add_parser("mcp").set_defaults(f=lambda a: __import__("cotrail.memory_mcp", fromlist=["main"]).main())
    sub.add_parser("hook-stop").set_defaults(f=cmd_hook_stop)
    sub.add_parser("hook-start").set_defaults(f=cmd_hook_start)
    p = sub.add_parser("hook-turn", help="(client hooks: Cursor, Codex, Gemini CLI) record a prompt / a reply")
    p.add_argument("--client", required=True)
    p.set_defaults(f=cmd_hook_turn)
    p = sub.add_parser("hook-import", help="(started by hook-turn) import the turns a client hook wrote")
    p.add_argument("--file", required=True)
    p.set_defaults(f=lambda a: __import__("cotrail.clients", fromlist=["import_file"]).import_file(
        Path(a.project or Path.cwd()), a.file, a.home))
    p = sub.add_parser("overview", help="a map of the project (<= ~600 tokens): code areas + their newest decisions")
    p.add_argument("--max-chars", type=int, default=1500)
    p.set_defaults(f=cmd_overview)
    p = sub.add_parser("later", help="open 'later' items: deferred decisions, 'later' answers, deferred Beads issues")
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--json", action="store_true", help="a JSON array (README: JSON output)")
    p.set_defaults(f=cmd_later)
    p = sub.add_parser("setup", help="connect this project: MCP server, Stop hook; then the questions once (history, "
                                     "code graph, WordNet; --quality: + model)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="take the default answers without asking (import history: yes, Graphify: no, WordNet: yes)")
    p.add_argument("--import-history", choices=["yes", "no", "show"],
                   help="import this project's earlier Claude Code sessions; `show` lists them and imports nothing")
    p.add_argument("--client", help="where to register: claude-code (default), claude-desktop, cursor, codex, gemini, "
                                    "windsurf, cline, opencode, auto (detect); several: comma-separated")
    p.add_argument("--graphify", choices=["yes", "no"], help="build a code graph with Graphify when code is found")
    p.add_argument("--wordnet", choices=["yes", "no"], help="download WordNet data for topic names (~10 MB)")
    p.add_argument("--lang", dest="setup_lang", choices=["en", "ru"],
                   help="language of the memory's labels, saved for every project (default: each project's language)")
    p.add_argument("--no-model", action="store_true", help="only write the config files")
    p.add_argument("--quality", action="store_true",
                   help="better recall: BM25 + multilingual-e5-base (int8 ONNX, ~300 MB download, needs the `quality` extra)")
    p.add_argument("--no-import", action="store_true", help="same as --import-history no")
    p.add_argument("--print-cursor", action="store_true", help="also print the Cursor MCP config")
    p.set_defaults(f=cmd_setup)
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):  # a cp1251 console / pipe has no "→": replace, never crash an agent's call
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass
    if a.home:  # before cotrail.memory is imported: its HOME is read once
        os.environ["COTRAIL_HOME"] = a.home
    if a.lang:
        os.environ["COTRAIL_LANG"] = a.lang
    from cotrail.model import DownloadFailed, ModelMissing

    try:
        a.f(a)
    except (ModelMissing, DownloadFailed) as e:  # a message for people, not a traceback
        sys.exit(f"cotrail: {e}")
    except RuntimeError as e:
        if type(e).__name__ != "EncoderMismatch":
            raise
        sys.exit(f"cotrail: {e}")


if __name__ == "__main__":
    main()
