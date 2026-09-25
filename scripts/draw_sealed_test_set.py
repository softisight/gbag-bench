"""Draw and SEAL the test set for the v0.5 verifying judge (PROTOCOL_v0.4.md, deviation D12).

The 7 truth-set cases and the 15 reserve cases have now been read line by line: any judge
designed from here on is designed with them in sight, so they are its development set.
Its test set must be answers nobody has read. This script draws them from what is left of
the held-out pool and writes them to data/sealed/test-v05/, without printing a single
answer: only ids and fingerprints reach the terminal.

Selection is the reserve's own mechanics (build_reserve_worksheet.py): same eligible pool,
same strata {'giant': 8, 'l1_36': 4, 'l1_small': 3}, same round-robin over questions with a
rotating model offset, deterministic order. The only change is the exclusion list, which
now also holds the 15 reserve cases.

Usage (repo root):  python scripts/draw_sealed_test_set.py
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_reserve_worksheet import STRATA, TUNING, run_sql, stratum_of  # read-only helpers

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "sealed" / "test-v05"

README = """# SEALED — test set of the v0.5 verifying judge

Do not open the `.jsonl` files in this folder until the v0.5 judge is frozen
(PROTOCOL_v0.4.md, deviation D12). They are model answers that nobody has read: that is
the only thing that makes them a test.

- Drawn on 2026-09-25 by `scripts/draw_sealed_test_set.py`, before any v0.5 design work.
- Their SHA-256 fingerprints are recorded in PROTOCOL_v0.4.md (D12). A file whose
  fingerprint no longer matches is no longer the test set.
- Arbitration happens after the judge is frozen, with the same rules as the reserve (D9):
  proof by SQL for every condemnation, blind to every judge output, `disputed` excluded.
"""


def load(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def main() -> int:
    qs = {q["id"]: q for q in load(ROOT / "data" / "questions-heldout.jsonl")}
    reserve = {tuple(a["id"].split("__", 1)) for a in load(ROOT / "data" / "answers-reserve.jsonl")}
    excluded = TUNING | reserve

    cands = []
    for path in sorted((ROOT / "runs").glob("*-heldout.jsonl")):
        if "scored" in path.name:
            continue
        model = path.name.replace("-heldout.jsonl", "")
        for d in load(path):
            if d["id"] in qs and (model, d["id"]) not in excluded:
                cands.append((model, d["id"], d["model_answer"]))
    cands.sort(key=lambda t: (t[1], t[0]))

    sizes = {qid: len(run_sql(q)[1]) for qid, q in qs.items()}
    by_stratum: dict[str, dict[str, list]] = {k: {} for k in STRATA}
    for model, qid, ans in cands:
        by_stratum[stratum_of(sizes[qid])].setdefault(qid, []).append((model, qid, ans))
    picked = []
    for st in STRATA:
        target = sum(STRATA[k] for k in list(STRATA)[:list(STRATA).index(st) + 1])
        buckets = [by_stratum[st][q] for q in sorted(by_stratum[st])]
        i = 0
        while len(picked) < target and buckets:
            bi = i % len(buckets)
            b = buckets[bi]
            depth = i // len(buckets)
            if depth < len(b):
                picked.append((*b[(bi + depth) % len(b)], st))
            i += 1
            if i > len(buckets) * 20:
                break

    OUT.mkdir(parents=True, exist_ok=True)
    fq, fa, fv = OUT / "questions.jsonl", OUT / "answers.jsonl", OUT / "verdicts.template.jsonl"
    with fq.open("w", encoding="utf-8", newline="\n") as q_out, \
         fa.open("w", encoding="utf-8", newline="\n") as a_out, \
         fv.open("w", encoding="utf-8", newline="\n") as v_out:
        for model, qid, ans, st in picked:
            nid = f"{model}__{qid}"
            qq = dict(qs[qid])
            qq["id"] = nid
            q_out.write(json.dumps(qq, ensure_ascii=False) + "\n")
            a_out.write(json.dumps({"id": nid, "model_answer": ans}, ensure_ascii=False) + "\n")
            v_out.write(json.dumps({"id": nid, "stratum": st, "verdict": "", "band": "",
                                    "material_claim": "", "proof_sql": "", "proof_result": "",
                                    "arbitrated_by": "", "date": ""}, ensure_ascii=False) + "\n")
    (OUT / "README.md").write_text(README, encoding="utf-8")

    print(f"eligible after exclusions: {len(cands)}  (tuning {len(TUNING)}, reserve {len(reserve)})")
    print(f"drawn: {len(picked)}  strata {STRATA}")
    for model, qid, _, st in picked:
        print(f"  {st:9} {model}__{qid}")
    for f in (fq, fa, fv):
        print(f"sha256 {f.relative_to(ROOT).as_posix()} {hashlib.sha256(f.read_bytes()).hexdigest()}")
    assert not ({(m, q) for m, q, _, _ in picked} & excluded), "drew an excluded case"
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
