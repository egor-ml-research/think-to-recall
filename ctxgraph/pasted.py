"""A user turn that is a pasted assistant report (the pasted-reports rule, written before the code).

Primary: word 5-shingles of the turn found in earlier assistant messages of the store; lines with >= 50 % of their
words covered, joined into runs, a run counts when its normalized text has >= N characters (or the whole turn is
covered). Fallback without a match: a long turn with report markup. Pure functions; the store keeps the index."""

from __future__ import annotations

import re

K = 5  # shingle size, words
N = 200  # a pasted run counts from this many normalized characters
LINE_COVER = 0.5
WHOLE_COVER, WHOLE_MIN_WORDS = 0.9, 12
FRAG_COVER = 0.5
FB_MIN_CHARS, FB_FRAME_MAX = 800, 400
W_PASTED, W_PASTED_MD = 0.6, 0.45
ACTING = ("transcript",)  # sources whose assistant does the work itself (Claude Code); amendment 1

_WORD = re.compile(r"\w+")


def norm(text: str) -> str:
    return " ".join(_WORD.findall((text or "").lower().replace("ё", "е").replace("_", " ")))


def words(text: str) -> list[str]:
    return norm(text).split()


def shingles(ws: list[str]) -> list[tuple]:
    return [tuple(ws[i:i + K]) for i in range(len(ws) - K + 1)]


def primary(text: str, lookup) -> tuple[str, str] | None:
    """(ref, spans) when the turn is wholly or partly pasted, else None. `lookup(shingle)` -> the earlier assistant
    episodes containing it (iterable). `spans` is the normalized text of the pasted runs, newline-separated."""
    lines = [ln for ln in (text or "").splitlines()]
    toks: list[tuple[int, str]] = []  # (line index, word)
    for i, ln in enumerate(lines):
        toks += [(i, w) for w in words(ln)]
    ws = [w for _, w in toks]
    if len(ws) < K:
        return None
    covered = [False] * len(ws)
    votes: dict[str, int] = {}
    for j, sh in enumerate(shingles(ws)):
        eps = list(lookup(sh) or ())
        if eps:
            for k in range(j, j + K):
                covered[k] = True
            for e in set(eps):
                votes[e] = votes.get(e, 0) + 1
    if not votes:
        return None
    per_line: dict[int, list[bool]] = {}
    for (i, _), c in zip(toks, covered, strict=True):
        per_line.setdefault(i, []).append(c)
    whole = sum(covered) / len(ws) >= WHOLE_COVER and len(ws) >= WHOLE_MIN_WORDS
    runs, cur = [], []
    for i, ln in enumerate(lines):
        if i not in per_line:  # a blank / punctuation-only line does not break a run
            continue
        cv = per_line[i]
        if sum(cv) / len(cv) >= LINE_COVER:
            cur.append(norm(ln))
        else:
            if cur:
                runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    keep = [" ".join(r) for r in runs if whole or len(" ".join(r)) >= N]
    if not keep:
        return None
    ref = min(votes, key=lambda e: (-votes[e], e))
    return ref, "\n".join(keep)


def frag_pasted(frag: str, spans: str) -> bool:
    """A stored sentence of the turn lies in its pasted runs."""
    ws = words(frag)
    if not ws or not spans:
        return False
    if len(ws) < K:
        return f" {' '.join(ws)} " in f" {spans.replace(chr(10), ' ')} "
    have = set()
    for run in spans.split("\n"):
        have.update(shingles(run.split()))
    sh = shingles(ws)
    return sum(s in have for s in sh) / len(sh) >= FRAG_COVER


HEADER = re.compile(r"^\s{0,3}#{1,6}\s", re.M)
TABLE = re.compile(r"^\s*\|.*\|\s*$", re.M)
CC_UI = re.compile(r"^\s*(Ran|Read|Edited|Searched|Wrote|Created|Updated) (\d+|a|an) \w+", re.M)
CHECK = re.compile(r"[✓✔✅❌✗☑⚠]")
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")
FENCE = re.compile(r"```")
BULLET = re.compile(r"^\s*([-*•]|\d+[.)])\s+\S")
BOLD = re.compile(r"\*\*[^*\n]{2,40}\*\*")


def features(text: str) -> tuple[int, int]:
    """(strong, all) report-markup features of a text."""
    strong = [len(HEADER.findall(text)) >= 2, len(TABLE.findall(text)) >= 2, bool(CC_UI.search(text)),
              len(CHECK.findall(text)) >= 2]  # fmt: skip
    nonempty = [ln for ln in text.splitlines() if ln.strip()]
    bullets = sum(bool(BULLET.match(ln)) for ln in nonempty)
    hashes = [h for h in HASH.findall(text) if re.search(r"\d", h) and re.search(r"[a-f]", h)]
    weak = [len(hashes) >= 2, bool(FENCE.search(text)), bullets >= 5 and bullets >= 0.4 * len(nonempty),
            len(BOLD.findall(text)) >= 3]  # fmt: skip
    return sum(strong), sum(strong) + sum(weak)


def _any_feature(par: str) -> bool:
    nonempty = [ln for ln in par.splitlines() if ln.strip()]
    return bool(HEADER.search(par) or TABLE.search(par) or CC_UI.search(par) or CHECK.search(par) or FENCE.search(par)
                or BOLD.search(par) or any(BULLET.match(ln) for ln in nonempty)
                or any(re.search(r"\d", h) and re.search(r"[a-f]", h) for h in HASH.findall(par)))  # fmt: skip


def fallback(text: str) -> str | None:
    """The normalized pasted text of a long turn with report markup (its framing first / last paragraph excluded),
    else None."""
    if len(text or "") < FB_MIN_CHARS:
        return None
    strong, total = features(text)
    if strong < 1 or total < 3:
        return None
    pars = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    if len(pars) > 1 and len(pars[0]) < FB_FRAME_MAX and not _any_feature(pars[0]):
        pars = pars[1:]
    if len(pars) > 1 and len(pars[-1]) < FB_FRAME_MAX and not _any_feature(pars[-1]):
        pars = pars[:-1]
    return "\n".join(" ".join(norm(ln) for ln in p.splitlines() if norm(ln)) for p in pars)
