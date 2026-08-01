# -*- coding: utf-8 -*-
"""
generate_ledger.py -- Generates the GBAG held-out database: ledger.sqlite

A fully synthetic double-entry bookkeeping database for a fictional UK
trading company ("Harborview Trading Ltd"). Never published anywhere
before this repository, so it cannot appear in any model's training data.

Properties:
- Deterministic: same seed => byte-identical business content.
  Re-roll every number for a future benchmark version by changing SEED.
- Every journal entry is balanced (debit == credit, asserted), except a
  handful of deliberate, UNMARKED audit anomalies (unbalanced entry,
  duplicate document number, aberrant VAT amount, suspicious 0.01 posting,
  late posting into a closed fiscal year). The verify() report printed at
  build time lists them for the benchmark author's eyes only -- nothing in
  the data itself marks them as anomalies.
- 3 fiscal years (2023-2025), sales trend +8%/year with seasonality
  (August shutdown slump, Nov-Dec peak), quarterly VAT returns, monthly
  payroll and rent, customer/supplier settlement with reconciliation codes.

Usage:  python scripts/generate_ledger.py
Output: databases/ledger.sqlite (overwritten)
"""

import os
import sqlite3
import random
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(HERE, "..", "databases", "ledger.sqlite")

SEED = 20260718
INCLUDE_ANOMALIES = True
YEARS = [2023, 2024, 2025]
random.seed(SEED)

# Sales trend + seasonality (drives realistic trend/forecast questions)
BASE_SALES_NET = 23000.0    # reference monthly net sales, first year
GROWTH = 1.08               # +8% sales growth per year
SEASON = {1: 0.80, 2: 0.92, 3: 1.02, 4: 1.05, 5: 1.08, 6: 1.00,
          7: 0.90, 8: 0.60, 9: 1.12, 10: 1.18, 11: 1.30, 12: 1.40}
GROSS_PAYROLL_PER_YEAR = {2023: 6100.0, 2024: 6600.0, 2025: 7100.0}

# ------------------------------------------------------------------
# Embedded schema (English)
# ------------------------------------------------------------------
SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE companies (
    company_id          INTEGER NOT NULL PRIMARY KEY,
    company_name        VARCHAR(100) NOT NULL,
    legal_form          VARCHAR(20),
    registration_number VARCHAR(14),
    industry_code       VARCHAR(6),
    vat_number          VARCHAR(15),
    address             VARCHAR(200),
    postal_code         VARCHAR(10),
    city                VARCHAR(50),
    phone               VARCHAR(20),
    email               VARCHAR(100)
);

CREATE TABLE fiscal_years (
    fiscal_year_id INTEGER NOT NULL PRIMARY KEY,
    company_id     INTEGER NOT NULL,
    year           INTEGER NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE NOT NULL,
    closed         INTEGER NOT NULL DEFAULT 0 CHECK (closed IN (0, 1)),
    FOREIGN KEY (company_id) REFERENCES companies(company_id)
);

CREATE TABLE chart_of_accounts (
    account_code    VARCHAR(10) NOT NULL PRIMARY KEY,
    account_name    VARCHAR(100) NOT NULL,
    account_type    VARCHAR(1) NOT NULL CHECK (account_type IN ('A', 'P', 'C', 'R', 'D')),
    -- A: Asset, P: Liability/Equity, C: Cost (expense), R: Revenue, D: special
    account_class   INTEGER NOT NULL CHECK (account_class BETWEEN 1 AND 8),
    control_account VARCHAR(1) CHECK (control_account IN ('C', 'S', NULL))
    -- C: customers control account, S: suppliers control account
);

CREATE TABLE journals (
    journal_code   VARCHAR(5) NOT NULL PRIMARY KEY,
    journal_name   VARCHAR(50) NOT NULL,
    journal_type   VARCHAR(20) NOT NULL
        CHECK (journal_type IN ('PURCHASES','SALES','BANK','CASH','PAYROLL','GENERAL')),
    offset_account VARCHAR(10),
    FOREIGN KEY (offset_account) REFERENCES chart_of_accounts(account_code)
);

CREATE TABLE customers (
    customer_id         INTEGER NOT NULL PRIMARY KEY,
    customer_code       VARCHAR(20) NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    registration_number VARCHAR(14),
    address             VARCHAR(200),
    postal_code         VARCHAR(10),
    city                VARCHAR(50),
    phone               VARCHAR(20),
    email               VARCHAR(100),
    account_code        VARCHAR(10),
    credit_limit        NUMERIC(12,2) DEFAULT 0,
    payment_terms_days  INTEGER DEFAULT 30,
    active              INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_date        DATE,
    FOREIGN KEY (account_code) REFERENCES chart_of_accounts(account_code)
);

