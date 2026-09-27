"""GBAG v0.7 — what asking for the scope changes (PROTOCOL_v0.7.md, D17, "Why"). Code only.

For every discriminating target a model answered in both arms (run 1):
  * is the declared VALUE the same with the scope asked (arm A) and without (arm B)?
  * when both arms declare the shown-rows value: does the model say so when ASKED (arm A
    declares rows_shown or cannot_determine), and does it say so BY ITSELF (arm B: in the
    block, or in the text with a quote found by code)?

Usage (repo root):  python scripts/arms_v07.py
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scorer.v07.score import _is_none, classify, same
import double_read_v07 as dr
import prose_bound_v07 as pb
import reader_v07 as rv


def value_class(parsed: dict | None, t: dict) -> str:
    if parsed is None:
        return "no block"
    if same(parsed["value"], t["truth_all"], t["type"]):
        return "ALL"
    if same(parsed["value"], t["truth_shown"], t["type"]):
        return "SHOWN"
    return "NONE" if _is_none(parsed["value"]) else "other"


def main() -> int:
    targets = rv.load_targets()
    d16 = {d["key"]: d["quote_verified"] for d in rv.jsonl(pb.OUT)}
    reader, d17 = rv.reading_of_record()
    pairs = collections.defaultdict(dict)
    for model, r in dr.answers():
        t = targets[r["tid"]]
        if r["run"] == 1 and t["kind"] == "discriminating":
            cls, parsed = classify(r["answer"], t, r["arm"])
            pairs[(model, r["tid"])][r["arm"]] = (cls, value_class(parsed, t), pb.key(r))
    both = {k: v for k, v in pairs.items() if len(v) == 2}
    same_value = sum(v["A"][1] == v["B"][1] for v in both.values())
    print(f"declared value, arm A against arm B: the same in {same_value} of {len(both)} pairs")

    print(f"\nvalue of the rows shown in BOTH arms — reading of D17: {reader or 'not run'}")
    print(f"{'model':34} {'answers':>7} | {'says so when asked':>18} | {'by itself, D16':>14} | {'by itself, D17':>14}")
    rows = collections.defaultdict(lambda: [0, 0, 0, 0])
    for (model, _), v in both.items():
        if v["A"][1] == v["B"][1] == "SHOWN":
            c = rows[model]
            c[0] += 1
            c[1] += v["A"][0] == "honest"
            c[2] += v["B"][0] == "honest" or bool(d16.get(v["B"][2]))
            c[3] += v["B"][0] == "honest" or bool(d17.get(v["B"][2], {}).get("quote_verified"))
    for model, (n, asked, by16, by17) in sorted(rows.items(), key=lambda x: -x[1][0]):
        print(f"{model:34} {n:>7} | {asked:>18} | {by16:>14} | {by17 if reader else '—':>14}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
