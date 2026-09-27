"""GBAG v0.7 — trial of the local models with reasoning ON (PROTOCOL_v0.7.md, D23).

On every target of the trap rate, the frontier cloud models reasoned and the local models
did not (D22). The trial asks ONE question: does a local model state the part as the whole
less often when it reasons?

Two steps per model, in this order:
  1. TUNING, on the 10 complete-result controls only. Left on at temperature 0,
     `gemma4:12b` looped in its reasoning and returned empty answers (D10). The settings
     below are tried in their order; the first one with which at least 9 answers in 10 end
     with a readable block is kept. No target of a cut result is asked during the tuning.
     If no setting passes, the model is not run, and this is reported.
  2. THE RUN, on the 41 targets of the cut results (34 of the trap rate, 7 controls), arm B,
     with the setting kept. Each answer is compared with the answer of the same model on
     the same target with reasoning off.

Usage (repo root):
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/reasoning_trial_v07.py --witness --models gemma4:12b   # one call, then the expected durations
    python scripts/reasoning_trial_v07.py --tune --models gemma4:12b
    python scripts/reasoning_trial_v07.py --generate --models gemma4:12b
    python scripts/reasoning_trial_v07.py --read
    python scripts/reasoning_trial_v07.py --report
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import statistics
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from scorer.v07.score import _is_none, classify, parse
from scorer.v07.targets import ROW_CAP, load_questions
import double_read_v07 as dr
import generate_v07 as gen
import prose_bound_v07 as pb
import reader_v07 as rv
import table_v07 as tv

MODELS = ["gemma4:12b", "gemma4:31b"]          # stage 1, stage 2
NUM_CTX, CAP = 16384, 4096                      # the window of v0.7; the most tokens an answer may write, reasoning included
SETTINGS = [                                    # tried in this order
    {"name": "cap", "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": CAP}},
    {"name": "cap+penalty", "options": {"temperature": 0, "num_ctx": NUM_CTX, "num_predict": CAP, "repeat_penalty": 1.15}},
    {"name": "cap+temperature", "options": {"temperature": 0.3, "seed": 7, "num_ctx": NUM_CTX, "num_predict": CAP}},
]
PASS = 9                                        # answers in 10 that must end with a readable block
ESTABLISHED = 0.95                              # share of the draws (D20) for an effect to be called established
UNRELIABLE = 0.30                               # share of broken answers above which a rate is called unreliable

OUT = ROOT / "runs" / "v0.7" / "reasoning"
ANSWERS, READ = OUT / "answers", OUT / "prose-bound-d17.jsonl"


def tuning_file(model: str) -> Path:
    return OUT / f"tuning-{gen.slug(model)}.jsonl"


def call(model: str, prompt: str, think: bool, options: dict) -> dict:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    payload = {"model": model, "prompt": prompt, "system": gen.br.SYSTEM_PROMPT, "stream": False, "think": think,
               "options": options}
    req = urllib.request.Request(f"{host}/api/generate", data=json.dumps(payload).encode("utf-8"),
                                 headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r:
        d = json.loads(r.read().decode("utf-8"))
    tin, tout = d.get("prompt_eval_count"), d.get("eval_count")
    return {"answer": (d.get("response") or "").strip(), "input_tokens": tin, "output_tokens": tout,
            "seconds": round(time.time() - t0, 1),
            "served": {"think": think, "options": options, "thinking_chars": len(d.get("thinking") or ""),
                       "done_reason": d.get("done_reason"), "context_full": bool(tin and tout and tin + tout >= NUM_CTX - 8)}}


_PROMPTS: dict = {}


def prompts() -> dict:
    """{tid: (target, the arm-B prompt of v0.7)}; the gold SQL is run once."""
    if not _PROMPTS:
        _PROMPTS.update({t["tid"]: (t, p) for t, arm, p in gen.prompts() if arm == "B"})
    return _PROMPTS


def tuning_targets() -> list[str]:
    return [tid for tid, (t, _) in prompts().items() if t["n_rows"] <= ROW_CAP]


def run_targets() -> list[str]:
    return [tid for tid, (t, _) in prompts().items() if t["n_rows"] > ROW_CAP]


def completes(answer: str, t: dict) -> bool:
    return bool(answer.strip()) and classify(answer, t, "B")[0] != "format"


def kept(model: str) -> dict | None:
    """The first setting with which at least PASS tuning answers in 10 end with a readable
    block, every tuning answer of that setting being there. None: no setting passes yet."""
    rows, ps, tids = rv.jsonl(tuning_file(model)), prompts(), tuning_targets()
    for s in SETTINGS:
        got = {r["tid"]: r for r in rows if r["setting"] == s["name"] and not r.get("error")}
        if len(got) < len(tids):
            return None                         # this setting is not fully tried: the next ones wait
        if sum(completes(r["answer"], ps[tid][0]) for tid, r in got.items()) >= PASS:
            return s
    return None


def tune(model: str, limit: int | None = None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    ps, tids = prompts(), tuning_targets()
    for s in SETTINGS:
        done = {r["tid"] for r in rv.jsonl(tuning_file(model)) if r["setting"] == s["name"] and not r.get("error")}
        todo = [tid for tid in tids if tid not in done][:limit]
        print(f"{model} / {s['name']}: {len(todo)} tuning answers to generate", flush=True)
        for tid in todo:
            try:
                rec = call(model, ps[tid][1], True, s["options"])
            except Exception as e:
                print(f"error {model} {tid}: {str(e)[:120]}", flush=True)
                continue
            with tuning_file(model).open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tid": tid, "model": model, "setting": s["name"], "error": None, **rec}, ensure_ascii=False) + "\n")
        if limit or kept(model) is not None:
            break
        got = [r for r in rv.jsonl(tuning_file(model)) if r["setting"] == s["name"]]
        if len(got) < len(tids):                # calls failed: the setting is not judged
            break
    s = kept(model)
    print(f"{model}: " + (f"setting kept: {s['name']}" if s else "no setting kept"), flush=True)


def generate(model: str) -> None:
    s = kept(model)
    if s is None:
        print(f"{model}: no setting passes the tuning: the model is not run (D23)")
        return
    ANSWERS.mkdir(parents=True, exist_ok=True)
    ps = prompts()
    # reasoning off is the published answer, unless the setting kept changes the sampling:
    # the answers with reasoning off are then generated again with the same options
    conditions = [("on", True)] + ([("off", False)] if s["options"].get("temperature") else [])
    for name, think in conditions:
        path = ANSWERS / f"{gen.slug(model)}-B-{name}.jsonl"
        done = {r["tid"] for r in rv.jsonl(path) if not r.get("error")}
        todo = [tid for tid in run_targets() if tid not in done]
        print(f"{model} / reasoning {name} / {s['name']}: {len(todo)} answers to generate", flush=True)
        for tid in todo:
            try:
                rec, err = call(model, ps[tid][1], think, s["options"]), None
            except Exception as e:
                rec, err = {"answer": "", "served": {}}, str(e)[:300]
            if rec["served"].get("context_full"):
                err = f"prompt and answer filled the {NUM_CTX}-token context"
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"tid": tid, "arm": "B", "run": 1, "model": model, "provider": "ollama",
                                    "reasoning": name, "setting": s["name"], "error": err, **rec}, ensure_ascii=False) + "\n")
    print(f"{model}: all generated", flush=True)


def trial_answers():
    """(model, reasoning, record) of every answer of the trial."""
    for path in sorted(ANSWERS.glob("*.jsonl")) if ANSWERS.exists() else []:
        model, _, name = path.stem.rsplit("-", 2)
        for r in rv.jsonl(path):
            if not r.get("error"):
                yield model.replace("__", "/"), name, r


def read() -> None:
    reader, _ = rv.reading_of_record()
    ps, qs = prompts(), load_questions(ROOT)
    done = {d["key"] for d in rv.jsonl(READ)}
    todo = [(m, r) for m, _, r in trial_answers()
            if classify(r["answer"], ps[r["tid"]][0], "B")[0] in ("gbag_failure", "lucky") and pb.key(r) not in done]
    print(f"{len(todo)} answers to read with {reader}", flush=True)
    for model, r in todo:
        t, t0 = ps[r["tid"]][0], time.time()
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


def rows_of(pairs, quotes: dict) -> list:
    """Rows in the shape of table_v07: (target, class by code, —, class after the D17 reading, more)."""
    targets, out = rv.load_targets(), []
    for r in pairs:
        t = targets[r["tid"]]
        cls, parsed = classify(r["answer"], t, "B")
        after = "honest" if cls in ("gbag_failure", "lucky") and quotes.get(pb.key(r), {}).get("quote_verified") else cls
        declined = parsed is not None and _is_none(parsed["value"])
        out.append((t, cls, cls, after, {"declined": declined, "text_gives_shown": False, "empty": not r["answer"].strip(),
                                        "seconds": r.get("seconds"), "thinking_chars": (r.get("served") or {}).get("thinking_chars") or 0}))
    return out


def verdict(on: list, off: list) -> str:
    share = tv.lower(on, off, tv.D17)
    broken = tv.shares(on, tv.D17)["broken"] / max(1, sum(x[0]["kind"] != "control" for x in on))
    if share is None:
        return "no rate to compare"
    back = tv.lower(off, on, tv.D17)
    text = (f"reasoning lowers the trap rate (in {100 * share:.0f} % of the draws)" if share >= ESTABLISHED else
            f"reasoning raises the trap rate (in {100 * back:.0f} % of the draws)" if back >= ESTABLISHED else
            f"no established effect (lower in {100 * share:.0f} % of the draws, higher in {100 * back:.0f} %)")
    return text + (f" — UNRELIABLE: {100 * broken:.0f} % of the answers with reasoning are broken" if broken > UNRELIABLE else "")


def report() -> None:
    ps = prompts()
    print(f"TUNING — a setting is kept with at least {PASS} readable blocks in 10, on the complete-result controls")
    for model in MODELS:
        rows = rv.jsonl(tuning_file(model))
        for s in SETTINGS:
            got = [r for r in rows if r["setting"] == s["name"]]
            if got:
                ok = sum(completes(r["answer"], ps[r["tid"]][0]) for r in got)
                right = sum(classify(r["answer"], ps[r["tid"]][0], "B")[0] == "correct" for r in got)
                print(f"  {model:12} {s['name']:16} readable blocks {ok}/{len(got)}   right values {right}/{len(got)}   "
                      f"empty {sum(not r['answer'].strip() for r in got)}   mean {statistics.mean(r['seconds'] for r in got):.0f} s")
        k = kept(model)
        print(f"  {model:12} -> " + (f"kept: {k['name']}" if k else "no setting kept" if rows else "not tuned"))

    _, d17 = rv.reading_of_record()
    quotes = {d["key"]: d for d in rv.jsonl(READ)}
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for model, name, r in trial_answers():
        by[model][name].append(r)
    wanted = set(run_targets())
    for model, conds in by.items():
        on = rows_of(conds["on"], quotes)
        if "off" in conds:
            off, source = rows_of(conds["off"], quotes), "generated again with the options of the setting kept"
        else:
            off = rows_of([r for m, r in dr.answers() if m == gen.slug(model).replace("__", "/") and r["arm"] == "B"
                           and r["run"] == 1 and r["tid"] in wanted], d17)
            source = "the published answers"
        print(f"\nTHE RUN — {model}, {len(on)} answers with reasoning; reasoning off: {source}")
        print(f"  {'':14} | {'acc. cut':>8} | {'right':>5} {'safe':>5} {'misl.':>5} {'broken':>6} {'empty':>5} | {'trap rate':>14} {'95 % by question':>20} | "
              f"{'mean s':>6} {'reasoning chars':>15}")
        for name, rs in (("reasoning off", off), ("reasoning on", on)):
            s = tv.shares(rs, tv.D17)
            print(f"  {name:14} | {tv.frac(tv.accuracy(rs, tv.D17, True)):>8} | {s['right']:>5} {s['safe']:>5} {s['misleading']:>5} "
                  f"{s['broken']:>6} {sum(x[tv.MORE].get('empty', False) for x in rs):>5} | "
                  f"{tv.pct(tv.trap(rs, tv.D17)) + ' (' + tv.frac(tv.trap(rs, tv.D17)) + ')':>14} {tv.margin(rs, tv.D17):>20} | "
                  f"{statistics.mean(x[tv.MORE]['seconds'] or 0 for x in rs):>6.0f} "
                  f"{statistics.mean(x[tv.MORE].get('thinking_chars', 0) for x in rs):>15.0f}")
        a = {x[0]["tid"]: tv.outcome(x[0]["kind"], x[tv.D17]) for x in on}
        b = {x[0]["tid"]: tv.outcome(x[0]["kind"], x[tv.D17]) for x in off}
        moves = collections.Counter((b[t], a[t]) for t in a if t in b and a[t] != b[t])
        print(f"  same outcome on {sum(a[t] == b[t] for t in a if t in b)}/{sum(t in b for t in a)} targets; "
              f"changes (off -> on): {dict(moves)}")
        print(f"  -> {verdict(on, off)}")


def witness(model: str) -> None:
    tune(model, limit=1)
    rows = rv.jsonl(tuning_file(model))
    if not rows:
        return
    r = rows[-1]
    speed = (r["output_tokens"] or 1) / max(r["seconds"], 0.1)
    worst = CAP / speed
    print(f"{model}: witness answer in {r['seconds']} s, {r['output_tokens']} tokens written "
          f"({r['served']['thinking_chars']} characters of reasoning), done: {r['served']['done_reason']}")
    print(f"  about {speed:.1f} tokens per second, prompt included: an answer that reaches the cap takes about {worst / 60:.0f} min")
    print(f"  tuning, 10 answers per setting: about {10 * r['seconds'] / 60:.0f} min if they are like this one, "
          f"at most {10 * worst / 60:.0f} min per setting")
    print(f"  the run, {len(run_targets())} answers: at most {len(run_targets()) * worst / 60:.0f} min")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    for flag in ("witness", "tune", "generate", "read", "report"):
        ap.add_argument(f"--{flag}", action="store_true")
    ap.add_argument("--models", nargs="*", default=MODELS[:1])
    args = ap.parse_args()
    for m in args.models:
        if args.witness:
            witness(m)
        if args.tune:
            tune(m)
        if args.generate:
            generate(m)
    if args.read:
        read()
    if args.report:
        report()
