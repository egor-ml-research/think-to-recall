"""Read Claude Code session transcripts (~/.claude/projects/<project>/*.jsonl) as conversation turns (ARCHITECTURE_V2 §3.15).

Only what the people in the chat said: user prompts and the assistant's visible prose. Not stored (noise for a
decision memory): tool calls and results, thinking, system reminders and harness notices, compaction summaries,
sidechains (subagents), code blocks, command lines, git / log / traceback output, and lines repeated from earlier
turns (pastes, resumed sessions). Each turn: {"id", "session", "role", "ts", "text", "source"}.

    python -m ctxgraph.cc_transcripts <project_dir>
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
ACT_REJECT = re.compile(r"^(нет|не надо|не нужно|не стоит|отмена|отменяй|стоп|no|nope|don'?t|cancel|stop)\b", re.I)
ACT_DEFER = re.compile(r"\b(потом|позже|подожди|погоди|не сейчас|сначала обсудим|обсудим|later|wait|not now|hold on)\b", re.I)
ACT_STATUS_WORDS = {"готово", "готов", "завершён", "завершен", "завершено", "закончилось", "ошибка", "ошибкой", "упал",
                    "упало", "done", "started", "finished", "failed", "error", "crashed", "deleted", "ready"}
ACT_ED_EXCEPT = {"need", "seed", "feed", "speed", "bed"}
ACT_AGREE = re.compile(r"^(да|ага|угу|ок|окей|ok|okay|давай|давайте|согласен|согласна|конечно|хорошо|ладно|принято|yes|"
                       r"yep|yeah|sure|go|fine)\b", re.I)
ACT_EN_VERBS = {"fix", "do", "push", "start", "connect", "continue", "run", "delete", "check", "add", "make", "try",
                "commit", "merge", "retry", "rerun", "proceed", "use", "keep", "remove", "revert", "apply", "deploy",
                "publish", "send", "write", "go", "restart", "recreate", "rollback", "undo", "open", "show", "stop"}
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
    if any(w in ACT_STATUS_WORDS for w in words) or any(re.fullmatch(r"[a-z]+ed", w) and w not in ACT_ED_EXCEPT
                                                         for w in words):  # fmt: skip
        return "status"
    cyr = [w for w in words if re.search(r"[а-яё]", w)]
    parses = [_morph().parse(w)[0] for w in cyr]
    if any(("VERB" in p.tag and "past" in p.tag) or "PRTS" in p.tag for p in parses):
        return "status"
    if ACT_AGREE.search(s):
        return "agree"
    lead_infn = bool(cyr) and words[0] == cyr[0] and "INFN" in parses[0].tag  # "Откатить миграцию": directive infinitive
    if any(_imperative(w) for w in cyr) or lead_infn or (words and words[0] in ACT_EN_VERBS):
        return "directive"
    return "other"


CONTINUE = re.compile(r"^\W*(continue|продолжай|продолжи|продолжаем)\W*$", re.I)
QUOTED = re.compile(r"«[^»]*»|`[^`]*`|\"[^\"]*\"")


def is_request(assistant_text: str) -> bool:
    """The assistant's message asks the user to do something: a Russian imperative verb outside quotes, English
    "please", or a sentence starting with an English verb of the directive list (dialog_acts_rule.md, addendum 2)."""
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


def clean(text: str) -> str:
    text = FENCE.sub("\n", PASTE.sub("", NOISE.sub("", text)))
    lines = [ln for ln in text.splitlines() if not OUTPUT_LINE.search(ln)]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def turns(path: Path):
    after_summary = False  # the next kept turn comes right after a compaction summary
    for line in path.read_text("utf-8", errors="replace").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        if r.get("isCompactSummary"):
            after_summary = True
            continue
        if r.get("isSidechain") or r.get("isMeta") or r.get("type") not in ("user", "assistant"):
            continue  # isMeta: notes the app injects, not typed by the user
        content = (r.get("message") or {}).get("content")
        if r["type"] == "user" and isinstance(content, list) and any(
                isinstance(b, dict) and b.get("type") == "tool_result" for b in content):  # fmt: skip
            continue
        text = clean(_text(content))
        role = "user" if r["type"] == "user" else "assistant"
        anchor = role == "user" and is_short(text)
        if text.startswith("This session is being continued from a previous"):
            after_summary = True
            continue
        if (not anchor and (len(text) < 12 or SERVICE.match(text))) or text.startswith("Caveat: The messages below"):
            continue
        uid = r.get("uuid") or hashlib.sha1(f"{path.stem}|{r.get('timestamp')}|{text[:200]}".encode()).hexdigest()
        yield {"id": uid, "session": r.get("sessionId") or path.stem, "role": role, "ts": r.get("timestamp", ""),
               "text": text, "source": "transcript", "after_summary": after_summary and role == "user",
               "ask": _ask(content) if role == "assistant" else ""}  # fmt: skip
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


def project_turns(project_dir: Path) -> list[dict]:
    return dedupe([t for p in sorted(project_dir.glob("*.jsonl")) for t in turns(p)])


if __name__ == "__main__":
    ts = project_turns(Path(sys.argv[1]))
    by: dict = {}
    for t in ts:
        by[t["role"]] = by.get(t["role"], 0) + 1
    print(len(ts), "turns", by, "chars", sum(len(t["text"]) for t in ts))
    if ts:
        print("from", ts[0]["ts"], "to", ts[-1]["ts"])
