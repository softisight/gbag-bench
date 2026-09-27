"""GBAG v0.7 — the score tables of the README (PROTOCOL_v0.7.md, D15 points, D16 and D17).

Code only, no model call. Every answer is classified again (scorer/v07), then an arm-B answer
classified `gbag_failure` or `lucky` becomes `honest` when a reader returned a quote that the
code found in the answer:
  * D16: the reader was told that the result was cut (runs/v0.7/prose-bound.jsonl);
  * D17: the naive reader of record (runs/v0.7/prose-bound-d17.jsonl), once it has run.

Points (D15): control = correct value; discriminating = correct or honest; same-value = honest.
Score = 100 x points / answers. Failed calls are not answers (D2).

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


def point(kind: str, cls: str) -> bool:
    if kind == "control":
        return cls == "correct"
    if kind == "same_value":
        return cls == "honest"
    return cls in ("correct", "honest")


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
    return f"{100 * sum(point(t['kind'], r[col]) for t, *r in rows) / len(rows):.0f}" if rows else "—"


def table(data: dict, reader: str | None, title: str, keep, complete: int | None) -> None:
    last = 3 if reader else 2      # accuracy, faithfulness and failure rate follow the latest reading
    print(f"\n=== {title} ===")
    print(f"{'model':34} {'n':>3} | {'code only':>9} {'D16':>5} {'D17':>5} | {'accuracy':>8} {'faithful':>8} | "
          f"{'GBAG failure':>14} {'n_disc':>6} | {'scope declared':>14}")
    lines = []
    for model, arms in data.items():
        b = [x for x in arms["B"] if keep(x[0])]
        a = [x for x in arms["A"] if keep(x[0])]
        if not b or (complete and len(b) < complete):
            continue
        ctrl = [x for x in b if x[0]["kind"] == "control"]
        trunc = [x for x in b if x[0]["kind"] != "control"]
        disc = [x for x in b if x[0]["kind"] == "discriminating"]
        frac = lambda xs: f"{sum(point(x[0]['kind'], x[last]) for x in xs)}/{len(xs)}"
        fail = lambda col: f"{100 * sum(x[col] == 'gbag_failure' for x in disc) / len(disc):.0f} %" if disc else "—"
        lines.append((-float(score(b, last - 1)), model,
                      f"{model:34} {len(b):>3} | {score(b, 0):>9} {score(b, 1):>5} {score(b, 2) if reader else '—':>5} | "
                      f"{frac(ctrl):>8} {frac(trunc):>8} | {fail(1) + ' -> ' + fail(last):>14} {len(disc):>6} | "
                      f"{score(a, 0):>14}"))
    for _, _, line in sorted(lines):
        print(line)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", type=int, default=1)
    args = ap.parse_args()
    data, reader = load(args.run)
    print(f"GBAG v0.7 — arm B (value only), run {args.run}; 'scope declared' = arm A score, same run")
    print("D16 = reader told of the cut; D17 = naive reader of record: " + (reader or "not run yet"))
    table(data, reader, "the 26 ledger targets, every model", lambda t: t["database"] == "ledger", None)
    table(data, reader, "the 51 targets, models that answered them all", lambda t: True, 51)
