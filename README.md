<p align="center"><img src="docs/media/ctxgraph_icon.svg" width="140" alt="ctxgraph logo"></p>

# ctxgraph — decision memory for AI coding assistants

**English** · [Русский](README.ru.md)

Your assistant forgets what you decided last week. ctxgraph remembers it.

ctxgraph is a local memory of your conversations with Claude Code, organised around **decisions**: what you decided
to do, what you decided not to do, what you put on hold, and when the assistant reported it done. It runs as an MCP
server next to Claude Code. Before answering, the assistant can ask it what was decided earlier in the project. The
answer comes with dates and statuses, and every turn is recorded automatically.

![Before and after: in a new session, asked "which database did we choose?", the assistant without memory does not know; with ctxgraph it answers SQLite, with the change of decision and the commit](docs/media/before_after.en.gif)

*A synthetic project. The memory block is the real output of `recall`; the answers are real answers of one model
(Mistral Large 4) without memory and with that block.*

- **Local only.** One SQLite file per project on your machine. No cloud, no account, no LLM calls to build the memory.
- **Works on the history you already have.** On first connection it imports your earlier Claude Code sessions of the
  project (if you agree) and shows the decision chronology right away.
- **One command to connect.** `ctxgraph setup` writes the MCP config and the hook for the project you are in.
- **Small answers.** When nothing in memory is about the question, recall answers in one line instead of a block.
  One-line records show the sentence that answers the question, and in one session a record is not repeated.
- **A project map in one call.** `overview` gives a new chat the areas of the code (from the Graphify graph:
  main files, functions, links) with the newest decisions about each, in about 600 tokens, without reading code.
