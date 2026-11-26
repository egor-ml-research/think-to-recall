"""Read Claude Code session transcripts (~/.claude/projects/<project>/*.jsonl) as conversation turns (ARCHITECTURE_V2 §3.15).

Only what the people in the chat said: user prompts and the assistant's visible prose. Not stored (noise for a
decision memory): tool calls and results, thinking, system reminders and harness notices, compaction summaries,
sidechains (subagents), code blocks, command lines, git / log / traceback output, and lines repeated from earlier
turns (pastes, resumed sessions). Each turn: {"id", "session", "role", "ts", "text", "source"}.

    python -m cotrail.cc_transcripts <project_dir>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

NOISE = re.compile(r"<system-reminder>.*?</system-reminder>|<task-notification>.*?</task-notification>|"
                   r"<command-[a-z-]+>.*?</command-[a-z-]+>|<local-command-[a-z-]+>.*?</local-command-[a-z-]+>|"
                   r"<agent-message.*?</agent-message>|\[Request interrupted[^\]]*\]|\[SYSTEM NOTIFICATION[^\n]*|"
                   r"<(side-sessions-event|ci-monitor-event)[^>]*>.*?</\1>|^API Error:[^\n]*", re.S | re.M)  # fmt: skip
PASTE = re.compile(r"</?pasted_content[^>]*>")
PASTE_BLOCK = re.compile(r"<pasted_content[^>]*>(.*?)</pasted_content>", re.S)
TERM_START = re.compile(r"^\s*(PS [A-Za-z]:\\[^>\n]*>|\$ )")


def pasted_blocks(raw: str) -> str:
    """The pasted material of a user turn (the inbox rule B): `<pasted_content>` blocks and terminal blocks (a line
    `PS C:\\...>` / `$ ` and the non-blank lines after it); "" when none."""
    out = [m.group(1).strip() for m in PASTE_BLOCK.finditer(raw or "")]
    cur: list[str] | None = None
    for ln in PASTE_BLOCK.sub("\n", raw or "").splitlines():
        if TERM_START.match(ln):
            cur = [ln]
            out.append(cur)  # type: ignore[arg-type]
        elif cur is not None and ln.strip():
            cur.append(ln)
        else:
            cur = None
    return "\n\n".join(b if isinstance(b, str) else "\n".join(b) for b in out if b).strip()
FENCE = re.compile(r"```.*?(```|$)", re.S)
# a line of tool / git / log output rather than something a person said
OUTPUT_LINE = re.compile(
    r"^\s*(\$ |> \$|PS [A-Z]:|warning:|error:|fatal:|Traceback|  File \"|Exit code|exit \d|\[\d{2}/\d{2}/\d{2}|"
    r"[0-9a-f]{7,40} [A-Z][^\n]{0,80}$|(On branch|Your branch|Changes (not staged|to be committed)|Untracked files)|"
    r"\s*(M|A|D|R|\?\?) +[\w./-]+$|Kernel (version|push)|Dataset version|Upload successful|Starting upload|"
    r"Loading weights|Batches:|INFO |DEBUG |WARN(ING)? |\d+ (passed|failed)|=+ .* =+$|[A-Z]:[\\/][^ ]+$|"
    r"/c/Users/[^ ]+$|https?://\S+$)", re.I)  # fmt: skip
# A short user turn with no content of its own ("Fix them", "да", "ок", "давай", "Yes, recreate") confirms the
# assistant's previous message. Criterion fixed before any check: at most SHORT_WORDS words and not
# a question. It is kept as an anchor (the report that follows belongs to it) but has no place of its own in search.
SHORT_WORDS = 3
ASKS = re.compile(r"(\?\s*$|^\W*(?:(?:ну|а|и|ок|ok),?\s+)?(почему|зачем|как|что|где|когда|сколько|кто|какой|какая|какие|"
                  r"чем|разве|what|why|how|where|when|which|who)\b)", re.I)


def is_short(text: str) -> bool:
    t = text.strip()
    return 0 < len(re.findall(r"\w+", t)) <= SHORT_WORDS and not ASKS.search(t)


# Dialogue act of a short user turn (ISO 24617-2 / DAMSL classes, rules written before
# the check). Checked in this order, the first that fires wins: reject / defer -> status -> agree -> directive -> other.
ACT_REJECT = re.compile(r"^(нет|не надо|не нужно|не стоит|отмена|отменяй|стоп|no|nope|don'?t|cancel|stop|"
                        # v2 (the english cues v2 rule)
                        r"nah|not that|let'?s not|skip( it| that)?|never ?mind|scratch that|scrap( it| that)?|forget)\b", re.I)
ACT_DEFER = re.compile(r"\b(потом|позже|подожди|погоди|не сейчас|сначала обсудим|обсудим|later|wait|not now|hold on|"
                       r"postpone|discuss first|let'?s discuss|"
                       # v2 (the english cues v2 rule)
                       r"revisit|park( it| that)?|table( it| that)|punt|tomorrow|next (week|sprint|time)|hold off|hang on|"
                       r"(a|one) (sec|second|minute|moment)|remind me|someday)\b", re.I)
ACT_STATUS_WORDS = {"готово", "готов", "завершён", "завершен", "завершено", "закончилось", "ошибка", "ошибкой", "упал",
                    "упало", "done", "started", "finished", "failed", "error", "crashed", "deleted", "ready"}
ACT_ED_EXCEPT = {"need", "seed", "feed", "speed", "bed"}
# v2 (the english cues v2 rule): "still broken", "works now", "ci is green"
ACT_STATUS = re.compile(r"\b(still (broken|failing|red)|works now|working now|(is|are) (green|red|broken|passing|failing))\b")
ACT_AGREE = re.compile(r"^(да|ага|угу|ок|окей|ok|okay|давай|давайте|согласен|согласна|конечно|хорошо|ладно|принято|yes|"
                       r"yep|yeah|sure|go|fine|agreed|approved|lgtm|sounds good|go ahead|do it|let'?s go|"
                       # v2 (the english cues v2 rule)
                       r"ship it|perfect|makes sense|alright|all right|works for me|great|nice|cool)\b", re.I)
ACT_EN_VERBS = {"fix", "do", "push", "start", "connect", "continue", "run", "delete", "check", "add", "make", "try",
                "commit", "merge", "retry", "rerun", "proceed", "use", "keep", "remove", "revert", "apply", "deploy",
                "publish", "send", "write", "go", "restart", "recreate", "rollback", "undo", "open", "show", "stop",
                "bump", "refactor", "rename", "update", "implement", "revert", "wire", "install", "upgrade"}
_MORPH = None


def _morph():
    global _MORPH
    if _MORPH is None:
        import pymorphy3

        _MORPH = pymorphy3.MorphAnalyzer()
    return _MORPH


def short_act(text: str) -> str:
    """"reject" / "defer" / "status" / "agree" / "directive" / "other" for a short user turn."""
    s = " ".join(re.findall(r"[\w'-]+", text.lower()))
    words = s.split()
    if ACT_REJECT.search(s):
        return "reject"
    if ACT_DEFER.search(s):
        return "defer"
    if ACT_STATUS.search(s) or any(w in ACT_STATUS_WORDS for w in words) or any(re.fullmatch(r"[a-z]+ed", w) and w not in ACT_ED_EXCEPT
                                                         for w in words):  # fmt: skip
        return "status"
    cyr = [w for w in words if re.search(r"[а-яё]", w)]
    parses = [_morph().parse(w)[0] for w in cyr]
    if any(("VERB" in p.tag and "past" in p.tag) or "PRTS" in p.tag for p in parses):
        return "status"
    if ACT_AGREE.search(s):
        return "agree"
    lead_infn = bool(cyr) and words[0] == cyr[0] and "INFN" in parses[0].tag  # "Откатить миграцию": directive infinitive
    lets = len(words) >= 2 and words[0] in ("let's", "lets")  # "let's do it", "let's ship"
    if any(_imperative(w) for w in cyr) or lead_infn or lets or (words and words[0] in ACT_EN_VERBS):
        return "directive"
    return "other"


CONTINUE = re.compile(r"^\W*(continue|продолжай|продолжи|продолжаем)\W*$", re.I)
QUOTED = re.compile(r"«[^»]*»|`[^`]*`|\"[^\"]*\"")


def is_request(assistant_text: str) -> bool:
    """The assistant's message asks the user to do something: a Russian imperative verb outside quotes, English
    "please", or a sentence starting with an English verb of the directive list (the dialog acts rule, addendum 2)."""
    s = QUOTED.sub(" ", assistant_text)
    if re.search(r"\bplease\b", s, re.I):
        return True
    for sent in re.split(r"(?<=[.!?:])\s+|\n", s):
        w = re.findall(r"[a-z]+", sent.strip().lower()[:20])
        if w and sent.strip()[:1].isalpha() and sent.strip().lower().startswith(w[0]) and w[0] in ACT_EN_VERBS:
            return True
    return any(_imperative(w) for w in re.findall(r"[а-яё]+", s.lower()))


def _imperative(word: str) -> bool:
    """A verb that reads as imperative: its first parse is a verb and a parse of the same lemma has `impr`
    ("удалите" is first parsed as future indicative; "мой" is a pronoun, not "мыть")."""
    ps = _morph().parse(word)
    return "VERB" in ps[0].tag and any("impr" in p.tag and p.normal_form == ps[0].normal_form for p in ps)


SERVICE = re.compile(r"^(Continue\.?|Tool loaded\.?|No response requested\.?|ок|ok|да|нет|ну что там|сколько там ещё)$", re.I)


def _ask(content) -> str:
    """The question of the desktop app's end-of-turn box (`wrap_up.ask`): what the assistant asked the user to decide
    or do; the user's short reply answers it."""
    for b in content or [] if isinstance(content, list) else []:
        if isinstance(b, dict) and b.get("type") == "tool_use" and str(b.get("name", "")).endswith("wrap_up"):
            return str((b.get("input") or {}).get("ask") or "")
    return ""


