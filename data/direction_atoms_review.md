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

## Second review (2026-08-01) — the cumulative-column trap

A parallel design review (product side, DeskInsight Class-A study) found a
rule the pilot lacked: **a cumulative column must never be bucketed on its
level**. A running total of positive amounts rises by construction — its
level direction is information-free at best, and points the wrong way
relative to the question at worst.

The trap had fired here and passed the hand-check: `sakila-l10-02` was
proposed `up` and ratified ("running total rises by construction"), while
the question asks about the *rate of accumulation over time* — the flux.
Verification, run with this extractor's own `series_bucket` on the real
database:

| Check | Result |
|---|---|
| `running_total` level | `up` (window means 8,332 → 59,188) — the ratified trap |
| monotonicity | true on all 16,049 points — the form index sees this cumul |
| daily flux, zero-filled calendar (267 d) | **`down`** (521 → 7.8) — the opposite of the ratified atom; consistent with `sakila-l10-01` (`down`, ratified, same underlying activity) |
| monthly flux (5 present months) | too-small-to-claim — the window guard refuses, correctly |
| diff of last-cumul-per-period vs `GROUP BY` sums | identical — the flux treatment is exact |
| synthetic credit notes (flat business, ~10 % negative lines) | cumul **not** monotone (form index misses it) yet its level still buckets `up` — only the SQL proof catches this case |

### Rule added in v1.2

1. **Detection — two signals of different rank.** `SUM(...) OVER (... ORDER
   BY ...)` with an unbounded frame in the gold SQL is a *proof of
   construction* (bounded frames such as `3 PRECEDING` are moving windows
   and do not match). Full monotonicity of a series is a *form index* for
   cumuls the SQL does not reveal (pre-computed columns). When the proof
   fires and the form index sees nothing (signed cumul, e.g. a running
   balance), the carrier column is chosen by an explicit rule: single value
   column, else single name-hint match (`running|cumul|balance`), else
   refuse to bucket anything.
2. **Treatment.** Bucket the **per-period first differences**: last cumul of
   each period, differenced — identical to `SUM(value) GROUP BY period`,
   verified. Zero-filled calendar (a cumul does not move when nothing
   happens), first period dropped (its diff-against-zero is the opening
   value — the partial-first-period trap in another form). Level start/end
   recorded in the evidence.
3. **Segmented cumul**: per-segment flux not implemented; refuse to bucket.

### Consequences on re-run (v1.2, both datasets: 35 original + 15 held-out)

- **34 reviewed records preserved byte-for-byte; 1 re-proposed**:
  `sakila-l10-02` `up` → **`down`** (day grain, flux windows 521 → 7.8) —
  pending re-review.
- **15 held-out (ledger) proposals**, all pending review. Notable:
  - `ledger-l8-02` / `ledger-l9-01`: `running_balance` flux-treated (monthly
    flux 196.8 → 718.8 ⇒ `up` component; combined `mixed`). Reviewer note:
    in l8-02 the raw `net_movement` column buckets `down` only because the
    opening-balance month sits inside its head window; the flux treatment of
    the same series (first period dropped) says `up`. The evidence makes the
    disagreement and its cause visible.
  - `ledger-l10-01` and `ledger-l9-03`: segmented + cumulative → refusal by
    rule 3. Honest silence, not a level bucket.
  - `ledger-l6-01`: yearly grain, 3 points → too-small-to-claim.
- Re-runs now preserve reviewed records byte-for-byte when bucket and
  derivation are unchanged, and carry historical `changed from` notes.

## What this pilot did NOT do yet

- Human review of the 16 pending proposals (1 changed by the v1.2 rule +
  15 held-out) — every `status: proposed` atom above.
- No adversarial check (generate the opposite conclusion, verify the judge
  rejects it) — next step before judge integration.
- No judge-prompt integration; current scores are unaffected. Integrating
  atoms is a scoring change and requires a full re-judge before any
  comparison with existing leaderboard numbers.
- Atoms other than direction (entity, inclusion rule, time window,
  comparator) still need SQL-side extraction: 16/35 gold queries are flat
  SELECTs, 15 are CTEs, 4 use window functions, so the escalation bucket is
  the majority there.
