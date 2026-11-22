"""`ctxgraph setup`: connect the memory to the project in the current directory, in one command.

1. The `ctxgraph` MCP server, registered without any path that could leak into git: with the `claude` CLI -
   `claude mcp add --scope local` (stored in the user's Claude Code config, not in the repository); without it - the
   project's `.mcp.json` gets only the command `ctxgraph-mcp` (`ctxgraph-mcpw` on Windows: no console window; no paths,
   no env). The server takes the project from its working directory.
2. `.claude/settings.local.json`: the Claude Code Stop hook `ctxgraph hook-stop` (the project comes from the hook's
   input; merged, an earlier ctxgraph hook is replaced, other hooks are kept). `settings.local.json` is per-user.
3. Nothing to download by default: recall is BM25 over the stored sentences. `--quality` adds multilingual-e5-base
   (int8 ONNX, ~300 MB, downloaded once after the user agrees; then offline) and fuses it with BM25 by RRF; an
   existing default store is rebuilt for it (pinned rules are kept).
4. All questions come first, once, with defaults on Enter: import this project's earlier Claude Code sessions (yes),
   build a code graph with Graphify when code is found (no), download WordNet data for topic names (yes); with
   `--quality`, download the model (yes). Flags answer them without asking (`--import-history yes|no`,
   `--graphify yes|no`, `--wordnet yes|no`; `-y` takes the defaults). Without a terminal nothing is imported,
   installed or downloaded: only the server and the hook are written, and the end lists what was skipped with the
   commands to do it.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

YES = ("y", "yes", "д", "да")


def _ask(question: str, assume: bool | None, default: bool = False) -> bool:
    """Yes / no. `assume` answers for the user (--yes); Enter takes `default`. Without a terminal nothing is downloaded
    or imported: the answer is no."""
    if assume is not None:
        print(f"{question} [{'y' if assume else 'n'}]")
        return assume
    if not sys.stdin or not sys.stdin.isatty():
        print(f"{question} [n] (no terminal to ask; rerun with --yes to agree)")
        return False
    try:
        ans = input(f"{question} {'[Y/n]' if default else '[y/N]'} ").strip().lower()
        return default if not ans else ans in YES
    except EOFError:  # a terminal that gives no input (Git Bash / mintty pipes): no answer means no
        print("\n  No answer (no input from the terminal); rerun with --yes to agree.")
        return False


def _q(s: str) -> str:
    """Quote a path for the hook command (Claude Code runs hooks through a POSIX-style shell, Git Bash on Windows)."""
    return shlex.quote(s) if os.name != "nt" else f'"{s}"'


def _read_json(p: Path) -> dict:
    if not p.exists() or not p.read_text("utf-8").strip():
        return {}
    data = json.loads(p.read_text("utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{p}: expected a JSON object")
    return data


def _write_json(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", "utf-8")


SERVER = "ctxgraph-mcp"  # console script of the package; the server takes the project from its working directory
SERVER_W = "ctxgraph-mcpw"  # gui script, same server: on Windows a GUI client starting it opens no console window
WINDOWS = os.name == "nt"


def server_command() -> str:
    """`ctxgraph-mcpw` on Windows (a console launcher started by Claude Desktop / Claude Code desktop pops up a console
    window; the GUI one keeps stdio and shows none), `ctxgraph-mcp` elsewhere."""
    return SERVER_W if WINDOWS else SERVER


def mcp_entry(project: Path | None = None, home: str | None = None) -> dict:
    """The server entry for a shared config (.mcp.json, Cursor): a command name only - no paths, no env."""
    return {"type": "stdio", "command": server_command(), "args": []}


def hook_command(project: Path | None = None, home: str | None = None) -> str:
    """The Stop hook: `ctxgraph hook-stop`; the project comes from the hook's input (`cwd`), the stores from --home,
    CTXGRAPH_HOME or ~/.ctxgraph. A --home path lives in settings.local.json, which is per-user and not committed."""
    return "ctxgraph" + (f" --home {_q(Path(home).as_posix())}" if home else "") + " hook-stop"


def _ours(entry: dict) -> bool:
    c = " ".join([str(entry.get("command", "")), *map(str, entry.get("args", []))])
    return "ctxgraph.memory_mcp" in c or SERVER in c


def register_local(project: Path, home: str | None, claude: str) -> tuple[str, str]:
    """`claude mcp add --scope local`: the entry lives in the user's Claude Code config for this project only."""
    cmd = shutil.which(server_command()) or server_command()  # local scope may hold a path: it never reaches the repository
    env = ["-e", f"CTXGRAPH_HOME={Path(home).as_posix()}"] if home else []
    subprocess.run([claude, "mcp", "remove", "--scope", "local", "ctxgraph"], cwd=project, capture_output=True)
    r = subprocess.run([claude, "mcp", "add", "--scope", "local", *env, "ctxgraph", "--", cmd], cwd=project,
                       capture_output=True, text=True)  # fmt: skip
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout or "claude mcp add failed").strip()[:300])
    return "claude mcp add --scope local (your Claude Code config, not the repository)", "added"


