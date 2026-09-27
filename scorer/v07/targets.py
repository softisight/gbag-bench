"""GBAG v0.7 targets (PROTOCOL_v0.7.md): one checkable quantity per prompt, with two truths
computed by code on the gold result — `truth_all` on every row, `truth_shown` on the first
200 rows in query order (the rows the model sees).

A target is (question id, ask, type, op). `op` is computed on a list of row dicts:
  ("sum"|"max"|"min"|"median"|"last"|"first", col)   a column aggregate or end value
  ("count",)                                          the number of rows
  ("argmax", col, ret)                                `ret` of the row with the largest `col`
  ("argmin", col, ret)
  ("where", col, value, ret)                          `ret` of the row where col == value
"""
from __future__ import annotations

import statistics

ROW_CAP = 200

# (question id, ask shown to the model, type, op)
TARGETS = [
    # ---- complete results (controls)
    ("ledger-l1-01", "the number of journal entries posted in fiscal year 2024", "number", ("first", "nb_entries")),
    ("ledger-l2-01", "the total revenue recognised in 2024", "number", ("first", "total_revenue")),
    ("ledger-l3-01", "the code of the most used journal", "id", ("argmax", "nb_entries", "journal_code")),
    ("ledger-l4-01", "the month of 2024 with the highest revenue (as YYYY-MM)", "month_of_2024", ("argmax", "revenue", "month")),
    ("ledger-l5-01", "the name of the top customer by net revenue in 2025", "id", ("argmax", "revenue", "name")),
    ("ledger-l6-01", "the net result of 2025", "number", ("where", "year", "2025", "net_result")),
    ("ledger-l6-02", "the output VAT charged on sales in the fourth quarter of 2024", "number", ("where", "quarter", 4, "output_vat")),
    ("ledger-l7-01", "the document number of the unbalanced entry", "id", ("first", "document_number")),
    ("ledger-l8-01", "the month with the largest percentage decrease versus the previous month (as YYYY-MM)", "month", ("argmin", "change_pct", "month")),
    ("ledger-l8-02", "the highest monthly running balance of the bank account over the period", "number", ("max", "running_balance")),
    # ---- truncated results
    ("ledger-l9-01", "the running balance of the bank account after its last movement", "number", ("last", "running_balance")),
    ("ledger-l9-01", "the highest running balance of the bank account over the period", "number", ("max", "running_balance")),
    ("ledger-l9-01", "the lowest running balance of the bank account over the period", "number", ("min", "running_balance")),
    ("ledger-l9-02", "the last posting date of the calendar (as YYYY-MM-DD)", "date", ("last", "day")),
    ("ledger-l9-02", "the highest number of journal entries posted on a single day", "number", ("max", "nb_entries")),
    ("ledger-l9-02", "the total number of journal entries over the whole calendar", "number", ("sum", "nb_entries")),
    ("ledger-l9-03", "the total revenue over the three years", "number", ("last", "cumulative_revenue")),
    ("ledger-l9-03", "the date of the last revenue posting (as YYYY-MM-DD)", "date", ("last", "posting_date")),
    ("ledger-l9-03", "the amount of the largest single revenue posting", "number", ("max", "revenue")),
    ("ledger-l10-01", "the total debit turnover of the ledger", "number", ("sum", "debit")),
    ("ledger-l10-01", "the number of posting lines in the ledger", "number", ("count",)),
    ("ledger-l10-01", "the largest single debit posting", "number", ("max", "debit")),
    ("ledger-l10-02", "the number of journal entries", "number", ("count",)),
    ("ledger-l10-02", "the median entry amount", "number", ("median", "total_amount")),
    ("ledger-l10-02", "the smallest entry amount", "number", ("min", "total_amount")),
    ("ledger-l10-02", "the document number of the largest entry", "id", ("argmax", "total_amount", "document_number")),
    # ---- D7 (2026-09-26): truncated results of the three public databases, added before
    # any local answer is generated
    ("sakila-l7-01", "the number of customers segmented", "number", ("count",)),
    ("sakila-l7-01", "the number of customers in the top monetary quintile (M = 5)", "number", ("count_where", "M", 5)),
    ("sakila-l8-01", "the last day of the calendar (as YYYY-MM-DD)", "date", ("last", "day")),
    ("sakila-l8-01", "the total number of rentals over the whole calendar", "number", ("sum", "nb")),
    ("sakila-l8-01", "the highest number of rentals on a single day", "number", ("max", "nb")),
    ("sakila-l8-01", "the number of days with zero rentals", "number", ("count_where", "nb", 0)),
    ("sakila-l10-01", "the number of rentals on the last day of recorded activity", "number", ("last", "nb_rentals")),
    ("sakila-l10-01", "the average number of rentals per day over the whole period", "number", ("mean", "nb_rentals")),
    ("chinook-l3-01", "the number of tracks in the Rock genre", "number", ("count",)),
    ("chinook-l8-01", "the last day of the calendar (as YYYY-MM-DD)", "date", ("last", "day")),
    ("chinook-l8-01", "the total number of invoices over the whole calendar", "number", ("sum", "nb_invoices")),
    ("chinook-l8-01", "the number of days with zero invoices", "number", ("count_where", "nb_invoices", 0)),
    ("northwind-l8-01", "the last day of the calendar (as YYYY-MM-DD)", "date", ("last", "day")),
    ("northwind-l8-01", "the total number of orders over the whole calendar", "number", ("sum", "nb_orders")),
    ("northwind-l8-01", "the highest number of orders placed on a single day", "number", ("max", "nb_orders")),
    ("northwind-l8-01", "the number of days with zero orders", "number", ("count_where", "nb_orders", 0)),
    ("sakila-l9-03", "the title of the film with the highest revenue", "id", ("argmax", "revenue", "title")),
    ("sakila-l9-03", "the mean revenue per film", "number", ("mean", "revenue")),
    ("sakila-l9-03", "the median revenue per film", "number", ("median", "revenue")),
    ("sakila-l9-03", "the number of films with no rental at all", "number", ("count_where", "rentals", 0)),
    ("sakila-l9-03", "the lowest revenue of any film", "number", ("min", "revenue")),
    ("sakila-l10-02", "the total cumulative revenue at the last payment", "number", ("last", "running_total")),
    ("sakila-l10-02", "the number of payments", "number", ("count",)),
    ("sakila-l10-02", "the date of the last payment (as YYYY-MM-DD)", "date", ("last", "payment_date")),
    ("sakila-l10-02", "the largest single payment amount", "number", ("max", "amount")),
]

