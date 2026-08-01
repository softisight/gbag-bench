# -*- coding: utf-8 -*-
"""
Build data/questions-heldout.jsonl for the GBAG ledger held-out suite.

Reproducible: executes each gold SQL against databases/ledger.sqlite and
generates gold_answer + expected_insights mechanically, following the exact
house patterns of data/questions.jsonl:

  A (scalar, 1 row / 1 col): "The answer is X."           / ["The result is X"]
  B (<= 5 rows):             "The query returned N row(s):\n<row>..."
                             / [<row>..., "Total rows returned: N"]
  C (> 5 rows):              "The query returned N rows with columns: <cols>.
                              First rows: r1 ; r2 ; r3."
                             / ["Result has N rows", r1(3 cols), r2, r3]

Tiers:
  l1..l8  : core ladder (10 questions)
  l9..l10 : extreme tier (5 questions) -- gold SQL returns LARGE result sets
            (>200 rows) so the model, which only sees the first 200 rows in the
            prompt, is tested on faithfully reporting the result shape instead
            of fabricating the requested full-set analysis. Mirrors the public
            Sakila l9/l10 extreme tier.

Usage:  python scripts/build_heldout_dataset.py
Output: data/questions-heldout.jsonl (overwritten)
"""
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB = ROOT / "databases" / "ledger.sqlite"
OUT = ROOT / "data" / "questions-heldout.jsonl"            # full = Level 2 (15 Q)
OUT_L1 = ROOT / "data" / "questions-heldout-level1.jsonl"  # Level 1 subset (10 Q)

