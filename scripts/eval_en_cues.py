"""English cue check on tests/realworld_en: synthetic developer turns, gold label per sentence (do / not / hold /
later / change / rule / none) and a dialogue act per short turn; dev for pattern work, test held out (split by
sha1(id) % 2, written before the patterns changed).

python scripts/eval_en_cues.py test [--out english_cues_test.md]
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from cotrail.cc_transcripts import is_short, short_act
from cotrail.memory import classify

ROOT = Path(__file__).resolve().parents[1]
MAP = {"do": "yes", "change": "yes", "not": "no", "hold": "hold", "later": "hold"}


def predicted(sentence: str) -> str:
    st, ref = classify("user", sentence)
    return {"said": "none", "rule": "rule"}.get(st, ref if st == "decision" else "none")


def correct(gold: str, pred: str) -> bool:
    if gold == "none":
        return pred == "none"
    if gold == "rule":
        return pred == "rule"
    if gold == "change":  # a decision (do or not), no hold
        return pred != "none" and pred != "rule" and set(pred.split("+")) <= {"yes", "no"}
    return set(pred.split("+")) == {MAP[g] for g in gold.split("+")}


def run(split: str) -> tuple[dict, str]:
    rows = [json.loads(x) for x in (ROOT / "tests/realworld_en" / f"{split}.jsonl").read_text("utf-8").splitlines()]
    found, total, false_hits = Counter(), Counter(), Counter()
    miss, fh, act_miss = [], [], []
    a_found, a_total = Counter(), Counter()
    for r in rows:
        if "act" in r:
            assert is_short(r["turn"]), r
            p = short_act(r["turn"])
            a_total[r["act"]] += 1
            if p == r["act"]:
                a_found[r["act"]] += 1
            else:
                act_miss.append(f"- {r['id']} «{r['turn']}» gold {r['act']}, got {p}")
            continue
        assert not is_short(r["turn"]), r
        for s, g in r["sents"]:
            p = predicted(s)
            total[g] += 1
            if correct(g, p):
                found[g] += 1
                continue
            miss.append(f"- {r['id']} «{s}» gold {g}, got {p}")
            if p != "none":
                false_hits[p] += 1
                fh.append(f"- {r['id']} «{s}» got {p}, gold {g}")
    res = {"sent": {g: [found[g], total[g]] for g in sorted(total)}, "acts": {a: [a_found[a], a_total[a]] for a in sorted(a_total)},
           "false_hits": dict(false_hits), "sent_acc": [sum(found.values()), sum(total.values())],
           "act_acc": [sum(a_found.values()), sum(a_total.values())]}
    md = [f"## {split}: sentences {res['sent_acc'][0]}/{res['sent_acc'][1]}, short-turn acts {res['act_acc'][0]}/{res['act_acc'][1]}", "",
          "| gold class | found / total |", "|---|---|"]
    md += [f"| {g} | {f}/{t} |" for g, (f, t) in res["sent"].items()]
    md += ["", "| act | found / total |", "|---|---|"] + [f"| {a} | {f}/{t} |" for a, (f, t) in res["acts"].items()]
    md += ["", f"False hits by predicted class: {res['false_hits']}", "", "### Misses (sentences)"] + miss
    md += ["", "### False hits (sentence got a class it should not have)"] + fh + ["", "### Misses (acts)"] + act_miss
    return res, "\n".join(md) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("split", choices=["dev", "test"])
    ap.add_argument("--out")
    a = ap.parse_args()
    res, md = run(a.split)
    if a.out:
        Path(a.out).write_text(md, encoding="utf-8")
        Path(a.out).with_suffix(".json").write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(md[:600] if a.out else md)