def write_mcp(project: Path, home: str | None) -> tuple[Path | str, str]:
    """Local registration when the `claude` CLI is there; otherwise a path-free entry in `.mcp.json`. An entry that an
    earlier version wrote into `.mcp.json` (with absolute paths) is removed once the local one is in place."""
    p = project / ".mcp.json"
    claude = shutil.which("claude")
    if claude:
        try:
            where, state = register_local(project, home, claude)
        except (OSError, RuntimeError) as e:
            print(f"  `claude mcp add` failed ({e}); writing a path-free entry to .mcp.json instead.")
        else:
            data = _read_json(p)
            if _ours(data.get("mcpServers", {}).get("ctxgraph", {})):
                del data["mcpServers"]["ctxgraph"]
                _write_json(p, data)
                print(f"  Removed the old ctxgraph entry from {p}.")
            return where, state
    data = _read_json(p)
    servers = data.setdefault("mcpServers", {})
    new = mcp_entry()
    state = "unchanged" if servers.get("ctxgraph") == new else "updated" if "ctxgraph" in servers else "added"
    servers["ctxgraph"] = new
    _write_json(p, data)
    if home:
        print(f"  Note: .mcp.json holds no paths; set CTXGRAPH_HOME={Path(home).as_posix()} in your environment.")
    if not shutil.which(server_command()):
        print(f"  Note: `{server_command()}` is not on PATH here; install with uv/pipx (see README) so Claude Code can start it.")
    return p, state


def _is_ours(h: dict, kind: str = "hook-stop") -> bool:
    c = str(h.get("command", ""))
    return kind in c and "ctxgraph" in c


def write_hook(project: Path, home: str | None) -> tuple[Path, str]:
    p = project / ".claude" / "settings.local.json"
    data = _read_json(p)
    stop = data.setdefault("hooks", {}).setdefault("Stop", [])
    cmd = hook_command(project, home)
    had = any(_is_ours(h) for g in stop for h in g.get("hooks", []))
    same = any(h.get("command") == cmd for g in stop for h in g.get("hooks", []))
    for g in stop:
        g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
    stop[:] = [g for g in stop if g.get("hooks")]
    stop.append({"hooks": [{"type": "command", "command": cmd, "timeout": 30}]})
    # SessionStart: one line of open "later" items goes into the new session's context (nothing when none is open)
    start = data["hooks"].setdefault("SessionStart", [])
    for g in start:
        g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h, "hook-start")]
    start[:] = [g for g in start if g.get("hooks")]
    start.append({"hooks": [{"type": "command", "command": cmd.replace(" hook-stop", " hook-start"), "timeout": 15}]})
    _write_json(p, data)
    return p, "unchanged" if same else "updated" if had else "added"


def ensure_model(assume: bool | None) -> bool:
    from ctxgraph import model as M

    if M.is_cached():
        print(f"Model: {M.REPO} is already downloaded ({M.snapshot_dir()}); the memory runs offline.")
        return True
    print(f"Model: the memory needs the sentence encoder {M.REPO} (multilingual-e5-base, int8 ONNX, MIT), about "
          f"{M.SIZE_MB} MB, downloaded once from huggingface.co into the Hugging Face cache. After that nothing goes "
          "to the network.")  # fmt: skip
    if not _ask("Download it now?", assume):
        print("  Skipped. The memory will not work until the model is downloaded: rerun `ctxgraph setup`.")
        return False
    try:
        p = M.download()
    except M.DownloadFailed as e:
        print("  " + str(e).replace("\n", "\n  "))
        return False
    print(f"  Downloaded to {p}")
    return True


def check_spacy() -> None:
    from ctxgraph.v2 import english

    if not english.available():
        print("Note: spaCy (en_core_web_sm) is not installed; English concepts in the graph view use the rules "
              "fallback. Recall does not need it. For finer English concepts install the `english` extra, "
              "then `python -m spacy download en_core_web_sm`.")  # fmt: skip


