"""overview() (rule written before the measurement): communities, exact-name decision links, budget, determinism,
the fallback without a code graph. Synthetic projects only."""

import json
import random

from ctxgraph import graphify as GF
from ctxgraph.memory import ProjectMemory
from ctxgraph.overview import MAX_CHARS, overview

MODS = {"shop/cart.py": ["add_item", "remove_item", "cart_total", "CartLine", "apply_coupon", "cart_items"],
        "shop/payments.py": ["charge_card", "refund_order", "PaymentGateway", "retry_policy", "capture_hold"],
        "shop/orders.py": ["place_order", "cancel_order", "OrderStatus", "ship_order", "order_lines"]}  # fmt: skip


def _graph(path, vendor=True, community=True):
    nodes, links = [], []
    for ci, (f, syms) in enumerate(MODS.items()):
        fid = f.replace("/", "_")
        nodes.append({"id": fid, "label": f.rsplit("/", 1)[-1], "source_file": f, "file_type": "code",
                      **({"community": ci} if community else {})})  # fmt: skip
        prev = fid
        for s in syms:
            nodes.append({"id": f"{fid}_{s}", "label": f"{s}()" if s[0].islower() else s, "source_file": f,
                          "file_type": "code", **({"community": ci} if community else {})})  # fmt: skip
            links.append({"source": fid, "target": f"{fid}_{s}", "relation": "contains"})
            links.append({"source": prev, "target": f"{fid}_{s}", "relation": "calls"})
            prev = f"{fid}_{s}"
    links.append({"source": "shop_orders.py_place_order", "target": "shop_payments.py_charge_card", "relation": "calls"})
    links.append({"source": "shop_orders.py_place_order", "target": "shop_cart.py_cart_total", "relation": "calls"})
    if vendor:  # a minified bundle with many nodes: left out
        for i in range(40):
            nodes.append({"id": f"v{i}", "label": f"Zq{i}", "source_file": "static/vendor/lib.min.js",
                          "file_type": "code", "community": 9})  # fmt: skip
            links.append({"source": "v0", "target": f"v{i}", "relation": "calls"}) if i else None
    nodes.append({"id": "why1", "label": "Rationale text", "source_file": "shop/cart.py", "file_type": "rationale",
                  "community": 0})  # fmt: skip
    path.write_text(json.dumps({"nodes": nodes, "links": links}), "utf-8")
    return path


def _t(i, text, ts):
    return {"id": f"o{i:03d}", "session": "s1", "role": "user", "ts": ts, "text": text, "source": "transcript"}


TURNS = [
    _t(1, "Решили: charge_card повторяет платёж три раза, retry_policy держим в payments.py.", "2026-11-02T10:00:00Z"),
    _t(2, "Let's keep the cart in memory for now; cart_total rounds to cents at the end only.", "2026-11-03T10:00:00Z"),
    _t(3, "We decided: ship_order sends no email inline.", "2026-11-05T10:00:00Z"),
    _t(4, "Decided to rename OrderStatus values to lower case.", "2026-11-07T10:00:00Z"),
    _t(5, "Решили не трогать дизайн писем до релиза.", "2026-11-08T10:00:00Z"),
    _t(6, "We decided the payments page stays as is.", "2026-11-09T10:00:00Z"),
]


def _mem(tmp_path, monkeypatch, turns=TURNS, graph=True, **kw):
    monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    monkeypatch.setenv("CTXGRAPH_HOME", str(tmp_path / "home"))
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(turns)
    if graph:
        GF.import_graph(m.db_path, _graph(tmp_path / "graph.json", **kw))
    return m


def test_map_names_communities_links_and_decisions(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch)
    text = overview(m)
    lines = text.splitlines()
    assert lines[0].startswith("Project map: 3 code communities, 19 nodes")  # vendor + rationale nodes left out
    assert "lib.min.js" not in text and "Zq" not in text
    rows = {ln.split()[1]: ln for ln in lines if ln.startswith("#c")}
    assert set(rows) == {"cart.py", "payments.py", "orders.py"}
    assert "↔" in rows["orders.py"]
    # every decision shown sits under the community whose code it names; plain words never link
    owner = None
    for ln in lines[1:]:
        if ln.startswith("#c"):
            owner = ln.split()[1]
        elif ln.startswith("   "):
            names = {"cart.py": MODS["shop/cart.py"], "payments.py": MODS["shop/payments.py"] + ["payments.py"],
                     "orders.py": MODS["shop/orders.py"]}[owner]  # fmt: skip
            assert any(n in ln for n in names), ln
    assert "дизайн писем" not in text and "payments page" not in text
    assert "charge_card повторяет" in text and "OrderStatus values" in text


def test_ambiguous_and_short_names_do_not_link(tmp_path, monkeypatch):
    turns = [_t(1, "Decided: keep add_item, and run() stays.", "2026-11-02T10:00:00Z")]
    m = _mem(tmp_path, monkeypatch, turns)
    db = GF.connect(m.db_path)
    db.execute("INSERT INTO code_nodes VALUES ('x','add_item()','other/x.py','','code',1)")
    db.commit()
    assert "keep add_item" not in overview(m)  # add_item is in two communities now: too frequent to place


def test_deterministic_and_leiden_when_graph_has_no_communities(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, community=False)
    a, b = overview(m), overview(m)
    assert a == b and a.startswith("Project map:") and "#c1" in a


def test_budget_on_5000_nodes(tmp_path, monkeypatch):
    rnd = random.Random(0)
    nodes, links = [], []
    for i in range(5000):
        f = f"pkg/mod_{i % 120:03d}.py"
        nodes.append({"id": f"n{i}", "label": f"function_with_long_name_{i}()", "source_file": f, "file_type": "code",
                      "community": i // 20})  # fmt: skip
    for i in range(12000):
        a = rnd.randrange(5000)
        b = a + rnd.randrange(1, 40) if rnd.random() < 0.8 else rnd.randrange(5000)
        links.append({"source": f"n{a}", "target": f"n{b % 5000}", "relation": "calls"})
    turns = [_t(i, f"Decided: function_with_long_name_{i * 37}() keeps its cache of {i} entries for the batch "
                   "import, and we never retry it inside the request path.", f"2026-10-{1 + i % 28:02d}T10:00:00Z")
             for i in range(60)]  # fmt: skip
    monkeypatch.delenv("CTXGRAPH_QUALITY", raising=False)
    m = ProjectMemory(tmp_path / "proj", home=tmp_path / "home")
    m.import_turns(turns)
    (tmp_path / "g.json").write_text(json.dumps({"nodes": nodes, "links": links}), "utf-8")
    GF.import_graph(m.db_path, tmp_path / "g.json")
    text = overview(m)
    assert len(text) <= MAX_CHARS and text == overview(m)
    assert sum(ln.startswith("#c") for ln in text.splitlines()) >= 1


def test_fallback_without_code_graph(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, graph=False)
    text = overview(m)
    assert "ctxgraph setup --graphify yes" in text and len(text) <= MAX_CHARS
    assert "payments page" in text  # the newest decisions still shown
    empty = ProjectMemory(tmp_path / "e", home=tmp_path / "home2")
    assert "empty" in overview(empty)
