"""
Build the held-out reserve worksheet.

The campaign of 2026-08-05 wrote the scope law against seven hand-verified cases and
then measured judges on those same seven. A judge scoring 7/7 there has demonstrated
nothing about generalisation: the reserve agreed at the start of the campaign was never
built. This script builds it.

What is mechanical here, and what is not:

  * SELECTION is mechanical. Stratified by result regime, deterministic ordering, and the
    seven tuning cases are excluded by name. No case is chosen because it looked
    interesting - that is how a reserve stops being a reserve.
  * CLAIM EXTRACTION is mechanical: scope markers from Law 1-bis r1, and figures from the
    numeric checker's rules.
  * SCOPE is mechanical: r1 markers first, then the scope resolver's verdict on any
    governing declaration.
  * TRUTH is mechanical: every proposed verdict carries the SQL that settles it. Nobody
    has to believe the annotator, only re-run the query.
  * MATERIALITY is NOT mechanical, and neither is the final band. Those are left to the
    arbitrator, which is why this is a worksheet and not a verdict file.

Usage:
    python scripts/build_reserve_worksheet.py > reserve_worksheet.md
"""
from __future__ import annotations

import json
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parent.parent
CAP = 200

# The seven cases the law was written against. Excluded by name, on purpose.
TUNING = {
    ("nemotron-3-nano-30b", "ledger-l10-01"), ("nemotron-3-nano-30b", "ledger-l10-02"),
    ("nemotron-3-nano-30b", "ledger-l8-01"), ("nemotron-3-nano-30b", "ledger-l9-01"),
    ("claude-fable-5", "ledger-l10-02"), ("qwen3-coder-480b", "ledger-l8-02"),
    ("qwen3.6", "ledger-l9-02"),
}
# Fable's stratification (entry 14): the common error lives where claims are many and the
# gold is thin, so a uniform draw would over-sample the small questions.
STRATA = {"giant": 8, "l1_36": 4, "l1_small": 3}

POP_MARKERS = (r"\b(every|all|none|no other|entire|overall|total|final|ends at|majority|"
               r"most|typical|whole|in the dataset|in the ledger|across the (?:full )?period)\b")
WIN_MARKERS = (r"\b(shown|displayed|visible|returned|the rows I have|period shown|so far|"
               r"I can see|first \d+ rows)\b")


def db_of(q: dict) -> str:
    from resolve_scope import DB_FILES
    return next(k for k in DB_FILES if k in q["database"].lower())


def run_sql(q: dict):
    from resolve_scope import DB_FILES
    con = sqlite3.connect(DB_FILES[db_of(q)])
    cur = con.execute(q["gold_sql"].strip().rstrip(";"))
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    con.close()
    return cols, rows


def stratum_of(nrows: int) -> str:
    if nrows > CAP:
        return "giant"
    return "l1_36" if nrows >= 30 else "l1_small"


