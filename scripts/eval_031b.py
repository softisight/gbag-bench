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

Usage (repo root):  python scripts/eval_031b.py [runs/031b/measure.jsonl]
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
