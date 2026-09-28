"""Judge experiment "031-B": the local judge beside the cloud judge, on the same 12 answers.

Only pass 1 is read, because the local judge ran one pass. For the cloud judge, a call
played again with a higher output cap takes the place of the call that gave no verdict.

Usage (repo root):  python scripts/compare_031b.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
RUN = Path(__file__).resolve().parent.parent / "runs" / "031b"
CONDITIONS = ("avant", "apres")          # before: no facts; after: facts computed by code


def load(name: str) -> list[dict]:
    return [json.loads(l) for l in (RUN / name).read_text(encoding="utf-8").splitlines() if l.strip()]


def verdict(r: dict) -> str:
    nh = r.get("no_hallucination")
    if nh is None or r.get("empty_verdict"):
        return "failed"
    return "acquit" if nh >= 20 else "condemn"


def table(name: str, rows: list[dict], ids: list[str]) -> dict:
    calls = {(r["id"], r["condition"]): r for r in rows if r["id"] in ids and r["pass"] == 1}
    print(f"\n== {name}: {len(calls)} calls")
    for cond in CONDITIONS:
        got = [calls[(i, cond)] for i in ids if (i, cond) in calls]
        if not got:
            continue
        out = {"faithful": [0, 0, 0], "unfaithful_material": [0, 0, 0]}      # right, wrong, no verdict
        for r in got:
            v = verdict(r)
            right = (v == "acquit") if r["truth"] == "faithful" else (v == "condemn")
            out[r["truth"]][2 if v == "failed" else (0 if right else 1)] += 1
        f, u = out["faithful"], out["unfaithful_material"]
        print(f"{cond:6} right {f[0] + u[0]}/{len(got)} | correct answers acquitted {f[0]}/{sum(f)} "
              f"(no verdict {f[2]}) | false answers condemned {u[0]}/{sum(u)} (no verdict {u[2]})")
    return calls


def main() -> int:
    ids = [c["id"] for c in load("cases-gt200-short.jsonl")]
    truth = {c["id"]: c["truth"] for c in load("cases-gt200-short.jsonl")}
    cloud = load("measure-deepseek-v41-flash.jsonl")
    again = {(r["id"], r["condition"], r["pass"]): r for r in load("measure-deepseek-v41-flash-replay16k.jsonl")}
    local = table("gemma4:31b, local", load("measure-gemma4-31b-gt200.jsonl"), ids)
    table("deepseek-v4.1-flash, as measured", cloud, ids)
    played = table("deepseek-v4.1-flash, calls played again included",
                   [again.get((r["id"], r["condition"], r["pass"]), r) for r in cloud], ids)

    print("\nper answer (no facts -> facts)             truth      | local                | cloud")
    for i in ids:
        def pair(calls: dict) -> str:
            return " -> ".join(verdict(calls[(i, c)]) if (i, c) in calls else "..." for c in CONDITIONS)
        print(f"{i:42} {truth[i][:10]:10} | {pair(local):20} | {pair(played)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
