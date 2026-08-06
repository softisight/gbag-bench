# Reserve worksheet — held out from the law-writing set

Selected 15 of 98 eligible cases, deterministic order, stratified {'giant': 8, 'l1_36': 4, 'l1_small': 3}. The seven tuning cases are excluded by name.

For each case: the claims carrying an explicit scope marker, the scope the law assigns, and the computed facts at both scopes. **The arbitrator supplies materiality and the band.**


---

## claude-fable-5 / ledger-l10-01  *(stratum: giant, 3616 rows)*

**Question** — Show every posting line in the entire ledger in chronological order (posting date, journal, account, debit, credit) with a running cumulative total of all debits. What is the total debit turnover of the ledger, and does 

**Scope resolution** — form 1, declared 2023-01-01 -> 2023-03-28 vs actual 2023-01-01 -> 2023-03-28

- **POPULATION (r1)** — markers ['every', 'total']
  > ## Ledger Posting Analysis  The query returned every posting line in chronological order with a running debit total.
- **WINDOW (r1)** — markers ['shown']
  > The result shown covers **200 lines from 2023-01-01 through 2023-03-28**, by which point the **cumulative debit turnover reaches 289,822.36**.
- **POPULATION (r1)** — markers ['in the ledger', 'total']
  > This one posting is roughly **7x larger** than any other debit in the ledger and accounts for the cumulative total jumping immediately to 45,000 on day one.
- **WINDOW (r1)** — markers ['shown']
  > **Conclusion:** Debit turnover through the shown period is **289,822.36**, and the only unusually large single posting is the **45,000 opening balance debit**, which is expected and not suspicious in nature.

**Computed facts**
```
    window  debit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=0, sum=289822.36, n=200
    window  credit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=167.22, sum=286780.3, n=200
    window  cumulative_debit: min=45000.0 (at 2023-01-01), max=289822.36 (at 2023-03-28), median=151714.39, sum=31903787.34, n=200
    populn  debit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=0, sum=4634633.34, n=3616
    populn  credit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=164.44, sum=4634393.34, n=3616
    populn  cumulative_debit: min=45000.0 (at 2023-01-01), max=4634633.34 (at 2025-12-31), median=2392230.32, sum=8490935563.77, n=3616
    rows: window=200  population=3616
```

**Proof query** — `SELECT e.posting_date, e.journal_code, l.account_code, l.debit, l.credit, ROUND(SUM(l.debit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gpt-5.6-sol / ledger-l10-02  *(stratum: giant, 1412 rows)*

**Question** — List every journal entry (document number, posting date, journal, total amount) ordered from the largest amount to the smallest. Identify the entries whose amount is a statistical outlier, far above the typical entry, an

**Scope resolution** — form 3

- **WINDOW (r1)** — markers ['displayed']
  > Using the 200 displayed entries, the median amount is **5,639.13**.
- **POPULATION (r1)** — markers ['all']
  > - The **11 VAT entries** are all high outliers, but their recurring quarterly pattern makes them less inherently suspicious.

**Computed facts**
```
    window  total_amount: min=5254.97 (at SI23-0048), max=45000 (at OB-2023), median=5642.63, sum=1376821.2, n=200
    populn  total_amount: min=0.01 (at CS24-9003), max=45000 (at OB-2023), median=3079.46, sum=4634633.34, n=1412
    rows: window=200  population=1412
```

**Proof query** — `SELECT e.document_number, e.posting_date, e.journal_code, e.total_amount FROM journal_entries e ORDER BY e.total_amount DESC, e.entry_id;…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gpt-5.6-sol / ledger-l9-01  *(stratum: giant, 684 rows)*

