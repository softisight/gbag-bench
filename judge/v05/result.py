"""The judge's whole universe: the SQL result, at the two scopes a claim can speak about.

`shown` = the rows the answering model received (the first CAP rows, in the SQL's order —
the runner did fetchmany(200)); `full` = the complete result. Nothing outside the result
is ever looked up: a claim about something the result does not contain is undecided.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB_FILES = {
    "sakila": ROOT / "databases" / "sakila.sqlite",
    "chinook": ROOT / "databases" / "chinook.sqlite",
    "northwind": ROOT / "databases" / "northwind.sqlite",
    "ledger": ROOT / "databases" / "ledger.sqlite",
}
CAP = 200


@dataclass
class Result:
    columns: list[str]
    full: list[tuple]
    shown: list[tuple] = field(default_factory=list)

    @property
    def truncated(self) -> bool:
        return len(self.full) > len(self.shown)

    def rows(self, scope: str) -> list[tuple]:
        return self.shown if scope == "rows_shown" else self.full

    def col(self, name: str) -> int | None:
        """Column index by name, tolerant on case, spaces and underscores."""
        norm = lambda s: "".join(ch for ch in s.lower() if ch.isalnum())
        want = norm(name or "")
        for i, c in enumerate(self.columns):
            if norm(c) == want:
                return i
        return None

    def numeric(self, idx: int, scope: str) -> list[float]:
        return [float(r[idx]) for r in self.rows(scope)
                if isinstance(r[idx], (int, float)) and not isinstance(r[idx], bool)]

    def describe(self) -> str:
        """Column names, types and two example values — what the translator is told."""
        out = []
        for i, c in enumerate(self.columns):
            ex = [r[i] for r in self.shown[:2]]
            kind = "number" if all(isinstance(v, (int, float)) for v in ex if v is not None) else "text/date"
            out.append(f"- {c} ({kind}), e.g. {', '.join(repr(v) for v in ex)}")
        return "\n".join(out)


def load(question: dict) -> Result:
    db = next(k for k in DB_FILES if k in question["database"].lower())
    con = sqlite3.connect(f"file:{DB_FILES[db].as_posix()}?mode=ro", uri=True)
    try:
        cur = con.execute(question["gold_sql"].strip().rstrip(";"))
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()
    return Result(cols, rows, rows[:CAP])
