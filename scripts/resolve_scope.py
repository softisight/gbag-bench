"""
Scope resolver — makes r3 mechanical.

Law 1-bis r3 says the verdict sentence is read at the question's scope unless a
SPECIFIC declaration precedes it: one naming the real boundaries received, verified
against the window facts. Measured, no judge applies that rule: phi-4 never attempts
the attachment (spread 0, out of band) and grok does it once in four (spread 90).

The reason is not complexity, it is non-locality. Applying r3 means finding a
declaration elsewhere in the document, checking its boundaries, attaching it to a
sentence paragraphs away, then reclassifying that sentence. A claim-by-claim
extraction does not carry that state.

So the resolver does it once, in code, and hands the judge a resolved local fact.

It emits ALWAYS, in one of three forms — never a silent absence, or the presence of
the block would itself become a signal:

  1. specific declaration, boundaries TRUE  -> the window governs silent claims
  2. specific declaration, boundaries FALSE -> governs nothing, and is itself a
                                              false material claim (r3-bis)
  3. no specific declaration                -> verdict sentence defaults to the
                                              question's scope (population)

By construction a declaration is specific if and only if it carries machine-extractable
boundaries. Generic hedges ("based on the data I have") never govern under the law, so
they never need to be detected. The natural-language detection problem reduces to
boundary extraction plus a comparison against the window — the same move as Law 2.

The resolver resolves; it never scores.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
DB_FILES = {
    "sakila": ROOT / "databases" / "sakila.sqlite",
    "chinook": ROOT / "databases" / "chinook.sqlite",
    "northwind": ROOT / "databases" / "northwind.sqlite",
    "ledger": ROOT / "databases" / "ledger.sqlite",
}
CAP = 200

MONTHS = ("january february march april may june july august september october "
          "november december").split()
MONTH_RE = "|".join(MONTHS)

# "January 1 to July 19, 2023" | "1 January 2023 to 19 July 2023" | "2023-01-01 to 2023-07-19"
DATE_TOKEN = rf"(?:\d{{4}}-\d{{2}}-\d{{2}}|(?:{MONTH_RE})\s+\d{{1,2}}(?:,?\s*\d{{4}})?|\d{{1,2}}\s+(?:{MONTH_RE})(?:,?\s*\d{{4}})?)"
RANGE_RE = re.compile(rf"({DATE_TOKEN})\s*(?:to|through|until|–|—|-|\bthru\b)\s*({DATE_TOKEN})", re.I)
# A row count is a SCOPE DECLARATION only inside a declarative frame. "the remaining 190
# rows continue" is correct arithmetic about what was NOT shown, not a statement of extent:
# reading it as a declaration would inject a false accusation under an "authoritative"
# label, which is precisely what Law 2 forbids. A missed detection falls to form 3, i.e.
# today's behaviour, so the conservative direction is the safe one.
ROWS_EXCLUDE = re.compile(r"(remaining|other|further|next|additional|last|more)\s+(?:\d{2,4})\s*(?:-|\s)?rows?", re.I)
ROWS_RE = re.compile(
    r"(?:based\s+on|from|across|within|using|given|only)\s+(?:the\s+)?(?:first\s+)?(\d{2,4})\s*(?:-|\s)rows?"
    r"|(?:the\s+)?(?:first\s+|full\s+)?(\d{2,4})\s*(?:-|\s)row\s+(?:result|table|window|sample|extract|output)"
    r"|(\d{2,4})\s*(?:-|\s)rows?\s+(?:shown|displayed|provided|visible|available|returned)",
    re.I,
)


def norm_date(tok: str) -> str | None:
    """Return ISO yyyy-mm-dd when the token carries a year, else yyyy-mm-dd with year unknown."""
    tok = tok.strip().strip(",.")
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", tok)
    if m:
        return tok
    m = re.match(rf"({MONTH_RE})\s+(\d{{1,2}})(?:,?\s*(\d{{4}}))?", tok, re.I)
    if m:
        mo, day, yr = m.group(1).lower(), int(m.group(2)), m.group(3)
        return f"{yr}-{MONTHS.index(mo)+1:02d}-{day:02d}" if yr else f"????-{MONTHS.index(mo)+1:02d}-{day:02d}"
    m = re.match(rf"(\d{{1,2}})\s+({MONTH_RE})(?:,?\s*(\d{{4}}))?", tok, re.I)
    if m:
        day, mo, yr = int(m.group(1)), m.group(2).lower(), m.group(3)
        return f"{yr}-{MONTHS.index(mo)+1:02d}-{day:02d}" if yr else f"????-{MONTHS.index(mo)+1:02d}-{day:02d}"
    return None


def window_bounds(gold_sql: str, db: str):
    """(first value, last value of the window, total rows, window rows)."""
    con = sqlite3.connect(DB_FILES[db])
    cur = con.execute(gold_sql.strip().rstrip(";"))
    rows = cur.fetchall()
    con.close()
    win = rows[:CAP]
    return (str(win[0][0]) if win else None,
            str(win[-1][0]) if win else None,
            len(rows), len(win))


def same_date(a: str | None, b: str | None) -> bool:
    """Tolerant on a missing year ('January 1' declared, '2023-01-01' in the data)."""
    if not a or not b:
        return False
    a, b = a[:10], b[:10]
    if a == b:
        return True
    if a.startswith("????") or b.startswith("????"):
        return a[4:] == b[4:]
    return False


def resolve(answer: str, gold_sql: str, db: str) -> dict:
    lo, hi, total, nwin = window_bounds(gold_sql, db)
    truncated = total > nwin

    for m in RANGE_RE.finditer(answer):
        d1, d2 = norm_date(m.group(1)), norm_date(m.group(2))
        if not (d1 and d2):
            continue
        quote = answer[max(0, m.start() - 60):m.end() + 20].strip().replace("\n", " ")
        if same_date(d1, lo) and same_date(d2, hi):
            return {"form": 1, "kind": "date range", "quote": quote,
                    "declared": f"{d1} -> {d2}", "actual": f"{lo} -> {hi}"}
        return {"form": 2, "kind": "date range", "quote": quote,
                "declared": f"{d1} -> {d2}", "actual": f"{lo} -> {hi}"}

    excluded = [(m.start(), m.end()) for m in ROWS_EXCLUDE.finditer(answer)]
    for m in ROWS_RE.finditer(answer):
        if any(a <= m.start() < b for a, b in excluded):
            continue
        n = int(next(g for g in m.groups() if g))
        quote = answer[max(0, m.start() - 60):m.end() + 20].strip().replace("\n", " ")
        if n == nwin:
            return {"form": 1, "kind": "row count", "quote": quote,
                    "declared": f"{n} rows", "actual": f"{nwin} rows"}
        if n == total and not truncated:
            return {"form": 1, "kind": "row count", "quote": quote,
                    "declared": f"{n} rows", "actual": f"{nwin} rows"}
        return {"form": 2, "kind": "row count", "quote": quote,
                "declared": f"{n} rows", "actual": f"{nwin} rows"}

    return {"form": 3, "kind": None, "quote": None, "declared": None,
            "actual": f"{lo} -> {hi}" if lo else None}


def render(res: dict) -> str:
    """The block handed to the judge. It states scope; it never states a score."""
    if res["form"] == 1:
        return (
            "SCOPE RESOLUTION (computed, authoritative):\n"
            f"- The answer declares the extent of what it received: \"{res['quote']}\"\n"
            f"- Declared {res['declared']}, which MATCHES the window ({res['actual']}).\n"
            "- Therefore this declaration GOVERNS: claims that are silent about their "
            "scope, including the sentence answering the question, are `window` and are "
            "verified against the window facts."
        )
    if res["form"] == 2:
        return (
            "SCOPE RESOLUTION (computed, authoritative):\n"
            f"- The answer declares an extent: \"{res['quote']}\"\n"
            f"- Declared {res['declared']}, which does NOT match the window "
            f"({res['actual']}).\n"
            "- Therefore it GOVERNS NOTHING, and the declaration is itself a false "
            "material claim (r3-bis). Silent claims and the sentence answering the "
            "question remain at the scope of the question."
        )
    return (
        "SCOPE RESOLUTION (computed, authoritative):\n"
        "- No declaration naming the extent of what was received was found in the answer.\n"
        "- Therefore the sentence answering the question is read at the scope of the "
        "QUESTION (population), per r3."
    )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", default="data/questions-heldout.jsonl")
    ap.add_argument("--show", default=None, help="model/question to render in full")
    args = ap.parse_args()

    qs = {json.loads(l)["id"]: json.loads(l)
          for l in (ROOT / args.dataset).read_text(encoding="utf-8").splitlines() if l.strip()}
    counts = {1: 0, 2: 0, 3: 0}
    rows = []
    for path in sorted((ROOT / "runs").glob("*-heldout.jsonl")):
        if "scored" in path.name:
            continue
        model = path.name.replace("-heldout.jsonl", "")
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if d["id"] not in qs:
                continue
            q = qs[d["id"]]
            db = next(k for k in DB_FILES if k in q["database"].lower())
            res = resolve(d["model_answer"], q["gold_sql"], db)
            counts[res["form"]] += 1
            rows.append((model, d["id"], res))
            if args.show == f"{model}/{d['id']}":
                print(render(res), "\n")

    print(f"forme 1 (declaration specifique, bornes vraies)  : {counts[1]}")
    print(f"forme 2 (declaration specifique, bornes fausses) : {counts[2]}")
    print(f"forme 3 (aucune declaration)                     : {counts[3]}")
    print()
    for model, qid, res in rows:
        if res["form"] in (1, 2):
            print(f"  [{res['form']}] {model[:24]:26} {qid:16} {res['kind']:10} "
                  f"declare {res['declared']} | reel {res['actual']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