CREATE TABLE suppliers (
    supplier_id         INTEGER NOT NULL PRIMARY KEY,
    supplier_code       VARCHAR(20) NOT NULL UNIQUE,
    name                VARCHAR(100) NOT NULL,
    registration_number VARCHAR(14),
    address             VARCHAR(200),
    postal_code         VARCHAR(10),
    city                VARCHAR(50),
    phone               VARCHAR(20),
    email               VARCHAR(100),
    account_code        VARCHAR(10),
    payment_terms_days  INTEGER DEFAULT 30,
    active              INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    created_date        DATE,
    FOREIGN KEY (account_code) REFERENCES chart_of_accounts(account_code)
);

CREATE TABLE journal_entries (
    entry_id            INTEGER NOT NULL PRIMARY KEY,
    company_id          INTEGER NOT NULL DEFAULT 1,
    fiscal_year_id      INTEGER,
    journal_code        VARCHAR(5) NOT NULL,
    document_number     VARCHAR(20),
    entry_date          DATE NOT NULL,   -- date the entry was keyed in
    posting_date        DATE NOT NULL,   -- accounting date
    due_date            DATE,            -- invoices only
    description         VARCHAR(200) NOT NULL,
    total_amount        NUMERIC(12,2) DEFAULT 0,
    payment_method      VARCHAR(20),
    reconciliation_code VARCHAR(10),     -- links an invoice to its settlement
    validated           INTEGER NOT NULL DEFAULT 1 CHECK (validated IN (0, 1)),
    customer_id         INTEGER,
    supplier_id         INTEGER,
    FOREIGN KEY (company_id)     REFERENCES companies(company_id),
    FOREIGN KEY (fiscal_year_id) REFERENCES fiscal_years(fiscal_year_id),
    FOREIGN KEY (journal_code)   REFERENCES journals(journal_code),
    FOREIGN KEY (customer_id)    REFERENCES customers(customer_id),
    FOREIGN KEY (supplier_id)    REFERENCES suppliers(supplier_id)
);

CREATE TABLE journal_entry_lines (
    line_id             INTEGER NOT NULL PRIMARY KEY,
    entry_id            INTEGER NOT NULL,
    account_code        VARCHAR(10) NOT NULL,
    debit               NUMERIC(12,2) DEFAULT 0,
    credit              NUMERIC(12,2) DEFAULT 0,
    line_description    VARCHAR(200),
    reconciliation_code VARCHAR(10),
    FOREIGN KEY (entry_id)     REFERENCES journal_entries(entry_id),
    FOREIGN KEY (account_code) REFERENCES chart_of_accounts(account_code),
    CHECK (debit >= 0 AND credit >= 0),
    CHECK (debit = 0 OR credit = 0)
);

CREATE INDEX idx_entries_posting_date ON journal_entries(posting_date);
CREATE INDEX idx_entries_journal      ON journal_entries(journal_code);
CREATE INDEX idx_entries_fiscal_year  ON journal_entries(fiscal_year_id);
CREATE INDEX idx_entries_customer     ON journal_entries(customer_id);
CREATE INDEX idx_entries_supplier     ON journal_entries(supplier_id);
CREATE INDEX idx_lines_account        ON journal_entry_lines(account_code);
CREATE INDEX idx_lines_entry          ON journal_entry_lines(entry_id);

-- Analysis views ----------------------------------------------------

CREATE VIEW general_ledger AS
SELECT
    e.entry_id, e.journal_code, e.document_number, e.posting_date,
    e.description, l.account_code, a.account_name, l.debit, l.credit,
    l.line_description, l.reconciliation_code,
    c.name AS customer_name, s.name AS supplier_name
FROM journal_entries e
JOIN journal_entry_lines l  ON e.entry_id = l.entry_id
JOIN chart_of_accounts a    ON l.account_code = a.account_code
LEFT JOIN customers c       ON e.customer_id = c.customer_id
LEFT JOIN suppliers s       ON e.supplier_id = s.supplier_id
ORDER BY e.posting_date, e.entry_id;

CREATE VIEW trial_balance AS
SELECT
    a.account_code, a.account_name, a.account_type, a.account_class,
    COALESCE(SUM(l.debit),  0) AS total_debit,
    COALESCE(SUM(l.credit), 0) AS total_credit,
    CASE
        WHEN a.account_type IN ('A', 'C', 'D')
            THEN COALESCE(SUM(l.debit), 0) - COALESCE(SUM(l.credit), 0)
        ELSE COALESCE(SUM(l.credit), 0) - COALESCE(SUM(l.debit), 0)
    END AS balance
FROM chart_of_accounts a
LEFT JOIN journal_entry_lines l ON a.account_code = l.account_code
GROUP BY a.account_code, a.account_name, a.account_type, a.account_class
HAVING COALESCE(SUM(l.debit), 0) <> 0 OR COALESCE(SUM(l.credit), 0) <> 0
ORDER BY a.account_code;

CREATE VIEW journal_control AS
SELECT
    e.entry_id, e.journal_code, e.document_number, e.posting_date, e.description,
    SUM(l.debit)  AS total_debit,
    SUM(l.credit) AS total_credit,
    ROUND(SUM(l.debit) - SUM(l.credit), 2) AS imbalance
FROM journal_entries e
JOIN journal_entry_lines l ON e.entry_id = l.entry_id
GROUP BY e.entry_id, e.journal_code, e.document_number, e.posting_date, e.description
ORDER BY e.posting_date, e.entry_id;

