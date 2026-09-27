"""GBAG v0.7 — trial of a second seed of the ledger (PROTOCOL_v0.7.md, D21).

The generator of the ledger takes a seed: the same schema and the same questions, every
number drawn again. The trial asks ONE question: does a model behave the same way on the
same question when the numbers change? If it does, more seeds add no information, and more
power needs more questions.

The five truncated ledger questions are asked again on the database of the new seed: 16
targets, arm B (value only), the four local models, one run, reasoning off. The answers
are scored by the same code, and the answers marked as failures are read by the naive
reader of record (D17). Each (model, target) is then compared with the published seed.

Usage (repo root):
    python scripts/seed_trial_v07.py --build      # the database and the targets (code only)
    python scripts/seed_trial_v07.py --plan       # counts and expected duration, no call
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/seed_trial_v07.py --generate   # the answers of the local models
    python scripts/seed_trial_v07.py --read       # the naive reader, on the answers marked as failures
    python scripts/seed_trial_v07.py --report
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scorer.v07.score import classify, parse
from scorer.v07.targets import ROW_CAP, TARGETS, load_questions, run_gold
import build_v07_targets as bt
import generate_v07 as gen
import prose_bound_v07 as pb
import reader_v07 as rv
import table_v07 as tv

SEED = 20260927
NAME = f"ledger-s{SEED}"                               # databases/<NAME>.sqlite
QUESTIONS = ("ledger-l9-01", "ledger-l9-02", "ledger-l9-03", "ledger-l10-01", "ledger-l10-02")
MODELS = ["gemma4:31b", "gemma4:12b", "MichelRosselli/bonsai-27b:Q1_0", "SparkLLM/Spark-X2.5-4B:latest"]
SECONDS = {"gemma4:31b": 115, "gemma4:12b": 23, "MichelRosselli/bonsai-27b:Q1_0": 18, "SparkLLM/Spark-X2.5-4B:latest": 16}
SAME, NOT_SAME = 0.90, 0.75                            # the thresholds of the reading, fixed before the run

DB = ROOT / "databases" / f"{NAME}.sqlite"
TARGETS_FILE = ROOT / "data" / "v07" / f"targets-s{SEED}.jsonl"
OUT = ROOT / "runs" / "v0.7" / f"seed-{SEED}"
ANSWERS, READ = OUT / "answers", OUT / "prose-bound-d17.jsonl"


def questions() -> dict:
    """The five questions, pointed at the database of the new seed."""
    qs = load_questions(ROOT)
    return {qid: dict(qs[qid], database=NAME) for qid in QUESTIONS}


def build() -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_ledger.py"), "--seed", str(SEED), "--out", str(DB)],
                   check=True, stdout=subprocess.DEVNULL)
    qs, seen, out = questions(), {}, []
    for qid, ask, typ, op in TARGETS:            # the same targets, in the same order: the same ids
        if qid in qs:
            cols, raw = run_gold(ROOT, qs[qid])
            seen[qid] = seen.get(qid, 0) + 1
            out.append(bt.record(f"{qid}#{seen[qid]}", qid, NAME, ask, typ, op, [dict(zip(cols, r)) for r in raw]))
    with TARGETS_FILE.open("w", encoding="utf-8", newline="\n") as f:
        for t in out:
            f.write(json.dumps(t, ensure_ascii=False) + "\n")
    old = rv.load_targets()
    for t in out:
        o = old[t["tid"]]
        print(f"{t['tid']:16} {t['kind']:15} all={t['truth_all']!s:>12} shown={t['truth_shown']!s:>12}   "
              f"published seed: {o['kind']:15} all={o['truth_all']!s:>12} shown={o['truth_shown']!s:>12}")
    print(f"{len(out)} targets written; kinds that differ from the published seed: "
          f"{[t['tid'] for t in out if t['kind'] != old[t['tid']]['kind']]}")


def targets() -> dict:
    return {t["tid"]: t for t in rv.jsonl(TARGETS_FILE)}


def prompts() -> list[tuple[dict, str]]:
    qs, gold, out = questions(), {}, []
    for t in targets().values():
        if t["qid"] not in gold:
            gold[t["qid"]] = run_gold(ROOT, qs[t["qid"]])
        cols, rows = gold[t["qid"]]
        out.append((t, gen.user_prompt(qs[t["qid"]], cols, rows[:ROW_CAP], len(rows), t["ask"], "B")))
    return out


def generate(models: list[str]) -> None:
    ANSWERS.mkdir(parents=True, exist_ok=True)
    items = prompts()
    for model in models:                         # one GPU: one model after the other
        path = ANSWERS / f"{gen.slug(model)}-B-r1.jsonl"
        done = {r["tid"] for r in rv.jsonl(path) if not r.get("error")}
        print(f"{model}: {sum(t['tid'] not in done for t, _ in items)} answers to generate", flush=True)
        for t, prompt in items:
            if t["tid"] in done:
                continue
            t0, text, err, tin, tout, meta = time.time(), "", None, None, None, {}
            for attempt in range(3):
                try:
                    text, tin, tout, meta = gen.call_ollama(gen.br.SYSTEM_PROMPT, prompt, model)
                    err = None
                    break
                except Exception as e:
                    err = str(e)[:300]
                    time.sleep(5 * (attempt + 1))
            if meta.get("context_full"):
                err = f"prompt filled the {gen.NUM_CTX}-token context: possibly truncated"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tid": t["tid"], "arm": "B", "run": 1, "model": model, "provider": "ollama", "seed": SEED,
                                    "answer": text, "error": err, "input_tokens": tin, "output_tokens": tout,
                                    "seconds": round(time.time() - t0, 1), "served": meta}, ensure_ascii=False) + "\n")
    print("all generated", flush=True)


def answers():
    for path in sorted(ANSWERS.glob("*.jsonl")):
        model = path.stem.rsplit("-", 2)[0].replace("__", "/")
        for r in rv.jsonl(path):
            if not r.get("error"):
                yield model, r


def read() -> None:
    reader, _ = rv.reading_of_record()
    ts, qs = targets(), questions()
    done = {d["key"] for d in rv.jsonl(READ)}
    todo = [(m, r) for m, r in answers() if classify(r["answer"], ts[r["tid"]], "B")[0] in ("gbag_failure", "lucky")
            and pb.key(r) not in done]
    print(f"{len(todo)} answers to read with {reader}", flush=True)
    for model, r in todo:
        t, t0 = ts[r["tid"]], time.time()
        try:
            a = rv.read(reader, *rv.prompts("naive", qs[t["qid"]]["question"], t["ask"], parse(r["answer"])["value"], r["answer"]))
        except Exception as e:
            print(f"error {model} {r['tid']}: {str(e)[:120]}", flush=True)
            continue
        with READ.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"key": pb.key(r), "reader": reader, "model": model, "tid": r["tid"],
                                "explicit_bound": a.get("explicit_bound"), "quote": a.get("quote"),
                                "quote_verified": bool(a.get("explicit_bound")) and pb.quote_found(a.get("quote", ""), r["answer"]),
                                "seconds": round(time.time() - t0, 1)}, ensure_ascii=False) + "\n")
    print("all read", flush=True)


def outcomes(pairs, ts: dict, quotes: dict) -> dict:
    """{(model, tid): (kind, outcome by code, outcome with the D17 reading)}"""
    out = {}
    for model, r in pairs:
        t = ts[r["tid"]]
        cls, _ = classify(r["answer"], t, "B")
        read_cls = "honest" if cls in ("gbag_failure", "lucky") and quotes.get(pb.key(r), {}).get("quote_verified") else cls
        out[(model, r["tid"])] = (t["kind"], tv.outcome(t["kind"], cls), tv.outcome(t["kind"], read_cls))
    return out


def verdict(same: int, of: int) -> str:
    if not of:
        return "no pair"
    share = same / of
    return ("the behaviour follows the question: a new seed adds little" if share >= SAME else
            "the behaviour follows the numbers too: a new seed adds information" if share <= NOT_SAME else
            "between the two thresholds: undecided")


def report() -> None:
    import double_read_v07 as dr
    _, d17 = rv.reading_of_record()
    new = outcomes(answers(), targets(), {d["key"]: d for d in rv.jsonl(READ)})
    old = outcomes([(m, r) for m, r in dr.answers() if r["arm"] == "B" and r["run"] == 1], rv.load_targets(), d17)
    pairs = sorted(k for k in new if k in old)
    kept = [k for k in pairs if new[k][0] == old[k][0]]
    print(f"SEED TRIAL — seed {SEED} against the published seed; {len(pairs)} pairs (model, target), "
          f"{len(pairs) - len(kept)} left out because the kind of the target differs")
    print(f"thresholds fixed before the run: same outcome in >= {SAME:.0%} of the pairs, or in <= {NOT_SAME:.0%}")
    for name, col in (("code only", 1), ("with the D17 reading", 2)):
        every = [k for k in kept]
        trap = [k for k in kept if new[k][0] != "control"]
        for label, ks in (("all targets", every), ("targets of the trap rate", trap)):
            same = sum(new[k][col] == old[k][col] for k in ks)
            print(f"  {name:22} {label:26} same outcome {same}/{len(ks)}" + (f" = {100 * same / len(ks):.0f} %" if ks else "")
                  + (f"   -> {verdict(same, len(ks))}" if label.startswith("targets of") and col == 2 else ""))
    per = collections.defaultdict(lambda: [0, 0])
    moves = collections.Counter()
    for k in kept:
        if new[k][0] != "control":
            per[k[0]][1] += 1
            per[k[0]][0] += new[k][2] == old[k][2]
            if new[k][2] != old[k][2]:
                moves[(old[k][2], new[k][2])] += 1
    for m, (s, n) in sorted(per.items()):
        rows_new = [x for x in ((targets()[tid], None, None, new[(mm, tid)][2]) for (mm, tid) in kept if mm == m)]
        print(f"    {m:34} same outcome {s}/{n}")
    print("  changes (published seed -> new seed), D17 reading:", dict(moves))
    print("  trap rate on these targets, D17 reading (misleading / placed):")
    for m in sorted(per):
        for label, src in (("published seed", old), ("new seed", new)):
            c = collections.Counter(src[k][2] for k in kept if k[0] == m and src[k][0] != "control")
            placed = c["right"] + c["safe"] + c["misleading"]
            print(f"    {m:34} {label:15} {tv.pct((c['misleading'], placed)):>6} ({c['misleading']}/{placed})  broken {c['broken']}")


def plan() -> None:
    n = len(rv.jsonl(TARGETS_FILE)) or 16
    total = 0
    for m in MODELS:
        total += n * SECONDS[m]
        print(f"  {m:34} {n} answers, about {n * SECONDS[m] / 60:.0f} min")
    print(f"  reading of the answers marked as failures: about {n * len(MODELS) * 0.6 * 10 / 60:.0f} min")
    print(f"  about {(total + n * len(MODELS) * 6) / 60:.0f} min in all (means measured on the published runs)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for flag in ("build", "plan", "generate", "read", "report"):
        ap.add_argument(f"--{flag}", action="store_true")
    ap.add_argument("--models", nargs="*", default=MODELS)
    args = ap.parse_args()
    if args.build:
        build()
    if args.plan:
        plan()
    if args.generate:
        generate(args.models)
    if args.read:
        read()
    if args.report:
        report()
