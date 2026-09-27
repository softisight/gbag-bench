"""GBAG v0.4, Stage 2 — judges on the 15-case reserve (PROTOCOL_v0.4.md, section 5; D9).

Same mechanics as Stage 1 (scripts/campaign_v04_stage1.py, whose judge configurations are
reused unchanged), on cases the scope law was never written against. The truth is
data/verdicts-reserve.jsonl, committed BEFORE this script first ran; `disputed` cases are
excluded from accuracy, never settled here.

Configurations, as the protocol fixes them: J2, J5 (hosted) and J4, J6 (local).
5 ordered passes + 1 isolated pass each. The hosted and local chains run side by side.

Usage (repo root):
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/campaign_v04_stage2.py run
    python scripts/campaign_v04_stage2.py report
"""
from __future__ import annotations

import json
import os
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from campaign_v04_stage1 import BUDGET_USD, CONFIGS, PROMPT  # the Stage 1 configurations, unchanged

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "v0.4" / "stage2"
QUESTIONS = ROOT / "data" / "questions-reserve.jsonl"
ANSWERS = ROOT / "data" / "answers-reserve.jsonl"
TRUTH = ROOT / "data" / "verdicts-reserve.jsonl"
PASSES = 5
LOCAL_CHAIN = ["J4", "J6"]      # J4 first: the shorter one gives a result sooner
HOSTED_CHAIN = ["J2", "J5"]

_lock = threading.Lock()


def log(msg: str) -> None:
    with _lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def lines(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


N_CASES = len(lines(ANSWERS))


def spent_usd() -> float:
    files = list((ROOT / "runs" / "v0.4").rglob("J*.jsonl"))
    return sum((r.get("judge_cost_usd") or 0.0) for f in files for r in lines(f))


def judge(cfg: str, dataset: Path, answers: Path, output: Path) -> bool:
    args, _, _ = CONFIGS[cfg]
    cmd = [sys.executable, str(ROOT / "judge" / "run_judge.py"), "--dataset", str(dataset),
           "--answers", str(answers), "--output", str(output), "--prompt", str(PROMPT), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=ROOT)
    if r.returncode != 0:
        log(f"  {cfg} FAILED: {(r.stderr or '').strip()[-400:]}")
    return r.returncode == 0


def ordered_pass(cfg: str, n: int) -> None:
    out = OUT / f"{cfg}-p{n}.jsonl"
    if len(lines(out)) >= N_CASES:
        return
    if spent_usd() >= BUDGET_USD:
        raise SystemExit(f"budget cap {BUDGET_USD} USD reached — stopping (log a deviation)")
    t0 = time.time()
    if out.exists():            # a partial pass is redone whole: batch positions must not move
        out.unlink()
    if judge(cfg, QUESTIONS, ANSWERS, out):
        log(f"{cfg} p{n}: {verdicts_line(lines(out))}  ({time.time() - t0:.0f}s)")


def isolated_pass(cfg: str) -> None:
    out = OUT / f"{cfg}-iso.jsonl"
    done = {r["id"] for r in lines(out)}
    qs = {q["id"]: q for q in lines(QUESTIONS)}
    for a in lines(ANSWERS):
        if a["id"] in done:
            continue
        with tempfile.TemporaryDirectory() as td:
            dq, da, do = Path(td) / "q.jsonl", Path(td) / "a.jsonl", Path(td) / "o.jsonl"
            dq.write_text(json.dumps(qs[a["id"]], ensure_ascii=False) + "\n", encoding="utf-8")
            da.write_text(json.dumps(a, ensure_ascii=False) + "\n", encoding="utf-8")
            if judge(cfg, dq, da, do):
                with out.open("a", encoding="utf-8") as f:
                    for rec in lines(do):
                        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"{cfg} iso: {verdicts_line(lines(out))}")


def run_config(cfg: str) -> None:
    for n in range(1, PASSES + 1):
        ordered_pass(cfg, n)
    isolated_pass(cfg)


