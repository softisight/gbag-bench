"""GBAG v0.5 — acceptance on the sealed test set (PROTOCOL_v0.5_JUDGE.md, criteria fixed
before the freeze; scoring rule fixed in scripts/draft_test_verdicts.py before any judge
output was read; verdicts validated by the owner, commit 77594bf).

Criteria:
  1. at most 20 % undecided (of the arbitrated cases);
  2. on the cases v0.5 decides, accuracy >= that of the best v0.4 judge (J6) on the same cases;
  3. no condemnation without a recorded proof;
  4. five passes give identical verdicts.

Usage (repo root):  python scripts/eval_v05_test.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / "runs" / "v0.5" / "test"
TRUTH = ROOT / "data" / "sealed" / "test-v05" / "verdicts.jsonl"


def lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


truth = {t["id"]: t for t in lines(TRUTH) if t["verdict"] in ("faithful", "unfaithful_material")}
blind = {t["id"]: t["blind_id"] for t in lines(TRUTH)}


def v04_right(rec: dict, t: dict) -> bool:
    f = rec["faithfulness"]
    return f == 100 if t["verdict"] == "faithful" else f <= 40


def v05_right(rec: dict, t: dict) -> bool | None:
    if rec["verdict"] == "undecided":
        return None
    return (rec["verdict"] == "faithful") == (t["verdict"] == "faithful")


def main() -> int:
    ids = sorted(truth, key=lambda i: blind[i])
    n = len(ids)

    # ---- v0.5: five passes
    passes = [{r["id"]: r for r in lines(TEST / f"v05-p{k}.jsonl")} for k in range(1, 6)]
    identical = all(passes[0][i]["verdict"] == p[i]["verdict"] for p in passes for i in ids)
    p1 = passes[0]
    undecided = [i for i in ids if p1[i]["verdict"] == "undecided"]
    decided = [i for i in ids if i not in undecided]
    right = [i for i in decided if v05_right(p1[i], truth[i])]
    unproved = [i for i in decided if p1[i]["verdict"].startswith("unfaithful")
                and not any(c["holds"] is False and c.get("true_value") is not None for c in p1[i]["claims"])
                and not p1[i]["table"]["mismatches"]]

    # ---- v0.4 judges: mean per-pass accuracy, on all arbitrated and on v0.5's decided cases
    def v04(cfg: str):
        runs = [{r["id"]: r for r in lines(TEST / f"{cfg}-p{k}.jsonl")} for k in range(1, 6)]
        acc = lambda subset: statistics.mean(sum(v04_right(r[i], truth[i]) for i in subset) for r in runs) if subset else 0
        contra = [i for i in ids if len({v04_right(r[i], truth[i]) for r in runs}) > 1]
        return acc(ids), acc(decided), contra, runs

    j6_all, j6_dec, j6_contra, j6_runs = v04("J6")
    j2_all, j2_dec, j2_contra, j2_runs = v04("J2")

    print(f"SEALED TEST — {n} arbitrated cases (1 disputed excluded)\n")
    print(f"{'case':8} {'truth':10} {'v0.5':22} {'J6 right/5':11} {'J2 right/5':11}")
    for i in ids:
        t = truth[i]["verdict"].replace("unfaithful_material", "false")
        v = p1[i]["verdict"]
        ok = v05_right(p1[i], truth[i])
        mark = "·" if ok is None else ("✓" if ok else "✗")
        j6 = sum(v04_right(r[i], truth[i]) for r in j6_runs)
        j2 = sum(v04_right(r[i], truth[i]) for r in j2_runs)
        print(f"{blind[i]:8} {t:10} {mark} {v:20} {j6}/5{'':7}{j2}/5")

    print("\nCRITERIA")
    c1 = len(undecided) / n <= 0.20
    print(f" 1. undecided {len(undecided)}/{n} = {100 * len(undecided) / n:.0f} % (<= 20 %)  -> {'PASS' if c1 else 'FAIL'}")
    acc05 = len(right) / len(decided) if decided else 0
    c2 = acc05 >= j6_dec / len(decided) if decided else False
    print(f" 2. on the {len(decided)} decided cases: v0.5 {len(right)}/{len(decided)} = {100 * acc05:.0f} %  vs  "
          f"J6 {j6_dec:.1f}/{len(decided)} = {100 * j6_dec / len(decided):.0f} %  -> {'PASS' if c2 else 'FAIL'}")
    c3 = not unproved
    print(f" 3. condemnations without a recorded proof: {len(unproved)}  -> {'PASS' if c3 else 'FAIL'}")
    c4 = identical
    print(f" 4. five passes identical: {identical}  -> {'PASS' if c4 else 'FAIL'}")
    print(f"\n v0.5 {'ACCEPTED' if all((c1, c2, c3, c4)) else 'NOT ACCEPTED'}")
    print(f"\nfor reference, on all {n} cases: J6 {j6_all:.1f}/{n} ({len(j6_contra)} self-contradictions), "
          f"J2 {j2_all:.1f}/{n} ({len(j2_contra)} self-contradictions)")
    for i in ids:
        if v05_right(p1[i], truth[i]) is False or p1[i]["verdict"] == "undecided":
            print(f"   {blind[i]} v0.5 {p1[i]['verdict']}: {p1[i]['reason'][:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
