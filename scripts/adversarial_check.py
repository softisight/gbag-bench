#!/usr/bin/env python3
"""Adversarial check for the direction atoms (issue #1 commitment).

For each enforceable direction atom (v1.3: 11 atoms), two hand-written
answers that differ ONLY in the overall-direction claim: one asserts the
atom's direction (control), one asserts the opposite (adversarial). Both
use the same real numbers from the result set, so the judged difference
is attributable to the direction claim alone. The adversarial answers
reuse the real traps: endpoint deltas (8 -> 182), the partial-first-month
+41%, a decelerating growth rate read as decline, the opening-balance
month.

Each answer is scored by the reference judge (Grok-4.3, prompt v0.2)
under two conditions:

  bare : the judge exactly as shipped (no atoms)
  atom : the same judge with the direction atom injected into the user
         message as a must-preserve fact (prototype integration)

What this measures:
  1. Does the bare judge already catch inverted-direction answers?
     (Mostly it cannot: gold answers show only the first rows.)
  2. Does the atom make the inversion enforceable: inverted rejected,
     control preserved? A rule is only tested the day something tries
     to break it.

Output: data/adversarial_check_results.jsonl (incremental, resumable)
Usage:  python scripts/adversarial_check.py             # 44 judge calls
        python scripts/adversarial_check.py --only ledger-l8-02
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "judge"))

import run_judge as rj  # noqa: E402  (judge/run_judge.py)

JUDGE_MODEL = "x-ai/grok-4.3"
OUT_PATH = ROOT / "data" / "adversarial_check_results.jsonl"

# ---------------------------------------------------------------------------
# The 22 answers. Hand-written, versioned here on purpose: the pairs are the
# experiment. Same numbers on both sides; only the direction claim flips.
# ---------------------------------------------------------------------------
ANSWERS = {
    "sakila-l8-01": {
        "correct": (
            "Rental activity declines sharply over the period. The early "
            "months run at well over a hundred rentals a day on average, "
            "then activity collapses after August 2005 to near zero for "
            "months, with only a brief burst in February 2006. The overall "
            "direction is clearly downward."),
        "inverted": (
            "Rental activity grows strongly over the period. The first "
            "recorded day shows 8 rentals against 182 on the last day, a "
            "more than twentyfold increase, and the overall direction is "
            "clearly upward."),
    },
    "sakila-l10-01": {
        "correct": (
            "Across the full period the daily rental count trends steeply "
            "downward: the average of the first quarter of the series is "
            "about 124.6 rentals per day against about 2.8 in the last "
            "quarter. In the visible early stretch the counts run above one "
            "hundred a day, so the striking anomaly is that activity later "
            "collapses to near zero, possibly a system or store shutdown "
            "(a hypothesis, not an established fact)."),
        "inverted": (
            "Daily rentals trend upward across the window: the first day "
            "shows 8 rentals and the last day 182, and the series ends at "
            "its strongest point. The most striking anomaly is the quiet "
            "stretch in between, possibly seasonal (a hypothesis, not an "
            "established fact). The overall trend is growth."),
    },
    "sakila-l10-02": {
        "correct": (
            "The running total accumulates rapidly through the visible "
            "early window. Over the full period, though, the pace of "
            "accumulation falls off sharply: the per-period flux drops "
            "from about 562 early on to about 7.8 late in the series. The "
            "cumulative level still ends at 67,416.51, as a running total "
            "necessarily rises, but the accumulation rate is anything but "
            "constant."),
        "inverted": (
            "The cumulative total reaches 67,416.51 by the end of the "
            "window, and the pace of accumulation keeps increasing over "
            "the period: the running total rises steadily month after "
            "month and accelerates toward the end of the window."),
    },
    "chinook-l4-01": {
        "correct": (
            "Monthly revenue is essentially stable across the five years, "
            "hovering around 38-40 per month with normal fluctuation and "
            "no sustained trend in either direction."),
        "inverted": (
            "Monthly revenue grows steadily across the five years, ending "
            "around 38.62 versus 35.64 at the start, a clear upward "
            "trajectory for the business."),
    },
    "chinook-l8-01": {
        "correct": (
            "Invoice frequency is stable across the whole five-year span, "
            "at roughly 0.23 invoices per day (about one every four to "
            "five days), with no trend in either direction."),
        "inverted": (
            "Invoice frequency increases over the five years: by the end "
            "of the period invoices arrive noticeably more often than at "
            "the start, a clear upward drift in activity."),
    },
    "northwind-l4-01": {
        "correct": (
            "Monthly revenue is flat across the eleven years: the average "
            "of the early years and the average of the late years differ "
            "by only a few percent. The apparently low first month "
            "(about 2.07M) is a partial month, not a real starting level, "
            "so the endpoint comparison overstates any change."),
        "inverted": (
            "Revenue shows sustained growth across the period: it starts "
            "around 2.07M in the first month and ends around 2.92M, "
            "roughly 41% higher, a clear long-term upward trend for the "
            "business."),
    },
    "northwind-l8-01": {
        "correct": (
            "Daily order volume is remarkably stable across the eleven "
            "years, at roughly 3-4 orders per day throughout, with no "
            "upward or downward trend."),
        "inverted": (
            "Daily order volume declines over the eleven years: the first "
            "day shows 2 orders against a single order on the last day, "
            "and the long-term direction is downward."),
    },
    "ledger-l8-01": {
        "correct": (
            "Revenue trends upward across 2023-2025: early months average "
            "around 23-24k while the late months average around 30k, with "
            "the usual seasonal dip each August. The direction over the "
            "three years is growth."),
        "inverted": (
            "Revenue trends downward across 2023-2025: the growth rate "
            "shrinks year after year and the monthly percentage change "
            "ends lower than it started, so the overall direction of the "
            "business is decline."),
    },
    "ledger-l8-02": {
        "correct": (
            "The bank position strengthens over the period: the balance "
            "moves from about 34.7k after the opening month to 54.9k at "
            "the end, and the average monthly net inflow is higher in the "
            "last year than in the first. Direction: upward."),
        "inverted": (
            "The bank position weakens over the period: monthly net "
            "movements deteriorate, with the last month at just 3.7k "
            "against 34.8k in the first month, so the cash trend is "
            "clearly downward."),
    },
    "ledger-l9-01": {
        "correct": (
            "The running balance starts at 45,000, dips to its lowest "
            "point in the spring of 2023, and ends at 54,883.50, higher "
            "than it started. Over the whole period the account grows."),
        "inverted": (
            "The running balance starts at 45,000 and spends much of the "
            "period below that level, with a deep trough in 2023; overall "
            "the account is on a declining path."),
    },
    "ledger-l9-02": {
        "correct": (
            "Posting activity increases over the three years: daily entry "
            "counts average around 1.1 in the early months and around 1.5 "
            "by the end, a steady rise in volume."),
        "inverted": (
            "Posting activity decreases over the three years: the first "
            "day shows 2 entries against a single entry on the last day, "
            "and daily volume drifts downward over time."),
    },
}

OPPOSITE = {"up": "down", "down": "up", "flat": "a clear trend"}


def load_atoms() -> dict:
    atoms = {}
    for line in (ROOT / "data" / "direction_atoms_proposed.jsonl").open(encoding="utf-8"):
        a = json.loads(line)
        if a["bucket"] in ("up", "down", "flat"):
            atoms[a["id"]] = a
    return atoms


def load_questions() -> dict:
    qs = {}
    for name in ("questions.jsonl", "questions-heldout.jsonl"):
        for line in (ROOT / "data" / name).open(encoding="utf-8"):
            q = json.loads(line)
            qs[q["id"]] = q
    return qs


def atom_block(atom: dict) -> str:
    """The prototype injection: the atom as a must-preserve fact."""
    ev = atom["evidence"]
    voter = next((s for s in ev.get("series", {}).values()
                  if isinstance(s, dict) and s.get("votes", True)), {})
    if voter.get("treatment") == "cumulative-flux":
        subject = (
            f"the per-period accumulation rate (the flux of the cumulative "
            f"column, NOT its level -- the cumulative level itself rises by "
            f"construction, from {voter.get('level_first')} to "
            f"{voter.get('level_last')})")
        evidence = (
            f"window means of the per-period flux: "
            f"{voter.get('flux_head_mean')} -> {voter.get('flux_tail_mean')}")
    else:
        subject = "the question's series"
        evidence = (
            f"window means over the first/last quarter of the ordered "
            f"points: {voter.get('head_mean')} -> {voter.get('tail_mean')}")
    return (
        "DIRECTION ATOM (machine-computed from the FULL result set, "
        "human-reviewed):\n"
        f"- Overall full-period direction of {subject}: "
        f"{atom['bucket'].upper()}\n"
        f"- Evidence: {evidence}\n"
        "Scoring rule: an answer asserting the OPPOSITE overall direction "
        "for the full period contradicts the full data and must be scored "
        "as unfaithful on that claim. An answer whose overall-direction "
        "claim matches the atom is grounded on that claim. Claims "
        "explicitly scoped to a visible subset follow the normal "
        "truncation scoping rules.\n"
    )


def build_user(q: dict, answer: str, atom: dict | None) -> str:
    base = rj.build_user_message(q, answer)
    if atom is None:
        return base
    marker = "\nMODEL ANSWER:\n"
    head, _, tail = base.rpartition(marker)
    return head + "\n" + atom_block(atom) + marker + tail


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="single question id")
    ap.add_argument("--model", default=JUDGE_MODEL)
    args = ap.parse_args()

    atoms, questions = load_atoms(), load_questions()
    system = rj.load_judge_system_prompt()

    done = set()
    if OUT_PATH.exists() and not args.only:
        for line in OUT_PATH.open(encoding="utf-8"):
            if line.strip():
                r = json.loads(line)
                done.add((r["id"], r["variant"], r["condition"]))

    out = OUT_PATH.open("a", encoding="utf-8")
    results = []
    ids = [args.only] if args.only else list(ANSWERS)
    for qid in ids:
        atom, q = atoms[qid], questions[qid]
        for variant in ("inverted", "correct"):
            answer = ANSWERS[qid][variant]
            for condition in ("bare", "atom"):
                key = (qid, variant, condition)
                if key in done:
                    print(f"{qid:16s} {variant:8s} {condition:4s}  (already done)")
                    continue
                user = build_user(q, answer, atom if condition == "atom" else None)
                for attempt in (1, 2):
                    try:
                        raw, ti, to = rj.call_openrouter(system, user, model=args.model)
                        parsed = rj.clamp_scores(rj.parse_judge_response(raw))
                        break
                    except Exception as e:
                        if attempt == 2:
                            print(f"{qid} {variant} {condition}: ERROR {e}", file=sys.stderr)
                            parsed = None
                        else:
                            time.sleep(3)
                if parsed is None:
                    continue
                rec = {
                    "id": qid, "variant": variant, "condition": condition,
                    "atom_bucket": atom["bucket"],
                    "faithfulness": parsed["faithfulness"],
                    "completeness": parsed["completeness"],
                    "insight": parsed["insight"],
                    "gbag_score": rj.compute_gbag_score(parsed),
                    "faithfulness_justification": parsed.get("faithfulness_justification", ""),
                    "judge_model": args.model,
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                out.flush()
                results.append(rec)
                print(f"{qid:16s} {variant:8s} {condition:4s}  F={rec['faithfulness']:3d}  GBAG={rec['gbag_score']}")
                time.sleep(0.5)
    out.close()

    # Summary over the full result file
    allr = [json.loads(l) for l in OUT_PATH.open(encoding="utf-8") if l.strip()]
    def bucket(rs, variant, condition):
        return [r for r in rs if r["variant"] == variant and r["condition"] == condition]
    print("\n=== Summary (F = faithfulness) ===")
    for condition in ("bare", "atom"):
        inv = bucket(allr, "inverted", condition)
        cor = bucket(allr, "correct", condition)
        caught = sum(1 for r in inv if r["faithfulness"] <= 40)
        slipped = sum(1 for r in inv if r["faithfulness"] >= 70)
        ok = sum(1 for r in cor if r["faithfulness"] >= 70)
        print(f"{condition:4s} judge: inverted caught {caught}/{len(inv)}, "
              f"slipped {slipped}/{len(inv)} | correct preserved {ok}/{len(cor)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
