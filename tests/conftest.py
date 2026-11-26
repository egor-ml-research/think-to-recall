from __future__ import annotations

import pytest

from cotrail.embed import HashingEncoder
from cotrail.graph import Engine
from cotrail.menu import MenuConfig
from cotrail.sources.base import Link, Source
from cotrail.sources.experience import ExperienceSource
from cotrail.store import Node, Store

# Маленький таксономический граф: рыбы → хордовые/виды, аквариум → оборудование.
GRAPH = {
    "f:fish": (
        "рыба",
        [
            ("f:salmonids", "лососевые", "подвид", "deeper"),
            ("f:cyprinids", "карповые", "подвид", "deeper"),
            ("f:cichlids", "цихлиды", "подвид", "deeper"),
            ("f:sharks", "акулы", "подвид", "deeper"),
            ("f:chordates", "хордовые", "обобщение", "side"),
            ("f:amphibians", "земноводные", "брат", "side"),
            ("f:reptiles", "пресмыкающиеся", "брат", "side"),
            ("f:food", "пища", "применяется для", "assoc"),
            ("f:gills", "жабры", "состоит из", "assoc"),
            ("f:ornament", "орнамент", "применяется для", "assoc"),
            ("f:water", "вода", "среда", "assoc"),
        ],
    ),
    "f:salmonids": (
        "лососевые",
        [
            ("f:salmon", "сёмга", "подвид", "deeper"),
            ("f:trout", "форель", "подвид", "deeper"),
            ("f:fish", "рыба", "обобщение", "side"),
        ],
    ),
    "f:aquarium": (
        "аквариум",
        [
            ("f:reef", "рифовый аквариум", "подкласс", "deeper"),
            ("f:filter", "фильтр для воды", "часть", "deeper"),
            ("f:cichlids", "цихлиды", "содержат", "assoc"),
            ("f:terrarium", "террариум", "брат", "side"),
        ],
    ),
    "f:chordates": ("хордовые", [("f:vertebrates", "позвоночные", "подвид", "deeper")]),
}
LINKS = {"рыба": "f:fish", "аквариум": "f:aquarium", "лососевые": "f:salmonids"}


class FakeSource(Source):
    name = "fake"
    prefix = "f:"

    def __init__(self) -> None:
        self.calls = 0

    def link(self, term: str, lang: str) -> list[Node]:
        nid = LINKS.get(term)
        return [Node(nid, GRAPH[nid][0], self.name)] if nid else []

    def neighbors(self, node: Node) -> list[Link]:
        self.calls += 1
        _, nb = GRAPH.get(node.id, ("", []))
        return [
            Link(Node(i, lab, self.name), rel, slot, 0.8, self.name) for i, lab, rel, slot in nb
        ]


@pytest.fixture
def store() -> Store:
    return Store(":memory:")


@pytest.fixture
def make_engine(store):
    def _make(**cfg) -> Engine:
        config = MenuConfig(link_min_sim=-1.0, **cfg)
        return Engine(
            store,
            [FakeSource(), ExperienceSource(store)],
            HashingEncoder(),
            config=config,
            session="s1",
            seed=1,
        )

    return _make


@pytest.fixture(autouse=True)
def _economy_off_for_legacy_tests(monkeypatch, request):
    """The token economy of recall (tests/test_economy.py) is off in the older tests: they pin the full labels."""
    if "test_economy" not in request.node.nodeid:
        monkeypatch.setenv("COTRAIL_ECONOMY", "off")


@pytest.fixture(autouse=True)
def _no_update_check(monkeypatch):
    """No network in tests: the daily update check (autosync.check_update) stays off unless a test asks."""
    monkeypatch.setenv("COTRAIL_NO_UPDATE_CHECK", "1")


@pytest.fixture(autouse=True)
def _isolated_cotrail_home(tmp_path_factory, monkeypatch):
    """No test may write into the real ~/.cotrail: every test gets its own home (env and the module global), and
    whatever a test sets (`--home`, COTRAIL_HOME) is restored afterwards."""
    import cotrail.memory as MM

    home = tmp_path_factory.mktemp("cotrail_home")
    monkeypatch.setenv("COTRAIL_HOME", str(home))
    monkeypatch.setattr(MM, "HOME", home)
