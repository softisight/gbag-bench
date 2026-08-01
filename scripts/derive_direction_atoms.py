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
  5. v1.2: a CUMULATIVE column (SUM(...) OVER (... ORDER BY ...) in the
     gold SQL, or a fully monotone series) is never bucketed on its
     level. A running total of positive amounts rises by construction,
     so its level direction is information-free at best and inverted at
     worst. The bucket is computed on per-period first differences (the
     flux), zero-filled over the period calendar, first period dropped.
     Found by a second review: sakila-l10-02 was proposed "up" and
     ratified, while the activity it accumulates is "down". Full record
     in data/direction_atoms_review.md.

Output: data/direction_atoms_proposed.jsonl  (status: "proposed",
human_verdict: null). These are PROPOSED atoms, not ground truth,
until the hand-check measures extraction error. questions.jsonl is
not modified. Re-runs preserve reviewed records byte-for-byte when the
bucket and the derivation are unchanged; anything changed or new goes
back to "proposed".

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

# --- v1.2: cumulative-column rule (see direction_atoms_review.md) ------------
# Proof of construction: an unbounded SUM window ordered in time. A bounded
# frame ("3 PRECEDING") is a moving window, not a cumul, and must not match.
CUMULATIVE_SQL = re.compile(
    r"(?is)\bsum\s*\([^()]*\)\s*over\s*\(([^()]*\border\s+by\b[^()]*)\)")
BOUNDED_FRAME = re.compile(r"(?i)\b\d+\s+preceding\b")
CUMULATIVE_NAME_HINT = re.compile(r"(?i)running|cumul|balance")
MIN_MONO_POINTS = 8         # a monotone series shorter than this is not
                            # treated as a cumul (too little evidence)

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


def sql_has_cumulative_window(sql):
    """Proof of construction: an unbounded SUM window ordered in time."""
    for m in CUMULATIVE_SQL.finditer(sql):
        if not BOUNDED_FRAME.search(m.group(1)):
            return True
    return False


def is_monotone_nondecreasing(values):
    """Form index: a real activity series is never perfectly monotone."""
    if len(values) < MIN_MONO_POINTS:
        return False
    return (all(a <= b for a, b in zip(values, values[1:]))
            and values[-1] > values[0])


def _period_key(label, grain):
    return str(label)[:7] if grain == "month" else str(label)[:10]


def _fill_periods(keys, grain):
    """Every period between the first and last key, so absent periods count
    as zero flux -- true by construction for a cumul: it does not move when
    nothing happens."""
    if grain == "month":
        y0, m0 = int(keys[0][:4]), int(keys[0][5:7])
        y1, m1 = int(keys[-1][:4]), int(keys[-1][5:7])
        out, cur = [], y0 * 12 + (m0 - 1)
        while cur <= y1 * 12 + (m1 - 1):
            out.append(f"{cur // 12:04d}-{cur % 12 + 1:02d}")
            cur += 1
        return out
    import datetime as _dt
    d0 = _dt.date.fromisoformat(keys[0])
    d1 = _dt.date.fromisoformat(keys[-1])
    return [(d0 + _dt.timedelta(days=i)).isoformat()
            for i in range((d1 - d0).days + 1)]


