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

**V1 — 2026-09-25 — development translations are hosted until the local GPU is free.**
- **What changes.** The local GPU is measuring the v0.4 Stage 2 control (J6) overnight,
  and loading another model on it would disturb that measurement. Development iterations
  therefore translate with the **same model family, hosted**: `qwen/qwen3.8-27b`, pinned
  to `deepinfra/bf16`, with seed 42 and reasoning off.
- **Freezing and test stay local.** The frozen v0.5 is re-measured on the development set
  with the local `qwen3.8:27b` before freezing, and those local numbers are the ones that
  count against the 20 % threshold. The test set is only ever judged locally.
- **Implementation details fixed during development** (no measured result depends on them
  yet):
  - `column` is constrained to the result's real columns by the output schema;
  - `value` is always present;
  - translator output is capped at 1,200 tokens, and a capped output is treated as
    unparseable (every claim of that sentence undecided).

**V2 — 2026-09-25 — a 9th type, `point`, found by the development set.**
- **What was measured.** In development iteration 2, 11 of the 19 claims blocking an
  acquittal were typed `other`, and nearly all had one form: the value of a column at a
  row or period ("a net movement of +18,528.56 in May 2024", "−44.9% in January 2024").
  None of the 8 designed types expresses it, although it is the most common claim in
  answers over monthly results.
- **What changes.**
  - `point` is added: the column's value on the row(s) the statement locates. It is true
    if a located row matches. It is false only if at most 3 rows are located and none
    matches; otherwise it is undecided.
  - An `end_value` whose place is not the first or last row, and whose words do not say
    "end" ("ends at", "closes", "final", "last"…), is evaluated as a `point`.
- **Other fixes of this iteration**, all in reading or verification, none in the decision
  rules:
  - partial dates ("26 Nov", "August", "January 2023");
  - counts read from an aggregated row;
  - local peaks not taken as the global extreme unless a singular superlative asserts it;
  - an `extreme` with neither value nor place is undecided (it was vacuously true);
  - figures written in words ("twice", "six");
  - currency symbols ignored when checking that a value occurs in the sentence.
- The design's list of 8 types becomes 9, before freezing.

**V3 — 2026-09-25 — development iterations 3 to 5 (reading and validation only).**

| iteration | undecided | correct on decided |
|---|---|---|
| 1 | 14 % | 12/18 |
| 2 | 24 % | 15/16 |
| 3 | 14 % | 15/18 |
| 4 | 24 % | 16/16 |
| 5 | **19 %** | **17/17** |

Iterations 4 and 5 reuse the translations of iteration 3 (the development cache), so they
measure code changes only. The changes, none of them to the decision rules:
- the currency sign between the sign and the digits ("-$18,489.48");
- comparators read in the sentence ("above 30,000" is ≥, not =);
- r3 declarations counted in entries, movements, lines… as well as rows ("Using the 200
  displayed entries");
- max/min inferred from the words when the translator left it empty;
- a count filter that selects no row is undecided;
- sheet figures validated as values ("20,000 to 53,000" is supported by "between 20,000
  and 53,000");
- a normalised date is validated component by component against the sentence and the one
  before it.

**Caveat, stated before anyone reads it as a result.** These numbers come from five
iterations on the same 21 cases. They show that the code works on its development set,
not that it generalises. Only the local re-measurement (V1) and then the sealed test set
can say that.