- **A graph you can look at.** `ctxgraph view` opens a local 2D or 3D map of topics, concepts and decisions. A
  [Graphify](https://github.com/Graphify-Labs/graphify) code graph can be shown on the same map.

## Install

One line (Python 3.11+ and [uv](https://docs.astral.sh/uv/)), from the project you want to connect:

```bash
uv tool install "think-to-recall @ git+https://github.com/egor-ml-research/think-to-recall@v0.6.0" && ctxgraph setup
```

With [pipx](https://pipx.pypa.io/) instead of uv:

```bash
pipx install "think-to-recall @ git+https://github.com/egor-ml-research/think-to-recall@v0.6.0" && ctxgraph setup
```

**Works right away, without downloading a model.** Recall is BM25 over your conversations; the install is about
125 MB. The quality mode is optional: it adds multilingual-e5-base (int8 ONNX, about 300 MB, no PyTorch) and fuses it
with BM25, which finds a few more answers worded differently from your question:

```bash
uv tool install --reinstall "think-to-recall[quality] @ git+https://github.com/egor-ml-research/think-to-recall@v0.6.0" && ctxgraph setup --quality
```

The package is not on PyPI yet; the commands install release v0.6.0 from GitHub. For finer English concepts in the
graph view, add the `english` extra. **Installing through an AI assistant?** Point it to
[INSTALL_FOR_AI.md](INSTALL_FOR_AI.md).

`setup` asks all its questions once, before doing anything, and Enter takes the default:

| question | default | flag |
|---|---|---|
| import this project's earlier Claude Code sessions | yes | `--import-history yes\|no` |
| build a code graph with Graphify (only when code is found; installs `graphifyy`, ~150 MB, local AST, no LLM) | no | `--graphify yes\|no` |
| download WordNet data that names the topics in `expand` (~10 MB) | yes | `--wordnet yes\|no` |

`-y` takes the defaults. **Without a terminal** (an assistant running setup for you) nothing is imported, installed
or downloaded unless a flag says so: only the server and the hook are written, and the end lists what was skipped,
with the command for each.

Then it does four things:

1. Registers the `ctxgraph` MCP server **without any path that could end up in git**. With the `claude` CLI on
   PATH it runs `claude mcp add --scope local ctxgraph -- ctxgraph-mcp`: the entry is kept in your own Claude Code
   config for this project, not in the repository. Without the CLI it adds to the project's `.mcp.json` only
   `{"command": "ctxgraph-mcp"}` (no home folder, no Python path, no project path); other servers in that file are
   kept. The server takes the project from the folder Claude Code starts it in.
2. Adds a Claude Code **Stop hook** `ctxgraph hook-stop` to `.claude/settings.local.json`. After every turn it queues
   the session transcript; the project comes from the hook's input. The hook is fast: it only appends a path, and the
   server reads the transcript later. Other hooks and settings are kept, and an earlier ctxgraph hook is replaced.
   A **SessionStart hook** `ctxgraph hook-start` puts one line into each new session when something is open "for
   later" (see `later` below); nothing when nothing is open.
3. **Downloads nothing by default.** Recall works on BM25 over the stored sentences (Russian words lemmatized with
   pymorphy3, whose dictionaries ship with the package). With `--quality` setup **asks before downloading** the
   sentence encoder multilingual-e5-base as int8 ONNX
   ([Xenova/multilingual-e5-base](https://huggingface.co/Xenova/multilingual-e5-base), an export of
   [intfloat/multilingual-e5-base](https://huggingface.co/intfloat/multilingual-e5-base), MIT; about 300 MB, a pinned
   revision) and turns the quality mode on: BM25 and the encoder's vectors are fused by reciprocal rank fusion. The
   download happens once; after that every ctxgraph process runs with the Hugging Face hub offline. A memory built
   in the default mode is moved aside and rebuilt (pinned rules are kept). If the download fails (no network, proxy),
   setup says what was not downloaded, from where, and to rerun it; a partial download resumes.
4. Imports the project's earlier Claude Code sessions (`~/.claude/projects/<project>/*.jsonl`) if you agreed, and
   prints the **decision chronology**, so you see what the memory knows straight away.

Restart Claude Code in the project folder and approve the `ctxgraph` server when it asks.

### Installing through an AI assistant

Point the assistant to [INSTALL_FOR_AI.md](INSTALL_FOR_AI.md). Before running `ctxgraph setup` it asks you, in one
message, with the default in brackets:

1. "Import the history of your earlier conversations about this project, so the memory knows right away what you
   decided? (no)" -> `--import-history yes|no`
2. "Will you work with code in this project? (no)" - if yes: "Also install Graphify, so the memory sees the
   structure of the code (what calls what)? (no)" -> `--graphify yes|no`; if no, `--graphify no` without the second
   question.
3. "Which language for the memory's labels - Russian or English?" -> `--lang ru|en` (not asked when the language is
   obvious from the conversation).

No answer means the safe values: no / no / the language of the conversation.

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

Options: `--quality` turns on the quality mode (see above), `--yes` agrees to the questions (for scripts),
`--no-model` only writes the config files, `--no-import` skips the history, `--home DIR` keeps the stores somewhere other than `~/.ctxgraph`, and `--print-cursor` prints a
Cursor config. Cursor has no hooks, so there turns are saved through the `remember` tool.

## Use

In Claude Code the assistant gets these tools:

| tool | what it does |
|---|---|
| `recall(question, steps, detail)` | finds earlier turns relevant to the question and to the assistant's reasoning steps; `detail="brief"` gives one line per record (date, status, topic, gist, `#id`), `"mixed"` the best records in full and the rest as lines; one line when nothing is about the question; `fresh=True` repeats records already shown in the session |
| `overview()` | a map of the project in ≤ ~600 tokens without reading code: areas of the Graphify code graph (main files, functions, links between areas), ranked by entry points, PageRank and recent commits, with the newest decisions that name their code or whose commit touched it (tests / scripts / docs, git-ignored paths and the patterns in an `overview.exclude` file are left out); without a code graph, conversation topics with their newest decisions. Call it first in a new chat |
| `expand(id)` | one record in full (exact wording, numbers, commits) and the thread of its topic by date: how it started, what changed, the reports |
| `decisions(limit)` | the decision chronology, newest first, with confirmations and reports |
| `later(limit)` | what was put off: decisions on hold ("later", "на потом", TODO), proposals you answered "later", and deferred [Beads](https://github.com/gastownhall/beads) issues from `.beads/*.jsonl` (read only). An item closes itself when a later report of done work matches it; recall adds a line of open items on the same topic |
| `rules`, `pin_rule`, `unpin_rule` | the project's pinned permanent rules (only "always / never / from now on" rules you stated; not ordinary or conditional decisions) |
| `save_chat(title, turns)` | save the current chat of Claude Desktop / Cursor ("add this chat to memory"); repeat-safe |
| `import_claude_ai(export, match)` | import chosen chats from a claude.ai data export |
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
ctxgraph expand 1a2b3c4d   # a record id shown by recall
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

## Claude Desktop, Cursor and claude.ai chats

**Save the current chat.** In any MCP client (the Claude Desktop Chat tab, Cursor) say *"add this chat to memory"*.
The assistant calls `save_chat` with the chat's turns word for word (in portions of up to 30 turns for long chats).
It is safe to repeat: saying it again later in the same chat adds only the new turns, the memory is never rebuilt.
Saved chats get the same statuses as Claude Code sessions (decisions, rules, reports) and the source "chat".

**Claude Desktop extension (no developer mode).** Install ctxgraph once in a terminal (the `uv tool install` or
`pipx install` command above), then download `ctxgraph-0.6.0.mcpb` from the
[release page](https://github.com/egor-ml-research/think-to-recall/releases/tag/v0.6.0) and open it (or drag it
into Claude Desktop → Settings → Extensions). Claude Desktop asks for the project folder; the memory of that folder
is used. The extension contains no code: it runs the `ctxgraph-mcp` you installed (`~/.local/bin`).
ctxgraph is not offered as a remote "custom connector" URL on purpose: a connector runs on a server, and this memory
stays on your computer.

**claude.ai chats.** Export your data (claude.ai → Settings → Privacy → Export data), then ask the assistant to
import it (`import_claude_ai`: without a filter it lists the conversations and asks which belong to the project),
or run `ctxgraph import-claude-ai export.zip --match "..."`. Re-importing a newer export adds only new messages.

## How recall works

**One unit = your turn plus the assistant's report.** A turn of yours and the assistant's last message before your
next turn form one unit. That last message is the report of what was done. It is shown nested under your request and
does not take a result slot of its own. The assistant's intermediate messages ("running the tests now…") are
progress and are not searched.

**Main line + periphery.** `recall` first searches by the question itself (BM25 by default, BM25 + e5 in the quality
mode; a turn is scored by its best sentence). That is the **main line**: it comes first and is never displaced. The assistant also passes
1–3 short **reasoning steps**, such as "an earlier decision about this component" or "a constraint the user stated".
Turns found only through those steps form the **periphery**. They are added after the main line, without duplicates,
only in the space left in the block. The periphery is how a memory that looks unrelated to the question still turns
up: a constraint you mentioned once, three weeks ago, in another context.

**The same entity.** A decision changed later in other words ("we switch from Postgres to SQLite") may share no word
with the question ("which database did we choose?"). So from the turns found by the question recall takes their rare
entities (concepts that occur in a few turns, not everywhere) and adds up to 3 later turns that mention them to the
chronology, marked "same entity: Postgres". They never push out what the question found.

**Topics.** Every record belongs to a topic: a community of the concept graph (Leiden), named by its most connected
concepts. `expand(id)` shows the record in full and the other records of its topic and of its entities, by date.

**Statuses and chronology.** Every remembered sentence has a status, found by rules (no LLM):

- your sentences with decision cues are decisions: *do*, *not do*, or *on hold*;
- the assistant's sentences are *done* when they report finished work (a commit, "fixed", "published"), and
  *proposal, not applied* when they offer or draft something.

Results are shown oldest first, each with its date and status, so a later decision that changed an earlier one comes
after it. `decisions` lists the chronology newest first. A
decision is followed by the report that carried it out (date, commit), when one is found. A decision on hold is
followed by its later confirmation and execution.

**Fewer tokens.** If no remembered record holds enough of the question's words (in the quality mode: or is close to it by
meaning), recall answers with one line, "Nothing in memory on this question", instead of a block. In one-line records
(`detail="brief"`, and the short records of `"mixed"`) the gist is the decision or report sentence that shares the most
words with the question. Labels are compact: `11-18` for a date of this year, a short `#id` that `expand` accepts,
the topic once per run of lines. With `detail="brief"`, a record already shown in the same session comes back as one
short line, "`#id` (shown earlier): date · gist". After a context compaction or in a new session every record is
shown in full again; `recall(..., fresh=True)` does the same at once. Set `CTXGRAPH_ECONOMY=off` for the previous
behaviour.

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
- **Cosmos**: `ctxgraph view --cosmos` (or the «Космос» switch) draws the project as a galaxy on plain Canvas 2D:
  the core is the project, topics are constellations, concepts are stars. It has a greeting card with what changed
  since your last visit and a dashboard («Панель») with activity, topics, most connected concepts, recent decisions
  and search. Without a flag, the page opens in the mode you used last.

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
- **Size and speed.** The default install is about 125 MB and needs no model; importing a long history takes about
  a minute. The quality mode adds about 300 MB and makes the first import several times slower (291 s against 69 s
  for 775 turns on a laptop CPU). A store remembers its mode; switching to `--quality` rebuilds it.
- **Lexical by default.** BM25 finds what shares words with your question. On our check of 29 questions about past
  decisions it was correct on 19 (e5 alone: 18, BM25 + e5: 21; measured on 784 turns, later turns move these by about one
  question) and never showed an outdated answer as current, but
  it misses answers worded differently from the question (for example, "DB" for "database"); `--quality` recovers
  some of them.
- **Two languages.** Status labels follow the project's language (the language of most of your messages);
  `ctxgraph --lang en|ru …` or `CTXGRAPH_LANG` sets it. Cue words exist for English and Russian only.
- **Claude Code first.** Automatic recording relies on the Claude Code Stop hook. Claude Desktop and Cursor
  chats are saved when you ask (`save_chat`). Chats from claude.ai can be imported from a data export with `ctxgraph import-claude-ai`.
- **Tested on Windows and on a clean Linux install.** macOS has not been checked yet.

## Research

ctxgraph grew out of a research project on retrieval for conversational memory. Experiments, pre-registrations and
results: [docs/research_README.md](docs/research_README.md) (in this repository).

## License

Apache-2.0. Vendored libraries keep their own licenses (`ctxgraph/vendor/*.LICENSE`).