# --------------------------------------------------------------------------- scoring

def truth() -> dict[str, dict]:
    """Arbitrated cases only: `disputed` is excluded from accuracy by construction."""
    return {t["id"]: t for t in lines(TRUTH) if t["verdict"] in ("faithful", "unfaithful_material")}


def correct(rec: dict, t: dict) -> bool:
    f = rec["faithfulness"]
    return f <= 40 if t["band"] == "<=40" else f == 100


def verdicts_line(recs: list[dict]) -> str:
    tr = truth()
    marks = "".join(("✓" if correct(r, tr[r["id"]]) else "✗") if r["id"] in tr else "·" for r in recs)
    ok = marks.count("✓")
    return f"{marks} {ok}/{len(tr)}"


def summarise(cfg: str) -> dict | None:
    tr = truth()
    runs = [lines(OUT / f"{cfg}-p{n}.jsonl") for n in range(1, PASSES + 1)]
    runs = [r for r in runs if len(r) == N_CASES]
    if not runs:
        return None
    by_case = {cid: [next(x for x in r if x["id"] == cid) for r in runs] for cid in tr}
    per_pass = [sum(correct(x, tr[x["id"]]) for x in r if x["id"] in tr) for r in runs]
    contradictions = [cid for cid, xs in by_case.items() if len({correct(x, tr[cid]) for x in xs}) > 1]
    missed = [cid for cid, xs in by_case.items() if sum(correct(x, tr[cid]) for x in xs) * 2 <= len(xs)]
    # errors split by direction: acquitting a false answer is the failure GBAG exists to catch
    false_acquittals = [c for c in missed if tr[c]["band"] == "<=40"]
    false_condemnations = [c for c in missed if tr[c]["band"] == "100"]
    iso = {r["id"]: r for r in lines(OUT / f"{cfg}-iso.jsonl")}
    flips = None
    if len(iso) == N_CASES:
        flips = [cid for cid, xs in by_case.items()
                 if correct(iso[cid], tr[cid]) != (sum(correct(x, tr[cid]) for x in xs) * 2 > len(xs))]
    cost = sum((r.get("judge_cost_usd") or 0) for rs in runs for r in rs)
    return {"passes": len(runs), "score": round(statistics.mean(per_pass), 2), "per_pass": per_pass,
            "of": len(tr), "contradictions": contradictions, "false_acquittals": false_acquittals,
            "false_condemnations": false_condemnations, "iso_flips": flips, "cost_usd": round(cost, 4)}


def report() -> None:
    mp = json.loads((OUT / "mapping.json").read_text(encoding="utf-8"))
    blind = {v: k for k, v in mp.items()}
    for cfg in HOSTED_CHAIN + LOCAL_CHAIN:
        s = summarise(cfg)
        if not s:
            print(f"{cfg}: —")
            continue
        flips = "n/a" if s["iso_flips"] is None else len(s["iso_flips"])
        print(f"{cfg}: {s['score']}/{s['of']} over {s['passes']} passes {s['per_pass']} | "
              f"contradictions {len(s['contradictions'])} | iso flips {flips} | ${s['cost_usd']}")
        for label, ids in (("acquitted a false answer", s["false_acquittals"]),
                           ("condemned a correct answer", s["false_condemnations"]),
                           ("contradicted itself on", s["contradictions"])):
            if ids:
                print(f"      {label}: {', '.join(blind.get(i, i) for i in ids)}")
    print(f"\nspent (all v0.4 judge runs): ${spent_usd():.4f} of ${BUDGET_USD}")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "report"):
        print(__doc__)
        return 2
    if sys.argv[1] == "report":
        report()
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"OLLAMA_HOST={os.environ.get('OLLAMA_HOST')}  cases={N_CASES}  arbitrated={len(truth())}")
    threads = [threading.Thread(target=lambda: [run_config(c) for c in LOCAL_CHAIN]),
               threading.Thread(target=lambda: [run_config(c) for c in HOSTED_CHAIN])]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
