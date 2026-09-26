"""GBAG v0.7 — score the declared answers (PROTOCOL_v0.7.md, "Scoring"). Code only.

Usage (repo root):  python scripts/score_v07.py
Writes runs/v0.7/scores.jsonl (one line per answer, with its class) and prints the tables.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from scorer.v07.score import classify

TARGETS = ROOT / "data" / "v07" / "targets.jsonl"
ANSWERS = ROOT / "runs" / "v0.7" / "answers"
OUT = ROOT / "runs" / "v0.7" / "scores.jsonl"


def main() -> int:
    targets = {t["tid"]: t for t in (json.loads(l) for l in TARGETS.read_text(encoding="utf-8").splitlines() if l.strip())}
    rows = []
    for f in sorted(ANSWERS.glob("*.jsonl")):
        for rec in (json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()):
            t = targets[rec["tid"]]
            cls, parsed = ("error", None) if rec.get("error") else classify(rec["answer"], t, rec["arm"])
            # the model is the FILE's: the record's "model" field can carry another thread's
            # value (baseline_runner.LAST_CALL is shared between threads; deviation D2)
            rows.append({"model": f.stem.rsplit("-", 2)[0].replace("__", "/"), "arm": rec["arm"], "run": rec["run"], "tid": rec["tid"],
                         "kind": t["kind"], "class": cls, "parsed": parsed})
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    for arm in ("A", "B"):
        print(f"\n=== ARM {arm} ({'value + scope' if arm == 'A' else 'value only (priming check)'}) ===")
        print(f"{'model':34} {'run':>3} | {'GBAG fail':>9} {'honest':>7} {'correct':>7} {'wrong':>6} {'format':>6} "
              f"| {'control ok':>10}")
        by = collections.defaultdict(list)
        for r in rows:
            if r["arm"] == arm:
                by[(r["model"], r["run"])].append(r)
        for (model, run), rs in sorted(by.items()):
            # calls that failed (transport, credits) are not answers: out of every denominator
            disc = [r for r in rs if r["kind"] == "discriminating" and r["class"] != "error"]
            ctrl = [r for r in rs if r["kind"] == "control" and r["class"] != "error"]
            c = collections.Counter(r["class"] for r in disc)
            pct = lambda k: f"{100 * c[k] / len(disc):.0f} %" if disc else "—"
            ok = sum(r["class"] == "correct" for r in ctrl)
            print(f"{model:34} {run:>3} | {pct('gbag_failure'):>9} {pct('honest'):>7} {pct('correct'):>7} "
                  f"{pct('wrong'):>6} {pct('format'):>6} | {ok:>4}/{len(ctrl):<5}  n_disc {len(disc)}"
                  + (f"  errors {sum(r['class'] == 'error' for r in rs)}" if any(r['class'] == 'error' for r in rs) else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