def _text(content) -> str:
    """Visible text. The desktop app's end-of-turn box (`wrap_up`) holds the assistant's final recap in a tool call,
    not in text - it is the turn's report, so it is kept."""
    if isinstance(content, str):
        return content
    parts = []
    for b in content or []:
        if not isinstance(b, dict):
            continue
        if b.get("type") == "text":
            parts.append(b.get("text", ""))
        elif b.get("type") == "tool_use" and str(b.get("name", "")).endswith("wrap_up"):
            parts.append((b.get("input") or {}).get("recap", ""))
    return "\n".join(p for p in parts if p)


def agent_origin(r: dict) -> dict | None:
    """A `user` record the human did not type (rules written before the code): a peer session's message
    (`turnOrigin` / `origin.kind` "peer"), the task another session started this one with (`host_synthetic`), or a
    note of the app (`sdk` / `sdk`). None for the human's own turns and for old records without these fields."""
    o = r.get("origin") if isinstance(r.get("origin"), dict) else {}
    to, ps = r.get("turnOrigin"), r.get("promptSource")
    if to == "peer" or o.get("kind") == "peer":
        return {"kind": "peer", "parent": str(o.get("from") or ""), "body": str(o.get("body") or "")}
    if to == "host_synthetic":
        return {"kind": "brief", "parent": "", "body": ""}
    if to == "sdk" and ps == "sdk":
        return {"kind": "host", "parent": "", "body": ""}
    return None


