"""English cues v2 (tests/realworld_en, synthetic): typical refusals, changes, later items, rules and short answers."""
import importlib.util
from pathlib import Path

from ctxgraph.cc_transcripts import short_act
from ctxgraph.memory import classify, is_rule

ROOT = Path(__file__).resolve().parents[1]


def _kind(s):
    st, ref = classify("user", s)
    return ref if st == "decision" else st


def test_examples():
    assert _kind("let's not add redis for this") == "no"
    assert _kind("forget about the caching layer") == "no"
    assert _kind("on second thought, keep the old schema") == "yes"
    assert _kind("changed my mind, stick with fastapi") == "yes"
    assert _kind("let's park the i18n work for now") == "hold"
    assert _kind("don't push yet, i want to look at the diff first") == "hold"
    assert _kind("please don't rewrite the tests, just fix the import") == "no+yes"
    assert is_rule("don't ever force push to main") and is_rule("every time you change the schema, write a migration")
    assert not is_rule("it always fails on the second run") and not is_rule("the client never sends the header")
    assert [short_act(t) for t in ("nah", "park it", "makes sense", "works now", "bump the version")] == \
        ["reject", "defer", "agree", "status", "directive"]


def test_eval_set_scores_do_not_drop():
    spec = importlib.util.spec_from_file_location("eval_en_cues", ROOT / "scripts" / "eval_en_cues.py")
    ev = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ev)
    dev, test = ev.run("dev")[0], ev.run("test")[0]
    assert dev["sent_acc"][0] >= 81 and dev["act_acc"][0] >= 31
    assert test["sent_acc"][0] >= 64 and test["act_acc"][0] >= 25