CREATE VIEW income_statement AS
SELECT
    strftime('%Y', e.posting_date) AS year,
    SUM(CASE WHEN a.account_class = 7 THEN l.credit - l.debit ELSE 0 END) AS total_revenue,
    SUM(CASE WHEN a.account_class = 6 THEN l.debit - l.credit ELSE 0 END) AS total_expenses,
    SUM(CASE WHEN a.account_class = 7 THEN l.credit - l.debit ELSE 0 END)
      - SUM(CASE WHEN a.account_class = 6 THEN l.debit - l.credit ELSE 0 END) AS net_result
FROM journal_entries e
JOIN journal_entry_lines l ON e.entry_id = l.entry_id
JOIN chart_of_accounts a   ON l.account_code = a.account_code
WHERE a.account_class IN (6, 7)
GROUP BY strftime('%Y', e.posting_date)
ORDER BY year;
"""

# Chart of accounts: numeric-class chart (class 6 = expenses, class 7 = revenue,
# 411 = trade receivables, 401 = trade payables, 44571/44566 = output/input VAT).
CHART = [
    # class 1 -- equity & loans
    ("101",   "Share capital",                              "P", 1, None),
    ("106",   "Retained reserves",                          "P", 1, None),
    ("120",   "Profit for the year",                        "P", 1, None),
    ("129",   "Loss for the year",                          "A", 1, None),
    ("164",   "Bank loans",                                 "P", 1, None),
    # class 2 -- fixed assets
    ("205",   "Software licences",                          "A", 2, None),
    ("2154",  "Plant and machinery",                        "A", 2, None),
    ("2183",  "Computer equipment",                         "A", 2, None),
    ("2184",  "Furniture",                                  "A", 2, None),
    ("28183", "Accumulated depreciation - computer equipment", "P", 2, None),
    # class 4 -- third parties
    ("401",   "Trade payables",                             "P", 4, "S"),
    ("404",   "Fixed asset suppliers",                      "P", 4, "S"),
    ("411",   "Trade receivables",                          "A", 4, "C"),
    ("421",   "Employees - net pay due",                    "P", 4, None),
    ("431",   "Social security payable",                    "P", 4, None),
    ("44551", "VAT payable",                                "P", 4, None),
    ("44562", "Input VAT on fixed assets",                  "A", 4, None),
    ("44566", "Input VAT on goods and services",            "A", 4, None),
    ("44567", "VAT credit carried forward",                 "A", 4, None),
    ("44571", "Output VAT",                                 "P", 4, None),
    # class 5 -- cash & bank
    ("512",   "Bank account",                               "A", 5, None),
    ("530",   "Petty cash",                                 "A", 5, None),
    # class 6 -- expenses
    ("607",   "Purchases of goods for resale",              "C", 6, None),
    ("6063",  "Maintenance supplies and small equipment",   "C", 6, None),
    ("6064",  "Office supplies",                            "C", 6, None),
    ("6132",  "Property rent",                              "C", 6, None),
    ("615",   "Repairs and maintenance",                    "C", 6, None),
    ("616",   "Insurance premiums",                         "C", 6, None),
    ("6226",  "Professional fees",                          "C", 6, None),
    ("623",   "Advertising and publications",               "C", 6, None),
    ("6251",  "Travel expenses",                            "C", 6, None),
    ("6257",  "Business entertaining",                      "C", 6, None),
    ("626",   "Postage and telecommunications",             "C", 6, None),
    ("627",   "Bank charges",                               "C", 6, None),
    ("641",   "Staff remuneration",                         "C", 6, None),
    ("645",   "Social security and pension charges",        "C", 6, None),
    ("6811",  "Depreciation charges",                       "C", 6, None),
    # class 7 -- revenue
    ("706",   "Services revenue",                           "R", 7, None),
    ("707",   "Sales of goods",                             "R", 7, None),
    ("708",   "Other operating income",                     "R", 7, None),
    ("7085",  "Delivery charges re-invoiced",               "R", 7, None),
    ("764",   "Financial income",                           "R", 7, None),
]

JOURNALS = [
    ("OB", "Opening balances", "GENERAL",   None),
    ("PU", "Purchases",        "PURCHASES", "401"),
    ("SA", "Sales",            "SALES",     "411"),
    ("BK", "Bank",             "BANK",      "512"),
    ("CS", "Petty cash",       "CASH",      "530"),
    ("PY", "Payroll",          "PAYROLL",   None),
    ("GJ", "General journal",  "GENERAL",   None),
]

# ------------------------------------------------------------------
# Realistic English reference pools
# ------------------------------------------------------------------
CITIES = [
    ("London", "EC2A 3AR"), ("Manchester", "M1 4BT"), ("Birmingham", "B2 5EP"),
    ("Leeds", "LS1 4DY"), ("Bristol", "BS1 6QF"), ("Liverpool", "L2 2DP"),
    ("Newcastle", "NE1 6SN"), ("Sheffield", "S1 2HE"), ("Nottingham", "NG1 5FS"),
    ("Cardiff", "CF10 2HH"), ("Edinburgh", "EH2 2AD"), ("Glasgow", "G2 5QD"),
    ("Southampton", "SO14 3AB"), ("Reading", "RG1 3EH"), ("Cambridge", "CB2 1TN"),
    ("Oxford", "OX1 3HB"), ("York", "YO1 8QG"), ("Brighton", "BN1 4GH"),
]
LEGAL_FORMS = ["Ltd", "Ltd", "Ltd", "LLP", "PLC", "& Co"]
NAME_WORDS = ["Thames", "Mersey", "Pennine", "Cotswold", "Highland", "Severn",
              "Solent", "Chiltern", "Kestrel", "Beacon", "Fenland", "Orchard",
              "Granite", "Harbour", "Atlas", "Camden", "Windsor", "Avon"]
CUSTOMER_ACTIVITIES = ["Distribution", "Trading", "Construction", "Services",
                       "Industrial", "Retail", "Logistics", "Equipment",
                       "Office Solutions", "Renovation", "Engineering", "Consulting"]
SUPPLIER_TYPES = [
    ("Wholesale", "607"), ("Import Export", "607"), ("Building Supplies", "607"),
    ("Trade Materials", "607"), ("Office Products", "6064"),
    ("Insurance Brokers", "616"), ("Telecom", "626"),
    ("Advisory Partners", "6226"), ("Haulage", "607"), ("Utilities", "615"),
]
PAYMENT_METHODS = ["Bank transfer", "Cheque", "Card", "Direct debit"]

# expense accounts used for purchases (account, label, weight)
PURCHASE_ACCOUNTS = [
    ("607",  "Goods for resale",         55),
    ("6063", "Small equipment",           8),
    ("6064", "Office supplies",           8),
    ("615",  "Repairs and maintenance",   6),
    ("616",  "Insurance premium",         4),
    ("6226", "Professional fees",         6),
    ("623",  "Advertising",               5),
    ("626",  "Phone and internet",        5),
    ("6251", "Travel expenses",           3),
]
VAT_RATES = [(0.20, 88), (0.05, 12)]   # UK: standard 20%, reduced 5%


def weighted(choices):
    """choices: list of (value, weight)"""
    total = sum(w for _, w in choices)
    r = random.uniform(0, total)
    upto = 0
    for v, w in choices:
        upto += w
        if r <= upto:
            return v
    return choices[-1][0]


def rnd_regnum():
    return "".join(str(random.randint(0, 9)) for _ in range(8))


def rnd_phone():
    return "01%d %03d %04d" % (random.randint(10, 99),
                               random.randint(0, 999), random.randint(0, 9999))


# ------------------------------------------------------------------
# Double-entry engine
# ------------------------------------------------------------------
class Book:
    def __init__(self, conn):
        self.conn = conn
        self.cur = conn.cursor()
        self.eid = 0
        self.lid = 0

    @staticmethod
    def fiscal_year_of(d):
        return {2023: 1, 2024: 2, 2025: 3}.get(d.year, 3)

    def entry(self, journal, doc, posting, description, lines,
              entry_date=None, due=None, method=None, recon=None,
              customer_id=None, supplier_id=None, validated=1,
              allow_unbalanced=False):
        """lines: list of (account, debit, credit, line_description, line_recon)"""
        self.eid += 1
        tot_d = round(sum(l[1] for l in lines), 2)
        tot_c = round(sum(l[2] for l in lines), 2)
        if not allow_unbalanced:
            assert abs(tot_d - tot_c) < 0.005, \
                "Unbalanced entry: %s %s D=%s C=%s" % (journal, doc, tot_d, tot_c)
        if entry_date is None:
            entry_date = posting
        self.cur.execute(
            """INSERT INTO journal_entries
               (entry_id, company_id, fiscal_year_id, journal_code, document_number,
                entry_date, posting_date, due_date, description, total_amount,
                payment_method, reconciliation_code, validated, customer_id, supplier_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (self.eid, 1, self.fiscal_year_of(posting), journal, doc,
             entry_date.isoformat(), posting.isoformat(),
             due.isoformat() if due else None,
             description, tot_d, method, recon, validated, customer_id, supplier_id))
        for (account, debit, credit, ld, lr) in lines:
            self.lid += 1
            self.cur.execute(
                """INSERT INTO journal_entry_lines
                   (line_id, entry_id, account_code, debit, credit,
                    line_description, reconciliation_code)
                   VALUES (?,?,?,?,?,?,?)""",
                (self.lid, self.eid, account, round(debit, 2), round(credit, 2), ld, lr))
        return self.eid


