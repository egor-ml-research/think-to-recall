"""BM25 over the stored sentences: the default recall of the decision memory (no model, no download).

Words are lower-cased; Russian words are lemmatized with pymorphy3 (its dictionaries ship with the package). Okapi
BM25 with k1 = 1.5, b = 0.75. The index is built lazily and extended when new sentences arrive, so a long-running MCP
server only tokenizes what is new. Chosen on a real-world check of 29 questions about past decisions: BM25 19 / 0
/ 10 correct / outdated / wrong vs multilingual-e5-base int8 17 / 4 / 8; BM25 + e5 fused by RRF 21 / 2 / 6 is the
optional `cotrail setup --quality` mode.
"""

from __future__ import annotations

import math
import re
from collections import Counter

import numpy as np

K1, B = 1.5, 0.75
_LEMMA: dict[str, str] = {}
_MORPH = None


def _lemma(w: str) -> str:
    global _MORPH
    if w not in _LEMMA:
        if _MORPH is None:
            import pymorphy3

            _MORPH = pymorphy3.MorphAnalyzer()
        _LEMMA[w] = _MORPH.parse(w)[0].normal_form
    return _LEMMA[w]


def tokens(text: str) -> list[str]:
    return [_lemma(w) if re.search(r"[а-яё]", w) else w for w in re.findall(r"\w+", text.lower())]


class BM25Index:
    """Sentences in the order of `fids`; `extend` adds new ones (the order of the graph's fragment list)."""

    def __init__(self) -> None:
        self.fids: list[str] = []
        self.docs: list[Counter] = []
        self.df: Counter = Counter()
        self.lens: list[int] = []

    def extend(self, fids: list[str], texts: list[str]) -> None:
        for f, t in zip(fids, texts, strict=True):
            d = Counter(tokens(t))
            self.fids.append(f)
            self.docs.append(d)
            self.lens.append(sum(d.values()))
            self.df.update(d.keys())

    def scores(self, query: str) -> np.ndarray:
        n = len(self.docs)
        out = np.zeros(n, dtype=np.float32)
        if not n:
            return out
        avg = (sum(self.lens) / n) or 1.0
        q = [w for w in tokens(query) if w in self.df]
        if not q:
            return out
        idf = {w: math.log(1 + (n - self.df[w] + 0.5) / (self.df[w] + 0.5)) for w in set(q)}
        for i, d in enumerate(self.docs):
            s = 0.0
            for w in q:
                tf = d.get(w, 0)
                if tf:
                    s += idf[w] * tf * (K1 + 1) / (tf + K1 * (1 - B + B * self.lens[i] / avg))
            out[i] = s
        return out
