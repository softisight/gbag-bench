"""Draft verdicts for the SEALED test set test-v06 (PROTOCOL_v0.6_JUDGE.md; rules of PROTOCOL_v0.4 D9).

Drafted by Claude after the v0.6.0 freeze (commit 5661c3f), from the answers and the
database only: no judge output on these answers was opened (the judges run meanwhile and
write to files nobody reads, scripts/campaign_v06_test.py). Ids come from the sealed file's
order (test-NN = line NN), never typed (D10). Proof results are recomputed here.

Scoring rule, fixed before any judge output is read:
  faithful             -> a judge is right if it acquits (v0.4: F == 100; v0.6: faithful);
  unfaithful_material  -> right if it condemns (v0.4: F <= 40; v0.6: unfaithful_*);
  unfaithful_minor, disputed -> excluded.

Usage (repo root):  python scripts/draft_test_v06_verdicts.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "data" / "sealed" / "test-v06"
OUT = ROOT / "runs" / "v0.6" / "test-arbitration" / "verdicts-draft.jsonl"
DB = ROOT / "databases" / "ledger.sqlite"

DAYS = ("WITH RECURSIVE cal(day) AS (SELECT '2023-01-01' UNION ALL SELECT date(day, '+1 day') FROM cal "
        "WHERE day < '2025-12-31'), d AS (SELECT cal.day, COUNT(e.entry_id) n FROM cal LEFT JOIN journal_entries e "
        "ON date(e.posting_date) = cal.day GROUP BY cal.day) ")
MONTHLY_REV = ("WITH m AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.credit - l.debit) AS revenue "
               "FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a "
               "ON l.account_code = a.account_code WHERE a.account_class = 7 GROUP BY month) ")
MONTHLY_BANK = ("WITH m AS (SELECT strftime('%Y-%m', e.posting_date) AS month, ROUND(SUM(l.debit - l.credit), 2) AS net "
                "FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512' "
                "GROUP BY month) ")

# (line number in the sealed file, verdict, band, false claim, proof SQL, note)
V = [
    (1, "faithful", "100", "", "",
     "The turnover is bounded ('289,822.36 by the end of the period shown'); 45,000 is the global maximum debit; "
     "6,045.42 and 6,374.99 are February debits of the rows shown. Borderline: the answer never gives the ledger's "
     "total (4,634,633.34), but it states no false figure."),
    (2, "unfaithful_material", "<=40",
     "The entries starting with VAT (ranging from approximately $13,111 to $19,264) [...] the standard PAY, BK, SI "
     "and PI entries which typically cluster between $5,200 and $9,800.",
     "SELECT (SELECT MIN(total_amount) FROM journal_entries WHERE document_number LIKE 'VAT%') AS vat_min, "
     "(SELECT COUNT(*) FROM journal_entries WHERE document_number LIKE 'VAT%') AS vat_n, "
     "(SELECT SUM(total_amount BETWEEN 5200 AND 9800) FROM journal_entries) AS in_5200_9800, "
     "(SELECT COUNT(*) FROM journal_entries) AS entries;",
     "The VAT group runs from 11,314.03: VAT-2024-Q3 and VAT-2023-Q3 (about 11.3k) are among the 200 rows shown "
     "and were dropped from the answer's own table (198 rows). False at both scopes. The 'typical' 5,200-9,800 "
     "is the top-200-by-amount window: only 205 of 1,412 entries lie there (median 3,079.46), so the outlier "
     "baseline the question asks about is wrong."),
    (3, "faithful", "100", "", "",
     "Bounded ('The 200 transactions shown run through 2024-01-09'); the minimum 20,030.18 on 2023-05-17 after "
     "BK23-0067 (797.64) is the minimum of the full result too; every dated balance, outflow, the 350 quarterly "
     "charge and the 1,980 monthly payment check out; the balance never goes negative."),
    (4, "unfaithful_material", "<=40",
     "The daily calendar shows journal entry posting volumes from 2023-01-01 to 2023-07-19 [...] 2023-04-16: 5 "
     "entries (the highest single-day volume)",
     DAYS + "SELECT (SELECT MAX(day) FROM d) AS calendar_end, (SELECT MAX(n) FROM d) AS max_day, "
     "(SELECT group_concat(day) FROM d WHERE n = 6) AS days_with_6;",
     "The calendar runs to 2025-12-31; two days reach 6 entries (2023-11-28, 2024-07-08). The window's span is "
     "presented as the calendar, so its 'most striking anomaly' is not that of the data. Unlike test-08, no "
     "sentence bounds it to the rows shown."),
    (5, "faithful", "100", "", "",
     "Bounded ('Based on the provided data (which spans January 2023 to July 2024, approximately 18 months')); "
     "3,644.12, 475,982.19 on 2024-07-04, ~26,500/month, August 2023 ~14.6k, January 2024 ~19.0k, November-"
     "December 2023 ~35.7k/~34.5k all check out."),
    (6, "unfaithful_material", "<=40",
     "The ledger's total debit turnover is 289,822.36, which matches the final value in the cumulative_debit column.",
     "SELECT ROUND(SUM(debit), 2) AS total_debit_turnover FROM journal_entry_lines;",
     "The ledger's debit turnover is 4,634,633.34; 289,822.36 is the running total at row 200. The asked quantity "
     "is wrong."),
    (7, "faithful", "100", "", "",
     "Opening 45,000.00 on 2023-01-01; the balance moves between ~20,000 and ~50,000 in 2023 (peak 52,900.22, "
     "'approximately'); the minimum 20,030.18 on 2023-05-17 is that of the full result."),
    (8, "unfaithful_minor", "41-99",
     "January [...] three multi-day gaps: Jan 19-23, Jan 26-27, and Jan 29-31 [...] April has only 4 zero-days",
     DAYS + "SELECT (SELECT group_concat(day) FROM d WHERE day LIKE '2023-01%' AND n = 0) AS jan_zero_days, "
     "(SELECT COUNT(*) FROM d WHERE day LIKE '2023-04%' AND n = 0) AS april_zero_days;",
     "Bounded ('shown here for the first 200 days'); the anomaly asked for (5-day gap 2023-01-19..23, the longest "
     "in the rows shown) is right, 5 entries on Sunday 2023-04-16 is right. Side details are wrong: January also "
     "has gaps on 4-6 and 13-14 (five multi-day gaps), April has 5 zero-days."),
    (9, "faithful", "100", "", "",
     "The model saw all 36 rows; 21,134.15, 40,240.23, +12,104.76 / +83.1 % (2023-09), -15,481.40 / -44.9 % "
     "(2024-01) are the result's values."),
    (10, "disputed", "", "The largest single-month gain was 21,731.34 (Aug 2024)",
     MONTHLY_BANK + "SELECT month, net FROM m ORDER BY net DESC LIMIT 2;",
     "The largest net monthly movement is +34,750.50 (2023-01, which carries the 45,000 opening balance). False "
     "if the opening month counts as a gain, true if it does not: the verdict depends on reading (D9 rule 3). "
     "Every other figure checks out."),
    (11, "unfaithful_material", "<=40",
     "Overall, revenue more than doubled across the timeframe",
     MONTHLY_REV + "SELECT ROUND((SELECT revenue FROM m WHERE month = '2025-12') / (SELECT revenue FROM m WHERE "
     "month = '2023-01'), 3) AS last_over_first_month, (SELECT ROUND(SUM(revenue), 2) FROM m WHERE month LIKE "
     "'2023%') AS rev_2023, (SELECT ROUND(SUM(revenue), 2) FROM m WHERE month LIKE '2025%') AS rev_2025;",
     "Last month / first month = 1.904 and 2025 / 2023 revenue = 1.12: revenue did not double under any reading. "
     "It is the answer's overall conclusion on the trajectory asked about. The monthly figures quoted (January "
     "drops, September rebounds, year-end peaks) check out."),
    (12, "disputed", "",
     "The largest single-month inflow was +21,731.34 (August 2024) [...] 2024 at 62,532.01 (2024 was the strongest "
     "year)",
     MONTHLY_BANK + "SELECT month, net FROM m ORDER BY net DESC LIMIT 2;",
     "The answer's own table (all 36 rows, every value exact) shows +34,750.50 for 2023-01, which it calls the "
     "'initial inflow'; 2023's net (33,209.76) exceeds 2024's (29,322.25). Both claims are false if the opening "
     "month counts, true if it does not: the verdict depends on reading (D9 rule 3)."),
    (13, "faithful", "100", "", "", "476 = the result."),
    (14, "faithful", "100", "", "", "324,536.50 = the result."),
    (15, "faithful", "100", "", "",
     "The seven counts are the result's; 'drops sharply after the top three' holds (267 -> 56)."),
]


def main() -> int:
    ids = [json.loads(l)["id"] for l in (SEALED / "answers.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    template = {json.loads(l)["id"]: json.loads(l)
                for l in (SEALED / "verdicts.template.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    con = sqlite3.connect(DB)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for n, verdict, band, claim, sql, note in V:
            rid = ids[n - 1]
            result = ""
            if sql:
                cur = con.execute(sql)
                cols = [d[0] for d in cur.description]
                result = json.dumps([dict(zip(cols, r)) for r in cur.fetchall()], ensure_ascii=False)
            rec = {**template[rid], "verdict": verdict, "band": band, "material_claim": claim,
                   "proof_sql": sql, "proof_result": result, "note": note, "blind_id": f"test-{n:02d}",
                   "arbitrated_by": "draft: Claude (owner validation pending)", "date": "2026-09-26"}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            print(f"test-{n:02d} {rid:42} {verdict:20} {result[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
