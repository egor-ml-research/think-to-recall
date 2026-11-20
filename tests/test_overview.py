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
    _t(6, "We decided the checkout page stays as is.", "2026-11-09T10:00:00Z"),
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
    assert lines[0].startswith("Project map: 3 code areas, 19 nodes")  # vendor + rationale nodes left out
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
    assert "дизайн писем" not in text and "checkout page" not in text
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
    for _ in range(12000):
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
    from ctxgraph.overview import MAX_TOKENS, _ntok

    assert _ntok(text) <= MAX_TOKENS
    assert sum(ln.startswith("#c") for ln in text.splitlines()) >= 1


def test_fallback_without_code_graph(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, graph=False)
    text = overview(m)
    assert "ctxgraph setup --graphify yes" in text and len(text) <= MAX_CHARS
    assert "checkout page" in text  # the newest decisions still shown
    empty = ProjectMemory(tmp_path / "e", home=tmp_path / "home2")
    assert "empty" in overview(empty)


def _git(root, *a):
    import subprocess

    return subprocess.run(["git", "-C", str(root), "-c", "user.email=t@t", "-c", "user.name=t", *a], check=True,
                          capture_output=True, text=True).stdout.strip()  # fmt: skip


def _project(tmp_path):
    """The shop project on disk: orders.py is an entry point; tests/ and an overview.exclude entry are left out."""
    root = tmp_path / "proj"
    for f in MODS:
        (root / f).parent.mkdir(parents=True, exist_ok=True)
        (root / f).write_text("x = 1\n", "utf-8")
    (root / "shop/orders.py").write_text('def main():\n    pass\n\nif __name__ == "__main__":\n    main()\n', "utf-8")
    (root / "overview.exclude").write_text("# research\n/shop/legacy/\n", "utf-8")
    return root


def _extra_nodes(path):
    g = json.loads(path.read_text("utf-8"))
    for i, f in enumerate(["tests/test_cart.py", "scripts/bench.py", "shop/legacy/old.py"]):
        for j in range(6):
            g["nodes"].append({"id": f"x{i}_{j}", "label": f"helper_{i}_{j}()", "source_file": f, "file_type": "code",
                               "community": 20 + i})  # fmt: skip
            if j:
                g["links"].append({"source": f"x{i}_0", "target": f"x{i}_{j}", "relation": "calls"})
    path.write_text(json.dumps(g), "utf-8")


def test_exclusions_and_entry_point_ranking(tmp_path, monkeypatch):
    _project(tmp_path)
    m = _mem(tmp_path, monkeypatch, graph=False)
    _extra_nodes(_graph(tmp_path / "graph.json"))
    GF.import_graph(m.db_path, tmp_path / "graph.json")
    text = overview(m)
    assert "helper_" not in text and "test_cart" not in text and "bench.py" not in text and "old.py" not in text
    assert text.splitlines()[1].startswith("#c1 orders.py")  # the entry point ranks first


def test_decision_linked_by_its_commit(tmp_path, monkeypatch):
    root = _project(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    (root / "shop/payments.py").write_text("RETRIES = 3\n", "utf-8")
    _git(root, "commit", "-q", "-am", "retries")
    h = _git(root, "rev-parse", "HEAD")
    turns = [_t(1, "Решили: делаем повторные попытки для платежей.", "2026-11-10T10:00:00Z"),
             {**_t(2, f"Повторные попытки для платежей готовы, коммит {h[:7]}.", "2026-11-10T11:00:00Z"),
              "role": "assistant"}]  # fmt: skip
    m = _mem(tmp_path, monkeypatch, turns)
    text = overview(m)
    block = text.split("#c")[[i for i, b in enumerate(text.split("#c")) if b.split()[1:2] == ["payments.py,"]
                              or b.split()[1:2] == ["payments.py"]][0]]  # fmt: skip
    assert f"→ {h[:7]}" in block and "повторные попытки" in block


def test_ignore_patterns():
    from ctxgraph.overview import Ignore

    ig = Ignore(["# c", "benchmark_e1*/", "/ctxgraph/e1/", "*.egg-info/", "!keep.py", "docs/**/x.py"])
    assert ig("benchmark_e1b/run.py") and ig("a/benchmark_e1/x.py") and ig("ctxgraph/e1/runner.py")
    assert not ig("pkg/ctxgraph/e1/runner.py") and not ig("ctxgraph/e1b/x.py") and ig("pkg.egg-info/PKG")
    assert ig("docs/a/b/x.py") and not ig("keep.py")


def test_entry_nodes_are_functions_not_files(tmp_path):
    from ctxgraph.overview import _entry_nodes

    root = tmp_path / "p"
    (root / "shop").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project.scripts]\nshop = "shop.cart:add_item"\n', "utf-8")
    (root / "shop/cart.py").write_text("def add_item():\n    pass\n", "utf-8")
    (root / "shop/api.py").write_text("@server.tool()\n@cached\ndef cart_total():\n    pass\n\ndef helper():\n    pass\n",
                                      "utf-8")  # fmt: skip
    (root / "shop/run.py").write_text('def go():\n    pass\n\nif __name__ == "__main__":\n    go()\nprint(1)\n', "utf-8")
    nodes = {"f1": ("cart.py", "shop/cart.py", "code", 0), "a": ("add_item()", "shop/cart.py", "code", 1),
             "f2": ("api.py", "shop/api.py", "code", 2), "t": ("cart_total()", "shop/api.py", "code", 3),
             "h": ("helper()", "shop/api.py", "code", 2), "f3": ("run.py", "shop/run.py", "code", 4),
             "g": ("go()", "shop/run.py", "code", 5)}  # fmt: skip
    assert _entry_nodes(root, nodes) == {"a", "t", "g"}


