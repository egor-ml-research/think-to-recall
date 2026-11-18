# ctxgraph — decision memory for AI coding assistants

Your assistant forgets what you decided last week. ctxgraph remembers it.

ctxgraph is a local memory of your conversations with Claude Code, organised around **decisions**: what you decided
to do, what you decided not to do, what you put on hold, and when the assistant reported it done. It runs as an MCP
server next to Claude Code. Before answering, the assistant can ask it what was decided earlier in the project. The
answer comes with dates and statuses, and every turn is recorded automatically.

- **Local only.** One SQLite file per project on your machine. No cloud, no account, no LLM calls to build the memory.
- **Works on the history you already have.** On first connection it imports your earlier Claude Code sessions of the
  project (if you agree) and shows the decision chronology right away.
- **One command to connect.** `ctxgraph setup` writes the MCP config and the hook for the project you are in.
- **A graph you can look at.** `ctxgraph view` opens a local 2D or 3D map of topics, concepts and decisions. A
  [Graphify](https://github.com/Graphify-Labs/graphify) code graph can be shown on the same map.

## Install

One line (Python 3.11+ and [uv](https://docs.astral.sh/uv/)), from the project you want to connect:

```bash
uv tool install "think-to-recall @ git+https://github.com/egor-ml-research/think-to-recall@launch" && ctxgraph setup
```

With [pipx](https://pipx.pypa.io/) instead of uv:

```bash
pipx install "think-to-recall @ git+https://github.com/egor-ml-research/think-to-recall@launch" && ctxgraph setup
```

The package is not on PyPI yet; both commands install this branch from GitHub. No PyTorch: the encoder runs as int8
ONNX on onnxruntime. The install is about 200 MB, plus about 300 MB for the model that `ctxgraph setup` downloads.
For finer English concepts in the graph view (spaCy parser, WordNet), install `think-to-recall[english]` instead;
recall does not need it.

`setup` does four things, and asks before the two that need your consent:

1. Registers the `ctxgraph` MCP server **without any path that could end up in git**. With the `claude` CLI on
   PATH it runs `claude mcp add --scope local ctxgraph -- ctxgraph-mcp`: the entry is kept in your own Claude Code
   config for this project, not in the repository. Without the CLI it adds to the project's `.mcp.json` only
   `{"command": "ctxgraph-mcp"}` (no home folder, no Python path, no project path); other servers in that file are
   kept. The server takes the project from the folder Claude Code starts it in.
2. Adds a Claude Code **Stop hook** `ctxgraph hook-stop` to `.claude/settings.local.json`. After every turn it queues
   the session transcript; the project comes from the hook's input. The hook is fast: it only appends a path, and the
   server reads the transcript later. Other hooks and settings are kept, and an earlier ctxgraph hook is replaced.
3. **Asks before downloading** the sentence encoder: multilingual-e5-base as int8 ONNX
   ([Xenova/multilingual-e5-base](https://huggingface.co/Xenova/multilingual-e5-base), an export of
   [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base), MIT; about 300 MB, a
   pinned revision), run by onnxruntime on the CPU. No PyTorch. The download happens once. After that every ctxgraph
   process runs with the Hugging Face hub in offline mode, and the memory never touches the network. The MCP server
   will not start a download nobody agreed to: without the model it answers "run `ctxgraph setup`". If the download
   fails (no network, proxy), setup says what was not downloaded, from where, and to rerun `ctxgraph setup`; a
   partial download resumes.
4. **Asks before importing** the project's earlier Claude Code sessions (`~/.claude/projects/<project>/*.jsonl`).
   It then prints the **decision chronology**, so you see what the memory knows straight away.

Restart Claude Code in the project folder and approve the `ctxgraph` server when it asks.

### Recommended `.gitignore`

The memory itself lives outside the project (`~/.ctxgraph/<project>/`), and `setup` writes no paths into shared
files. Still, keep the per-user and generated files out of the repository:

```gitignore
# ctxgraph: per-user Claude Code settings (the Stop hook) and local data
.claude/settings.local.json
.ctxgraph/
```

`.ctxgraph/` matters if you point `--home` / `CTXGRAPH_HOME` inside the project. `ctxgraph view` writes its HTML
into the memory folder; if you pass `--out` inside the project, ignore that file too: it embeds quotes from your
conversations. If your team does not use ctxgraph, keep the `ctxgraph` entry out of a shared `.mcp.json`
(with the `claude` CLI, setup does not write it there at all).

Options: `--yes` agrees to both questions (for scripts), `--no-model` only writes the config files, `--no-import`
skips the history, `--home DIR` keeps the stores somewhere other than `~/.ctxgraph`, and `--print-cursor` prints a
Cursor config. Cursor has no hooks, so there turns are saved through the `remember` tool.

## Use

In Claude Code the assistant gets these tools:

| tool | what it does |
|---|---|
| `recall(question, steps)` | finds earlier turns relevant to the question and to the assistant's reasoning steps |
| `decisions(limit)` | the decision chronology, newest first, with confirmations and reports |
| `rules`, `pin_rule`, `unpin_rule` | the project's pinned standing rules |
| `remember(text)` | save one statement explicitly |
| `import_history` | import earlier sessions (only when you ask), then show the chronology |
| `forget(episode)` | hide one turn from recall |
| `memory_status`, `show_graph` | what is stored; the path of the graph view |

The same things are available from the terminal:

```bash
ctxgraph decisions --limit 30
```

```bash
ctxgraph recall "which encoder do we use" --step "an earlier decision about the model" --step "a size limit the user set"
```

```bash
ctxgraph rules --add "Never push to main without asking"
```

```bash
ctxgraph import
```

```bash
ctxgraph view --3d
```

## How recall works

**One unit = your turn plus the assistant's report.** A turn of yours and the assistant's last message before your
next turn form one unit. That last message is the report of what was done. It is shown nested under your request and
does not take a result slot of its own. The assistant's intermediate messages ("running the tests now…") are
progress and are not searched.

**Main line + periphery.** `recall` first searches by the question itself (dense retrieval with e5; a turn is scored
by its best sentence). That is the **main line**: it comes first and is never displaced. The assistant also passes
1–3 short **reasoning steps**, such as "an earlier decision about this component" or "a constraint the user stated".
Turns found only through those steps form the **periphery**. They are added after the main line, without duplicates,
only in the space left in the block. The periphery is how a memory that looks unrelated to the question still turns
up: a constraint you mentioned once, three weeks ago, in another context.

**Statuses and chronology.** Every remembered sentence has a status, found by rules (no LLM):

- your sentences with decision cues are decisions: *do*, *not do*, or *on hold*;
- the assistant's sentences are *done* when they report finished work (a commit, "fixed", "published"), and
  *proposal, not applied* when they offer or draft something.

Results are shown oldest first, each with its date and status, so a later decision that changed an earlier one comes
after it. `decisions` lists the chronology newest first. A
decision is followed by the report that carried it out (date, commit), when one is found. A decision on hold is
followed by its later confirmation and execution.

**Pinned rules.** Standing rules you state ("always…", "never…", "by default…", "keys only in `.env`") are pinned and
shown at the top of every recall result, whatever the question. You can also pin or unpin rules by hand.

**Short confirmations.** A short reply of yours (up to three words, not a question) has no content of its own, for
example "yes", "go ahead", "not now" or "done". It is read as an answer to the assistant's previous message. "Yes" /
"go ahead" confirm the assistant's proposal, "no" rejects it, "later" defers it, and "done" closes a request the
assistant made to you. The result is shown on that message ("proposal → confirmed by the user on 2026-11-18"). The
short reply gets no search slot of its own, and the report that follows it belongs to it.

## Graph view

`ctxgraph view` writes one self-contained HTML file into the project's memory folder and opens it. The page needs
no network: the graph libraries are vendored.

- **Topics** are communities of concepts. A concept shared by several topics is drawn in their colours.
- **Per topic**, the page shows what `recall` returns for it (the same block the assistant gets) and the decisions
  about it.
- **The decisions journal** lists all decisions by date: do / not do / on hold.
- **2D / 3D**: switch in the sidebar, or open in 3D with `ctxgraph view --3d`. 2D uses
  [force-graph](https://github.com/vasturiano/force-graph) and 3D uses
  [3d-force-graph](https://github.com/vasturiano/3d-force-graph) (both MIT).

### Code from Graphify

[Graphify](https://github.com/Graphify-Labs/graphify) (Apache-2.0) builds a graph of a codebase from its syntax tree
and writes `graphify-out/graph.json`. To show your code next to your conversations:

```bash
ctxgraph import-graphify path/to/repo/graphify-out
```

Every edge then has an **origin label**:

- `conversation`: between concepts of your conversations (round nodes, topic colours);
- `code`: extracted from the code by Graphify (square nodes, slate colour);
- `inferred`: guessed rather than extracted. Graphify's own INFERRED / AMBIGUOUS edges are drawn as a grey dashed
  line. Links between a conversation concept and a code node are drawn as a yellow dashed line. ctxgraph makes such a
  link only when a file path or identifier said in the chat exactly matches a file or symbol in the graph. It does not
  match by similarity, and it skips generic names such as `main` or `utils`.

Layers can be switched on and off in the sidebar. Clicking a code node shows its file and line, its code relations,
and the conversation concepts and decisions that mention it. Re-importing replaces the code layer.

## Privacy

- Everything stays on your machine. Each project has its own store: `~/.ctxgraph/<project>/graph.sqlite`.
- Only what people said is imported: your prompts and the assistant's visible prose. Tool calls and their output,
  thinking, system reminders, subagent sidechains, code blocks, command lines and log output are dropped.
- **Secrets and personal data are scrubbed before storage**, by pattern: API keys and tokens, private keys,
  passwords and secrets in assignments, credentials inside URLs, e-mail addresses and phone numbers. A match is
  replaced with `[REDACTED:<kind>]` before the text reaches the database. Pattern matching can miss secrets of
  unusual formats.
- After the one-time model download, nothing goes to the network.
- The graph view embeds quotes from your conversations. Treat the HTML file as private, like the store itself.
- `forget` hides a turn from recall. To remove a project's memory completely, delete its folder in `~/.ctxgraph`.

## Limits

- **Rules, not an LLM.** Statuses, decisions, reports and confirmations are found by cue words and structure, tuned
  on Russian and English conversations. They miss some decisions and mislabel others. The decisions list says so.
- **Recall searches conversations, not code.** The Graphify layer is shown in the graph view only.
- **Name links are exact.** A code symbol is linked only when the chat names it exactly as written. Only concepts
  frequent enough to appear in the view get links drawn.
- **Size and speed.** The encoder is about 300 MB (int8 ONNX, onnxruntime; no PyTorch). The MCP server starts
  loading it in the background as soon as Claude Code connects. Importing a long history takes minutes. int8
  vectors are close to the full-precision model (cosine 0.98–0.99), not identical: a store keeps the name of the
  encoder that built it and refuses vectors of another one (`ctxgraph import` into a fresh folder rebuilds it).
- **Claude Code first.** Automatic recording relies on the Claude Code Stop hook. Cursor works through the
  `remember` tool only. Chats from claude.ai can be imported from a data export with `ctxgraph import-claude-ai`.
- **Tested on Windows.** Linux and macOS should work, but have not been checked yet.

## Research

ctxgraph grew out of a research project on retrieval for conversational memory. Experiments, pre-registrations and
results: [docs/research_README.md](docs/research_README.md) (the `main` branch of this repository).

## License

Apache-2.0. Vendored libraries keep their own licenses (`ctxgraph/vendor/*.LICENSE`).
