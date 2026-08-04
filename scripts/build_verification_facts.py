"""
Build verification facts for GBAG gold answers.

For every question, executes the gold SQL and computes the deterministic facts a
judge needs in order to verify a model's claims:

  * WINDOW facts  — computed over the first `--cap` rows (what the model actually saw)
  * POPULATION facts — computed over the whole result set

When the result fits under the cap, window == population and only one block is emitted.

Report mode (default) writes nothing. It prints what would be produced and, more
importantly, flags the questions whose window is NOT well defined:

  * no top-level ORDER BY on a result larger than the cap -> the "first 200 rows"
    are an accident of the engine, not a fact
  * a tie straddling the cap boundary -> the window edge is unstable across engines

Usage:
    python scripts/build_verification_facts.py --report
    python scripts/build_verification_facts.py --write
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
DATASETS = [ROOT / "data" / "questions.jsonl", ROOT / "data" / "questions-heldout.jsonl"]

MAX_DISTINCT_FOR_DISTRIBUTION = 20

# Questions whose ORDER BY references columns absent from the output, and whose
# ordering key was verified unique by hand against the schema. The mechanical
# tie-check cannot see those columns, so it must be told.
#
#   ledger: (entry_id, line_id) is unique on journal_entry_lines (3616/3616)
#           entry_id           is unique on journal_entries      (1412/1412)
#   -> the ordering is total, the window edge is stable.
ORDERING_VERIFIED_UNIQUE = {
    "ledger-l9-01",
    "ledger-l9-03",
    "ledger-l10-01",
    "ledger-l10-02",
}


# --------------------------------------------------------------------------- SQL


def strip_trailing_semicolon(sql: str) -> str:
    return sql.strip().rstrip(";").strip()


def top_level_order_by(sql: str) -> str | None:
    """Return the text following a depth-0 ORDER BY, or None.

    Depth-aware on purpose: `SUM(...) OVER (ORDER BY x)` must NOT be mistaken for a
    top-level ordering. This is the same trap documented in AI.SQLResultShaping.
    """
    depth = 0
    in_str = False
    i = 0
    last = None
    while i < len(sql):
        ch = sql[i]
        if in_str:
            if ch == "'":
                in_str = False
        elif ch == "'":
            in_str = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif depth == 0 and sql[i : i + 8].upper() == "ORDER BY" and (
            i == 0 or not sql[i - 1].isalnum()
        ):
            last = i
        i += 1
    if last is None:
        return None
    return sql[last + 8 :].strip()


def order_by_column_names(order_clause: str) -> list[str]:
    """Best-effort: pull bare identifiers out of an ORDER BY clause."""
    names = []
    for part in order_clause.split(","):
        token = part.strip().split()[0] if part.strip() else ""
        token = token.split(".")[-1].strip('"`[]')
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", token):
            names.append(token)
    return names


# ----------------------------------------------------------------------- facts


def is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def fmt(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else repr(v)
    return str(v)


def column_facts(cols: list[str], rows: list[tuple]) -> list[str]:
    """Deterministic per-column facts. The label of an extreme row is the first column."""
    out: list[str] = []
    if not rows:
        return out
    for idx, col in enumerate(cols):
        vals = [r[idx] for r in rows]
        non_null = [v for v in vals if v is not None]
        if not non_null:
            out.append(f"{col}: all NULL")
            continue
        if all(is_number(v) for v in non_null):
            lo = min(non_null)
            hi = max(non_null)
            lo_row = next(r for r in rows if r[idx] == lo)
            hi_row = next(r for r in rows if r[idx] == hi)
            total = sum(non_null)
            line = (
                f"{col}: min={fmt(lo)}, max={fmt(hi)}, "
                f"sum={fmt(total)}, avg={fmt(total / len(non_null))}"
            )
            if idx != 0:
                line += f"; lowest at {cols[0]}={fmt(lo_row[0])}, highest at {cols[0]}={fmt(hi_row[0])}"
            out.append(line)
        else:
            distinct = {fmt(v) for v in non_null}
            line = f"{col}: {len(distinct)} distinct, first={fmt(vals[0])}, last={fmt(vals[-1])}"
            if len(distinct) <= MAX_DISTINCT_FOR_DISTRIBUTION:
                counts: dict[str, int] = {}
                for v in non_null:
                    counts[fmt(v)] = counts.get(fmt(v), 0) + 1
                ordered = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
                line += " | distribution: " + ", ".join(f"{k} ({n})" for k, n in ordered)
            out.append(line)
    return out


def render_row(cols: list[str], row: tuple) -> str:
    return " | ".join(f"{c}={fmt(v)}" for c, v in zip(cols, row))


# ------------------------------------------------------------------------ main


def analyse(q: dict, cap: int) -> dict:
    db_key = next((k for k in DB_FILES if k in q.get("database", "").lower()), None)
    if db_key is None:
        return {"id": q["id"], "error": f"unknown database: {q.get('database')!r}"}

    sql = strip_trailing_semicolon(q["gold_sql"])
    con = sqlite3.connect(DB_FILES[db_key])
    try:
        cur = con.execute(sql)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    except Exception as exc:  # noqa: BLE001 - reported, not raised
        return {"id": q["id"], "error": f"SQL failed: {exc}"}
    finally:
        con.close()

    total = len(rows)
    over_cap = total > cap
    window = rows[:cap] if over_cap else rows

    flags: list[str] = []
    order_clause = top_level_order_by(sql)
    if over_cap:
        if order_clause is None:
            flags.append(
                "NO TOP-LEVEL ORDER BY — the first %d rows are an engine accident, "
                "not a fact. Amend gold_sql with a deterministic total order before "
                "computing window facts." % cap
            )
        else:
            names = order_by_column_names(order_clause)
            missing = [n for n in names if n not in cols]
            idxs = [cols.index(n) for n in names if n in cols]
            if q["id"] in ORDERING_VERIFIED_UNIQUE:
                pass  # ordering key verified unique by hand — see the constant above
            elif not names or missing:
                # Comparing on a SUBSET of the ordering key invents ties that do not
                # exist. Report as unverified rather than guessing.
                flags.append(
                    "ORDER BY references column(s) absent from the output (%s) — the "
                    "tie-break cannot be verified mechanically; needs a human read."
                    % (", ".join(missing) if missing else "unparsed")
                )
            else:
                key_last_in = tuple(rows[cap - 1][i] for i in idxs)
                key_first_out = tuple(rows[cap][i] for i in idxs)
                if key_last_in == key_first_out:
                    flags.append(
                        "TIE ACROSS THE CAP BOUNDARY on (%s) — rows %d and %d share the "
                        "same ordering key, so the window edge is unstable."
                        % (", ".join(names), cap, cap + 1)
                    )

    block: list[str] = []
    if over_cap:
        block.append(f"Window facts (first {cap} of {total} rows, in query order):")
        block.append(f"- window covers row 1 to row {cap}")
        block.append(f"- first row: {render_row(cols, window[0])}")
        block.append(f"- last row of the window: {render_row(cols, window[-1])}")
        block += [f"- {line}" for line in column_facts(cols, window)]
        block.append("")
        block.append(f"Population facts (all {total} rows):")
        block.append(f"- last row of the full result: {render_row(cols, rows[-1])}")
        block += [f"- {line}" for line in column_facts(cols, rows)]
    else:
        block.append(
            f"Result facts (all {total} rows — the model saw the complete result):"
        )
        block.append(f"- first row: {render_row(cols, rows[0])}")
        block.append(f"- last row: {render_row(cols, rows[-1])}")
        block += [f"- {line}" for line in column_facts(cols, rows)]

    return {
        "id": q["id"],
        "database": db_key,
        "total_rows": total,
        "over_cap": over_cap,
        "flags": flags,
        "verification_facts": "\n".join(block),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--cap", type=int, default=200)
    ap.add_argument("--write", action="store_true", help="write the field back into the datasets")
    ap.add_argument("--show", default=None, help="print the full block for one question id")
    args = ap.parse_args()

    problems: list[dict] = []
    for path in DATASETS:
        questions = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        results = [analyse(q, args.cap) for q in questions]

        n_over = sum(1 for r in results if r.get("over_cap"))
        n_err = sum(1 for r in results if r.get("error"))
        print(f"\n=== {path.name} — {len(questions)} questions ===")
        print(f"    over cap ({args.cap}): {n_over}    under cap: {len(questions) - n_over - n_err}    errors: {n_err}")

        for r in results:
            if r.get("error"):
                print(f"    !! {r['id']}: {r['error']}")
            for f in r.get("flags", []):
                print(f"    [!] {r['id']} ({r['total_rows']} rows): {f}")
                problems.append(r)
            if args.show and r["id"] == args.show:
                print("\n" + r["verification_facts"] + "\n")

        if args.write:
            by_id = {r["id"]: r for r in results}
            out = []
            for q in questions:
                r = by_id[q["id"]]
                if r.get("error") or r.get("flags"):
                    out.append(json.dumps(q, ensure_ascii=False))
                    continue
                q["verification_facts"] = r["verification_facts"]
                out.append(json.dumps(q, ensure_ascii=False))
            path.write_text("\n".join(out) + "\n", encoding="utf-8")
            print("    -> written (questions with flags left untouched)")

    print(f"\nQuestions needing a human decision before their window is defined: {len(problems)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
