"""Step 3/4 — the questions scored by Jev, and the thresholds that turn scores into choices.

Jev only scores options written here. Its state never contains the data, the truncation,
or any judge output. A choice is kept only at >= 0.80 with a >= 0.10 lead; otherwise it
is uncertain (PROTOCOL_v0.6_JUDGE.md, step 4).
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

MODEL = "typesafe/jev-1.13"
URL = "https://openrouter.ai/api/alpha/decisions"
ACCEPT_P, ACCEPT_MARGIN = 0.80, 0.10
ON_Q_YES, ON_Q_NO = 0.80, 0.20
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


def ask(question: str, context: str, sentence: str, figure: str, columns: list[str]) -> tuple[dict, dict]:
    """(answers, metadata). Development cache on unless GBAG_V06_NO_CACHE=1."""
    import requests
    body = {"model": MODEL,
            "state": {"question_asked": question, "previous_sentence": context or "(none)",
                      "sentence": sentence, "figure_under_review": figure, "result_columns": columns},
            "questions": questions(columns)}
    key = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
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
    """The choice if it clears 0.80 with a 0.10 lead, else None (uncertain)."""
    if not answer or answer.get("type") != "choice":
        return None
    probs = sorted((answer.get("probabilities") or {}).items(), key=lambda kv: -kv[1])
    if not probs:
        return None
    top = probs[0][1]
    second = probs[1][1] if len(probs) > 1 else 0.0
    return probs[0][0] if top >= ACCEPT_P and top - second >= ACCEPT_MARGIN else None


def bears_on_question(answer: dict | None) -> bool:
    """p >= 0.80 yes; p <= 0.20 no; in between counts as bearing (the conservative side)."""
    p = (answer or {}).get("noul")
    if p is None:
        return True
    return not (p <= ON_Q_NO)
