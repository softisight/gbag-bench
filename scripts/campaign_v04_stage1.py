"""GBAG v0.4, Stage 1 — judge qualification on the truth set (PROTOCOL_v0.4.md, section 4).

Nothing here decides a score. It runs judge/run_judge.py under the configurations the
protocol fixed (as amended by deviations D1 and D2), and reads the results back against
data/judge-truth-set.jsonl.

Order, as the protocol requires:

  1. the control J6 (gemma4:31b, local), 5 ordered passes, alone;
  2. the GATE: J6 must score 7/7 with 0 self-contradictions, or nothing else runs;
  3. the rest. The local chain (J6 isolated pass, then J4) and the hosted chain (J1, J2,
     J3, J5, then J7) run side by side: they share no hardware.

Resumable: a pass whose output file already holds 7 lines is skipped, so an interrupted
run is relaunched with the same command.

Usage (repo root):
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/campaign_v04_stage1.py run        # gate, then everything
    python scripts/campaign_v04_stage1.py report     # read back what exists
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

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "v0.4" / "stage1"
QUESTIONS = ROOT / "runs" / "judge-calibration" / "t7-q.jsonl"
ANSWERS = ROOT / "runs" / "judge-calibration" / "t7-a.jsonl"
TRUTH = ROOT / "data" / "judge-truth-set.jsonl"
PROMPT = ROOT / "judge" / "prompt-v041.md"
BUDGET_USD = 15.0

# id -> (run_judge arguments, ordered passes, isolated pass)
CONFIGS: dict[str, tuple[list[str], int, bool]] = {
    # D2: the DeepSeek endpoint is refused by the account's no-training policy; J1 is
    # J2 without the seed, which isolates the variable J1-vs-J2 was meant to test.
    "J1": (["--judge", "openrouter", "--model", "deepseek/deepseek-v4.1-flash",
            "--provider", "deepinfra/fp8", "--reasoning", "off"], 5, True),
    "J2": (["--judge", "openrouter", "--model", "deepseek/deepseek-v4.1-flash",
            "--provider", "deepinfra/fp8", "--seed", "42", "--reasoning", "off"], 5, True),
    "J3": (["--judge", "openrouter", "--model", "deepseek/deepseek-v4.1-flash",
            "--seed", "42", "--reasoning", "off"], 5, True),
    "J4": (["--judge", "ollama", "--model", "qwen3.8:27b"], 5, True),
    # D1: local q4_K_M, so J5 takes the protocol's q4 branch.
    "J5": (["--judge", "openrouter", "--model", "qwen/qwen3.8-27b",
            "--provider", "darkbloom/fp4", "--seed", "42", "--reasoning", "off"], 5, True),
    "J6": (["--judge", "ollama", "--model", "gemma4:31b"], 5, True),
    "J7": (["--judge", "openrouter", "--model", "deepseek/deepseek-v4.1-flash",
            "--provider", "deepinfra/fp8", "--seed", "42", "--reasoning", "on"], 3, False),
}
LOCAL_CHAIN = ["J4"]
HOSTED_CHAIN = ["J1", "J2", "J3", "J5", "J7"]

_lock = threading.Lock()


def log(msg: str) -> None:
    with _lock:
        print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def lines(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def spent_usd() -> float:
    return sum((r.get("judge_cost_usd") or 0.0) for f in OUT.glob("*.jsonl") for r in lines(f))


def judge(cfg: str, dataset: Path, answers: Path, output: Path) -> bool:
    args, _, _ = CONFIGS[cfg]
    cmd = [sys.executable, str(ROOT / "judge" / "run_judge.py"), "--dataset", str(dataset),
           "--answers", str(answers), "--output", str(output), "--prompt", str(PROMPT), *args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=ROOT)
    if r.returncode != 0:
        log(f"  {cfg} FAILED: {(r.stderr or '').strip()[-400:]}")
    return r.returncode == 0


def ordered_pass(cfg: str, n: int) -> None:
    out = OUT / f"{cfg}-p{n}.jsonl"
    if len(lines(out)) >= 7:
        return
    if spent_usd() >= BUDGET_USD:
        raise SystemExit(f"budget cap {BUDGET_USD} USD reached — stopping (log a deviation)")
    t0 = time.time()
    # A pass is one process over the 7 cases in file order. A partial file is redone
    # whole, never resumed: resuming would change the batch positions.
    if out.exists():
        out.unlink()
    if judge(cfg, QUESTIONS, ANSWERS, out):
        log(f"{cfg} p{n}: {verdicts_line(cfg, lines(out))}  ({time.time() - t0:.0f}s)")


def isolated_pass(cfg: str) -> None:
    """Each case alone, one process per case: every call is the first of its process."""
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
    log(f"{cfg} iso: {verdicts_line(cfg, lines(out))}")


def run_config(cfg: str, isolated_too: bool = True) -> None:
    _, passes, iso = CONFIGS[cfg]
    for n in range(1, passes + 1):
        ordered_pass(cfg, n)
    if iso and isolated_too:
        isolated_pass(cfg)


# --------------------------------------------------------------------------- scoring

def truth() -> dict[str, dict]:
    return {t["id"]: t for t in lines(TRUTH)}


def correct(rec: dict, t: dict) -> bool:
    f = rec["faithfulness"]
    return f <= 40 if t["band"] == "<=40" else f == 100


def verdicts_line(cfg: str, recs: list[dict]) -> str:
    tr = truth()
    marks = "".join("✓" if correct(r, tr[r["id"]]) else "✗" for r in recs if r["id"] in tr)
    return f"{marks} {marks.count('✓')}/{len(marks)}  F={[r['faithfulness'] for r in recs]}"


def summarise(cfg: str) -> dict | None:
    tr = truth()
    _, passes, _ = CONFIGS[cfg]
    runs = [lines(OUT / f"{cfg}-p{n}.jsonl") for n in range(1, passes + 1)]
    runs = [r for r in runs if len(r) == 7]
    if not runs:
        return None
    by_case = {cid: [next(x for x in r if x["id"] == cid) for r in runs] for cid in tr}
    per_pass = [sum(correct(x, tr[x["id"]]) for x in r) for r in runs]
    contradictions = [cid for cid, xs in by_case.items() if len({correct(x, tr[cid]) for x in xs}) > 1]
    spread = {cid: (min(x["faithfulness"] for x in xs), max(x["faithfulness"] for x in xs),
                    round(statistics.pstdev([x["faithfulness"] for x in xs]), 1))
              for cid, xs in by_case.items()}
    iso = {r["id"]: r for r in lines(OUT / f"{cfg}-iso.jsonl")}
    flips = None
    if len(iso) == 7:
        # a flip: the isolated verdict differs from the verdict of the ordered majority
        flips = []
        for cid, xs in by_case.items():
            maj = sum(correct(x, tr[cid]) for x in xs) * 2 > len(xs)
            if correct(iso[cid], tr[cid]) != maj:
                flips.append(cid)
    served = {(r.get("judge_served") or {}).get("provider") for rs in runs for r in rs} - {None}
    cost = sum((r.get("judge_cost_usd") or 0) for rs in runs for r in rs)
    return {"passes": len(runs), "score": round(statistics.mean(per_pass), 2), "per_pass": per_pass,
            "contradictions": contradictions, "spread": spread, "iso_flips": flips,
            "served": sorted(served), "cost_usd": round(cost, 4),
            "out_tokens_mean": round(statistics.mean(r["judge_output_tokens"] or 0 for rs in runs for r in rs))}


def gate_ok() -> bool:
    s = summarise("J6")
    if not s or s["passes"] < 5:
        return False
    return s["score"] == 7 and not s["contradictions"]


def report() -> None:
    for cfg in CONFIGS:
        s = summarise(cfg)
        if not s:
            print(f"{cfg}: —")
            continue
        flips = "n/a" if s["iso_flips"] is None else len(s["iso_flips"])
        print(f"{cfg}: {s['score']}/7 over {s['passes']} passes {s['per_pass']} | "
              f"contradictions {len(s['contradictions'])} {s['contradictions']} | iso flips {flips} | "
              f"served {s['served']} | {s['out_tokens_mean']} out tok | ${s['cost_usd']}")
        for cid, (lo, hi, sd) in s["spread"].items():
            if hi != lo:
                print(f"      F spread {cid}: {lo}..{hi} (sd {sd})")
    print(f"\nspent: ${spent_usd():.4f} of ${BUDGET_USD}")


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in ("run", "report"):
        print(__doc__)
        return 2
    if sys.argv[1] == "report":
        report()
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"OLLAMA_HOST={os.environ.get('OLLAMA_HOST')}")
    log("=== control J6, 5 ordered passes ===")
    run_config("J6", isolated_too=False)
    if not gate_ok():
        log("GATE FAILED: J6 does not reproduce 7/7 with 0 contradictions. Stopping.")
        report()
        return 1
    log("GATE PASSED: J6 reproduces 7/7, 0 contradictions.")

    def local():
        isolated_pass("J6")
        for c in LOCAL_CHAIN:
            run_config(c)

    def hosted():
        for c in HOSTED_CHAIN:
            run_config(c)

    threads = [threading.Thread(target=local), threading.Thread(target=hosted)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