# ------------------------------------------------------------------
# Generation
# ------------------------------------------------------------------
def build():
    db_path = os.path.abspath(DB_FILE)
    if os.path.exists(db_path):
        os.remove(db_path)
    for ext in ("-wal", "-shm"):
        p = db_path + ext
        if os.path.exists(p):
            os.remove(p)

    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA_SQL)
    cur = conn.cursor()

    # ---- Reference data -------------------------------------------
    cur.execute(
        """INSERT INTO companies (company_id, company_name, legal_form,
           registration_number, industry_code, vat_number, address, postal_code,
           city, phone, email) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (1, "Harborview Trading Ltd", "Ltd", "08412675", "4690",
         "GB731945082", "24 Merchant Quay", "BS1 6QF", "Bristol",
         "0117 946 0824", "accounts@harborviewtrading.co.uk"))

    for i, year in enumerate(YEARS, start=1):
        cur.execute(
            "INSERT INTO fiscal_years VALUES (?,?,?,?,?,?)",
            (i, 1, year, date(year, 1, 1).isoformat(),
             date(year, 12, 31).isoformat(), 1 if year < YEARS[-1] else 0))

    cur.executemany("INSERT INTO chart_of_accounts VALUES (?,?,?,?,?)", CHART)
    cur.executemany("INSERT INTO journals VALUES (?,?,?,?)", JOURNALS)

    # ---- Customers -------------------------------------------------
    customers = []
    n_customers = 38
    used = set()
    for i in range(1, n_customers + 1):
        city, pc = random.choice(CITIES)
        act = random.choice(CUSTOMER_ACTIVITIES)
        form = random.choice(LEGAL_FORMS)
        while True:
            name = "%s %s %s" % (random.choice(NAME_WORDS), act, form)
            if name not in used:
                used.add(name)
                break
        cur.execute(
            """INSERT INTO customers (customer_id, customer_code, name,
               registration_number, address, postal_code, city, phone, email,
               account_code, credit_limit, payment_terms_days, active, created_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, "CUS%03d" % i, name, rnd_regnum(),
             "%d %s" % (random.randint(1, 140), random.choice(
                 ["High Street", "Station Road", "Victoria Road",
                  "Church Lane", "Mill Road", "Queensway"])),
             pc, city, rnd_phone(),
             "accounts@%s%d.co.uk" % (act.split()[0].lower(), i),
             "411", random.choice([5000, 10000, 15000, 25000, 40000]),
             random.choice([30, 30, 30, 45, 60]), 1,
             date(2022, random.randint(1, 12), random.randint(1, 28)).isoformat()))
        customers.append(i)

    # ---- Suppliers --------------------------------------------------
    suppliers = []
    supplier_account = {}
    n_suppliers = 15
    for i in range(1, n_suppliers + 1):
        city, pc = random.choice(CITIES)
        stype, acct = random.choice(SUPPLIER_TYPES)
        name = "%s %s" % (random.choice(NAME_WORDS), stype)
        cur.execute(
            """INSERT INTO suppliers (supplier_id, supplier_code, name,
               registration_number, address, postal_code, city, phone, email,
               account_code, payment_terms_days, active, created_date)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i, "SUP%03d" % i, name, rnd_regnum(),
             "%d %s" % (random.randint(1, 60),
                        random.choice(["Industrial Estate", "Enterprise Way",
                                       "Trading Park", "Depot Road"])),
             pc, city, rnd_phone(),
             "sales@%s%d.co.uk" % (stype.split()[0].lower(), i),
             "401", random.choice([30, 30, 45, 60]), 1,
             date(2022, random.randint(1, 12), random.randint(1, 28)).isoformat()))
        suppliers.append(i)
        supplier_account[i] = acct

    # dedicated landlord for the monthly rent
    landlord_id = suppliers[0]
    cur.execute("UPDATE suppliers SET name=?, account_code='6132' WHERE supplier_id=?",
                ("Oakfield Estates Ltd", landlord_id))
    supplier_account[landlord_id] = "6132"

    book = Book(conn)

    seq = {"SI": 0, "PI": 0, "BK": 0, "CS": 0}
    recon_seq = [0]

    def next_recon():
        recon_seq[0] += 1
        return "R%05d" % recon_seq[0]

    open_recv = []   # customer receivables awaiting settlement
    open_pay = []    # supplier payables awaiting settlement
    vat = {}         # (year, quarter) -> {"out": x, "inp": y}

    def vat_bucket(d):
        q = (d.month - 1) // 3 + 1
        return vat.setdefault((d.year, q), {"out": 0.0, "inp": 0.0})

    # ---- Opening entry (share capital in the bank) ------------------
    book.entry("OB", "OB-2023", date(2023, 1, 1), "Opening balance: share capital",
               [("512", 45000, 0, "Bank - opening funds", None),
                ("101", 0, 45000, "Share capital", None)])

    first_purchase_doc = None  # reused by the duplicate-document anomaly

    # ---- Monthly loop ------------------------------------------------
    for year in YEARS:
        monthly_gross = GROSS_PAYROLL_PER_YEAR.get(year, 7100.0)
        for month in range(1, 13):
            # VAT return for the previous quarter (filed the month after quarter end)
            if month in (4, 7, 10):
                file_vat_return(book, year, (month - 1) // 3, vat, seq)
            if month == 1 and (year - 1) in YEARS:
                file_vat_return(book, year - 1, 4, vat, seq,
                                filing_date=date(year, 1, 24))

            dim = 28
            yidx = year - YEARS[0]
            # ---------- SALES (trend + seasonality driven) ----------
            target_sales = (BASE_SALES_NET * (GROWTH ** yidx)
                            * SEASON[month] * random.uniform(0.93, 1.07))
            total_sales = 0.0
            while total_sales < target_sales:
                d = date(year, month, random.randint(1, dim))
                cid = random.choice(customers)
                rate = weighted(VAT_RATES)
                # one or two revenue lines
                if random.random() < 0.25:
                    net1 = round(random.uniform(350, 4200), 2)
                    net2 = round(random.uniform(180, 1600), 2)
                    rev_lines = [("707", 0, net1, "Sale of goods", None),
                                 ("706", 0, net2, "Services rendered", None)]
                    net = round(net1 + net2, 2)
                else:
                    net = round(random.uniform(250, 4800), 2)
                    account = weighted([("707", 70), ("706", 25), ("708", 5)])
                    lbl = {"707": "Sale of goods", "706": "Services rendered",
                           "708": "Other operating income"}[account]
                    rev_lines = [(account, 0, net, lbl, None)]
                total_sales += net
                vat_out = round(net * rate, 2)
                gross = round(net + vat_out, 2)
                seq["SI"] += 1
                doc = "SI%02d-%04d" % (year % 100, seq["SI"])
                recon = next_recon()
                terms = random.choice([30, 30, 45, 60])
                due = d + timedelta(days=terms)
                lines = [("411", gross, 0, "Customer - invoice %s" % doc, recon)] + rev_lines
                if vat_out > 0:
                    lines.append(("44571", 0, vat_out,
                                  "Output VAT %.1f%%" % (rate * 100), None))
                book.entry("SA", doc, d, "Sales invoice %s" % doc, lines,
                           due=due, customer_id=cid, recon=recon)
                vat_bucket(d)["out"] += vat_out
                open_recv.append(dict(amount=gross, due=due, recon=recon,
                                      customer_id=cid, doc=doc))

            # ---------- PURCHASES (correlated to sales) ----------
            target_purchases = target_sales * random.uniform(0.48, 0.62)
            total_purchases = 0.0
            while total_purchases < target_purchases:
                d = date(year, month, random.randint(1, dim))
                sid = random.choice([s for s in suppliers if s != landlord_id])
                account = weighted([(a, w) for (a, _l, w) in PURCHASE_ACCOUNTS])
                lbl = next(l for (a, l, _w) in PURCHASE_ACCOUNTS if a == account)
                rate = 0.20 if random.random() < 0.9 else 0.05
                net = round(random.uniform(120, 4800), 2)
                total_purchases += net
                vat_in = round(net * rate, 2)
                gross = round(net + vat_in, 2)
                seq["PI"] += 1
                doc = "PI%02d-%04d" % (year % 100, seq["PI"])
                if first_purchase_doc is None:
                    first_purchase_doc = doc
                recon = next_recon()
                due = d + timedelta(days=random.choice([30, 30, 45, 60]))
                book.entry("PU", doc, d, "Purchase invoice %s" % doc,
                           [(account, net, 0, lbl, None),
                            ("44566", vat_in, 0, "Input VAT", None),
                            ("401", 0, gross, "Supplier - invoice %s" % doc, recon)],
                           due=due, supplier_id=sid, recon=recon)
                vat_bucket(d)["inp"] += vat_in
                open_pay.append(dict(amount=gross, due=due, recon=recon,
                                     supplier_id=sid, doc=doc))

            # ---------- RENT (monthly) ----------
            d = date(year, month, 3)
            net = 1650.0
            vat_in = round(net * 0.20, 2)
            gross = round(net + vat_in, 2)
            seq["PI"] += 1
            doc = "PI%02d-%04d" % (year % 100, seq["PI"])
            recon = next_recon()
            book.entry("PU", doc, d, "Rent %02d/%d" % (month, year),
                       [("6132", net, 0, "Office and warehouse rent", None),
                        ("44566", vat_in, 0, "Input VAT", None),
                        ("401", 0, gross, "Oakfield Estates Ltd", recon)],
                       due=d + timedelta(days=7), supplier_id=landlord_id, recon=recon)
            vat_bucket(d)["inp"] += vat_in
            open_pay.append(dict(amount=gross, due=d + timedelta(days=7),
                                 recon=recon, supplier_id=landlord_id, doc=doc))

            # ---------- PAYROLL (monthly) ----------
            d_pay = date(year, month, 28)
            gross_pay = round(monthly_gross * random.uniform(0.97, 1.06), 2)
            emp_deductions = round(gross_pay * 0.24, 2)
            employer_costs = round(gross_pay * 0.31, 2)
            net_pay = round(gross_pay - emp_deductions, 2)
            book.entry("PY", "PAY-%d-%02d" % (year, month), d_pay,
                       "Salaries %02d/%d" % (month, year),
                       [("641", gross_pay, 0, "Gross salaries", None),
                        ("645", employer_costs, 0, "Employer contributions", None),
                        ("421", 0, net_pay, "Net pay due", None),
                        ("431", 0, round(emp_deductions + employer_costs, 2),
                         "Social security payable", None)])
            # net pay transfer
            seq["BK"] += 1
            book.entry("BK", "BK%02d-%04d" % (year % 100, seq["BK"]), d_pay,
                       "Salaries paid %02d/%d" % (month, year),
                       [("421", net_pay, 0, "Net pay settled", None),
                        ("512", 0, net_pay, "Bank", None)], method="Bank transfer")
            # social security payment
            seq["BK"] += 1
            d_ss = date(year, month, 15)
            book.entry("BK", "BK%02d-%04d" % (year % 100, seq["BK"]), d_ss,
                       "Social security payment %02d/%d" % (month, year),
                       [("431", round(emp_deductions + employer_costs, 2), 0,
                         "HMRC / pension remittance", None),
                        ("512", 0, round(emp_deductions + employer_costs, 2),
                         "Bank", None)], method="Bank transfer")

            # ---------- CUSTOMER RECEIPTS ----------
            month_end = date(year, month, dim)
            still_open = []
            for r in open_recv:
                if r["due"] <= month_end and random.random() < 0.88:
                    seq["BK"] += 1
                    dpay = r["due"] + timedelta(days=random.randint(0, 9))
                    if dpay > date(YEARS[-1], 12, 31):
                        dpay = date(YEARS[-1], 12, 31)
                    book.entry("BK", "BK%02d-%04d" % (dpay.year % 100, seq["BK"]), dpay,
                               "Customer payment %s" % r["doc"],
                               [("512", r["amount"], 0, "Bank", None),
                                ("411", 0, r["amount"], "Receivable settled", r["recon"])],
                               method=random.choice(PAYMENT_METHODS),
                               customer_id=r["customer_id"], recon=r["recon"])
                else:
                    still_open.append(r)
            open_recv[:] = still_open

            # ---------- SUPPLIER PAYMENTS ----------
            still_open = []
            for p in open_pay:
                if p["due"] <= month_end and random.random() < 0.93:
                    seq["BK"] += 1
                    dpay = p["due"] + timedelta(days=random.randint(0, 6))
                    if dpay > date(YEARS[-1], 12, 31):
                        dpay = date(YEARS[-1], 12, 31)
                    book.entry("BK", "BK%02d-%04d" % (dpay.year % 100, seq["BK"]), dpay,
                               "Supplier payment %s" % p["doc"],
                               [("401", p["amount"], 0, "Payable settled", p["recon"]),
                                ("512", 0, p["amount"], "Bank", None)],
                               method=random.choice(PAYMENT_METHODS),
                               supplier_id=p["supplier_id"], recon=p["recon"])
                else:
                    still_open.append(p)
            open_pay[:] = still_open

            # ---------- PETTY CASH (small expenses) ----------
            for _ in range(random.randint(1, 2)):
                d = date(year, month, random.randint(1, dim))
                account, lbl = random.choice(
                    [("6064", "Office supplies"), ("626", "Postage"),
                     ("6257", "Client entertaining"), ("6251", "Travel fares")])
                amount = round(random.uniform(10, 140), 2)
                seq["CS"] += 1
                book.entry("CS", "CS%02d-%04d" % (year % 100, seq["CS"]), d,
                           "Petty cash - %s" % lbl.lower(),
                           [(account, amount, 0, lbl, None),
                            ("530", 0, amount, "Petty cash", None)], method="Cash")

            # quarterly float top-up from the bank
            if month in (1, 4, 7, 10):
                d = date(year, month, 2)
                seq["BK"] += 1
                book.entry("BK", "BK%02d-%04d" % (year % 100, seq["BK"]), d,
                           "Cash float top-up",
                           [("530", 350, 0, "Petty cash", None),
                            ("512", 0, 350, "Bank", None)], method="Bank transfer")

    # ---- Deliberate audit anomalies (unmarked) ----------------------
    if INCLUDE_ANOMALIES:
        add_anomalies(book, customers, first_purchase_doc)

    conn.commit()
    verify(conn)
    conn.close()


def file_vat_return(book, year, quarter, vat, seq, filing_date=None):
    b = vat.get((year, quarter))
    if not b:
        return
    out = round(b["out"], 2)
    inp = round(b["inp"], 2)
    if filing_date is None:
        m = quarter * 3 + 1
        filing_date = date(year, m, 22) if m <= 12 else date(year + 1, 1, 22)
    doc = "VAT-%d-Q%d" % (year, quarter)
    if out >= inp:
        payable = round(out - inp, 2)
        book.entry("GJ", doc, filing_date, "VAT return %d Q%d" % (year, quarter),
                   [("44571", out, 0, "Output VAT for the quarter", None),
                    ("44566", 0, inp, "Input VAT for the quarter", None),
                    ("44551", 0, payable, "VAT payable", None)])
        seq["BK"] += 1
        dpay = filing_date + timedelta(days=random.randint(2, 7))
        book.entry("BK", "BK%02d-%04d" % (dpay.year % 100, seq["BK"]), dpay,
                   "VAT payment %d Q%d" % (year, quarter),
                   [("44551", payable, 0, "VAT payable settled", None),
                    ("512", 0, payable, "Bank", None)], method="Bank transfer")
    else:
        credit = round(inp - out, 2)
        book.entry("GJ", doc, filing_date,
                   "VAT return %d Q%d (credit)" % (year, quarter),
                   [("44571", out, 0, "Output VAT for the quarter", None),
                    ("44567", credit, 0, "VAT credit carried forward", None),
                    ("44566", 0, inp, "Input VAT for the quarter", None)])


def add_anomalies(book, customers, dup_doc):
    """Deliberate erroneous entries for audit-style questions.

    IMPORTANT: nothing in the stored data marks these as anomalies --
    they read like ordinary entries. The build log below is the only map.
    """
    cid = customers[0]
    # 1) UNBALANCED entry (VAT line forgotten: debits 1,440 vs credits 1,200)
    book.entry("SA", "SI24-9001", date(2024, 5, 9), "Sales invoice SI24-9001",
               [("411", 1440.00, 0, "Customer - invoice SI24-9001", None),
                ("707", 0, 1200.00, "Sale of goods", None)],
               customer_id=cid, allow_unbalanced=True)
    # 2) DUPLICATE document number (same as an existing purchase invoice)
    if dup_doc:
        book.entry("PU", dup_doc, date(2024, 6, 17), "Purchase invoice %s" % dup_doc,
                   [("607", 640.00, 0, "Goods for resale", None),
                    ("44566", 128.00, 0, "Input VAT", None),
                    ("401", 0, 768.00, "Supplier - invoice %s" % dup_doc, None)])
    # 3) SUSPICIOUS negligible amount (0.01)
    book.entry("CS", "CS24-9003", date(2024, 7, 8), "Petty cash - office supplies",
               [("6064", 0.01, 0, "Office supplies", None),
                ("530", 0, 0.01, "Petty cash", None)])
    # 4) ABERRANT VAT amount (32% of net, labelled as standard output VAT)
    book.entry("SA", "SI24-9004", date(2024, 8, 19), "Sales invoice SI24-9004",
               [("411", 1320.00, 0, "Customer - invoice SI24-9004", None),
                ("707", 0, 1000.00, "Sale of goods", None),
                ("44571", 0, 320.00, "Output VAT 20.0%", None)],
               customer_id=cid)
    # 5) LATE POSTING into a closed fiscal year (posted 2023, keyed in 2024)
    book.entry("GJ", "ADJ-2023-11", date(2023, 6, 12),
               "Professional fees adjustment",
               [("6226", 520.00, 0, "Professional fees", None),
                ("401", 0, 520.00, "Supplier balance", None)],
               entry_date=date(2024, 11, 25))


def verify(conn):
    cur = conn.cursor()

    def one(q):
        return cur.execute(q).fetchone()[0]

    print("=" * 56)
    print("LEDGER BUILD REPORT (seed %d)" % SEED)
    print("=" * 56)
    for label, q in [
        ("Companies", "SELECT COUNT(*) FROM companies"),
        ("Fiscal years", "SELECT COUNT(*) FROM fiscal_years"),
        ("Chart of accounts", "SELECT COUNT(*) FROM chart_of_accounts"),
        ("Journals", "SELECT COUNT(*) FROM journals"),
        ("Customers", "SELECT COUNT(*) FROM customers"),
        ("Suppliers", "SELECT COUNT(*) FROM suppliers"),
        ("Journal entries", "SELECT COUNT(*) FROM journal_entries"),
        ("Entry lines", "SELECT COUNT(*) FROM journal_entry_lines"),
    ]:
        print("  %-22s : %d" % (label, one(q)))

    td = one("SELECT COALESCE(SUM(debit),0)  FROM journal_entry_lines")
    tc = one("SELECT COALESCE(SUM(credit),0) FROM journal_entry_lines")
    print("-" * 56)
    print("  Total debits  : %14.2f" % td)
    print("  Total credits : %14.2f" % tc)
    print("  Global gap    : %14.2f  %s" % (
        td - tc, "(= deliberate anomalies)" if abs(td - tc) > 0.005 else "(balanced)"))

    rows = cur.execute("""
        SELECT entry_id, document_number, description, imbalance
        FROM journal_control WHERE ABS(imbalance) > 0.005
        ORDER BY entry_id""").fetchall()
    print("-" * 56)
    print("  Unbalanced entries : %d" % len(rows))
    for r in rows:
        print("    #%d %-12s gap=%.2f  | %s" % (r[0], r[1], r[3], r[2]))

    print("-" * 56)
    print("  Income statement by year:")
    for r in cur.execute("SELECT year, total_revenue, total_expenses, net_result"
                         " FROM income_statement"):
        print("    %s  Revenue=%12.2f  Expenses=%12.2f  Net=%12.2f"
              % (r[0], r[1], r[2], r[3]))
    print("=" * 56)


if __name__ == "__main__":
    build()
    print("\nDatabase generated: %s" % os.path.abspath(DB_FILE))