def launches(path: Path) -> list[tuple[str, str]]:
    """(session, text) of the tasks this transcript sent to other sessions: `start_session` prompts and
    `SendMessage` messages."""
    out = []
    for line in path.read_text("utf-8", errors="replace").splitlines():
        if '"tool_use"' not in line or ("start_session" not in line and "SendMessage" not in line):
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        for b in (r.get("message") or {}).get("content") or []:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                name, inp = str(b.get("name", "")), b.get("input") or {}
                text = inp.get("prompt") if name.endswith("start_session") else inp.get("message") if name == "SendMessage" else None
                if text:
                    out.append((r.get("sessionId") or path.stem, str(text)))
    return out


def _key(text: str, n: int | None = 200) -> str:
    k = re.sub(r"\W+", " ", text).strip().lower()
    return k[:n] if n else k


def clean(text: str) -> str:
    text = FENCE.sub("\n", PASTE.sub("", NOISE.sub("", text)))
    lines = [ln for ln in text.splitlines() if not OUTPUT_LINE.search(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def title_of(lines: list[str]) -> str:
    """A Claude Code session's title: its `summary` record (the name the app shows), else ""."""
    for line in lines:
        if '"summary"' not in line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("type") == "summary" and isinstance(r.get("summary"), str) and r["summary"].strip():
            return r["summary"].strip()[:120]
    return ""


def turns(path: Path):
    after_summary = False  # the next kept turn comes right after a compaction summary
    lines = path.read_text("utf-8", errors="replace").splitlines()
    title = title_of(lines)
    for line in lines:
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("isCompactSummary"):
            after_summary = True
            continue
        peer = r.get("type") == "user" and (agent_origin(r) or {}).get("kind") == "peer"
        if r.get("isSidechain") or (r.get("isMeta") and not peer) or r.get("type") not in ("user", "assistant"):
            continue  # isMeta: notes the app injects, not typed by the user (a peer session's message is kept as a task)
        content = (r.get("message") or {}).get("content")
        if r["type"] == "user" and isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content):  # fmt: skip
            continue
        role = "user" if r["type"] == "user" else "assistant"
        agent = agent_origin(r) if role == "user" else None
        text = clean(agent["body"] if agent and agent["body"] else _text(content))
        anchor = role == "user" and not agent and is_short(text)
        if text.startswith("This session is being continued from a previous"):
            after_summary = True
            continue
        if (not anchor and (len(text) < 12 or SERVICE.match(text))) or text.startswith("Caveat: The messages below"):
            continue
        uid = r.get("uuid") or hashlib.sha1(f"{path.stem}|{r.get('timestamp')}|{text[:200]}".encode()).hexdigest()
        yield {"id": uid, "session": r.get("sessionId") or path.stem, "role": role, "ts": r.get("timestamp", ""),
               "text": text, "source": "transcript", "after_summary": after_summary and role == "user",
               "pasted": pasted_blocks(_text(content)) if role == "user" and not agent else "", "title": title,
               "ask": _ask(content) if role == "assistant" else "",
               "agent": {k: agent[k] for k in ("kind", "parent")} if agent else None}  # fmt: skip
        after_summary = False


def dedupe(turns_: list[dict]) -> list[dict]:
    """Drop turns repeated verbatim (resumed sessions) and, in the user's turns, lines already said earlier (pastes of
    earlier text). The assistant's lines are kept: a final report restates what was said along the way, and cutting
    those lines would cut the report."""
    seen_turn, seen_line, out = set(), set(), []
    for t in sorted(turns_, key=lambda t: (t["ts"], t["id"])):
        # a short confirmation ("да") repeats verbatim but each one is its own event
        k = (t["role"], t["text"]) if not (t["role"] == "user" and is_short(t["text"])) else (t["id"],)
        if k in seen_turn:
            continue
        seen_turn.add(k)
        keep = []
        for ln in t["text"].splitlines():
            if t["role"] != "user":
                keep.append(ln)
                continue
            norm = re.sub(r"\W+", " ", ln).strip().lower()
            if len(norm) >= 40 and norm in seen_line:
                continue
            if len(norm) >= 40:
                seen_line.add(norm)
            keep.append(ln)
        text = "\n".join(keep).strip()
        if len(text) >= 12 or (t["role"] == "user" and is_short(text)):
            out.append(t | {"text": text})
    return out


def link_parents(ts: list[dict], files: list[Path]) -> list[dict]:
    """An agent task's parent: the transcript that sent its text (start_session / SendMessage), else `origin.from`."""
    sent = [(s, _key(t, 120)) for f in files for s, t in launches(f)]
    for t in ts:
        a = t.get("agent")
        if a and a["kind"] != "host":
            k = _key(t["text"], None)  # a brief = the parent's background + its prompt: the prompt is inside
            hit = next((s for s, sk in sent if len(sk) >= 40 and sk in k and s != t["session"]), "")
            a["parent"] = hit or a["parent"]
    return ts


def project_turns(project_dir: Path) -> list[dict]:
    files = sorted(project_dir.glob("*.jsonl"))
    return link_parents(dedupe([t for p in files for t in turns(p)]), files)


if __name__ == "__main__":
    ts = project_turns(Path(sys.argv[1]))
    by: dict = {}
    for t in ts:
        by[t["role"]] = by.get(t["role"], 0) + 1
    print(len(ts), "turns", by, "chars", sum(len(t["text"]) for t in ts))
    if ts:
        print("from", ts[0]["ts"], "to", ts[-1]["ts"])
