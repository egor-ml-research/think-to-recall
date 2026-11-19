"""Topics of the memory: communities of the concept graph (Leiden, as Graphify does), one topic per record.

The concept graph is the store's own: concepts that occur in at least 2 sentences (hubs - concepts in more than
max(8, 2.5 %) of sentences - are left out, as in the graph view), joined by their co-occurrence and synonym edges.
Communities: networkx Leiden (seed 0). A topic is named by its 3 most connected concepts. A record (a user turn with
its report) belongs to the topic most of its concepts belong to; a record without graph concepts has no topic.
No new storage: computed from the store, cached until the number of sentences changes.
"""

from __future__ import annotations

import math
from collections import Counter

STOP = {"коммит", "commit", "тест", "тесты", "файл", "ответ", "вопрос", "час", "часа", "часов", "минут", "день", "раз"}


class Topics:
    def __init__(self, store) -> None:
        import networkx as nx

        s = store
        n_frag = s.q("SELECT COUNT(*) FROM fragments WHERE kind='sentence'")[0][0] or 1
        cap = max(8, int(0.025 * n_frag))
        cons = {c: lab for c, lab, n in s.q("SELECT id, label, n_fragments FROM concepts WHERE n_fragments >= 2")
                if n <= cap and lab.lower() not in STOP and not lab.isdigit() and len(lab) > 1}  # fmt: skip
        G = nx.Graph()
        G.add_nodes_from(cons)
        for a, b, rel, w in s.q("SELECT src, dst, rel, weight FROM edges WHERE rel IN ('cooccur','synonym') "
                                "AND t_invalid IS NULL"):  # fmt: skip
            if a in cons and b in cons and a != b:
                ww = math.log1p(w) if rel == "cooccur" else 0.5 * w
                G.add_edge(a, b, weight=G[a][b]["weight"] + ww if G.has_edge(a, b) else ww)
        G.remove_nodes_from([n for n in list(G) if G.degree(n) == 0])
        comms = nx.community.leiden_communities(G, weight="weight", seed=0) if G.number_of_edges() else []
        comms = sorted(comms, key=lambda c: (-len(c), min(c)))
        self.of = {n: i for i, c in enumerate(comms) for n in c}
        self.name = {}
        for i, c in enumerate(comms):
            lead = sorted(c, key=lambda n: (-G.degree(n, weight="weight"), n))[:3]
            self.name[i] = " · ".join(cons[n] for n in lead)
        self.size = {i: len(c) for i, c in enumerate(comms)}
        self._concepts: dict[str, list[str]] = {}
        for e, c in s.q("SELECT f.episode_id, x.concept_id FROM mentions x JOIN fragments f ON f.id=x.fragment_id"):
            if c in self.of:
                self._concepts.setdefault(e, []).append(c)

    def of_record(self, episodes: list[str]) -> int | None:
        """The topic of a record (its turn and report episodes): the most common topic of its concepts."""
        cnt = Counter(self.of[c] for e in episodes for c in self._concepts.get(e, []))
        if not cnt:
            return None
        return max(cnt, key=lambda t: (cnt[t], self.size[t], -t))
