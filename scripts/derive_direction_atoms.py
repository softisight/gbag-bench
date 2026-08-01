#!/usr/bin/env python3
"""Derive PROPOSED direction atoms from gold-SQL result sets.

Pilot for the "must-preserve atoms" extension discussed in issue #1.
Direction is the one atom class computable from the result set alone,
uniformly across all 35 questions, regardless of SQL complexity.

Deliberately boring, by design:
  1. Execute the gold SQL, normalize the result into ordered points
     (label, value, optional segment).
  2. Compute a COARSE bucket only: up / down / flat / mixed /
     too-small-to-claim / not-applicable. Nothing finer.
  3. Conservative rules: small wiggles are flat; one segment up and one
     down is mixed, never "overall growth".
  4. Evidence and provenance stored beside every bucket, so a failure
     can be traced to either the answer model losing the atom or this
     extractor inventing it.

Output: data/direction_atoms_proposed.jsonl  (status: "proposed",
human_verdict: null). These are PROPOSED atoms, not ground truth,
until the hand-check measures extraction error. questions.jsonl is
not modified.

Usage:
    python scripts/derive_direction_atoms.py
    python scripts/derive_direction_atoms.py --only sakila-l9-02
"""

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --- Tunable constants (documented, deliberate) ------------------------------
FLAT_REL_THRESHOLD = 0.05   # |relative change| below 5% is flat
MIN_POINTS_FOR_TREND = 3    # fewer ordered points cannot claim a trend
WINDOW_FRACTION = 0.25      # endpoint windows = first/last quarter of points
MIN_SEGMENT_POINTS = 3      # a segment thinner than this is ignored

DATE_PATTERNS = [
    re.compile(r"^\d{4}$"),                    # 2005
    re.compile(r"^\d{4}-\d{2}$"),              # 2005-05
    re.compile(r"^\d{4}-\d{2}-\d{2}"),         # 2005-05-24 (+ optional time)
    re.compile(r"^\d{4}[-/]?Q[1-4]$", re.I),   # 2005-Q1
]
DATE_NAME_HINT = re.compile(r"year|month|date|day|quarter|week|period", re.I)
ID_NAME = re.compile(r"(^id$|_id$|^id_)", re.I)


def is_dateish(value) -> bool:
    s = str(value)
    return any(p.match(s) for p in DATE_PATTERNS)


def classify_columns(columns, rows):
    """Return (temporal_col, segment_col, value_cols, notes) as indices."""
    notes = []
    n = len(columns)
    non_null = [[r[i] for r in rows if r[i] is not None] for i in range(n)]

    temporal = None
    for i in range(n):
        vals = non_null[i]
        if vals and all(is_dateish(v) for v in vals):
            temporal = i
            if DATE_NAME_HINT.search(columns[i]):
                notes.append(f"temporal column '{columns[i]}' by pattern + name hint")
            else:
                notes.append(f"temporal column '{columns[i]}' by value pattern")
            break  # leftmost wins

    value_cols = []
    for i in range(n):
        if i == temporal:
            continue
        vals = non_null[i]
        if not vals or not all(isinstance(v, (int, float)) for v in vals):
            continue
        if ID_NAME.search(columns[i]):
            notes.append(f"numeric column '{columns[i]}' skipped (id-like name)")
            continue
        value_cols.append(i)

    segment = None
    for i in range(n):
        if i == temporal or i in value_cols:
            continue
        vals = non_null[i]
        if vals and all(isinstance(v, str) for v in vals):
            distinct = len(set(vals))
            if 1 < distinct < len(rows):
                segment = i
                notes.append(f"segment column '{columns[i]}' ({distinct} distinct)")
                break  # leftmost wins

    return temporal, segment, value_cols, notes


def window_means(values):
    """Mean of the first and last WINDOW_FRACTION of the points."""
    k = max(1, int(len(values) * WINDOW_FRACTION))
    head = sum(values[:k]) / k
    tail = sum(values[-k:]) / k
    return head, tail, k


def series_bucket(values):
    """Coarse direction for one ordered numeric series."""
    if len(values) < MIN_POINTS_FOR_TREND:
        return "too-small-to-claim", None, None, None
    head, tail, k = window_means(values)
    if k < 2:
        # Guard added after the hand-check (see direction_atoms_review.md):
        # a 1-point window IS an endpoint comparison, the exact trap the
        # window means exist to avoid. Below 8 points we refuse to claim.
        return "too-small-to-claim", head, tail, k
    if head == 0:
        if tail == 0:
            return "flat", head, tail, k
        return ("up" if tail > 0 else "down"), head, tail, k
    rel = (tail - head) / abs(head)
    if abs(rel) < FLAT_REL_THRESHOLD:
        return "flat", head, tail, k
    return ("up" if rel > 0 else "down"), head, tail, k


def combine(buckets):
    """Combine per-series/per-segment buckets. Opposite signs => mixed."""
    real = [b for b in buckets if b in ("up", "down", "flat")]
    if not real:
        return "too-small-to-claim"
    if "up" in real and "down" in real:
        return "mixed"
    for sign in ("up", "down"):
        if sign in real:
            return sign
    return "flat"