def test_one_line_per_file(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, graph=False)
    g = json.loads(_graph(tmp_path / "graph.json").read_text("utf-8"))
    for n in g["nodes"]:  # cart.py split by Graphify into two communities
        if n["id"] in ("shop_cart.py_apply_coupon", "shop_cart.py_cart_items", "shop_cart.py_CartLine",
                       "shop_cart.py_cart_total", "shop_cart.py_remove_item"):  # fmt: skip
            n["community"] = 7
    (tmp_path / "graph.json").write_text(json.dumps(g), "utf-8")
    GF.import_graph(m.db_path, tmp_path / "graph.json")
    text = overview(m)
    assert sum(ln.split()[1].rstrip(",") == "cart.py" for ln in text.splitlines() if ln.startswith("#c")) == 1
    assert text.startswith("Project map: 3 code areas")


def test_commit_tie_without_a_name_does_not_link(tmp_path, monkeypatch):
    root = _project(tmp_path)
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "init")
    (root / "shop/payments.py").write_text("RETRIES = 3\n", "utf-8")
    (root / "shop/cart.py").write_text("RETRIES = 3\n", "utf-8")
    _git(root, "commit", "-q", "-am", "retries")
    h = _git(root, "rev-parse", "HEAD")
    turns = [_t(1, "Решили: делаем повторные попытки для платежей.", "2026-11-10T10:00:00Z"),
             {**_t(2, f"Повторные попытки для платежей готовы, коммит {h[:7]}.", "2026-11-10T11:00:00Z"),
              "role": "assistant"}]  # fmt: skip
    text = overview(_mem(tmp_path, monkeypatch, turns))
    assert "повторные попытки" not in text and "→" not in text


def test_top_level_modules_named_on_their_home_line(tmp_path, monkeypatch):
    m = _mem(tmp_path, monkeypatch, graph=False)
    g = json.loads(_graph(tmp_path / "graph.json").read_text("utf-8"))
    for i, f in enumerate(["shop/alpha.py", "shop/beta.py", "shop/gamma.py", "shop/delta.py"]):
        g["nodes"].append({"id": f"e{i}", "label": f"fn_{i}()", "source_file": f, "file_type": "code", "community": 0})
        g["links"].append({"source": "shop_cart.py", "target": f"e{i}", "relation": "calls"})
    (tmp_path / "graph.json").write_text(json.dumps(g), "utf-8")
    GF.import_graph(m.db_path, tmp_path / "graph.json")
    line = next(ln for ln in overview(m).splitlines() if ln.startswith("#c") and " cart.py" in ln)
    assert all(x in line for x in ("alpha.py", "beta.py", "gamma.py", "delta.py"))


def test_hard_token_limit(tmp_path, monkeypatch):
    from ctxgraph import overview as O

    m = _mem(tmp_path, monkeypatch)
    monkeypatch.setattr(O, "MAX_TOKENS", 60)
    text = O.overview(m)
    assert O._ntok(text) <= 60 and text.startswith("Project map:")
