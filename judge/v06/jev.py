"""Step 3/4 — the questions scored by Jev, and the thresholds that turn scores into choices.

Jev only scores options written here. Its state never contains the data, the truncation,
or any judge output. A choice is kept only when Jev's `confidence` is >= 0.70 and the top
option leads by >= 0.10; otherwise it is uncertain (PROTOCOL_v0.6_JUDGE.md, step 4 and V3).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

MODEL = "typesafe/jev-1.13"
URL = "https://openrouter.ai/api/alpha/decisions"
ACCEPT_CONF, ACCEPT_MARGIN = 0.70, 0.10     # V3: Jev's `confidence`, not the top probability
ON_Q_YES, ON_Q_NO = 0.80, 0.10              # V3: "not bearing" only at <= 0.10
CACHE_DIR = Path(__file__).resolve().parents[2] / "runs" / "v0.6" / "cache"

FAMILIES = {
    "cell": "The value of one row, day or period",
    "sum": "A total, a sum of several values, or the final value of a running total",
    "maximum": "The largest value", "minimum": "The smallest value",
    "last": "Where the data ends (its last value or last date)",
    "first": "Where the data starts (its first value or first date)",
    "ratio": "How many times larger one value is than another",
    "share": "A proportion or percentage of rows",
    "count": "A number of rows, entries, days or items",
    "change": "A difference or percentage change between two rows or periods",
    "place": "A date or label that only says WHERE another figure is",
    "other": "None of the above",
}
REFERENCES = {"second_largest": "The next-largest value", "median": "The median or typical value",
              "mean": "The average", "named_value": "A specific figure named in the sentence"}


def questions(columns: list[str]) -> dict:
    return {
        "scope": {"type": "choice", "instructions": "Which rows does the sentence make its claim about?",
                  "criteria": {"rows_shown": "Only the rows the answer displayed or received",
                               "all_data": "The whole data set, ledger or account, or no limit stated"}},
        "family": {"type": "choice", "instructions": "What kind of fact does the figure under review state?",
                   "criteria": FAMILIES},
        "column": {"type": "choice", "instructions": "Which result column is the figure under review about?",
                   "criteria": {c: f"The '{c}' column" for c in columns} | {"none": "No column (a count of rows, or not about the data)"}},
        "reference": {"type": "choice", "instructions": "If the figure is a ratio, what is it compared against?",
                      "criteria": REFERENCES},
        "on_question": {"type": "noul", "instructions": "Does the figure under review give (part of) what the question asks for?",
                        "criteria": {"true": "It answers the question or part of it",
                                     "false": "It is a side remark, not what was asked"}},
    }


SAMPLES = 3     # PROTOCOL_v0.6 V3: median of 3 calls per figure


def ask(question: str, context: str, sentence: str, figure: str, columns: list[str]) -> tuple[dict, dict]:
    """(answers, metadata): the per-option MEDIAN of SAMPLES independent calls.

    Two identical calls return probabilities up to ~0.03 apart; with scores sitting on the
    0.80 threshold, one verdict in 37 flipped between passes (development, 2026-09-26). The
    median of 3 halves that noise; the thresholds then apply to the median."""
    import statistics
    runs, metas = [], []
    for k in range(SAMPLES):
        a, m = _ask_once(question, context, sentence, figure, columns, k)
        runs.append(a)
        metas.append(m)
    merged: dict = {}
    for q in runs[0]:
        base = dict(runs[0][q])
        if base.get("type") == "choice":
            opts = set().union(*[(r[q].get("probabilities") or {}).keys() for r in runs])
            probs = {o: statistics.median([(r[q].get("probabilities") or {}).get(o, 0.0) for r in runs]) for o in opts}
            base["probabilities"] = probs
            base["choice"] = max(probs, key=probs.get)
            base["confidence"] = statistics.median([r[q].get("confidence", 0.0) for r in runs])
        elif base.get("type") == "noul":
            base["noul"] = statistics.median([r[q].get("noul", 0.5) for r in runs])
        merged[q] = base
    return merged, {"model": metas[0].get("model"), "cost": sum(m.get("cost") or 0 for m in metas),
                    "samples": SAMPLES}


def _ask_once(question: str, context: str, sentence: str, figure: str, columns: list[str],
              sample: int) -> tuple[dict, dict]:
    """One call. Development cache on unless GBAG_V06_NO_CACHE=1 (keyed per sample index)."""
    import requests
    body = {"model": MODEL,
            "state": {"question_asked": question, "previous_sentence": context or "(none)",
                      "sentence": sentence, "figure_under_review": figure, "result_columns": columns},
            "questions": questions(columns)}
    key = hashlib.sha256(json.dumps([body, sample], sort_keys=True).encode()).hexdigest()
    cached = CACHE_DIR / f"{key}.json"
    if not os.environ.get("GBAG_V06_NO_CACHE") and cached.exists():
        data = json.loads(cached.read_text(encoding="utf-8"))
        return data["answers"], {"model": data.get("model"), "cost": 0, "cached": True}
    data = None
    for attempt in range(3):              # transport retries only: same body
        try:
            r = requests.post(URL, headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                              json=body, timeout=60)
            data = r.json()
            if "answers" in data:
                break
        except (requests.RequestException, ValueError):
            pass
    if not data or "answers" not in data:
        raise RuntimeError(f"Decisions API: {str(data)[:300]}")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data), encoding="utf-8")
    return data["answers"], {"model": data.get("model"), "cost": (data.get("usage") or {}).get("cost")}


def accepted(answer: dict | None) -> str | None:
    """The choice if Jev's confidence is >= 0.70 and the top option leads by >= 0.10, else
    None (uncertain). `confidence` measures how concentrated the distribution is: a top
    option at 0.60 with its mass spread over the others scores lower than one at 0.60 with
    a single rival (V3)."""
    if not answer or answer.get("type") != "choice":
        return None
    probs = sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
    if not probs:
        return None
    top = probs[0][1]
    second = probs[1][1] if len(probs) > 1 else 0.0
    conf = answer.get("confidence") or 0.0
    return probs[0][0] if conf >= ACCEPT_CONF and top - second >= ACCEPT_MARGIN else None


def bears_on_question(answer: dict | None) -> bool:
    """p <= 0.10 does not bear; anything above counts as bearing (the conservative side:
    a condemnation stays material in doubt)."""
    p = (answer or {}).get("noul")
    if p is None:
        return True
    return not (p <= ON_Q_NO)
