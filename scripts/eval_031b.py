"""Evaluate the judge of DeskInsight's benchmark runner BEFORE (no facts) vs AFTER (verified
facts) on arbitrated GBAG answers. "031-B" is the name of that experiment in DeskInsight's
own work plan (the C# port of DeskInsight, a separate repository). Metrics fixed before the
run:

  * judge verdict of one call: ACQUIT if "No Hallucination" = 20 (no claim contradicted),
    CONDEMN if <= 10 (at least one claim contradicted); no score -> FAILED call;
  * accuracy: faithful -> ACQUIT is right, unfaithful_material -> CONDEMN is right; mean over
    passes, failed calls counted wrong;
  * self-contradictions: answers whose verdict is not the same on every pass;
  * unverifiable share: claims marked `unverifiable` / all claims listed, from the raw output.

Usage (repo root):  python scripts/eval_031b.py [runs/031b/measure.jsonl [replay.jsonl]]
"""
from __future__ import annotations

import collections
import json
import re
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
PATH = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs" / "031b" / "measure.jsonl"


def verdict(r: dict) -> str:
    nh = r.get("no_hallucination")
    if nh is None or r.get("empty_verdict"):
        return "failed"
    return "acquit" if nh >= 20 else "condemn"


def claims(raw: str) -> list[str]:
    return [m.lower() for m in re.findall(r'"verdict"\s*:\s*"(supported|contradicted|unverifiable)"', raw or "", re.I)]


def main() -> int:
    rows = [json.loads(l) for l in PATH.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"{len(rows)} judge calls from {PATH.name}")
    if len(sys.argv) > 2:       # a replay: a call played again takes the place of the first one
        again = {(r["id"], r["condition"], r["pass"]): r
                 for r in (json.loads(l) for l in Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if l.strip())}
        rows = [again.get((r["id"], r["condition"], r["pass"]), r) for r in rows]
        print(f"{len(again)} calls played again, from {Path(sys.argv[2]).name}: "
              f"{sum(verdict(r) != 'failed' for r in again.values())} give a verdict")
    for cond in ("avant", "apres"):
        rs = [r for r in rows if r["condition"] == cond]
        if not rs:
            continue
        by_pass = collections.defaultdict(list)
        by_case = collections.defaultdict(list)
        for r in rs:
            v = verdict(r)
            right = (v == "acquit") if r["truth"] == "faithful" else (v == "condemn")
            by_pass[r["pass"]].append(right)
            by_case[r["id"]].append(v)
        acc = statistics.mean(sum(x) / len(x) for x in by_pass.values())
        contra = sum(1 for vs in by_case.values() if len(set(vs)) > 1)
        cl = [c for r in rs for c in claims(r["raw"])]
        unv = cl.count("unverifiable") / len(cl) if cl else 0
        failed = sum(verdict(r) == "failed" for r in rs)
        fa = [r for r in rs if r["truth"] == "faithful"]
        un = [r for r in rs if r["truth"] != "faithful"]
        print(f"\n[{cond}] {len(by_case)} answers x {len(by_pass)} pass(es)")
        print(f"  accuracy (mean over passes): {100 * acc:.1f} %")
        print(f"    correct answers acquitted : {sum(verdict(r) == 'acquit' for r in fa)}/{len(fa)} calls")
        print(f"    false answers condemned   : {sum(verdict(r) == 'condemn' for r in un)}/{len(un)} calls")
        print(f"  self-contradictions: {contra} answer(s)")
        print(f"  unverifiable claims: {100 * unv:.1f} % of {len(cl)}")
        print(f"  failed calls: {failed}")
        # by the size of the result (fixed before the cloud run of 2026-09-27): the rows
        # carry `n_rows`, the number of rows of the gold result
        if all("n_rows" in r for r in rs):
            for label, big in (("200 rows or less ", False), ("more than 200 rows", True)):
                g = [r for r in rs if (r["n_rows"] > 200) == big]
                if not g:
                    continue
                ok = [right_call(r) for r in g]
                gf = [r for r in g if r["truth"] == "faithful"]
                gu = [r for r in g if r["truth"] != "faithful"]
                print(f"  {label}: {len({r['id'] for r in g}):>2} answers | right verdicts {sum(ok)}/{len(ok)} = {100 * sum(ok) / len(ok):.0f} %"
                      f" | correct acquitted {sum(right_call(r) for r in gf)}/{len(gf)} | false condemned {sum(right_call(r) for r in gu)}/{len(gu)}")

    # what the facts change, answer by answer: the verdict of the majority of the passes
    maj = {}
    for cond in ("avant", "apres"):
        by_case = collections.defaultdict(list)
        for r in rows:
            if r["condition"] == cond:
                by_case[r["id"]].append(right_call(r))
        maj[cond] = {k: sum(v) * 2 > len(v) for k, v in by_case.items()}
    both = sorted(set(maj["avant"]) & set(maj["apres"]))
    if both:
        truth = {r["id"]: r["truth"] for r in rows}
        size = {r["id"]: r.get("n_rows") for r in rows}
        fixed = [k for k in both if not maj["avant"][k] and maj["apres"][k]]
        broken = [k for k in both if maj["avant"][k] and not maj["apres"][k]]
        print(f"\n[avant -> apres] {len(both)} answers, verdict of the majority of the passes")
        print(f"  right in both: {sum(maj['avant'][k] and maj['apres'][k] for k in both)} | wrong in both: "
              f"{sum(not maj['avant'][k] and not maj['apres'][k] for k in both)} | repaired by the facts: {len(fixed)} | broken by the facts: {len(broken)}")
        for name, ks in (("repaired", fixed), ("broken", broken),
                         ("wrong in both", [k for k in both if not maj["avant"][k] and not maj["apres"][k]])):
            for k in ks:
                print(f"    {name:14} {k:42} {truth[k]:20} {size[k]} rows")
    if rows and "usd" in rows[0]:
        # the price set in the bench was wrong for the cloud judge: see runs/031b/README.md
        print(f"\ncost booked by the bench: {sum(r.get('usd') or 0 for r in rows):.4f} USD for {len(rows)} calls; "
              f"mean {statistics.mean(r['seconds'] for r in rows):.0f} s per call; "
              f"tokens written per call: {statistics.mean(r.get('output_tokens') or 0 for r in rows):.0f}")
    return 0


def right_call(r: dict) -> bool:
    v = verdict(r)
    return (v == "acquit") if r["truth"] == "faithful" else (v == "condemn")


if __name__ == "__main__":
    raise SystemExit(main())