def ensure_wordnet(assume: bool | None) -> bool:
    """WordNet data names the topics of `expand` and filters English concepts; optional, about 10 MB."""
    from ctxgraph.sources import wordnet as W

    if W.ready():
        return True
    try:
        import nltk  # noqa: F401
    except ImportError:
        print("Topic names: need nltk (`pip install nltk`), then rerun `ctxgraph setup`. Recall works without it.")
        return False
    if not _ask(f"Download data for topic names (WordNet, ~{W.SIZE_MB} MB)?", assume, default=True):
        print("  Skipped. `expand` shows topics without names; rerun `ctxgraph setup` to download it later.")
        return False
    try:
        ok = W.download()
    except Exception as e:  # noqa: BLE001 - network / server errors: a hint, not a crash
        print(f"  Download failed ({type(e).__name__}: {e}). Recall works without it; rerun `ctxgraph setup` later.")
        return False
    print(f"  Downloaded to {W.user_dir()}" if ok else "  Download did not complete; rerun `ctxgraph setup` later.")
    return ok


def first_import(project: Path, assume: bool | None, limit: int = 15, ask: bool = True) -> None:
    from ctxgraph.memory import ProjectMemory, claude_project_dir, format_decisions

    src = claude_project_dir(project)
    files = sorted(src.glob("*.jsonl")) if src.is_dir() else []
    m = ProjectMemory(project)
    n = m.s.q("SELECT COUNT(*) FROM turn_meta")[0][0]
    if n:
        print(f"Memory: {n} turns already stored ({m.db_path}); nothing to import on first connection "
              "(`ctxgraph import` adds new sessions).")  # fmt: skip
    elif not files:
        print("Memory: empty; no earlier Claude Code sessions of this project found. New turns are recorded by the hook.")
        return
    else:
        print(f"History: {len(files)} earlier Claude Code session file(s) of this project in {src}.\n"
              "  Only your prompts and the assistant's visible replies are stored (no tool calls, no thinking); "
              "secrets are filtered before storage. Everything stays on this machine.")  # fmt: skip
        if not (_ask("Import them into the project memory?", assume) if ask else assume):
            print("  Skipped. Import later with `ctxgraph import`.")
            return
        r = m.import_claude_code(src, progress=lambda i, k: print(f"\r  {i}/{k}", end="", flush=True))
        print(f"\n  Imported {r['new']} turns of {r['turns']} found.")
    rows = m.decisions(limit)
    print(f"\nDecision chronology (newest first, {len(rows)} shown; `ctxgraph decisions --limit N` for more):\n")
    print(format_decisions(rows))


def enable_quality(project: Path, home: str | None, assume: bool | None) -> bool:
    """The quality mode: onnxruntime installed, the model downloaded, `quality` in <home>/config.json; a store built in
    the default mode is moved aside (to `graph.sqlite.bm25-<time>`) so the next import rebuilds it with vectors."""
    import time

    try:
        import onnxruntime  # noqa: F401
        import tokenizers  # noqa: F401
    except ImportError:
        print("Quality mode needs the `quality` extra (onnxruntime, tokenizers, huggingface_hub). Reinstall with:\n"
              '  uv tool install --reinstall "think-to-recall[quality] @ <the same source>"')  # fmt: skip
        return False
    if not ensure_model(assume):
        return False
    from ctxgraph import memory as MM

    hdir = Path(home) if home else MM.HOME
    hdir.mkdir(parents=True, exist_ok=True)
    cfg = hdir / "config.json"
    data = _read_json(cfg)
    data["quality"] = True
    _write_json(cfg, data)
    print(f"Quality mode: on for new stores ({cfg}).")
    db = hdir / MM.project_slug(project) / "graph.sqlite"
    stored = MM._stored_encoder(db)
    if stored and not stored.startswith("e5-"):
        bak = db.with_name(f"graph.sqlite.bm25-{time.strftime('%Y%m%d-%H%M%S')}")
        db.rename(bak)
        print(f"  The memory of this project was built in the default mode; moved aside to {bak.name} and rebuilt "
              "from the history below (pinned rules are carried over).")  # fmt: skip
        _carry_rules(bak, db)
    return True


