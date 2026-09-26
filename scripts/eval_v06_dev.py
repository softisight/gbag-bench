"""Measure the v0.6 judge on its DEVELOPMENT set (PROTOCOL_v0.6_JUDGE.md): 36 cases already
read — 7 truth-set, 14 reserve, 14 of the spent v0.5 test set. The v0.6 sealed test set is
never touched here.

Usage (repo root):
    python scripts/eval_v06_dev.py run --mode jev --tag dev1
    python scripts/eval_v06_dev.py report --mode lex --tag dev1
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "v0.6" / "dev"
SETS = {
    "t7": (ROOT / "runs/judge-calibration/t7-q.jsonl", ROOT / "runs/judge-calibration/t7-a.jsonl",
           ROOT / "data/judge-truth-set.jsonl"),
    "reserve": (ROOT / "data/questions-reserve.jsonl", ROOT / "data/answers-reserve.jsonl",
                ROOT / "data/verdicts-reserve.jsonl"),
    "test05": (ROOT / "data/sealed/test-v05/questions.jsonl", ROOT / "data/sealed/test-v05/answers.jsonl",
               ROOT / "data/sealed/test-v05/verdicts.jsonl"),
}


def lines(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()] if p.exists() else []


def run(tag: str, mode: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (q, a, _) in SETS.items():
        subprocess.run([sys.executable, "-m", "judge.v06.run_v06", "--dataset", str(q), "--answers", str(a),
                        "--output", str(OUT / f"{tag}-{mode}-{name}.jsonl"), "--mode", mode], cwd=ROOT,
                       stdout=subprocess.DEVNULL, check=False)


def report(tag: str, mode: str, quiet: bool = False) -> None:
    n = decided = correct = undecided = 0
    for name, (_, _, tf) in SETS.items():
        truth = {t["id"]: t for t in lines(tf)}
        for r in lines(OUT / f"{tag}-{mode}-{name}.jsonl"):
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
            if not quiet and mark != "✓":
                cov = r["coverage"]
                print(f"{mark} {name:7} {r['id'][:40]:40} want {want:9} got {got:20} "
                      f"(T{cov['verified_true']} F{cov['false']} U{cov['undecided']})")
                print(f"      {r['reason'][:260]}")
    if n:
        print(f"[{mode}] arbitrated {n} | undecided {undecided} ({100 * undecided / n:.0f} %, threshold 20 %) | "
              f"decided {decided}, correct {correct}" + (f" ({100 * correct / decided:.0f} %)" if decided else ""))


if __name__ == "__main__":
    args = dict(zip(sys.argv[2::2], sys.argv[3::2]))
    tag, mode = args.get("--tag", "dev"), args.get("--mode", "jev")
    if len(sys.argv) >= 2 and sys.argv[1] == "run":
        run(tag, mode)
        report(tag, mode)
    elif len(sys.argv) >= 2 and sys.argv[1] == "report":
        report(tag, mode)
    else:
        print(__doc__)
