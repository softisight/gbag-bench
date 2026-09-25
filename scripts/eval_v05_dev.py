"""Measure the v0.5 judge on its DEVELOPMENT set (PROTOCOL_v0.5_JUDGE.md).

Development set = the 7 truth-set cases + the 14 arbitrated reserve cases (the disputed
one is run but excluded from accuracy). The sealed test set is never touched here.

Reports, against the arbitrated verdicts:
  * undecided rate (readiness threshold: <= 20 %),
  * accuracy on decided cases (condemned vs acquitted, band <=40 vs 100),
  * every disagreement, with the judge's own evidence, so the next iteration fixes a cause.

Usage (repo root):
    python scripts/eval_v05_dev.py run --backend openrouter --model qwen/qwen3.8-27b --tag dev1
    python scripts/eval_v05_dev.py report --tag dev1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "v0.5" / "dev"
SETS = {
    "t7": (ROOT / "runs/judge-calibration/t7-q.jsonl", ROOT / "runs/judge-calibration/t7-a.jsonl",
           ROOT / "data/judge-truth-set.jsonl"),
    "reserve": (ROOT / "data/questions-reserve.jsonl", ROOT / "data/answers-reserve.jsonl",
                ROOT / "data/verdicts-reserve.jsonl"),
}


def lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def run(tag: str, backend: str, model: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (q, a, _) in SETS.items():
        out = OUT / f"{tag}-{name}.jsonl"
        subprocess.run([sys.executable, "-m", "judge.v05.run_v05", "--dataset", str(q), "--answers", str(a),
                        "--output", str(out), "--backend", backend, "--model", model], cwd=ROOT, check=False)


def report(tag: str) -> None:
    n = decided = correct = undecided = 0
    for name, (_, _, truth_file) in SETS.items():
        truth = {t["id"]: t for t in lines(truth_file)}
        for r in lines(OUT / f"{tag}-{name}.jsonl"):
            t = truth.get(r["id"])
            if not t or t["verdict"] not in ("faithful", "unfaithful_material"):
                continue
            n += 1
            want = "faithful" if t["verdict"] == "faithful" else "condemned"
            got = r["verdict"]
            if got == "undecided":
                undecided += 1
                mark = "·"
            else:
                decided += 1
                ok = (got == "faithful") == (want == "faithful")
                correct += ok
                mark = "✓" if ok else "✗"
            cov = r["coverage"]
            print(f"{mark} {name:7} {r['id'][:40]:40} want {want:9} got {got:20} "
                  f"(T{cov['verified_true']} F{cov['false']} U{cov['undecided']} "
                  f"tbl {r['table']['cells_checked']}/{len(r['table']['mismatches'])})")
            if mark != "✓":
                print(f"      {r['reason'][:230]}")
    if n:
        print(f"\narbitrated {n} | undecided {undecided} ({100 * undecided / n:.0f} %, threshold 20 %) | "
              f"decided {decided}, correct {correct}"
              + (f" ({100 * correct / decided:.0f} %)" if decided else ""))


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
        run(args.get("--tag", "dev"), args.get("--backend", "openrouter"), args.get("--model", "qwen/qwen3.8-27b"))
        report(args.get("--tag", "dev"))
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
        report(args.get("--tag", "dev"))
    else:
        print(__doc__)