**Question** — Show every movement on the bank account (512) in chronological order, with the debit, credit, and a running cumulative balance from the first to the last transaction. Identify the moment of lowest liquidity (the minimum 

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['ends at']
  > Account 512 starts at **45,000.00** on 1 January 2023 and ends at **29,943.44** on 9 January 2024.

**Computed facts**
```
    window  debit: min=0 (at 2023-01-02), max=45000 (at 2023-01-01), median=0, sum=356858.85, n=200
    window  credit: min=0 (at 2023-01-01), max=6272.96 (at 2023-07-25), median=595.75, sum=326915.41, n=200
    window  running_balance: min=20030.18 (at 2023-05-17), max=52900.22 (at 2023-11-26), median=35604.19, sum=7125246.51, n=200
    populn  debit: min=0 (at 2023-01-02), max=45000 (at 2023-01-01), median=0, sum=1144767.4, n=684
    populn  credit: min=0 (at 2023-01-01), max=7385.31 (at 2025-01-30), median=330.71, sum=1089883.9, n=684
    populn  running_balance: min=20030.18 (at 2023-05-17), max=73516.22 (at 2025-07-27), median=48698.54, sum=32703272.61, n=684
    rows: window=200  population=684
```

**Proof query** — `SELECT e.posting_date, e.document_number, l.debit, l.credit, ROUND(SUM(l.debit - l.credit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED P…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## kimi-k3 / ledger-l9-02  *(stratum: giant, 1096 rows)*

**Question** — Build a daily calendar from the first to the last posting date (all days inclusive) and show the number of journal entries posted each day, including 0 for days with no activity. Identify the single most striking anomaly

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['every']
  > ## Daily Posting Calendar: 2023-01-01 → 2023-07-19 (200 days)  The calendar covers every day from the first posting (2023-01-01) to the last (2023-07-19), with zeros filled in for inactive days.
- **POPULATION (r1)** — markers ['most', 'overall']
  > Overall volume is low and steady: most days see **0–2 entries**, with an average of roughly **1 entry per day** (~213 entries across the 200 days).

**Computed facts**
```
    window  nb_entries: min=0 (at 2023-01-04), max=5 (at 2023-04-16), median=1, sum=213, n=200
    populn  nb_entries: min=0 (at 2023-01-04), max=6 (at 2023-11-28), median=1, sum=1412, n=1096
    rows: window=200  population=1096
```

**Proof query** — `WITH RECURSIVE cal(day) AS (SELECT date((SELECT MIN(posting_date) FROM journal_entries)) UNION ALL SELECT date(day, '+1 day') FROM cal WHERE day < (SELECT date(…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## nemotron-3-nano-30b / ledger-l9-03  *(stratum: giant, 443 rows)*

**Question** — Show every revenue posting (all class 7 accounts) in chronological order with its amount and a running cumulative revenue total. Is revenue accumulating at a roughly steady pace over the three years, or are there visible

**Scope resolution** — form 1, declared 200 rows vs actual 200 rows

- **POPULATION (r1)** — markers ['overall']
  > **Overall trend** – The cumulative revenue climbs from **≈ 3.6 k** in early January 2023 to **≈ 476 k** by 4 July 2024, i.e., more than a **130‑fold increase** over the 3‑year span.
- **WINDOW (r1)** — markers ['visible']
  > **Visible accelerations and slowdowns**  | Period | What the data show | |--------|--------------------| | **Jan – Mar 2023** | Several large single‑day postings (e.g., 3 974 € on 08‑Jan, 4 667 € on 17‑Jan, 4 363 € on 12‑Mar).
- **POPULATION (r1)** — markers ['total']
  > | | **Oct – Dec 2023** | A modest resurgence with a few mid‑range postings (≈ 3–4 k €) that push the cumulative total toward ≈ 300 k by year‑end.
- **POPULATION (r1)** — markers ['total']
  > | | **Apr – Jun 2024** | Growth remains strong, with several high‑value postings (≈ 4.5 k €) and the cumulative total crossing the **400 k** mark by early May.
- **POPULATION (r1)** — markers ['most', 'total']
  > | | **Jul 2024 (up to 04‑Jul)** | The most recent entry adds **2 785 €**, taking the cumulative total to **475 982 €** – the highest point in the series.
- **POPULATION (r1)** — markers ['total']
  > - After that slowdown, the pattern re‑establishes an upward acceleration, culminating in the latest cumulative total of **≈ 476 k €**.

**Computed facts**
```
    window  revenue: min=264.15 (at 2023-06-16), max=4770.16 (at 2024-03-03), median=2198.97, sum=475982.19, n=200
    window  cumulative_revenue: min=3644.12 (at 2023-01-02), max=475982.19 (at 2024-07-04), median=253081.52, sum=49299953.86, n=200
    populn  revenue: min=186.4 (at 2024-11-16), max=4770.16 (at 2024-03-03), median=2036.4, sum=986428.82, n=443
    populn  cumulative_revenue: min=3644.12 (at 2023-01-02), max=986428.82 (at 2025-12-25), median=519959.65, sum=226850162.98, n=443
    rows: window=200  population=443
```

**Proof query** — `SELECT e.posting_date, e.document_number, ROUND(l.credit - l.debit, 2) AS revenue, ROUND(SUM(l.credit - l.debit) OVER (ORDER BY e.posting_date, e.entry_id, l.li…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gemma4-12b / ledger-l10-01  *(stratum: giant, 3616 rows)*

**Question** — Show every posting line in the entire ledger in chronological order (posting date, journal, account, debit, credit) with a running cumulative total of all debits. What is the total debit turnover of the ledger, and does 

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['total']
  > The total debit turnover of the ledger is **289,822.36**.
- **POPULATION (r1)** — markers ['in the ledger', 'most']
  > Most other postings in the ledger are much smaller, typically ranging between 100 and 6,000.

**Computed facts**
```
    window  debit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=0, sum=289822.36, n=200
    window  credit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=167.22, sum=286780.3, n=200
    window  cumulative_debit: min=45000.0 (at 2023-01-01), max=289822.36 (at 2023-03-28), median=151714.39, sum=31903787.34, n=200
    populn  debit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=0, sum=4634633.34, n=3616
    populn  credit: min=0 (at 2023-01-01), max=45000 (at 2023-01-01), median=164.44, sum=4634393.34, n=3616
    populn  cumulative_debit: min=45000.0 (at 2023-01-01), max=4634633.34 (at 2025-12-31), median=2392230.32, sum=8490935563.77, n=3616
    rows: window=200  population=3616
```

**Proof query** — `SELECT e.posting_date, e.journal_code, l.account_code, l.debit, l.credit, ROUND(SUM(l.debit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## kimi-k3 / ledger-l10-02  *(stratum: giant, 1412 rows)*

**Question** — List every journal entry (document number, posting date, journal, total amount) ordered from the largest amount to the smallest. Identify the entries whose amount is a statistical outlier, far above the typical entry, an

**Scope resolution** — form 3

- **WINDOW (r1)** — markers ['returned']
  > ## Journal Entries Ranked by Amount (largest → smallest)  The query returned 200 rows (the full set was truncated at 200).
- **POPULATION (r1)** — markers ['typical']
  > **OB-2023 — 45,000 (statistical outlier).** It is ~2.3× the next-largest entry and ~8× the typical operational entry.
- **POPULATION (r1)** — markers ['in the ledger']
  > As the opening-balance posting on 2023-01-01, a large amount is expected, but it is by far the biggest entry in the ledger and worth verifying against the prior-period closing balance.
- **POPULATION (r1)** — markers ['whole']
  > This is consistent with invoice-then-payment matching, but the 1:1 duplication across the whole ledger should be confirmed as genuine settlements rather than double-postings.
- **POPULATION (r1)** — markers ['all']
  > - **Cluster of large bank entries on 2025-10-28:** BK25-0612 (7,237.76), BK25-0616 (5,387.33), and BK25-0613 (5,376.49) all posted the same day — unusual concentration of outflows worth a spot check.

**Computed facts**
```
    window  total_amount: min=5254.97 (at SI23-0048), max=45000 (at OB-2023), median=5642.63, sum=1376821.2, n=200
    populn  total_amount: min=0.01 (at CS24-9003), max=45000 (at OB-2023), median=3079.46, sum=4634633.34, n=1412
    rows: window=200  population=1412
```

**Proof query** — `SELECT e.document_number, e.posting_date, e.journal_code, e.total_amount FROM journal_entries e ORDER BY e.total_amount DESC, e.entry_id;…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## kimi-k3 / ledger-l9-01  *(stratum: giant, 684 rows)*

**Question** — Show every movement on the bank account (512) in chronological order, with the debit, credit, and a running cumulative balance from the first to the last transaction. Identify the moment of lowest liquidity (the minimum 

**Scope resolution** — form 1, declared 200 rows vs actual 200 rows

- **WINDOW (r1)** — markers ['shown']
  > ## Bank Account 512 – Movements & Running Balance (2023-01-01 → 2024-01-09)  The account opened with a **45,000.00** balance (OB-2023 on 2023-01-01) and, across the 200 movements shown, the running balance oscillated between rough
- **WINDOW (r1)** — markers ['visible']
  > The last visible position (2024-01-09, BK24-0214) stands at **29,943.44**.
- **POPULATION (r1)** — markers ['every', 'most']
  > ### Visible patterns - **Recurring fixed outflows:** a **1,980** credit appears around the 10th–16th of nearly every month (likely rent or a lease payment), and a **350** credit appears at the start of most months (likely bank fee
- **POPULATION (r1)** — markers ['all']
  > - **Seasonal rhythm:** liquidity is tightest in **mid-May, late July, and early August** (all in the 20k–24k zone) and strongest in **late November and mid-December** (peaks of 52,900.22 on 26 Nov and 50,423.37 on 17 Dec).
- **POPULATION (r1)** — markers ['overall']
  > - **Overall trend:** despite repeated drawdowns, inflows consistently outpace outflows over the long run — the balance ends the period roughly 15,000 below its opening level but well above the May trough, with the account never at
- **WINDOW (r1)** — markers ['returned']
  > Note: this summary reflects the 200 rows returned, which run through 2024-01-09; any transactions after that date are not included.

**Computed facts**
```
    window  debit: min=0 (at 2023-01-02), max=45000 (at 2023-01-01), median=0, sum=356858.85, n=200
    window  credit: min=0 (at 2023-01-01), max=6272.96 (at 2023-07-25), median=595.75, sum=326915.41, n=200
    window  running_balance: min=20030.18 (at 2023-05-17), max=52900.22 (at 2023-11-26), median=35604.19, sum=7125246.51, n=200
    populn  debit: min=0 (at 2023-01-02), max=45000 (at 2023-01-01), median=0, sum=1144767.4, n=684
    populn  credit: min=0 (at 2023-01-01), max=7385.31 (at 2025-01-30), median=330.71, sum=1089883.9, n=684
    populn  running_balance: min=20030.18 (at 2023-05-17), max=73516.22 (at 2025-07-27), median=48698.54, sum=32703272.61, n=684
    rows: window=200  population=684
```

**Proof query** — `SELECT e.posting_date, e.document_number, l.debit, l.credit, ROUND(SUM(l.debit - l.credit) OVER (ORDER BY e.posting_date, e.entry_id, l.line_id ROWS UNBOUNDED P…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## claude-fable-5 / ledger-l8-01  *(stratum: l1_36, 36 rows)*

**Question** — Show the monthly revenue across the full 2023-2025 period with, for each month, the absolute change and the percentage change versus the previous month.

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['entire', 'overall']
  > - **Overall upward trend**: peaks and troughs are rising year over year — August lows improved from 14,557.87 (2023) to 18,804.86 (2025), and December highs grew from 34,506.04 (2023) to 40,240.23 (2025), the highest month in the 

**Computed facts**
```
    window  revenue: min=14557.87 (at 2023-08), max=40240.23 (at 2025-12), median=26662.63, sum=986428.82, n=36
    window  change_abs: min=-15481.4 (at 2024-01), max=12104.76 (at 2023-09), median=1631.31, sum=19106.08, n=35
    window  change_pct: min=-44.9 (at 2024-01), max=83.1 (at 2023-09), median=5.9, sum=178.6, n=35
    rows: window=36  population=36
```

**Proof query** — `WITH monthly AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.credit - l.debit) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.en…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gemma4-12b / ledger-l8-02  *(stratum: l1_36, 36 rows)*

**Question** — Track the bank account (account 512) month by month over the whole period: show the net monthly movement and the cumulative running balance.

**Scope resolution** — form 3

_No sentence carries an explicit scope marker: every claim falls to inheritance or to the question's scope._


**Computed facts**
```
    window  net_movement: min=-18489.48 (at 2024-07), max=34750.5 (at 2023-01), median=3170.38, sum=54883.5, n=36
    window  running_balance: min=26738.74 (at 2023-04), max=66291.42 (at 2025-09), median=45642.95, sum=1638968.36, n=36
    rows: window=36  population=36
```

**Proof query** — `WITH movements AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.debit - l.credit) AS net_movement FROM journal_entries e JOIN journal_entry_lines l …`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gemma4-12b / ledger-l8-01  *(stratum: l1_36, 36 rows)*

**Question** — Show the monthly revenue across the full 2023-2025 period with, for each month, the absolute change and the percentage change versus the previous month.

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['overall']
  > Monthly revenue from January 2023 through December 2025 shows an overall upward trend, growing from 21,134.15 in early 2023 to a peak of 40,240.23 by the end of 2025.

**Computed facts**
```
    window  revenue: min=14557.87 (at 2023-08), max=40240.23 (at 2025-12), median=26662.63, sum=986428.82, n=36
    window  change_abs: min=-15481.4 (at 2024-01), max=12104.76 (at 2023-09), median=1631.31, sum=19106.08, n=35
    window  change_pct: min=-44.9 (at 2024-01), max=83.1 (at 2023-09), median=5.9, sum=178.6, n=35
    rows: window=36  population=36
```

**Proof query** — `WITH monthly AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.credit - l.debit) AS revenue FROM journal_entries e JOIN journal_entry_lines l ON e.en…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gpt-5.6-sol / ledger-l8-02  *(stratum: l1_36, 36 rows)*

**Question** — Track the bank account (account 512) month by month over the whole period: show the net monthly movement and the cumulative running balance.

**Scope resolution** — form 3

_No sentence carries an explicit scope marker: every claim falls to inheritance or to the question's scope._


**Computed facts**
```
    window  net_movement: min=-18489.48 (at 2024-07), max=34750.5 (at 2023-01), median=3170.38, sum=54883.5, n=36
    window  running_balance: min=26738.74 (at 2023-04), max=66291.42 (at 2025-09), median=45642.95, sum=1638968.36, n=36
    rows: window=36  population=36
```

**Proof query** — `WITH movements AS (SELECT strftime('%Y-%m', e.posting_date) AS month, SUM(l.debit - l.credit) AS net_movement FROM journal_entries e JOIN journal_entry_lines l …`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## claude-fable-5 / ledger-l1-01  *(stratum: l1_small, 1 rows)*

**Question** — How many journal entries were posted in fiscal year 2024?

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['total']
  > A total of **476 journal entries** were posted in fiscal year 2024.

**Computed facts**
```
    window  nb_entries: min=476 (at 476), max=476 (at 476), median=476, sum=476, n=1
    rows: window=1  population=1
```

**Proof query** — `SELECT COUNT(*) AS nb_entries FROM journal_entries WHERE strftime('%Y', posting_date) = '2024';…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gemma4-12b / ledger-l2-01  *(stratum: l1_small, 1 rows)*

**Question** — What is the total revenue (all class 7 accounts) recognised in 2024?

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['all', 'total']
  > The total revenue recognized from all class 7 accounts in 2024 was 324,536.50.

**Computed facts**
```
    window  total_revenue: min=324536.5 (at 324536.5), max=324536.5 (at 324536.5), median=324536.5, sum=324536.5, n=1
    rows: window=1  population=1
```

**Proof query** — `SELECT ROUND(SUM(l.credit - l.debit), 2) AS total_revenue FROM journal_entries e JOIN journal_entry_lines l ON e.entry_id = l.entry_id JOIN chart_of_accounts a …`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____


---

## gpt-5.6-sol / ledger-l3-01  *(stratum: l1_small, 7 rows)*

**Question** — List each journal (code and name) with the number of entries posted in it, from most to least used.

**Scope resolution** — form 3

- **POPULATION (r1)** — markers ['most']
  > Journals ranked from most to least used:  1.

**Computed facts**
```
    window  nb_entries: min=1 (at OB), max=683 (at BK), median=56, sum=1412, n=7
    rows: window=7  population=7
```

**Proof query** — `SELECT j.journal_code, j.journal_name, COUNT(e.entry_id) AS nb_entries FROM journals j LEFT JOIN journal_entries e ON e.journal_code = j.journal_code GROUP BY j…`

**Verdict (to fill):** `faithful` / `unfaithful_material` / `unverifiable` — band ____