def cumulative_flux(rows, temporal, vi):
    """Per-period first differences of a cumulative column.

    Last cumul of each period, differenced = the flux of that period
    (identical to SUM(value) GROUP BY period; verified on sakila). The
    first period is dropped: its diff-against-zero is the opening value,
    the partial-first-period trap in another form. Month grain when the
    span offers enough months, day grain otherwise.
    Returns (flux, meta) or (None, reason) when no calendar can be built.
    """
    last = {}
    for r in rows:
        if r[vi] is not None:
            last[_period_key(r[temporal], "month")] = r[vi]
    grain = "month"
    if len(last) < MIN_MONO_POINTS:
        last = {}
        for r in rows:
            if r[vi] is not None:
                last[_period_key(r[temporal], "day")] = r[vi]
        grain = "day"
    keys = sorted(last)
    if len(keys) < 2:
        return None, "cumulative column but fewer than 2 periods"
    try:
        calendar = _fill_periods(keys, grain)
    except ValueError:
        return None, "cumulative column but period labels not calendar-parsable"
    flux, prev, filled = [], None, 0
    for p in calendar:
        cur = last.get(p)
        if cur is None:
            cur = prev              # no rows: the cumul did not move
            filled += 1
        if prev is not None:
            flux.append(round(cur - prev, 6))
        prev = cur
    return flux, {"grain": grain, "periods": len(calendar),
                  "zero_filled_periods": filled}


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
                f"opposite segment signs => mixed; v1.2: cumulative columns "
                f"bucketed on per-period flux, never on level"
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

    # --- v1.2: cumulative columns are judged on flux, never on level --------
    sql_cumul = sql_has_cumulative_window(q["gold_sql"])
    cumul_cols = [vi for vi in value_cols
                  if is_monotone_nondecreasing(
                      [r[vi] for r in rows if r[vi] is not None])]
    cumul_signal = ("sql+form" if sql_cumul else "form only") \
        if cumul_cols else None
    if sql_cumul and not cumul_cols:
        # Signed cumul (e.g. a running balance): the construction proof is
        # there but the form index cannot see it. Explicit carrier rule:
        # a single value column, else a single name-hint match, else refuse.
        named = [vi for vi in value_cols
                 if CUMULATIVE_NAME_HINT.search(columns[vi])]
        if len(value_cols) == 1:
            cumul_cols = [value_cols[0]]
            cumul_signal = "sql+single-value-column"
        elif len(named) == 1:
            cumul_cols = named
            cumul_signal = "sql+name-hint"
        else:
            atom["provenance"]["notes"].append(
                "cumulative window in gold SQL but carrier column "
                "unidentifiable: refusing to bucket any level (v1.2 rule)")
            return atom
    if cumul_cols:
        atom["provenance"]["notes"].append(
            "cumulative column(s) "
            + ", ".join(f"'{columns[vi]}'" for vi in cumul_cols)
            + f" judged on per-period flux, never on level "
            + f"(signal: {cumul_signal})")

    if segment is not None:
        if sql_cumul or cumul_cols:
            atom["provenance"]["notes"].append(
                "cumulative column in segmented shape: per-segment flux not "
                "implemented, refusing to bucket levels (v1.2 rule)")
            atom["bucket"] = "too-small-to-claim"
            return atom
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
        if vi in cumul_cols:
            flux, meta = cumulative_flux(rows, temporal, vi)
            if flux is None:
                atom["provenance"]["notes"].append(
                    f"'{columns[vi]}': {meta}; refusing to bucket its level")
                continue
            b, head, tail, k = series_bucket(flux)
            entry = {"bucket": b, "points": len(vals),
                     "treatment": "cumulative-flux",
                     "flux_points": len(flux), **meta,
                     "level_first": vals[0], "level_last": vals[-1]}
            if head is not None:
                entry.update({"flux_head_mean": round(head, 4),
                              "flux_tail_mean": round(tail, 4),
                              "window_points": k})
        else:
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
    if cumul_cols:
        atom["confidence"] = "medium"   # derived treatment, review required
    atom["evidence"] = {
        "mode": "single-series" if len(value_cols) == 1 else "multi-series",
        "series": series_out,
        "first_label": str(rows[0][temporal]),
        "last_label": str(rows[-1][temporal]),
    }
    return atom


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", nargs="+", default=[
        str(ROOT / "data" / "questions.jsonl"),
        str(ROOT / "data" / "questions-heldout.jsonl"),
    ])
    ap.add_argument("--db-dir", default=str(ROOT / "databases"))
    ap.add_argument("--output",
                    default=str(ROOT / "data" / "direction_atoms_proposed.jsonl"))
    ap.add_argument("--only", help="single question id")
    args = ap.parse_args()

    questions = []
    for path in args.dataset:
        with open(path, encoding="utf-8") as f:
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

    if args.only:
        print("\n--only mode: no file written")
        return

    # Preserve hand-check verdicts: an atom whose bucket is unchanged and
    # whose derivation involved no cumulative treatment keeps its reviewed
    # record byte-for-byte. Anything changed or new goes back to "proposed".
    prev = {}
    out_path = Path(args.output)
    if out_path.exists():
        with open(out_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    a = json.loads(line)
                    prev[a["id"]] = a
    final, kept, reproposed = [], 0, 0
    for atom in atoms:
        old = prev.get(atom["id"])
        uses_flux = any(
            s.get("treatment") == "cumulative-flux"
            for s in atom.get("evidence", {}).get("series", {}).values())
        if (old and old.get("status") == "reviewed"
                and old.get("bucket") == atom["bucket"] and not uses_flux):
            final.append(old)
            kept += 1
        else:
            if old and old.get("bucket") != atom["bucket"]:
                atom["provenance"]["notes"].append(
                    f"changed from '{old['bucket']}' (hand-checked under "
                    f"v1.1) by the v1.2 cumulative rule")
                reproposed += 1
            elif old:
                # Same bucket, regenerated record: keep historical change
                # notes so a re-run does not erase the audit trail.
                for n in old.get("provenance", {}).get("notes", []):
                    if (n.startswith("changed from")
                            and n not in atom["provenance"]["notes"]):
                        atom["provenance"]["notes"].append(n)
            final.append(atom)
    atoms = final

    with open(args.output, "w", encoding="utf-8") as f:
        for atom in atoms:
            f.write(json.dumps(atom, ensure_ascii=True) + "\n")

    print("\nBuckets:", ", ".join(f"{k}={v}" for k, v in sorted(counts.items())))
    print(f"Wrote {len(atoms)} atoms to {args.output} "
          f"({kept} reviewed records preserved, {reproposed} re-proposed "
          f"after a bucket change)")
    print("These are PROPOSED atoms. Hand-check before any judge integration.")


if __name__ == "__main__":
    main()