def derive_for_question(q, db_dir):
    db = db_dir / f"{q['database']}.sqlite"
    con = sqlite3.connect(str(db))
    try:
        cur = con.execute(q["gold_sql"])
        columns = [d[0] for d in cur.description]
        rows = cur.fetchall()
    finally:
        con.close()

    atom = {
        "id": q["id"],
        "category": q.get("category"),
        "atom_type": "direction",
        "status": "proposed",
        "human_verdict": None,
        "bucket": "not-applicable",
        "confidence": "low",
        "evidence": {},
        "provenance": {
            "source": "derive_direction_atoms.py",
            "rule": (
                f"window means (first/last {int(WINDOW_FRACTION*100)}% of points), "
                f"flat if |rel change| < {FLAT_REL_THRESHOLD:.0%}, "
                f"opposite segment signs => mixed"
            ),
            "row_count": len(rows),
            "columns": columns,
            "notes": [],
        },
    }

    temporal, segment, value_cols, notes = classify_columns(columns, rows)
    atom["provenance"]["notes"] = notes

    if temporal is None:
        atom["provenance"]["notes"].append(
            "no temporal column detected: direction not applicable "
            "(ranking / point aggregate shape)"
        )
        return atom
    if not value_cols:
        atom["provenance"]["notes"].append("no usable numeric value column")
        return atom

    # Sort once by temporal label (ISO-style labels sort lexicographically).
    rows = sorted(rows, key=lambda r: str(r[temporal]))

    if segment is not None:
        vi = value_cols[0]  # segmented: first value column only, noted
        if len(value_cols) > 1:
            atom["provenance"]["notes"].append(
                f"multiple value columns, segmented mode uses '{columns[vi]}' only"
            )
        per_segment = {}
        for r in rows:
            if r[segment] is None or r[vi] is None:
                continue
            per_segment.setdefault(str(r[segment]), []).append(r[vi])
        seg_out, buckets = {}, []
        for name, vals in sorted(per_segment.items()):
            if len(vals) < MIN_SEGMENT_POINTS:
                continue
            b, head, tail, k = series_bucket(vals)
            seg_out[name] = {"bucket": b, "points": len(vals),
                             "head_mean": head, "tail_mean": tail}
            buckets.append(b)
        atom["bucket"] = combine(buckets)
        atom["confidence"] = "medium" if len(seg_out) >= 2 else "low"
        atom["evidence"] = {
            "mode": "segmented",
            "segment_column": columns[segment],
            "value_column": columns[vi],
            "segments_evaluated": len(seg_out),
            "segment_buckets": seg_out,
            "first_label": str(rows[0][temporal]),
            "last_label": str(rows[-1][temporal]),
        }
        return atom

    series_out, buckets = {}, []
    for vi in value_cols:
        vals = [r[vi] for r in rows if r[vi] is not None]
        b, head, tail, k = series_bucket(vals)
        entry = {"bucket": b, "points": len(vals)}
        if head is not None:
            entry.update({
                "head_mean": round(head, 4), "tail_mean": round(tail, 4),
                "window_points": k,
                "first_value": vals[0], "last_value": vals[-1],
            })
        series_out[columns[vi]] = entry
        buckets.append(b)
    atom["bucket"] = combine(buckets)
    atom["confidence"] = ("high" if len(value_cols) == 1
                          and len(rows) >= 2 * MIN_POINTS_FOR_TREND
                          else "medium")
    atom["evidence"] = {
        "mode": "single-series" if len(value_cols) == 1 else "multi-series",
        "series": series_out,
        "first_label": str(rows[0][temporal]),
        "last_label": str(rows[-1][temporal]),
    }
    return atom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=str(ROOT / "data" / "questions.jsonl"))
    ap.add_argument("--db-dir", default=str(ROOT / "databases"))
    ap.add_argument("--output",
                    default=str(ROOT / "data" / "direction_atoms_proposed.jsonl"))
    ap.add_argument("--only", help="single question id")
    args = ap.parse_args()

    questions = []
    with open(args.dataset, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                questions.append(json.loads(line))
    if args.only:
        questions = [q for q in questions if q["id"] == args.only]

    atoms, counts = [], {}
    for q in questions:
        try:
            atom = derive_for_question(q, Path(args.db_dir))
        except Exception as e:  # a broken derivation must be visible, not fatal
            atom = {"id": q["id"], "atom_type": "direction",
                    "status": "error", "human_verdict": None,
                    "bucket": "error", "confidence": "none",
                    "evidence": {}, "provenance": {"error": str(e)}}
        atoms.append(atom)
        counts[atom["bucket"]] = counts.get(atom["bucket"], 0) + 1
        ev = atom.get("evidence", {})
        extra = ""
        if ev.get("mode") == "segmented":
            extra = f" segments={ev.get('segments_evaluated')}"
        elif "series" in ev:
            first = next(iter(ev["series"].values()), {})
            if "first_value" in first:
                extra = f" first={first['first_value']} last={first['last_value']}"
        print(f"{atom['id']:18s} {atom['bucket']:20s} "
              f"conf={atom['confidence']:6s}{extra}")

    with open(args.output, "w", encoding="utf-8") as f:
        for atom in atoms:
            f.write(json.dumps(atom, ensure_ascii=True) + "\n")

    print("\nBuckets:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"Wrote {len(atoms)} proposed atoms to {args.output}")
    print("These are PROPOSED atoms. Hand-check before any judge integration.")


if __name__ == "__main__":
    main()
