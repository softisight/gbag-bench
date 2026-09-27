"""GBAG v0.6 — acceptance on the sealed test set (PROTOCOL_v0.6_JUDGE.md, criteria fixed
before the freeze; scoring rule fixed in scripts/draft_test_v06_verdicts.py before any judge
output was read; verdicts validated by the owner, commit c759696).

Criteria (v0.6-jev, and v0.6-lex under the same criteria):
  1. at most 20 % undecided (of the arbitrated cases);
  2. on the cases v0.6 decides, accuracy >= that of J6 on the same cases (open until J6 runs);
  3. no condemnation without a recorded proof;
  4. five passes give identical verdicts.
Secondary configuration: J6 (majority of 5 passes) on the answers v0.6-jev leaves undecided,
reported apart as unproven verdicts.

Usage (repo root):  python scripts/eval_v06_test.py
"""
from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
TEST = ROOT / "runs" / "v0.6" / "test"
TRUTH = ROOT / "data" / "sealed" / "test-v06" / "verdicts.jsonl"


def lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


truth = {t["id"]: t for t in lines(TRUTH) if t["verdict"] in ("faithful", "unfaithful_material")}
blind = {t["id"]: t["blind_id"] for t in lines(TRUTH)}
ids = sorted(truth, key=lambda i: blind[i])
n = len(ids)


def v04_right(rec: dict, t: dict) -> bool:
    f = rec["faithfulness"]
    return f == 100 if t["verdict"] == "faithful" else f <= 40


def v06_right(rec: dict, t: dict) -> bool | None:
    if rec["verdict"] == "undecided":
        return None
    return (rec["verdict"] == "faithful") == (t["verdict"] == "faithful")


def proved(rec: dict) -> bool:
    return any(u["holds"] is False and u.get("true_values") for u in rec["units"]) or bool(rec["table"]["mismatches"])


def v04_runs(cfg: str) -> list[dict]:
    runs = [{r["id"]: r for r in lines(TEST / f"{cfg}-p{k}.jsonl")} for k in range(1, 6)]
    return runs if all(len(r) >= len(ids) and all(i in r for i in ids) for r in runs) else []


def majority(runs: list[dict], i: str) -> str:
    fs = [r[i]["faithfulness"] for r in runs]
    return "faithful" if sum(f == 100 for f in fs) >= 3 else "condemned" if sum(f <= 40 for f in fs) >= 3 else "undecided"


def criteria(mode: str, j6: list[dict]) -> tuple[bool, dict]:
    passes = [{r["id"]: r for r in lines(TEST / f"v06-{mode}-p{k}.jsonl")} for k in range(1, 6)]
    if not all(all(i in p for i in ids) for p in passes):
        print(f"[{mode}] passes incomplete")
        return False, {}
    p1 = passes[0]
    identical = all(passes[0][i]["verdict"] == p[i]["verdict"] for p in passes for i in ids)
    undecided = [i for i in ids if p1[i]["verdict"] == "undecided"]
    decided = [i for i in ids if i not in undecided]
    right = [i for i in decided if v06_right(p1[i], truth[i])]
    unproved = [i for i in decided if p1[i]["verdict"].startswith("unfaithful") and not proved(p1[i])]
    print(f"\nv0.6-{mode.upper()} — CRITERIA")
    c1 = len(undecided) / n <= 0.20
    print(f" 1. undecided {len(undecided)}/{n} = {100 * len(undecided) / n:.0f} % (<= 20 %)  -> {'PASS' if c1 else 'FAIL'}")
    acc = len(right) / len(decided) if decided else 0
    if j6:
        j6_dec = statistics.mean(sum(v04_right(r[i], truth[i]) for i in decided) for r in j6) if decided else 0
        c2 = bool(decided) and acc >= j6_dec / len(decided)
        print(f" 2. on the {len(decided)} decided cases: v0.6 {len(right)}/{len(decided)} = {100 * acc:.0f} %  vs  "
              f"J6 {j6_dec:.1f}/{len(decided)} = {100 * j6_dec / len(decided):.0f} %  -> {'PASS' if c2 else 'FAIL'}")
    else:
        c2 = None
        print(f" 2. on the {len(decided)} decided cases: v0.6 {len(right)}/{len(decided)} = {100 * acc:.0f} %  vs  "
              f"J6 (not run yet)  -> OPEN")
    c3 = not unproved
    print(f" 3. condemnations without a recorded proof: {len(unproved)}  -> {'PASS' if c3 else 'FAIL'}")
    print(f" 4. five passes identical: {identical}  -> {'PASS' if identical else 'FAIL'}")
    verdict = "OPEN (criterion 2 awaits J6)" if c2 is None and all((c1, c3, identical)) else \
        ("ACCEPTED" if all((c1, c2, c3, identical)) else "NOT ACCEPTED")
    print(f" v0.6-{mode} {verdict}")
    models = sorted({m for p in passes for r in p.values() for m in (r.get("jev_models") or [])})
    if models:
        print(f" Jev version(s) returned: {models}; cost {sum(r.get('cost_usd') or 0 for p in passes for r in p.values()):.3f} USD")
    for i in ids:
        if v06_right(p1[i], truth[i]) is not True:
            print(f"   {blind[i]} {p1[i]['verdict']}: {p1[i]['reason'][:220]}")
    return True, p1


def main() -> int:
    j6, j2 = v04_runs("J6"), v04_runs("J2")
    print(f"SEALED TEST v06 — {n} arbitrated cases (1 minor and 2 disputed excluded)")
    _, jev = criteria("jev", j6)
    _, lex = criteria("lex", j6)

    print(f"\n{'case':8} {'truth':10} {'v0.6-jev':22} {'v0.6-lex':22} {'J6 right/5':11} {'J2 right/5':11}")
    for i in ids:
        t = truth[i]["verdict"].replace("unfaithful_material", "false")
        cells = []
        for p in (jev, lex):
            if p:
                ok = v06_right(p[i], truth[i])
                cells.append(f"{'·' if ok is None else ('✓' if ok else '✗')} {p[i]['verdict']:20}")
            else:
                cells.append(f"{'—':22}")
        j6c = f"{sum(v04_right(r[i], truth[i]) for r in j6)}/5" if j6 else "—"
        j2c = f"{sum(v04_right(r[i], truth[i]) for r in j2)}/5" if j2 else "—"
        print(f"{blind[i]:8} {t:10} {cells[0]} {cells[1]} {j6c:11} {j2c:11}")

    for cfg, runs in (("J6", j6), ("J2", j2)):
        if runs:
            acc = statistics.mean(sum(v04_right(r[i], truth[i]) for i in ids) for r in runs)
            contra = [i for i in ids if len({v04_right(r[i], truth[i]) for r in runs}) > 1]
            print(f"\n{cfg} on all {n} cases: {acc:.1f}/{n} per pass, {len(contra)} self-contradictions")

    if jev:
        und = [i for i in ids if jev[i]["verdict"] == "undecided"]
        print(f"\nSECONDARY CONFIGURATION — on the {len(und)} answers v0.6-jev leaves undecided (unproven verdicts)")
        for cfg, runs in (("J6", j6), ("J2 (for information)", j2)):
            if not runs:
                print(f" {cfg}: not run yet")
                continue
            got = {i: majority(runs, i) for i in und}
            dec = [i for i in und if got[i] != "undecided"]
            ok = sum((got[i] == "faithful") == (truth[i]["verdict"] == "faithful") for i in dec)
            print(f" {cfg}: decides {len(dec)}/{len(und)}, right on {ok}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
