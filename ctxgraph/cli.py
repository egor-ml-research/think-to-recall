"""`ctxgraph` command line: decision memory for AI assistants.

    ctxgraph setup                  # connect this project: .mcp.json, Stop hook, model, first import + decisions
    ctxgraph import                 # import this project's earlier Claude Code sessions (asks for consent)
    ctxgraph recall "question" [--step "..."]...
    ctxgraph decisions | rules | status
    ctxgraph view [--3d|--cosmos]  # local HTML graph of the memory (2D, 3D or cosmic)
    ctxgraph import-graphify PATH   # add a Graphify code graph (graph.json) to the view
    ctxgraph mcp                    # MCP server (stdio) for Claude Code / Cursor
    ctxgraph hook-stop              # Claude Code Stop hook: queues the transcript (fast, no model load)

All commands work on the project in the current directory (or --project / CTXGRAPH_PROJECT).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _mem(project):
    from ctxgraph.memory import ProjectMemory

    return ProjectMemory(project)


def cmd_import(a) -> None:
    from ctxgraph.memory import claude_project_dir

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
    from ctxgraph import claude_ai_export as CA

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
    m = _mem(a.project)
    k = a.k or (12 if a.detail == "brief" else 6)
    print(m.render(m.recall(a.question, a.step or None, k=k), detail=a.detail))


def cmd_expand(a) -> None:
    print(_mem(a.project).expand(a.id))


def cmd_decisions(a) -> None:
    from ctxgraph.memory import format_decisions

    print(format_decisions(_mem(a.project).decisions(a.limit)))


def cmd_rules(a) -> None:
    m = _mem(a.project)
    if a.add:
        print(f"Pinned as #{m.pin_rule(a.add)}")
    for rid in a.remove or []:
        print(f"#{rid}: " + ("removed" if m.unpin_rule(rid) else "not found"))
    for r in m.rules():
        print(f"- #{r['id']} {r['date']} ({r['origin']}): {r['text']}")


def cmd_status(a) -> None:
    print(json.dumps(_mem(a.project).stats(), ensure_ascii=False, indent=1))


def cmd_view(a) -> None:
    import webbrowser

    from ctxgraph.viewer import export_html

    p = export_html(_mem(a.project), out=a.out, mode="cosmos" if a.cosmos else "3d" if a.three_d else None)
    print(p)
    if not a.no_open:
        webbrowser.open(p.as_uri())


def cmd_hook_stop(a) -> None:
    from ctxgraph.memory import queue_transcript

    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return
    if data.get("transcript_path"):
        queue_transcript(data.get("cwd") or a.project or Path.cwd(), data["transcript_path"])


def cmd_setup(a) -> None:
    from ctxgraph import setup as S

    yn = {"yes": True, "no": False, None: None}
    flags = {"import": yn[a.import_history], "graphify": yn[a.graphify], "wordnet": yn[a.wordnet]}
    S.run(Path(a.project or Path.cwd()), a.home or os.environ.get("CTXGRAPH_HOME"), True if a.yes else None,
          model=not a.no_model, history=not a.no_import, quality=a.quality, flags=flags)
    if a.print_cursor:
        e = S.mcp_entry()
        print("\nCursor - .cursor/mcp.json of the project (no hooks there: turns are saved via the remember tool):\n"
              + json.dumps({"mcpServers": {"ctxgraph": {k: e[k] for k in ("command", "args")}}}, indent=2))


def cmd_import_graphify(a) -> None:
    from ctxgraph import graphify as GF
    from ctxgraph.memory import HOME, project_slug

    db = HOME / project_slug(Path(a.project or Path.cwd()).resolve()) / "graph.sqlite"
    if not db.exists():
        sys.exit(f"No memory for this project yet ({db}); run `ctxgraph setup` first.")
    r = GF.import_graph(db, a.path)
    print(f"Code graph from {r['source']}: {r['nodes']} nodes, {r['edges']} edges ({r['code']} code, "
          f"{r['inferred']} inferred by Graphify); {r['links']} inferred links to conversation concepts "
          "(exact file / symbol names). Shown in `ctxgraph view`.")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="ctxgraph", description=__doc__.split("\n")[0])
    ap.add_argument("--project", default=None, help="project directory (default: current)")
    ap.add_argument("--lang", choices=["en", "ru"], default=None,
                    help="language of the labels in recall / decisions / expand (default: the project's language)")
    ap.add_argument("--home", default=None, help="memory store folder (default: ~/.ctxgraph or CTXGRAPH_HOME)")
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
    p.set_defaults(f=cmd_recall)
    p = sub.add_parser("expand", help="a record in full and the thread of its topic")
    p.add_argument("id", help="the record id shown by recall (#...)")
    p.set_defaults(f=cmd_expand)
    p = sub.add_parser("decisions")
    p.add_argument("--limit", type=int, default=20)
    p.set_defaults(f=cmd_decisions)
    p = sub.add_parser("rules", help="pinned project rules: list, --add, --remove")
    p.add_argument("--add", help="pin a rule (text)")
    p.add_argument("--remove", action="append", help="rule id; repeatable")
    p.set_defaults(f=cmd_rules)
    sub.add_parser("status").set_defaults(f=cmd_status)
    p = sub.add_parser("view")
    p.add_argument("--no-open", action="store_true")
    p.add_argument("--out", help="write the HTML here instead of the memory folder")
    p.add_argument("--3d", dest="three_d", action="store_true", help="open in the 3D view (2D/3D toggle in the page)")
    p.add_argument("--cosmos", action="store_true", help="open in the cosmic view (default: the mode last used in the page)")
    p.set_defaults(f=cmd_view)
    p = sub.add_parser("import-graphify", help="add a Graphify code graph (graphify-out/graph.json) to the view")
    p.add_argument("path", help="graph.json, or the folder with it (graphify-out/ or the repo root)")
    p.set_defaults(f=cmd_import_graphify)
    sub.add_parser("mcp").set_defaults(f=lambda a: __import__("ctxgraph.memory_mcp", fromlist=["main"]).main())
    sub.add_parser("hook-stop").set_defaults(f=cmd_hook_stop)
    p = sub.add_parser("setup", help="connect this project: MCP server, Stop hook; then the questions once (history, "
                                     "code graph, WordNet; --quality: + model)")
    p.add_argument("-y", "--yes", action="store_true",
                   help="take the default answers without asking (import history: yes, Graphify: no, WordNet: yes)")
    p.add_argument("--import-history", choices=["yes", "no"], help="import this project's earlier Claude Code sessions")
    p.add_argument("--graphify", choices=["yes", "no"], help="build a code graph with Graphify when code is found")
    p.add_argument("--wordnet", choices=["yes", "no"], help="download WordNet data for topic names (~10 MB)")
    p.add_argument("--no-model", action="store_true", help="only write the config files")
    p.add_argument("--quality", action="store_true",
                   help="better recall: BM25 + multilingual-e5-base (int8 ONNX, ~300 MB download, needs the `quality` extra)")
    p.add_argument("--no-import", action="store_true", help="same as --import-history no")
    p.add_argument("--print-cursor", action="store_true", help="also print the Cursor MCP config")
    p.set_defaults(f=cmd_setup)
    a = ap.parse_args(argv)
    if a.home:  # before ctxgraph.memory is imported: its HOME is read once
        os.environ["CTXGRAPH_HOME"] = a.home
    if a.lang:
        os.environ["CTXGRAPH_LANG"] = a.lang
    from ctxgraph.model import DownloadFailed, ModelMissing

    try:
        a.f(a)
    except (ModelMissing, DownloadFailed) as e:  # a message for people, not a traceback
        sys.exit(f"ctxgraph: {e}")
    except RuntimeError as e:
        if type(e).__name__ != "EncoderMismatch":
            raise
        sys.exit(f"ctxgraph: {e}")


if __name__ == "__main__":
    main()