def column_facts(cols, rows, label):
    out = []
    for i, c in enumerate(cols):
        nums = [r[i] for r in rows if isinstance(r[i], (int, float)) and not isinstance(r[i], bool)]
        if not nums:
            continue
        lo, hi = min(nums), max(nums)
        lo_at = next(r[0] for r in rows if r[i] == lo)
        hi_at = next(r[0] for r in rows if r[i] == hi)
        med = sorted(nums)[len(nums) // 2]
        out.append(f"    {label} {c}: min={lo} (at {lo_at}), max={hi} (at {hi_at}), "
                   f"median={med}, sum={round(sum(nums), 2)}, n={len(nums)}")
    return out


def sentences_with_markers(answer: str):
    """Sentences carrying an explicit scope marker — the claims r1 decides first."""
    hits = []
    for sent in re.split(r"(?<=[.!?])\s+", answer):
        s = sent.strip().replace("\n", " ")
        if not s or len(s) > 400:
            continue
        pop = sorted({m.group(0).lower() for m in re.finditer(POP_MARKERS, s, re.I)})
        win = sorted({m.group(0).lower() for m in re.finditer(WIN_MARKERS, s, re.I)})
        if pop or win:
            hits.append((s, pop, win))
    return hits


def main() -> int:
    import resolve_scope as rs

    qs = {json.loads(l)["id"]: json.loads(l)
          for l in (ROOT / "data" / "questions-heldout.jsonl").read_text(encoding="utf-8").splitlines()
          if l.strip()}

    # deterministic candidate list: every (model, question) that is not a tuning case
    cands = []
    for path in sorted((ROOT / "runs").glob("*-heldout.jsonl")):
        if "scored" in path.name:
            continue
        model = path.name.replace("-heldout.jsonl", "")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d["id"] not in qs or (model, d["id"]) in TUNING:
                continue
            cands.append((model, d["id"], d["model_answer"]))
    cands.sort(key=lambda t: (t[1], t[0]))

    sizes = {qid: len(run_sql(q)[1]) for qid, q in qs.items()}
    # Round-robin over QUESTIONS inside each stratum. Filling a stratum in sorted order
    # would take the first N entries, which are all the same question with different
    # models: a reserve covering four questions tests generalisation across models, not
    # across questions, which is the thing at stake.
    by_stratum: dict[str, dict[str, list]] = {k: {} for k in STRATA}
    for model, qid, ans in cands:
        by_stratum[stratum_of(sizes[qid])].setdefault(qid, []).append((model, qid, ans))
    picked = []
    for st, want in STRATA.items():
        buckets = [by_stratum[st][q] for q in sorted(by_stratum[st])]
        i = 0
        while len(picked) < sum(STRATA[k] for k in list(STRATA)[:list(STRATA).index(st) + 1]):
            bi = i % len(buckets)
            b = buckets[bi]
            # Rotate the model offset by the bucket index: without it, each question
            # yields its alphabetically first model and the reserve covers ten questions
            # but only three models.
            depth = i // len(buckets)
            if depth < len(b):
                picked.append((*b[(bi + depth) % len(b)], st))
            i += 1
            if i > len(buckets) * 20:
                break

    # Machine-readable companions, so that measuring a judge on the reserve is one command
    # once the verdicts are filled in. Emitting them pre-judges nothing: the verdict column
    # is left empty on purpose, and the arbitrator must not be whoever wrote the law.
    out = ROOT / "data"
    with open(out / "questions-reserve.jsonl", "w", encoding="utf-8") as fq, \
         open(out / "answers-reserve.jsonl", "w", encoding="utf-8") as fa, \
         open(out / "verdicts-reserve.template.jsonl", "w", encoding="utf-8") as fv:
        for model, qid, ans, st in picked:
            nid = f"{model}__{qid}"
            qq = dict(qs[qid])
            qq["id"] = nid
            fq.write(json.dumps(qq, ensure_ascii=False) + "\n")
            fa.write(json.dumps({"id": nid, "model_answer": ans}, ensure_ascii=False) + "\n")
            fv.write(json.dumps({"id": nid, "stratum": st, "verdict": "", "band": "",
                                 "material_claim": "", "proof_sql": "",
                                 "arbitrated_by": "", "date": ""}, ensure_ascii=False) + "\n")

    print("# Reserve worksheet — held out from the law-writing set\n")
    print(f"Selected {len(picked)} of {len(cands)} eligible cases, deterministic order, "
          f"stratified {STRATA}. The seven tuning cases are excluded by name.\n")
    print("For each case: the claims carrying an explicit scope marker, the scope the law "
          "assigns, and the computed facts at both scopes. **The arbitrator supplies "
          "materiality and the band.**\n")

    for model, qid, ans, st in picked:
        q = qs[qid]
        cols, rows = run_sql(q)
        win = rows[:CAP]
        res = rs.resolve(ans, q["gold_sql"], db_of(q))
        print(f"\n---\n\n## {model} / {qid}  *(stratum: {st}, {len(rows)} rows)*\n")
        print(f"**Question** — {q['question'][:220]}\n")
        print(f"**Scope resolution** — form {res['form']}"
              + (f", declared {res['declared']} vs actual {res['actual']}" if res["declared"] else "")
              + "\n")
        marked = sentences_with_markers(ans)
        if not marked:
            print("_No sentence carries an explicit scope marker: every claim falls to "
                  "inheritance or to the question's scope._\n")
        for s, pop, w in marked[:6]:
            scope = "POPULATION (r1)" if pop else "WINDOW (r1)"
            print(f"- **{scope}** — markers {pop or w}\n  > {s[:230]}")
        print("\n**Computed facts**\n```")
        for line in column_facts(cols, win, "window "):
            print(line)
        if len(rows) > CAP:
            for line in column_facts(cols, rows, "populn "):
                print(line)
        print(f"    rows: window={len(win)}  population={len(rows)}")
        print("```")
        print(f"\n**Proof query** — `{q['gold_sql'].strip()[:160]}…`\n")
        print("**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