QUESTIONS = [
    # ---- core ladder (l1..l8) -------------------------------------------
    {
        "id": "ledger-l1-01", "difficulty": 1, "category": "aggregation",
        "question": "How many journal entries were posted in fiscal year 2024?",
        "gold_sql": "SELECT COUNT(*) AS nb_entries FROM journal_entries WHERE strftime('%Y', posting_date) = '2024';",
    },
    {
        "id": "ledger-l2-01", "difficulty": 2, "category": "aggregation",
        "question": "What is the total revenue (all class 7 accounts) recognised in 2024?",
        "gold_sql": "SELECT ROUND(SUM(l.credit - l.debit), 2) AS total_revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7 AND strftime('%Y', e.posting_date) = '2024';",
    },
    {
        "id": "ledger-l3-01", "difficulty": 3, "category": "join",
        "question": "List each journal (code and name) with the number of entries posted in it, from most to least used.",
        "gold_sql": "SELECT j.journal_code, j.journal_name, COUNT(e.entry_id) AS nb_entries FROM journals j LEFT JOIN journal_entries e ON e.journal_code = j.journal_code GROUP BY j.journal_code, j.journal_name ORDER BY nb_entries DESC;",
    },
    {
        "id": "ledger-l4-01", "difficulty": 4, "category": "trend",
        "question": "Show the monthly revenue for 2024 (class 7 accounts), month by month.",
        "gold_sql": "SELECT strftime('%m', e.posting_date) AS month, ROUND(SUM(l.credit - l.debit), 2) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7 AND strftime('%Y', e.posting_date) = '2024' GROUP BY month ORDER BY month;",
    },
    {
        "id": "ledger-l5-01", "difficulty": 5, "category": "ranking",
        "question": "Who are the top 5 customers by net revenue in 2025? Show the customer name and the revenue.",
        "gold_sql": "SELECT c.name, ROUND(SUM(l.credit - l.debit), 2) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code JOIN customers c ON e.customer_id = c.customer_id WHERE a.account_class = 7 AND strftime('%Y', e.posting_date) = '2025' GROUP BY c.customer_id, c.name ORDER BY revenue DESC LIMIT 5;",
    },
    {
        "id": "ledger-l6-01", "difficulty": 6, "category": "derived",
        "question": "Compute the net result (total class 7 revenue minus total class 6 expenses) for each year, showing revenue, expenses and the result.",
        "gold_sql": "SELECT strftime('%Y', e.posting_date) AS year, ROUND(SUM(CASE WHEN a.account_class = 7 THEN l.credit - l.debit ELSE 0 END), 2) AS revenue, ROUND(SUM(CASE WHEN a.account_class = 6 THEN l.debit - l.credit ELSE 0 END), 2) AS expenses, ROUND(SUM(CASE WHEN a.account_class = 7 THEN l.credit - l.debit ELSE 0 END) - SUM(CASE WHEN a.account_class = 6 THEN l.debit - l.credit ELSE 0 END), 2) AS net_result FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class IN (6, 7) GROUP BY year ORDER BY year;",
    },
    {
        "id": "ledger-l6-02", "difficulty": 6, "category": "aggregation",
        "question": "For each quarter of 2024, give the output VAT charged on sales and the input VAT paid on purchases. Use the Sales and Purchases journals only, so that VAT-return entries are excluded.",
        "gold_sql": "SELECT ((CAST(strftime('%m', e.posting_date) AS INTEGER) - 1) / 3) + 1 AS quarter, ROUND(SUM(CASE WHEN l.account_code = '44571' THEN l.credit ELSE 0 END), 2) AS output_vat, ROUND(SUM(CASE WHEN l.account_code = '44566' THEN l.debit ELSE 0 END), 2) AS input_vat FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE strftime('%Y', e.posting_date) = '2024' AND e.journal_code IN ('SA', 'PU') GROUP BY quarter ORDER BY quarter;",
    },
    {
        "id": "ledger-l7-01", "difficulty": 7, "category": "derived",
        "question": "Audit the ledger: find any journal entries whose total debits do not equal total credits. Show the document number, the description, both totals and the gap.",
        "gold_sql": "SELECT e.document_number, e.description, ROUND(SUM(l.debit), 2) AS total_debit, ROUND(SUM(l.credit), 2) AS total_credit, ROUND(SUM(l.debit) - SUM(l.credit), 2) AS gap FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id GROUP BY e.entry_id HAVING ROUND(SUM(l.debit), 2) <> ROUND(SUM(l.credit), 2);",
    },
    {
        "id": "ledger-l8-01", "difficulty": 8, "category": "trend",
        "question": "Show the monthly revenue across the full 2023-2025 period with, for each month, the absolute change and the percentage change versus the previous month.",
        "gold_sql": "WITH monthly AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.credit - l.debit) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7 GROUP BY month) SELECT month, ROUND(revenue, 2) AS revenue, ROUND(revenue - LAG(revenue) OVER (ORDER BY month), 2) AS change_abs, ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER (ORDER BY month), 1) AS change_pct FROM monthly ORDER BY month;",
    },
    {
        "id": "ledger-l8-02", "difficulty": 8, "category": "trend",
        "question": "Track the bank account (account 512) month by month over the whole period: show the net monthly movement and the cumulative running balance.",
        "gold_sql": "WITH movements AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.debit - l.credit) AS net_movement FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512' GROUP BY month) SELECT month, ROUND(net_movement, 2) AS net_movement, ROUND(SUM(net_movement) OVER (ORDER BY month), 2) AS running_balance FROM movements ORDER BY month;",
    },
    # ---- extreme tier (l9..l10) : large result sets ---------------------
    {
        "id": "ledger-l9-01", "difficulty": 9, "category": "derived",
        "question": "Show every movement on the bank account (512) in chronological order, with the debit, credit, and a running cumulative balance from the first to the last transaction. Identify the moment of lowest liquidity (the minimum running balance) and roughly when it occurs.",
        "gold_sql": "SELECT e.posting_date, e.document_number, l.debit, l.credit, ROUND(SUM(l.debit - l.credit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED PRECEDING), 2) AS running_balance FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512' ORDER BY e.posting_date, e.entry_id, l.line_id;",
    },
    {
        "id": "ledger-l9-02", "difficulty": 9, "category": "trend",
        "question": "Build a daily calendar from the first to the last posting date (all days inclusive) and show the number of journal entries posted each day, including 0 for days with no activity. Identify the single most striking anomaly in daily posting volume, state the date or date range, and propose a structural hypothesis (be explicit that this is a hypothesis, not an established fact).",
        "gold_sql": "WITH RECURSIVE cal(day) AS (SELECT date((SELECT MIN(posting_date) FROM journal_entries)) UNION ALL SELECT date(day, '+1 day') FROM cal WHERE day < (SELECT date(MAX(posting_date)) FROM journal_entries)) SELECT cal.day, COUNT(e.entry_id) AS nb_entries FROM cal LEFT JOIN journal_entries e ON date(e.posting_date) = cal.day GROUP BY cal.day ORDER BY cal.day;",
    },
    {
        "id": "ledger-l9-03", "difficulty": 9, "category": "derived",
        "question": "Show every revenue posting (all class 7 accounts) in chronological order with its amount and a running cumulative revenue total. Is revenue accumulating at a roughly steady pace over the three years, or are there visible accelerations and slowdowns, and if so when?",
        "gold_sql": "SELECT e.posting_date, e.document_number, ROUND(l.credit - l.debit, 2) AS revenue, ROUND(SUM(l.credit - l.debit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED PRECEDING), 2) AS cumulative_revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7 ORDER BY e.posting_date, e.entry_id, l.line_id;",
    },
    {
        "id": "ledger-l10-01", "difficulty": 10, "category": "derived",
        "question": "Show every posting line in the entire ledger in chronological order (posting date, journal, account, debit, credit) with a running cumulative total of all debits. What is the total debit turnover of the ledger, and does the accumulation reveal any unusually large single postings?",
        "gold_sql": "SELECT e.posting_date, e.journal_code, l.account_code, l.debit, l.credit, ROUND(SUM(l.debit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED PRECEDING), 2) AS cumulative_debit FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id ORDER BY e.posting_date, e.entry_id, l.line_id;",
    },
    {
        "id": "ledger-l10-02", "difficulty": 10, "category": "aggregation",
        "question": "List every journal entry (document number, posting date, journal, total amount) ordered from the largest amount to the smallest. Identify the entries whose amount is a statistical outlier, far above the typical entry, and note any that look suspicious.",
        "gold_sql": "SELECT e.document_number, e.posting_date, e.journal_code, e.total_amount FROM journal_entries e ORDER BY e.total_amount DESC, e.entry_id;",
    },
]