def _carry_rules(old: Path, new: Path) -> None:
    import sqlite3

    rows = sqlite3.connect(old).execute("SELECT id, text, ts, origin, fragment, removed FROM pinned_rules").fetchall()
    if not rows:
        return
    new.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(new)
    con.execute("CREATE TABLE IF NOT EXISTS pinned_rules (id TEXT PRIMARY KEY, text TEXT NOT NULL, ts TEXT NOT NULL, "
                "origin TEXT NOT NULL, fragment TEXT NOT NULL DEFAULT '', removed INTEGER NOT NULL DEFAULT 0)")  # fmt: skip
    con.executemany("INSERT OR REPLACE INTO pinned_rules VALUES(?,?,?,?,?,?)", rows)
    con.commit()
    con.close()


CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".go", ".rs", ".java", ".kt", ".cs", ".cpp", ".cc", ".c",
            ".h", ".hpp", ".rb", ".php", ".swift", ".scala", ".lua", ".dart", ".ex", ".zig"}
SKIP_DIRS = {".git", ".venv", "venv", "env", "node_modules", "dist", "build", "__pycache__", ".tox", ".mypy_cache",
             "graphify-out", "site-packages", ".next", "target", "vendor"}
GRAPHIFY_MB = 150


def code_files(project: Path, limit: int = 2000) -> int:
    """How many source files the project has (outside dependencies and build output; minified files are not code)."""
    n = 0
    for _root, dirs, files in os.walk(project):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        n += sum(1 for f in files if Path(f).suffix in CODE_EXT and ".min." not in f)
        if n >= limit:
            break
    return n


def _graphify_cmd() -> list[str] | None:
    exe = shutil.which("graphify")
    if exe:
        return [exe]
    try:
        import graphify  # noqa: F401  (graphifyy installed next to ctxgraph)

        return [sys.executable, "-m", "graphify"]
    except ImportError:
        return None


def _install_graphify() -> bool:
    """`graphifyy` into ctxgraph's own environment: pip, or `uv pip` for a uv tool environment (no pip there)."""
    has_pip = subprocess.run([sys.executable, "-m", "pip", "--version"], capture_output=True).returncode == 0
    if has_pip:
        argv = [sys.executable, "-m", "pip", "install", "-q", "graphifyy"]
    elif shutil.which("uv"):
        argv = ["uv", "pip", "install", "-q", "--python", sys.executable, "graphifyy"]
    else:
        return False
    print("  Installing Graphify (graphifyy, Apache-2.0)...", flush=True)
    return subprocess.run(argv).returncode == 0


def build_code_graph(project: Path) -> bool:
    """Graphify's local AST extraction (no LLM, no key) into `<project>/graphify-out/graph.json`, then import."""
    from ctxgraph import graphify as GF
    from ctxgraph.memory import ProjectMemory

    cmd = _graphify_cmd()
    if cmd is None and _install_graphify():
        import importlib

        importlib.invalidate_caches()
        cmd = _graphify_cmd()
    if cmd is None:
        print("  Could not install Graphify here. Install it (`pip install graphifyy`), then run "
              "`ctxgraph setup --graphify yes`.")  # fmt: skip
        return False
    print("  Building the code graph (local AST, no LLM)...", flush=True)
    r = subprocess.run(cmd + ["extract", str(project), "--code-only"], cwd=project, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)  # fmt: skip
    out = project / "graphify-out" / "graph.json"
    if r.returncode != 0 or not out.exists():
        tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or ["no output"]
        print(f"  Graphify failed: {tail[0]}")
        return False
    g = GF.import_graph(ProjectMemory(project).db_path, out)
    print(f"  Code graph: {g['nodes']} nodes, {g['edges']} edges; {g['links']} links to conversation concepts. "
          "Graphify wrote `graphify-out/` in the project - add it to .gitignore if you do not want it committed.")
    return True


def _has_code_graph(project: Path) -> bool:
    import sqlite3

    from ctxgraph.memory import ProjectMemory

    try:
        con = sqlite3.connect(ProjectMemory(project).db_path)
        try:
            return con.execute("SELECT COUNT(*) FROM code_nodes").fetchone()[0] > 0
        finally:
            con.close()
    except sqlite3.Error:
        return False


def _history_todo(project: Path) -> int:
    """Earlier session files to import (0 when there are none or the store already has turns)."""
    from ctxgraph.memory import ProjectMemory, claude_project_dir

    src = claude_project_dir(project)
    files = sorted(src.glob("*.jsonl")) if src.is_dir() else []
    if not files or ProjectMemory(project).s.q("SELECT COUNT(*) FROM turn_meta")[0][0]:
        return 0
    return len(files)