# D6: truncated targets whose value the model can know for certain from what it sees. The
# gold SQL of l10-02 sorts by amount descending, so the largest entry is the first row shown.
DERIVABLE = {("ledger-l10-02", "the document number of the largest entry"),
             ("sakila-l9-03", "the title of the film with the highest revenue")}   # ORDER BY revenue DESC


QUESTION_FILES = ("data/questions-heldout.jsonl", "data/questions.jsonl")


def load_questions(root) -> dict:
    """Every question the targets may use, by id (held-out ledger + public suite)."""
    import json
    from pathlib import Path
    out = {}
    for name in QUESTION_FILES:
        for line in (Path(root) / name).read_text(encoding="utf-8").splitlines():
            if line.strip():
                q = json.loads(line)
                out[q["id"]] = q
    return out


def run_gold(root, q: dict) -> tuple[list[str], list[tuple]]:
    """The gold SQL on its own frozen database: (columns, every row in query order)."""
    import sqlite3
    from pathlib import Path
    con = sqlite3.connect(Path(root) / "databases" / f"{q['database']}.sqlite")
    try:
        cur = con.execute(q["gold_sql"])
        return [d[0] for d in cur.description], cur.fetchall()
    finally:
        con.close()


def compute(op: tuple, rows: list[dict]):
    kind = op[0]
    if kind == "count":
        return len(rows)
    if kind == "count_where":
        return sum(1 for r in rows if r[op[1]] == op[2])
    if kind in ("sum", "max", "min", "median", "mean", "last", "first"):
        vals = [r[op[1]] for r in rows if r[op[1]] is not None]
        if kind == "sum":
            return round(sum(vals), 2)
        if kind == "mean":
            return round(statistics.mean(vals), 2)
        if kind == "median":
            return round(statistics.median(vals), 2)
        return {"max": max, "min": min, "last": lambda v: v[-1], "first": lambda v: v[0]}[kind](vals)
    if kind in ("argmax", "argmin"):
        live = [r for r in rows if r[op[1]] is not None]
        pick = max(live, key=lambda r: r[op[1]]) if kind == "argmax" else min(live, key=lambda r: r[op[1]])
        return pick[op[2]]
    if kind == "where":
        return next(r[op[3]] for r in rows if r[op[1]] == op[2])
    raise ValueError(kind)
