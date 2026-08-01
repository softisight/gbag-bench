# Direction atoms — pilot record (issue #1)

Pilot for the "must-preserve atoms" extension: derive a **direction** atom
(up / down / flat / mixed / too-small-to-claim / not-applicable) from each
question's gold-SQL result set, then hand-check every proposal before any
judge integration. Direction was chosen first because it is computable from
the result set alone (uniform across all 35 questions, whatever the SQL
complexity) and because inverted-direction answers are the catastrophic
failure class that motivated the benchmark.

Extractor: [`scripts/derive_direction_atoms.py`](../scripts/derive_direction_atoms.py).
Proposals + verdicts: [`data/direction_atoms_proposed.jsonl`](direction_atoms_proposed.jsonl).

## Protocol

1. Extractor v1: window means over the first/last 25 % of ordered points;
   |relative change| < 5 % = flat; opposite segment signs = mixed;
   < 3 points = too-small-to-claim. Evidence and provenance stored per atom.
2. Human review of all 35 proposals against the full result sets
   (not against the extractor's own evidence summaries).
3. Disagreements documented, rule amended, extractor re-run (v1.1).

## Hand-check result (extractor v1)

**Agreement: 8 / 9 on proposed atoms; 26 / 26 on not-applicable.**

| id | v1 bucket | Human verdict |
|---|---|---|
| northwind-l4-01 | flat | **agree** — endpoints rise +41 % (partial first month, the founding-failure trap) but 34-month window means differ < 5 %. The one case the whole atom class exists for. |
| chinook-l4-01 | flat | **agree** — endpoints +8.4 %, series near-constant across 60 months |
| chinook-l8-01 | flat | **agree** — ~1 invoice per 2–3 days, stable across 5 years |
| northwind-l8-01 | flat | **agree** — 2–6 orders/day, stable across 11 years |
| sakila-l8-01 | down | **agree** — activity ceases after 2005-08 (months of zeros, one final burst); endpoints 8 → 182 mislead, window means do not |
| sakila-l10-01 | down | **agree** — same series as l8-01 |
| sakila-l10-02 | up | **agree** — running total rises by construction |
| sakila-l9-02 | down | **agree with note** — all 16 category segments decline; **no category actually grows first-to-last month**, so the question's "3 strongest growth" premise is misleading relative to the data |
| sakila-l4-01 | down | **disagree** — 5 points with a data gap; a 25 % window of a 5-point series is 1 point, i.e. an endpoint comparison, the exact trap window means exist to avoid. Human verdict: too-small-to-claim. |

## Amendment after the hand-check

Guard added to `series_bucket`: **a window of fewer than 2 points refuses to
claim a direction** (returns too-small-to-claim). Effect: any series (or
segment) below 8 points is not given a direction.

Consequences on re-run (v1.1):

- `sakila-l4-01` down → **too-small-to-claim** (the disagreement, resolved)
- `sakila-l9-02` down → **too-small-to-claim** (consistency: its segments are
  5–6-point series, the same shape the human rejected in l4-01; the
  every-segment-declines observation stays recorded here)

## Final state (extractor v1.1)

| Bucket | Count | Questions |
|---|---|---|
| flat | 4 | chinook-l4-01, chinook-l8-01, northwind-l4-01, northwind-l8-01 |
| down | 2 | sakila-l8-01, sakila-l10-01 |
| up | 1 | sakila-l10-02 |
| too-small-to-claim | 2 | sakila-l4-01, sakila-l9-02 |
| not-applicable | 26 | rankings, point aggregates, joins; incl. the 3 RFM questions (category `trend` but segmentations, not series) |

7 enforceable direction atoms. Status of every atom: `reviewed`.

## What this pilot did NOT do yet

- No adversarial check (generate the opposite conclusion, verify the judge
  rejects it) — next step before judge integration.
- No judge-prompt integration; current scores are unaffected. Integrating
  atoms is a scoring change and requires a full re-judge before any
  comparison with existing leaderboard numbers.
- Atoms other than direction (entity, inclusion rule, time window,
  comparator) still need SQL-side extraction: 16/35 gold queries are flat
  SELECTs, 15 are CTEs, 4 use window functions, so the escalation bucket is
  the majority there.
