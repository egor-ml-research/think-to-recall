"""Name variants of one concept ("Postgres" / "PostgreSQL", "ctx-graph" / "cotrail", "постгрес" / "postgres").

Rule: reports/realworld/aliases_rule.md (written before the code). The idea - entity resolution by trigram
similarity with pg_trgm-style thresholds - is taken from Hindsight (github.com/vectorize-io/hindsight, MIT,
Copyright (c) Vectorize); this is our own re-implementation, no code copied. No model, no LLM.

The originals are never changed: the pairs live in a separate table and recall maps a concept to the canonical
one of its group only where it compares concepts across turns. `COTRAIL_ALIASES=off` turns it off.
"""

from __future__ import annotations

import math
import os
import re

SIM = 0.5  # Hindsight's in-batch merge threshold (pg_trgm similarity)
MIN_CHARS = 4
SKIP_KINDS = {"ent:DATE", "ent:TIME", "path", "code"}
_TR = dict(zip("абвгдежзийклмнопрстуфхцчшщъыьэюяё",
               ["a", "b", "v", "g", "d", "e", "zh", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u",
                "f", "h", "c", "ch", "sh", "sh", "", "y", "", "e", "yu", "ya", "e"]))  # fmt: skip
_NON = re.compile(r"[^0-9a-z]+")
_HASH = re.compile(r"[0-9a-f]{7,40}")


def enabled() -> bool:
    return os.environ.get("COTRAIL_ALIASES", "on").lower() not in ("off", "0", "no", "false")


def key(label: str) -> str:
    """Lower case, Cyrillic -> Latin, every non-alphanumeric run -> one space."""
    s = label.lower()
    if s.startswith("c:"):
        s = s[2:]
    s = "".join(_TR.get(ch, ch) for ch in s)
    return _NON.sub(" ", s).strip()


def trigrams(k: str) -> set[str]:
    """pg_trgm: each word padded with two spaces in front and one behind."""
    out = set()
    for w in k.split():
        p = "  " + w + " "
        out.update(p[i:i + 3] for i in range(len(p) - 2))
    return out


def similarity(a: str, b: str) -> float:
    ta, tb = trigrams(a), trigrams(b)
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _digits(k: str) -> str:
    return "".join(ch for ch in k if ch.isdigit())


def eligible(k: str, kind: str = "") -> bool:
    flat = k.replace(" ", "")
    return kind not in SKIP_KINDS and len(flat) >= MIN_CHARS and not _HASH.fullmatch(flat)


def same(a: str, b: str) -> tuple[bool, float, str]:
    """(alias?, similarity, method) for two keys by the rule (both assumed eligible)."""
    if a == b:
        return True, 1.0, "equal"
    if a.replace(" ", "") == b.replace(" ", ""):
        return True, 1.0, "spaces"
    if len(a.split()) != len(b.split()) or _digits(a) != _digits(b):
        return False, 0.0, ""
    s = similarity(a, b)
    return s >= SIM, s, "trigram"


def pairs(concepts: list[tuple[str, str, str, int]]) -> list[tuple[str, str, float, str]]:
    """Alias pairs among (id, label, kind, first_seq) rows: (alias, canonical, sim, method), one row per
    non-canonical member of a group (canonical = smallest first_seq, then id)."""
    items = []
    for cid, label, kind, seq in concepts:
        k = key(cid)
        if eligible(k, kind or ""):
            items.append((cid, k, seq))
    tri = [trigrams(k) for _, k, _ in items]
    freq: dict[str, int] = {}
    for t in tri:
        for g in t:
            freq[g] = freq.get(g, 0) + 1
    # prefix filter for Jaccard >= SIM: a pair shares at least one of the first n - ceil(SIM*n) + 1 rarest trigrams
    post: dict[str, list[int]] = {}
    pref = []
    for i, t in enumerate(tri):
        order = sorted(t, key=lambda g: (freq[g], g))
        p = order[: len(order) - math.ceil(SIM * len(order)) + 1]
        pref.append(p)
        for g in p:
            post.setdefault(g, []).append(i)
    flat: dict[str, list[int]] = {}
    for i, (_, k, _) in enumerate(items):
        flat.setdefault(k.replace(" ", ""), []).append(i)
    parent = list(range(len(items)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    best: dict[tuple[int, int], tuple[float, str]] = {}
    cand: set[tuple[int, int]] = set()
    for i, p in enumerate(pref):
        for g in p:
            cand.update((min(i, j), max(i, j)) for j in post[g] if j != i)
    for group in flat.values():
        cand.update((a, b) for a in group for b in group if a < b)
    for i, j in cand:
        ok, s, how = same(items[i][1], items[j][1])
        if ok:
            best[(i, j)] = (s, how)
            parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(items)):
        groups.setdefault(find(i), []).append(i)
    out = []
    for members in groups.values():
        if len(members) < 2:
            continue
        canon = min(members, key=lambda i: (items[i][2], items[i][0]))
        for i in members:
            if i != canon:
                s, how = best.get((min(i, canon), max(i, canon)), (0.0, "group"))
                out.append((items[i][0], items[canon][0], s, how))
    return out