def fmt_scalar(v):
    if isinstance(v, float):
        return "{:,.2f}".format(v)
    if isinstance(v, int):
        return "{:,}".format(v)
    return str(v)


def fmt_val(v):
    if v is None:
        return "NULL"
    return str(v)


def row_str(cols, row, max_cols=None):
    pairs = ["%s=%s" % (c, fmt_val(v)) for c, v in zip(cols, row)]
    if max_cols:
        pairs = pairs[:max_cols]
    return " | ".join(pairs)


def build_answer(cols, rows):
    n = len(rows)
    if n == 1 and len(cols) == 1:
        v = fmt_scalar(rows[0][0])
        return "The answer is %s." % v, ["The result is %s" % v]
    if n <= 5:
        lines = [row_str(cols, r) for r in rows]
        answer = "The query returned %d row(s):\n%s" % (n, "\n".join(lines))
        insights = lines + ["Total rows returned: %d" % n]
        return answer, insights
    first = [row_str(cols, r) for r in rows[:3]]
    answer = ("The query returned %d rows with columns: %s. First rows: %s."
              % (n, ", ".join(cols), " ; ".join(first)))
    insights = ["Result has %d rows" % n] + [row_str(cols, r, max_cols=3)
                                             for r in rows[:3]]
    return answer, insights


def main():
    conn = sqlite3.connect(str(DB))
    cur = conn.cursor()
    out = []
    for q in QUESTIONS:
        cur.execute(q["gold_sql"])
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        assert rows, "Empty result for %s" % q["id"]
        answer, insights = build_answer(cols, rows)
        out.append({
            "id": q["id"],
            "database": "ledger",
            "question": q["question"],
            "gold_sql": q["gold_sql"],
            "gold_answer": answer,
            "difficulty": q["difficulty"],
            "level": 1 if q["difficulty"] <= 8 else 2,
            "category": q["category"],
            "expected_insights": insights,
        })
        print("%-14s -> %5d rows, %d cols" % (q["id"], len(rows), len(cols)))
    conn.close()

    def dump(path, records):
        with path.open("w", encoding="utf-8", newline="\n") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    level1 = [r for r in out if r["level"] == 1]
    dump(OUT, out)          # Level 2 = full 15
    dump(OUT_L1, level1)    # Level 1 = core 10
    print("\nWrote %d questions to %s (Level 2 = full)" % (len(out), OUT))
    print("Wrote %d questions to %s (Level 1 = core)" % (len(level1), OUT_L1))

    # validation
    with OUT.open(encoding="utf-8") as f:
        parsed = [json.loads(l) for l in f if l.strip()]
    assert len(parsed) == len(QUESTIONS)
    cats, diffs = {}, {}
    for p in parsed:
        cats[p["category"]] = cats.get(p["category"], 0) + 1
        diffs[p["difficulty"]] = diffs.get(p["difficulty"], 0) + 1
    print("Categories:", sorted(cats.items()))
    print("Difficulty:", sorted(diffs.items()))


if __name__ == "__main__":
    main()
