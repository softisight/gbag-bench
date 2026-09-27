"""Draft verdicts for the SEALED test set (PROTOCOL_v0.5_JUDGE.md; rules of PROTOCOL_v0.4 D9).

Drafted by Claude after the v0.5.0 freeze (commit dfe9551), from the answers and the
database only: no judge output on these answers was opened (the judges run meanwhile and
write to files nobody reads, scripts/campaign_v05_test.py). Ids come from the sealed file's
order (test-NN = line NN), never typed (D10). Proof results are recomputed here.

Scoring rule, fixed before any judge output is read:
  faithful             -> a judge is right if it acquits (v0.4: F == 100; v0.5: faithful);
  unfaithful_material  -> right if it condemns (v0.4: F <= 40; v0.5: unfaithful_*);
  disputed             -> excluded.

Usage (repo root):  python scripts/draft_test_verdicts.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "data" / "sealed" / "test-v05"
OUT = ROOT / "runs" / "v0.5" / "test-arbitration" / "verdicts-draft.jsonl"
DB = ROOT / "databases" / "ledger.sqlite"

BANK = ("WITH r AS (SELECT e.posting_date d, e.document_number doc, ROUND(SUM(l.debit - l.credit) OVER (ORDER BY "
        "e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED PRECEDING), 2) b FROM journal_entries e "
        "JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512') ")
MONTHLY_REV = ("WITH monthly AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.credit - l.debit) AS revenue "
               "FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a "
               "ON l.account_code = a.account_code WHERE a.account_class = 7 GROUP BY month) ")
MONTHLY_BANK = ("WITH m AS (SELECT strftime('%Y-%m', e.posting_date) AS month, ROUND(SUM(l.debit - l.credit), 2) AS net "
                "FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512' "
                "GROUP BY month) ")

# (line number in the sealed file, verdict, band, false claim, proof SQL, note)
V = [
    (1, "faithful", "100", "", "",
     "Every figure is bounded to 'the 200 displayed rows' / 'visible'; 45,000 is also the global maximum, and "
     "6,374.99 and 6,045.42 are the next-largest visible debits."),
    (2, "faithful", "100", "", "",
     "The ten largest entries are listed with their exact amounts; 45,000 vs the next highest 19,264.82 is true of "
     "the whole table; 'no other entry appears suspicious' is hedged ('based on the data provided')."),
    (3, "unfaithful_material", "<=40",
     "The lowest liquidity (minimum running balance) occurred on April 30, 2023, with a balance of 20,827.82.",
     BANK + "SELECT d, doc, b FROM r ORDER BY b LIMIT 2;",
     "The minimum is 20,030.18 on 2023-05-17 - in the rows shown AND in the full result; 20,827.82 is the "
     "2023-05-16 balance, and no movement is posted on April 30. The asked quantity is wrong."),
    (4, "unfaithful_material", "<=40",
     "Daily posting volume (first = 2023-01-01 to last = 2023-07-19) [...] All other days have at most 4 entries.",
     "SELECT MAX(date(posting_date)) AS last_posting, (SELECT COUNT(*) FROM (SELECT date(posting_date) d, COUNT(*) n "
     "FROM journal_entries GROUP BY d HAVING n > 4)) AS days_above_4 FROM journal_entries;",
     "The last posting is 2025-12-31; 14 days exceed 4 entries (two reach 6). The window's end is presented as "
     "the data's end, so its 'single most striking anomaly' is not that of the data."),
    (5, "faithful", "100", "", "",
     "Figures are true as stated (3,644.12 in early January 2023, 475,982.19 by early July 2024 - a point value, "
     "never called the end or the total); 'steady upward trend over the three years' holds for the full series. "
     "Accelerations/slowdowns are interpretive and not contradicted by the monthly revenue."),
    (6, "unfaithful_material", "<=40",
     "This is the single largest posting in the ledger, roughly 7x the next-largest line [...] each entry is "
     "balanced (total debits = total credits per entry), so nothing else looks irregular.",
     "SELECT (SELECT MAX(debit) FROM journal_entry_lines WHERE debit < 45000) AS next_largest_debit, "
     "(SELECT COUNT(*) FROM journal_control WHERE ABS(imbalance) > 0.005) AS unbalanced_entries;",
     "In the ledger the next-largest line is 19,264.82 (2.3x, not 7x) and one entry is unbalanced (SI24-9001). "
     "Same failure as reserve cas-01, stated about 'the ledger'."),
    (7, "unfaithful_material", "<=40",
     "The nine VAT general journal entries [...] No other entries show irregular spikes, duplicate amounts, or "
     "unusual journal codes.",
     "WITH w AS (SELECT total_amount FROM journal_entries ORDER BY total_amount DESC, entry_id LIMIT 200) "
     "SELECT COUNT(*) AS rows_shown, COUNT(DISTINCT total_amount) AS distinct_amounts, "
     "(SELECT COUNT(*) FROM journal_entries WHERE document_number LIKE 'VAT-%') AS vat_entries FROM w;",
     "Even within the 200 rows shown, only 136 amounts are distinct (invoice/payment pairs share amounts), and there "
     "are 11 VAT entries, not nine. Both statements answer the 'note any that look suspicious' part."),
    (8, "unfaithful_material", "<=40",
     "The full ledger of 200 chronological movements for account 512 [...] Ending Balance: 29,943.44 (Jan 9, 2024) "
     "[...] resulting in a net decline over the full period. Liquidity was tightest in Q1 2024.",
     BANK + "SELECT COUNT(*) AS movements, MAX(d) AS last_date, (SELECT b FROM r ORDER BY d DESC LIMIT 1) AS closing, "
     "MIN(b) AS minimum FROM r;",
     "Account 512 has 684 movements to 2025-12-31 and closes at 54,883.50 (a net gain on 45,000). 'Tightest in Q1 "
     "2024' contradicts the answer's own minimum (20,030.18, May 2023). Same failure as reserve cas-03."),
    (9, "faithful", "100", "", "",
     "All 36 table rows match exactly; +83.1% (Sept 2023) and -44.9% (Jan 2024) are the extreme changes; "
     "40,240.23 (Dec 2025) is the highest month."),
    (10, "disputed", "",
     "Largest monthly inflow: +21,731.34 (Aug 2024).",
     MONTHLY_BANK + "SELECT month, net FROM m ORDER BY net DESC LIMIT 2;",
     "All 36 rows and every other figure are exact. The column's largest value is +34,750.50 (Jan 2023), which "
     "contains the 45,000 opening balance: whether the opening capital counts as an 'inflow' is a reading, not a "
     "fact, so the case is excluded rather than settled by us."),
    (11, "unfaithful_material", "<=40",
     "The August lows and January lows are progressively higher each year, indicating underlying growth.",
     MONTHLY_REV + "SELECT month, ROUND(revenue, 2) AS revenue FROM monthly WHERE month LIKE '%-01' ORDER BY month;",
     "January revenue: 21,134.15 (2023), 19,024.64 (2024), 22,647.48 (2025) - not progressively higher. The table "
     "(36 rows) is exact; the false statement characterises the asked series, as in truth-set case 3."),
    (12, "unfaithful_material", "<=40",
     "Monthly net movements vary widely, ranging from a high of +18,528 (May 2024) to a low of -18,489 (July 2024) "
     "[...] the most recent months showing a modest but consistent net increase.",
     MONTHLY_BANK + "SELECT (SELECT MAX(net) FROM m WHERE month <> '2023-01') AS max_excl_opening_month, "
     "(SELECT group_concat(month || ':' || net, ', ') FROM m WHERE month >= '2025-10') AS last_three;",
     "Even excluding the opening month, the high is +21,731.34 (Aug 2024), and October and November 2025 are "
     "negative (-8,987.26, -6,113.03). The table (36 rows) is exact; the range of the asked series is misstated, "
     "as in truth-set case 3."),
    (13, "faithful", "100", "", "", "476: exact."),
    (14, "faithful", "100", "", "", "324,536.50: exact."),
    (15, "faithful", "100", "", "",
     "Counts, order and names exact; 683 is 1.9x the next (357); the top three sum to 1,307 of 1,412 (92.6 %)."),
]


def main() -> int:
    ids = [json.loads(l)["id"] for l in (SEALED / "answers.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(ids) == len(V) == 15
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as f:
        for n, verdict, band, claim, sql, note in V:
            result = ""
            if sql:
                cur = con.execute(sql)
                cols = [d[0] for d in cur.description]
                result = json.dumps([dict(zip(cols, r)) for r in cur.fetchall()], ensure_ascii=False)
            f.write(json.dumps({
                "id": ids[n - 1], "blind_id": f"test-{n:02d}", "verdict": verdict, "band": band,
                "material_claim": claim, "proof_sql": sql, "proof_result": result, "note": note,
                "arbitrated_by": "drafted by Claude (D9 rules), pending owner validation", "date": "2026-09-26",
            }, ensure_ascii=False) + "\n")
    for n, verdict, *_ in V:
        print(f"  test-{n:02d}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