def questionnaire(project: Path, assume: bool | None, flags: dict, quality: bool) -> dict:
    """Every question once, before any work: {step: True / False} for the steps that apply here. A flag answers
    without asking, `-y` takes the default, a terminal asks (Enter = default), no terminal means no."""
    from ctxgraph.sources import wordnet as W

    qs = []  # (step, question, default)
    n_hist = _history_todo(project)
    if n_hist:
        qs.append(("import", f"Import {n_hist} earlier Claude Code session file(s) of this project? (your prompts and "
                             "the assistant's visible replies; secrets filtered; stays on this machine)", True))
    n_code = code_files(project)
    if n_code and (not _has_code_graph(project) or flags.get("graphify")):  # an explicit yes rebuilds it
        qs.append(("graphify", f"Found {n_code}{'+' if n_code >= 2000 else ''} source files. Build a code graph with "
                               f"Graphify (installs `graphifyy`, ~{GRAPHIFY_MB} MB, local AST, no LLM)?", False))
    try:
        import nltk  # noqa: F401

        if not W.ready():
            qs.append(("wordnet", f"Download data for topic names (WordNet, ~{W.SIZE_MB} MB)?", True))
    except ImportError:
        pass
    if quality:
        from ctxgraph import model as M

        if not M.is_cached():
            qs.append(("model", f"Download the quality model ({M.REPO}, ~{M.SIZE_MB} MB)?", True))
    tty = bool(sys.stdin) and sys.stdin.isatty()
    ans, why = {}, {}
    for key, q, default in qs:
        if flags.get(key) is not None:
            ans[key], why[key] = flags[key], "flag"
        elif assume:
            ans[key], why[key] = default, "default, -y"
        elif tty:
            ans[key], why[key] = _ask(q, None, default), "answer"
        else:
            ans[key], why[key] = False, "no terminal"
    if ans:
        print("Setup plan: " + "; ".join(f"{k} - {'yes' if v else 'no'} ({why[k]})" for k, v in ans.items()) + "\n")
    return ans


SKIP_HINT = {"import": "ctxgraph setup --import-history yes", "graphify": "ctxgraph setup --graphify yes",
             "wordnet": "ctxgraph setup --wordnet yes", "model": "ctxgraph setup --quality -y"}


def save_lang(home: str | None, lang: str) -> Path:
    """The label language for every store under this home: "lang" in <home>/config.json."""
    from ctxgraph import memory as MM

    hdir = Path(home) if home else MM.HOME
    hdir.mkdir(parents=True, exist_ok=True)
    cfg = hdir / "config.json"
    data = _read_json(cfg)
    data["lang"] = lang
    _write_json(cfg, data)
    return cfg


def run(project: Path, home: str | None, assume: bool | None, model: bool = True, history: bool = True,
        quality: bool = False, flags: dict | None = None, lang: str | None = None) -> dict:  # fmt: skip
    project = project.resolve()
    if lang:
        print(f"Labels: {lang} ({save_lang(home, lang)})")
    flags = dict(flags or {})
    if not history:
        flags["import"] = False
    print(f"Project: {project}\n")
    p, st = write_mcp(project, home)
    print(f"MCP server: {st} via {p}")
    p, st = write_hook(project, home)
    print(f"Stop hook: {st} in {p}")
    print("  Restart Claude Code in this folder and approve the `ctxgraph` server when it asks.\n")
    if not model:
        return {}
    ans = questionnaire(project, assume, flags, quality)
    ok = True
    if quality:
        ok = enable_quality(project, home, ans.get("model", True))
    else:
        print("Recall: BM25 over your conversations - works right away, nothing to download. "
              "`ctxgraph setup --quality` adds a 300 MB model for better recall (optional).")  # fmt: skip
    check_spacy()
    if ans.get("wordnet"):
        ans["wordnet"] = ensure_wordnet(True)
    if ok:
        print()
        first_import(project, bool(ans.get("import")), ask=False)
    if ans.get("graphify"):
        print("\nCode graph:")
        ans["graphify"] = build_code_graph(project)
    print("\nGraph view: `ctxgraph view` (add `--3d` for the 3D view).")
    skipped = [k for k, v in ans.items() if not v]
    if skipped:
        print("\nSkipped - to do it later:\n" + "\n".join(f"  {k}: {SKIP_HINT[k]}" for k in skipped))
    return ans
