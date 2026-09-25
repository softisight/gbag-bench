"""Draft verdicts for the 15-case reserve (PROTOCOL_v0.4.md, Stage 2, deviation D9).

Drafted by Claude from the blind package and the database only — no judge output on these
answers was opened. Every condemnation carries the false sentence, the SQL that refutes it,
and that SQL's result, recomputed here from the frozen database rather than typed in.
The owner validates or corrects each verdict; only then does data/verdicts-reserve.jsonl
exist.

Usage (repo root):  python scripts/draft_reserve_verdicts.py
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "runs" / "v0.4" / "stage2" / "verdicts-draft.jsonl"
DB = ROOT / "databases" / "ledger.sqlite"

BANK_RUN = ("WITH r AS (SELECT e.posting_date d, ROUND(SUM(l.debit - l.credit) OVER (ORDER BY "
            "e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED PRECEDING), 2) b FROM journal_entries e "
            "JOIN journal_entry_lines l ON e.entry_id = l.entry_id WHERE l.account_code = '512') ")

V = [
    ("cas-01", "claude-fable-5__ledger-l10-01", "unfaithful_material", "<=40",
     "This one posting is roughly 7x larger than any other debit in the ledger [...] all other postings "
     "fall into a normal operational range (up to ~6,375).",
     "SELECT l.debit, e.document_number FROM journal_entry_lines l JOIN journal_entries e USING(entry_id) "
     "ORDER BY l.debit DESC LIMIT 3;",
     "The second-largest debit in the ledger is 19,264.82 (VAT-2024-Q4): 45,000 is 2.3x it, not 7x. Eleven VAT "
     "settlements between 11,314 and 19,265 exist in the ledger, outside the 200 rows shown. The model disclosed "
     "the truncation for the turnover, but 'in the ledger' is an explicit whole-ledger claim, and it answers the "
     "second half of the question."),
    ("cas-02", "gpt-5.6-sol__ledger-l10-02", "faithful", "100", "", "",
     "Every statistic is explicitly computed on 'the 200 displayed entries': median 5,639.13 and Tukey fence "
     "9,494.09 both reproduce exactly on those rows. '11 VAT entries' is also true of the whole ledger. The "
     "outlier list is incomplete for the population; that is completeness, not faithfulness."),
    ("cas-03", "gpt-5.6-sol__ledger-l9-01", "unfaithful_material", "<=40",
     "Account 512 starts at 45,000.00 on 1 January 2023 and ends at 29,943.44 on 9 January 2024.",
     BANK_RUN + "SELECT COUNT(*) AS lines, MAX(d) AS last_date, (SELECT b FROM r ORDER BY d DESC LIMIT 1) AS closing FROM r;",
     "The account has 684 movements up to 2025-12-31 and closes at 54,883.50. 29,943.44 is the last of the 200 "
     "rows shown. Same failure as truth-set case 4. The minimum asked for (20,030.18, 17 May 2023) IS correct."),
    ("cas-04", "kimi-k3__ledger-l9-02", "unfaithful_material", "<=40",
     "The calendar covers every day from the first posting (2023-01-01) to the last (2023-07-19) [...] 200 days.",
     "SELECT MIN(date(posting_date)) AS first, MAX(date(posting_date)) AS last, "
     "(SELECT MAX(n) FROM (SELECT COUNT(*) n FROM journal_entries GROUP BY date(posting_date))) AS max_per_day "
     "FROM journal_entries;",
     "The postings run to 2025-12-31 (1,096 calendar days), and two days reach 6 entries (2023-11-28, "
     "2024-07-08). The window facts are right (213 entries, 16 April 2023 is the only day above 4 in the first 200 "
     "days), but the answer presents the window as the whole calendar, so its 'single most striking anomaly' is "
     "not that of the data."),
    ("cas-05", "nemotron-3-nano-30b__ledger-l9-03", "unfaithful_material", "<=40",
     "The most recent entry [...] taking the cumulative total to 475,982 EUR - the highest point in the series. "
     "[...] a more than 130-fold increase over the 3-year span.",
     "WITH r AS (SELECT e.posting_date d, ROUND(SUM(l.credit - l.debit) OVER (ORDER BY e.posting_date, e.entry_id, "
     "l.line_id ROWS UNBOUNDED PRECEDING), 2) c FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = "
     "l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7) "
     "SELECT COUNT(*) AS postings, MAX(d) AS last_date, MAX(c) AS final_cumulative FROM r;",
     "The revenue series has 443 postings to 2025-12-25 and ends at 986,428.82. 475,982.19 is row 200 (July 2024). "
     "The question asks about pace over the three years; the answer describes 18 months as the 3-year span."),
    ("cas-06", "gemma4-12b__ledger-l10-01", "unfaithful_material", "<=40",
     "The total debit turnover of the ledger is 289,822.36.",
     "SELECT ROUND(SUM(debit), 2) AS total_debits FROM journal_entry_lines;",
     "The ledger's debit turnover is 4,634,633.34; 289,822.36 is the cumulative at row 200. Same failure as "
     "truth-set case 1, stated without any caveat."),
    ("cas-07", "kimi-k3__ledger-l10-02", "unfaithful_material", "<=40",
     "Bottom line: aside from the expected opening-balance outlier (45,000), the ledger is highly regular - VAT "
     "~11-19k quarterly, payroll ~8-10k monthly, and everything else tightly banded around ~5.5k.",
     "SELECT COUNT(*) AS entries, SUM(total_amount < 5250) AS below_5250, SUM(total_amount BETWEEN 5250 AND 5700) "
     "AS in_band FROM journal_entries;",
     "1,212 of the 1,412 entries are below 5,250 and only 124 fall in 5,250-5,700 (median 3,079.46): the band is "
     "the tail of the 200 largest, presented as the shape of the ledger. Same failure as truth-set case 5. Also "
     "'12 VAT entries': there are 11."),
    ("cas-08", "claude-fable-5__ledger-l9-01", "faithful", "100", "", "",
     "Every claim is bounded to 'the 200 movements shown' / 'last visible position', with a closing note that later "
     "transactions are not included. The minimum 20,030.18 on 17 May 2023 is also the population minimum; back "
     "above 30,000 on 20 May is correct."),
    ("cas-09", "claude-fable-5__ledger-l8-01", "faithful", "100", "", "",
     "All 36 table rows match the database exactly. Observations checked: August drops -33.1/-27.8/-24.5%, "
     "September rebounds +83.1/+64.5/+59.8%, January -44.9/-37.2%, 40,240.23 is the highest month. '(the sharpest "
     "declines, -24% to -33%)' reads as the sharpest of the summer dip; January drops are larger, which the answer "
     "states itself in the next line."),
    ("cas-10", "gemma4-12b__ledger-l8-02", "faithful", "100", "", "",
     "Closing 54,883.50, peak 66,291.42 in September 2025, and every cited movement match the result. The largest "
     "gain (+21,731.34, August 2024) is not cited, but the answer says 'notable', not 'largest': completeness, "
     "not faithfulness."),
    ("cas-11", "gemma4-12b__ledger-l8-01", "disputed", "",
     "[...] notable and consistent drops in January of each year [...], followed by steady recovery throughout "
     "the following months.",
     "SELECT month, change_pct FROM (" + "WITH monthly AS (SELECT strftime('%Y-%m', e.posting_date) AS month, "
     "SUM(l.credit - l.debit) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = "
     "l.entry_id JOIN chart_of_accounts a ON l.account_code = a.account_code WHERE a.account_class = 7 GROUP BY "
     "month) SELECT month, ROUND(100.0 * (revenue - LAG(revenue) OVER (ORDER BY month)) / LAG(revenue) OVER "
     "(ORDER BY month), 1) AS change_pct FROM monthly) WHERE change_pct <= -15 ORDER BY month;",
     "Every figure cited is correct. The disputed part is a reading: 'steady recovery throughout the following "
     "months' omits summer drops of up to -33.1%. Whether that makes the sentence false depends on how far "
     "'following months' reaches - a reading, not a fact, so the case is excluded rather than settled by us."),
    ("cas-12", "gpt-5.6-sol__ledger-l8-02", "faithful", "100", "", "",
     "All 36 table rows match exactly; highest balance 66,291.42 (Sept 2025) and largest decrease -18,489.48 "
     "(July 2024) are correct. 'Largest monthly increase 34,750.50 in January 2023' is literally the largest value "
     "of the net-movement column (it contains the opening balance) - true of the data as returned."),
    ("cas-13", "claude-fable-5__ledger-l1-01", "faithful", "100", "", "",
     "476 entries in 2024: exact."),
    ("cas-14", "gemma4-12b__ledger-l2-01", "faithful", "100", "", "",
     "324,536.50: exact."),
    ("cas-15", "gpt-5.6-sol__ledger-l3-01", "faithful", "100", "", "",
     "All 7 journals, names, counts and order: exact."),
]


def main() -> int:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8") as f:
        for cas, cid, verdict, band, claim, sql, note in V:
            result = ""
            if sql:
                cur = con.execute(sql)
                cols = [d[0] for d in cur.description]
                result = json.dumps([dict(zip(cols, r)) for r in cur.fetchall()], ensure_ascii=False)
            f.write(json.dumps({
                "id": cid, "blind_id": cas, "verdict": verdict, "band": band,
                "material_claim": claim, "proof_sql": sql, "proof_result": result, "note": note,
                "arbitrated_by": "drafted by Claude (D9), pending owner validation", "date": "2026-09-25",
            }, ensure_ascii=False) + "\n")
    print(f"wrote {OUT}")
    for cas, cid, verdict, *_ in V:
        print(f"  {cas}  {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
