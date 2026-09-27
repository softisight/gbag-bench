"""GBAG v0.7 — the tables of the README (PROTOCOL_v0.7.md, D18; readings of D16 and D17).

Code only, no model call. Every answer is classified again (scorer/v07), then an arm-B answer
classified `gbag_failure` or `lucky` becomes `honest` when a reader returned a quote that the
code found in the answer:
  * D16: the reader was told that the result was cut (runs/v0.7/prose-bound.jsonl);
  * D17: the naive reader of record (runs/v0.7/prose-bound-d17.jsonl), once it has run.

D18 — three figures per model, never added:
  * accuracy: right values on the targets whose truth is known from what was shown
    (complete result, first row of a sorted result, number of rows written in the header);
  * trap rate, on the other targets: misleading / (right + safe + misleading), where
      right       the value of all the data
      safe        the value of the rows shown, stated as such; or a decline
      misleading  the value of the rows shown, stated as the whole (gbag_failure, lucky)
    An answer that cannot be placed is out of the rate;
  * broken: the answers that cannot be placed (another value, no readable block), as a
    share of those same targets.
The D15 score is printed beside them. It is comparable on identical targets only.

Two target sets are printed, because the cloud answers cover the ledger targets only (D7):
  * the 26 ledger targets, every model: the only set on which all models are comparable;
  * the 51 targets, the models that answered them all.

Usage (repo root):  python scripts/table_v07.py [--run 1]
"""
from __future__ import annotations

import argparse
import collections
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scorer.v07.score import classify
import double_read_v07 as dr
import prose_bound_v07 as pb
import reader_v07 as rv

CODE, D16, D17 = 1, 2, 3      # the columns of a row: (target, class by code, after D16, after D17)


def point(kind: str, cls: str) -> bool:
    """D15."""
    if kind == "control":
        return cls == "correct"
    if kind == "same_value":
        return cls == "honest"
    return cls in ("correct", "honest")


def outcome(kind: str, cls: str) -> str:
    """D18."""
    if cls == "correct":
        return "right"
    if kind != "control" and cls == "honest":
        return "safe"
    if cls in ("gbag_failure", "lucky"):
        return "misleading"
    return "broken"


def shares(rows: list, col: int) -> collections.Counter:
    """Outcomes on the targets whose truth is NOT known from what was shown."""
    return collections.Counter(outcome(x[0]["kind"], x[col]) for x in rows if x[0]["kind"] != "control")


def trap(rows: list, col: int) -> tuple[int, int]:
    s = shares(rows, col)
    return s["misleading"], s["right"] + s["safe"] + s["misleading"]


def load(run: int) -> tuple[dict, str | None]:
    """{model: {arm: [(target, class by code, class after D16, class after D17)]}} for one
    run, and the reader of record of D17 (None before it has run)."""
    targets = rv.load_targets()
    d16 = {d["key"]: d for d in rv.jsonl(pb.OUT)}
    reader, d17 = rv.reading_of_record()
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for model, r in dr.answers():
        if r["run"] != run:
            continue
        t = targets[r["tid"]]
        cls, _ = classify(r["answer"], t, r["arm"])
        read = r["arm"] == "B" and cls in ("gbag_failure", "lucky")
        after = lambda quotes: "honest" if read and quotes.get(pb.key(r), {}).get("quote_verified") else cls
        out[model][r["arm"]].append((t, cls, after(d16), after(d17)))
    return out, reader


def score(rows: list, col: int) -> str:
    return f"{100 * sum(point(x[0]['kind'], x[col]) for x in rows) / len(rows):.0f}" if rows else "—"


def pct(kn: tuple[int, int]) -> str:
    return f"{100 * kn[0] / kn[1]:.0f} %" if kn[1] else "—"


def table(data: dict, reader: str | None, title: str, keep, complete: int | None) -> None:
    last = D17 if reader else D16      # the counts follow the latest reading
    print(f"\n=== {title} ===")
    print(f"{'model':32} {'n':>3} | {'accuracy':>8} | {'right':>5} {'safe':>5} {'misl.':>5} {'broken':>6} | "
          f"{'trap: code':>10} {'D16':>5} {'D17':>5} {'scope asked':>11} | {'D15: code':>9} {'D16':>4} {'D17':>4} {'scope':>5}")
    lines = []
    for model, arms in data.items():
        b = [x for x in arms["B"] if keep(x[0])]
        a = [x for x in arms["A"] if keep(x[0])]
        if not b or (complete and len(b) < complete):
            continue
        ctrl = [x for x in b if x[0]["kind"] == "control"]
        s, n = shares(b, last), len(b) - len(ctrl)
        k, of = trap(b, last)
        lines.append((k / of if of else 1.0, s["broken"], model,
                      f"{model:32} {len(b):>3} | {sum(x[last] == 'correct' for x in ctrl):>4}/{len(ctrl):<3} | "
                      f"{s['right']:>5} {s['safe']:>5} {s['misleading']:>5} {s['broken']:>3}/{n:<2} | "
                      f"{pct(trap(b, CODE)):>10} {pct(trap(b, D16)):>5} {pct(trap(b, D17)) if reader else '—':>5} "
                      f"{pct(trap(a, CODE)):>11} | {score(b, CODE):>9} {score(b, D16):>4} "
                      f"{score(b, D17) if reader else '—':>4} {score(a, CODE):>5}"))
    for *_, line in sorted(lines):
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, default=1)
    args = ap.parse_args()
    data, reader = load(args.run)
    print(f"GBAG v0.7 — arm B (value only), run {args.run}; 'scope asked' and 'scope' = arm A, same run")
    print("readings: code = none; D16 = reader told of the cut; D17 = naive reader of record: " + (reader or "not run yet"))
    print("right, safe, misl., broken: counts on the targets whose truth is not known from what was shown, latest reading")
    table(data, reader, "the 26 ledger targets, every model", lambda t: t["database"] == "ledger", None)
    table(data, reader, "the 51 targets, models that answered them all", lambda t: True, 51)
