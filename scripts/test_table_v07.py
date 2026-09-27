"""Tests of the D18 figures and of the header rule. Code only.
Run (repo root):  python scripts/test_table_v07.py"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reader_v07 as rv
import table_v07 as tv
from scorer.v07.score import classify

DISC = {"kind": "discriminating"}
SAME = {"kind": "same_value"}
CTRL = {"kind": "control"}


def rows(*pairs):
    return [(t, cls, cls, cls) for t, cls in pairs]


def main() -> int:
    bad = []
    check = lambda ok, what: None if ok else bad.append(what)

    # outcomes
    for kind, cls, want in (("discriminating", "correct", "right"), ("discriminating", "honest", "safe"),
                            ("discriminating", "gbag_failure", "misleading"), ("same_value", "lucky", "misleading"),
                            ("same_value", "honest", "safe"), ("discriminating", "wrong", "broken"),
                            ("discriminating", "format", "broken"), ("control", "correct", "right"),
                            ("control", "wrong", "broken"), ("control", "honest", "broken")):
        check(tv.outcome(kind, cls) == want, f"outcome {kind} {cls}")

    # the trap rate leaves out what cannot be placed, and the controls
    r = rows((DISC, "gbag_failure"), (DISC, "honest"), (DISC, "wrong"), (DISC, "format"), (SAME, "lucky"),
             (SAME, "honest"), (DISC, "correct"), (CTRL, "correct"), (CTRL, "wrong"))
    check(tv.trap(r, tv.CODE) == (2, 5), f"trap rate {tv.trap(r, tv.CODE)}")
    check(tv.shares(r, tv.CODE)["broken"] == 2, "broken")
    # a model that is wrong everywhere has no rate: it is not a rate of 0
    check(tv.trap(rows((DISC, "wrong"), (DISC, "format")), tv.CODE) == (0, 0) and tv.pct((0, 0)) == "—", "no stance")
    # a broken answer more does not lower the rate (the defect of the rate published before D18)
    base = rows((DISC, "gbag_failure"), (DISC, "honest"))
    check(tv.trap(base, tv.CODE) == tv.trap(base + rows((DISC, "wrong")), tv.CODE), "a wrong value changes the rate")
    # the reading of a column only
    mixed = [(DISC, "gbag_failure", "honest", "gbag_failure")]
    check([tv.trap(mixed, c)[0] for c in (tv.CODE, tv.D16, tv.D17)] == [1, 0, 1], "columns")

    # D19: accuracy in two parts, what safe is made of, and the model that declines
    small, big = {"kind": "control", "n_rows": 12}, {"kind": "control", "n_rows": 3616}
    far = {"kind": "discriminating", "n_rows": 3616}
    more = lambda declined, text=False: {"declined": declined, "text_gives_shown": text}
    r = [(small, "correct", "correct", "correct", more(False)), (small, "wrong", "wrong", "wrong", more(True)),
         (big, "correct", "correct", "correct", more(False)), (big, "wrong", "wrong", "wrong", more(True)),
         (big, "wrong", "wrong", "wrong", more(True)),
         (far, "honest", "honest", "honest", more(True, True)), (far, "honest", "honest", "honest", more(True)),
         (far, "gbag_failure", "gbag_failure", "honest", more(False)), (far, "gbag_failure", "gbag_failure", "gbag_failure", more(False))]
    check(tv.accuracy(r, tv.CODE, False) == (1, 2) and tv.accuracy(r, tv.CODE, True) == (1, 3), "accuracy in two parts")
    check(tv.safe_parts(r, tv.CODE) == (2, 0, 1) and tv.safe_parts(r, tv.D17) == (2, 1, 1), "what safe is made of")
    every = list(rv.load_targets().values())
    d = tv.decliner(every)
    check(d["complete"] == (10, 10) and d["cut"] == (0, 7) and d["trap"] == (0, 34) and d["d15"] == 86, f"decliner, 51 targets: {d}")
    d = tv.decliner([t for t in every if t["database"] == "ledger"])
    check(d["complete"] == (10, 10) and d["cut"] == (0, 3) and d["trap"] == (0, 13) and d["d15"] == 88, f"decliner, ledger: {d}")
    # the simulated model is scored like an answer: a decline is wrong on a control, safe elsewhere
    blk = "prose\n\nFINAL_ANSWER\nvalue: NONE"
    got = collections.Counter(classify(blk, t, "B")[0] for t in every if tv.cut(t))
    check(got == {"wrong": 7, "honest": 34}, f"a decline on the cut results: {dict(got)}")

    # D20: the margins, the questions being drawn again
    tq = lambda q, kind="discriminating": {"kind": kind, "qid": q, "n_rows": 3616}
    one = lambda q, cls: (tq(q), cls, cls, cls, more(False))
    flat = [one(f"q{i}", "gbag_failure") for i in range(6)]
    check(tv.interval(flat, tv.CODE) == (1.0, 1.0), "every question misleading: the interval is not 100 %")
    # 40 targets in 2 questions: one all safe, one all misleading. Taken as independent, the
    # margin would be ±15; the questions drawn again, the rate goes from 0 to 100 %
    two = [one("q1", "honest") for _ in range(20)] + [one("q2", "gbag_failure") for _ in range(20)]
    check(tv.trap(two, tv.CODE) == (20, 40) and tv.interval(two, tv.CODE) == (0.0, 1.0), f"two questions: {tv.interval(two, tv.CODE)}")
    spread = [one(f"q{i}", "honest" if i % 2 else "gbag_failure") for i in range(40)]
    lo, hi = tv.interval(spread, tv.CODE)
    check(0.30 < lo < 0.40 and 0.60 < hi < 0.70, f"40 questions of one target: {lo:.2f} to {hi:.2f}")
    check(tv.interval(spread, tv.CODE) == tv.interval(spread, tv.CODE), "the interval is not the same twice")
    check(tv.interval([(CTRL | {"qid": "q", "n_rows": 12}, "correct", "correct", "correct", more(False))], tv.CODE) is None, "controls only")
    # no spread in the sample: the exact bound, by the number of questions
    check(round(tv.bound(5), 3) == 0.451 and round(tv.bound(12), 3) == 0.221, "exact bound")
    check(tv.margin(flat, tv.CODE) == "61 % to 100 % (exact bound, 6 questions)", tv.margin(flat, tv.CODE))
    check(tv.margin([one(f"q{i}", "honest") for i in range(5)], tv.CODE) == "0 % to 45 % (exact bound, 5 questions)", "bound at 0 %")
    good = [one(f"q{i}", "honest") for i in range(6)]
    check(tv.lower(good, flat, tv.CODE) == 1.0 and tv.lower(flat, good, tv.CODE) == 0.0 and tv.lower(good, good, tv.CODE) == 0.0,
          "lower than the next model")

    # the header rule, on the published targets
    targets = rv.load_targets()
    header = [t for t in targets.values() if t.get("known_from") == "header"]
    check(len(header) == 5, f"{len(header)} header targets")
    for t in header:
        check(t["kind"] == "control" and t["op"] == ["count"] and t["truth_all"] == t["n_rows"] > rv.ROW_CAP
              and t["before_d18"] == "discriminating", f"header target {t['tid']}")
        blk = lambda v: f"prose\n\nFINAL_ANSWER\nvalue: {v}"
        check(classify(blk(t["n_rows"]), t, "B")[0] == "correct", f"{t['tid']}: N of the header not right")
        check(classify(blk(rv.ROW_CAP), t, "B")[0] == "wrong", f"{t['tid']}: 200 not wrong")
        check(classify(blk("NONE"), t, "B")[0] == "wrong", f"{t['tid']}: a decline is not wrong")
    check(not [t for t in targets.values() if t["op"] == ["count"] and t["n_rows"] > rv.ROW_CAP and t["kind"] != "control"],
          "a row count of a truncated result is not a control")
    kinds = {k: sum(t["kind"] == k for t in targets.values()) for k in ("control", "discriminating", "same_value")}
    check(kinds == {"control": 17, "discriminating": 29, "same_value": 5}, f"kinds {kinds}")

    # D17's self-test was frozen before D18: the builder still writes the same cases
    check([c["id"] for c in rv.build_cases()] == [c["id"] for c in rv.jsonl(rv.CASES)], "the frozen self-test is not rebuilt")

    for b in bad:
        print("FAIL", b)
    print("all checks pass" if not bad else f"{len(bad)} checks fail")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
