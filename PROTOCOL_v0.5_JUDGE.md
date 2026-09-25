# GBAG v0.5 — the verifying judge (design, pre-registered)

**Status: design decisions fixed before any code is written** (2026-09-25). Why a new
judge: PROTOCOL_v0.4.md, deviation D12. Changes after this commit are logged in
[Deviations](#deviations), like v0.4.

## Principle

The model no longer scores; it translates. Code checks.

A v0.4 judge reads an answer and returns a score out of 100. On cases the rule was not
written against, no judge measured does this reliably (v0.4 Stage 2). The v0.5 judge
splits the job: whatever can be computed is computed, and a local model answers one
closed question per claim.

## The four steps

1. **Split (code).** The answer is cut into claims.
   - A sentence is a claim if it contains a digit, or a word from the published trigger
     list (`judge/v05/triggers.txt`: quantifiers, superlatives, scope and end markers).
   - Tables in the answer are compared row by row with the result.
   - Filtering is broad on purpose. Discarded sentences are logged, and their rate is
     reported.
2. **Translate (local model, closed question).** Each claim becomes a fact sheet, with no
   judgement asked:
   - **scope**: `rows_shown` | `all_data` | `interpretation`;
   - **type**, one of 8: `total`, `count`, `extreme`, `end_value`, `share`, `ratio`,
     `universal`, `trend`;
   - **arguments**: the column, and the stated value;
   - **span**: the exact passage it translated.
3. **Verify (code).** For every fact sheet, the true value is computed on both scopes —
   the rows shown to the model, and the full SQL result.
   - The judge's universe is that result, at those two scopes. Nothing else is looked up.
   - Trends use the direction atoms (`scripts/derive_direction_atoms.py`).
4. **Decide (code).** Fixed rules, listed below.

## Three verdicts, never a default

- **Condemned** — only on **positive proof**: the claim was translated, its true value
  was computed, and it differs.
  - A figure that cannot be found anywhere is **never** a condemnation on its own. It may
    be a legitimate derivation we did not foresee.
- **Acquitted** — only if **every claim bearing on what the question asks** was verified
  and is true.
- **Undecided** — everything else: unknown type, rejected translation, figure not found,
  claim about something outside the result, or `interpretation` scope.
  - An undecided answer is **never counted as faithful**.

Severity of a condemnation:
- a false claim on the quantity the question asks for → `unfaithful_material` (≤ 40);
- a false claim elsewhere → `unfaithful_minor` (41–99).

## Guards against a bad translation

- **Scope markers first.** Explicit markers ("shown", "every", "in the ledger"…) are
  resolved by code (`scripts/resolve_scope.py`, rule r1). The model is asked only when
  no marker decides.
- **The span must be real.** The quoted span, and the stated value, must occur verbatim
  in the answer. Otherwise the sheet is rejected, and the claim becomes undecided.
- **Everything is recorded.** Every sheet, computed value and rule applied is published
  with the verdict. Each condemnation therefore carries its proof: stated value against
  true value.

## Undecided answers — decision (c) completed by (a)

- **(a) Shown, never hidden or guessed.** Undecided answers are reported as such, and
  every score is published with its coverage (the share of answers decided).
- **(c) A readiness threshold.** v0.5 is **not ready**, and is not published, if more
  than **20 % of the arbitrated development cases** end undecided.
- Undecided answers are **not** sent back to a v0.4 judge.

## Development, test, and what v0.5 must beat

- **Development set**: the 7 truth-set cases plus the 14 arbitrated reserve cases. These
  have already been read, so v0.5 is tuned on them.
- **Test set**: `data/sealed/test-v05/` (fingerprints in PROTOCOL_v0.4.md, D12). It is
  opened and arbitrated (rules of D9) **only after v0.5 is frozen**. Freezing means the
  code, `triggers.txt`, the 8 types, the translation prompt and the local model, all by
  hash.
- **v0.5 is accepted on the test set if all of the following hold:**
  1. at most 20 % undecided;
  2. on decided cases, accuracy is at least that of the best v0.4 judge on the same
     cases;
  3. no condemnation without a recorded proof (true by construction; checked anyway);
  4. five passes give identical verdicts.
- Otherwise it is published as not accepted, with its numbers, like any failed judge.

## Scope of v0.5

- **Faithfulness only.** Completeness and insight are not scored by v0.5.
- The GBAG composite score is not recomputed with it until a later version says how.

## Deviations

*None yet.*
