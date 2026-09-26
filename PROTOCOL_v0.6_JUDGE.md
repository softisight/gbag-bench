# GBAG v0.6 — the verifying judge without free choice (design, pre-registered)

**Status: design fixed before any v0.6 code is written** (2026-09-26). Changes after this
commit are logged in [Deviations](#deviations).

## Why a v0.6

v0.5.0 was not accepted on its sealed test set (PROTOCOL_v0.5_JUDGE.md, "Test result"). It
caught every false answer it decided, but it wrongly condemned 3 correct answers out of
7. Each time, the translating model had made a free choice and got it wrong:
- it merged two figures into one sheet;
- it read "to X by July 2024" as the data's end;
- it read a partial sum as the total.

**The lesson, stated by the owner: the model must not choose. We choose for it.**

## Principle

- **Code extracts everything.** Figures, dates, columns and candidate facts all come from
  code; a model never copies or generates a value.
- **A decision model only scores options we wrote.** Jev (TypeSafe, System One) returns a
  calibrated probability per option. It cannot answer outside the options and it
  generates no text.
- **Code decides, with thresholds fixed here.** An uncertain score is an undecided claim,
  never a guess.

## The steps

**1. Split (code).** Same as v0.5.0 (`judge/v05/split.py`, trigger list included):
- sentences carrying a figure or a trigger word;
- table lines checked cell by cell against the result (`tables.py`, unchanged).

Sentences without a figure are **not judged** by v0.6. They are counted and reported as
the unjudged share.

**2. Figures (code).** Every figure and date in a selected sentence becomes one unit to
judge (`numbers.py`: locale-tolerant, words-to-digits, partial dates).
- A bare year used as a label ("in 2024") is a place, not a figure.
- Two figures in one sentence are two units, never one.

**3. Questions to Jev, per figure** (OpenRouter Decisions API, `POST /api/alpha/decisions`,
model `typesafe/jev-1.13`; the dated version returned by the API is recorded on every
verdict).
- **State given to Jev:** the question asked, the previous sentence, the sentence, the
  figure under review, and the result's column names.
- **Not given:** whether the answer was truncated, the data itself, and any judge output.

| question | type | options (written by us) |
|---|---|---|
| `scope` | choice | `rows_shown` (only the rows the answer displayed/received) · `all_data` (the whole data, or no limit stated) |
| `family` | choice | `cell` · `sum` · `maximum` · `minimum` · `last` · `first` · `ratio` · `share` · `count` · `change` (difference or % between two rows) · `other` |
| `column` | choice | the result's real columns · `none` |
| `reference` | choice, used only if `family = ratio` | `second_largest` · `median` · `mean` · `named_value` |
| `on_question` | noul | "Does this figure give (part of) what the question asks for?" |

**4. Accepting a score (code).**
- A `choice` answer is kept only if its top probability is **≥ 0.80** and it leads the
  second option by **≥ 0.10**. Otherwise that question is *uncertain*.
- Why the margin: in the probe of 2026-09-26, two identical calls returned the same
  choices, but probabilities differing by up to 0.03. The margin keeps that noise from
  flipping a decision.
- `on_question`:
  - p ≥ 0.80 → bears on the question;
  - p ≤ 0.20 → does not;
  - otherwise → treated as bearing (the conservative side: more undecided, never a
    silent acquittal).

**5. Scope (code first).**
1. An explicit marker in the sentence decides ("shown", "displayed", "visible" →
   `rows_shown`; "in the ledger", "entire", "whole", "overall" → `all_data`).
2. Otherwise, a **true declaration** of what was received governs later sentences. A
   declaration is a row count in a declarative frame, or a date range **in a sentence
   carrying a frame word** ("shown", "displayed", "output", "result", "returned",
   "covers", "received", "capped", "truncated").
   - "first = 2023-01-01 to last = 2023-07-19" is not a declaration: it is a claim about
     the data.
3. Otherwise, Jev's `scope`, if accepted (step 4).
4. Otherwise, both scopes are evaluated:
   - true on the full result → true;
   - false on both → false;
   - true only on the rows shown → undecided.

**6. Verify (code), per family, on the decided scope.**

| family | true if the figure matches… |
|---|---|
| `cell` | a cell of the column (any column if `column` is uncertain) |
| `sum` | the column sum, the final value of a running total, or a prefix sum in result order ("the top three account for 1,307") |
| `maximum` / `minimum` | the column's extreme |
| `last` / `first` | the column's value on the last/first row |
| `ratio` | the maximum divided by the chosen reference (by a figure named in the sentence for `named_value`) |
| `share` | a proportion of rows (a range or a count divided by the row count) |
| `count` | the row count, or a count cell of the row the sentence names |
| `change` | a difference or a percentage change between two rows of the column |
| `other` | — always undecided |

- Tolerance, comparators ("above 30,000") and partial dates are as in v0.5.0.
- A figure matching nothing in its family, when the family or the column is uncertain,
  is undecided, not false.
- **False requires:** an accepted family, an accepted or marker-decided scope, and no
  match at that scope. For `cell`, the row the sentence locates must also exist, with
  the figure absent from that row altogether (the v0.5 rule).

**7. Verdicts.** Unchanged from v0.5.0:
- **condemned** only on proof — `unfaithful_material` if the false figure bears on the
  question, `unfaithful_minor` otherwise;
- **acquitted** only if no figure is false, no figure bearing on the question is
  undecided, and at least one such figure is verified;
- **undecided** otherwise, never counted as faithful.

Table mismatches condemn, as in v0.5.0. Every verdict carries, for each figure, the
question scores, the decided scope and its source, the fact family, and the true value
at both scopes.

## The fallback: v0.6-lex (no model at all)

Used if the Decisions API is unavailable, and measured as a secondary configuration on
the same sets. In place of Jev:
- `family` comes from a fixed lexicon, first match in the sentence:

  | words | family |
  |---|---|
  | total, turnover, sum, overall revenue | `sum` |
  | highest, largest, maximum, peak, biggest, top | `maximum` |
  | lowest, smallest, minimum, trough | `minimum` |
  | ends, ending, closes, closing, final, last | `last` |
  | starts, opening, opened, first, initial | `first` |
  | times, x, -fold, twice | `ratio` |
  | %, of the, share, majority, proportion | `share` |
  | entries, rows, lines, items, days (with a count) | `count` |
  | change, increase, decrease, drop, rise (with a %) | `change` |
  | none of these | `cell` |

- `scope` comes only from markers and declarations (step 5.1–5.2); otherwise both
  scopes are evaluated (step 5.4).
- `column` is the column where the figure matches; if several columns match, it is
  uncertain.
- Every figure is treated as bearing on the question.

## Sets

- **Development: 36 cases already read** — the 7 truth-set cases, the 14 arbitrated
  reserve cases, and the 14 arbitrated cases of the spent v0.5 test set. Iteration is
  allowed.
  - Readiness threshold, as for v0.5: at most **20 % undecided** on the development set,
    measured with the configuration that will be frozen.
- **Test: `data/sealed/test-v06/`** — 15 answers drawn on 2026-09-26 by
  `scripts/draw_sealed_test_set.py --name test-v06 --exclude data/sealed/test-v05/answers.jsonl`.
  - Drawn before any v0.6 code, with the reserve's mechanics, from the 68 answers nobody
    has read. Only ids were printed.
  - Fingerprints:
    - `questions.jsonl` `22c566d7b189eb36929b5a7a838e6c75b7d9fc8159e7f23c9c501f6587199448`
    - `answers.jsonl` `9b77ee0c93aac2b327314e31cbb5706979eebae61f6441fc4abad048fa68c4f2`
    - `verdicts.template.jsonl` `935584ded504e44ddc4cd42d7f1b54b704a0d8398f95ee34a6618739f2df4944`
  - Opened only after the freeze.
  - Arbitrated before any judge output is read, with the rules of PROTOCOL_v0.4.md D9 and
    the owner's validation; the judges may run meanwhile, their outputs unread.
  - Like the earlier sets, these answers share their 15 questions with the held-out
    suite. The August judge scores in `runs/` that cover them are not opened.

## Acceptance on the test set (same criteria as v0.5)

1. at most 20 % undecided;
2. on the cases v0.6 decides, accuracy at least that of the best v0.4 judge (J6,
   `gemma4:31b`) on the same cases;
3. no condemnation without a recorded proof;
4. five passes give identical verdicts. For v0.6-jev this tests whether the margins of
   step 4 absorb the variation of the probabilities.

v0.6-lex is measured and reported on the same set, under the same criteria.

## Freeze

Before the test set is opened, the following are fingerprinted:
- the code, the lexicon, the question texts and options, the thresholds (0.80 / 0.10 /
  0.20), and the model version string.

After the freeze, any change is a new judge, to be measured on a new sealed set.

## Secondary configuration: v0.6 + J6 on the undecided (added 2026-09-26, before the freeze)

**Why.** v0.6 leaves some answers undecided: sentences about a subset the code cannot
recompute, strong claims without a figure. The owner asked whether an LLM judge could take
those cases. It can be measured, but it must not be mixed with v0.6's own score:
- these cases are the hardest by construction, the ones where the v0.4 LLM judges erred;
- an LLM gives no SQL proof (criterion 3) and varies between passes (criterion 4).

**What it is.**
- The LLM judge is **J6** (`gemma4:31b`, local), the best v0.4 judge and the comparator of
  criterion 2. Its outputs are produced anyway on every set (5 ordered passes). Nothing
  new is run for this configuration.
- On an answer v0.6-jev leaves undecided, J6 decides, by majority over its 5 passes:
  - faithful if F = 100 on at least 3 passes;
  - condemned if F ≤ 40 on at least 3 passes;
  - otherwise the answer stays undecided.

**How it is reported.** Always as two separate figures, never as one score:
1. v0.6 alone: undecided share, accuracy on decided cases, every condemnation proved;
2. on the answers v0.6 left undecided: how many J6 decides, and its accuracy there,
   labelled **"unproven verdict"**, with J6's agreement across its 5 passes.

**What it does not change.**
- The acceptance of v0.6 (criteria 1–4) is judged on v0.6 alone.
- The secondary configuration has no acceptance threshold. It is a measurement, reported
  on the development set (from existing J6 outputs) and on the test set.

## Scope and cost

- **Faithfulness only.** Sentences without a figure are not judged, and their share is
  reported.
- **Cost:** about 3 × 10⁻⁵ USD per Jev call (probe). **Hard cap for the whole v0.6
  campaign: 5 USD.**
- **Out of scope for v0.6:** `jaredpalmer/kev-4b` (open weights, same Decisions
  contract). It is a possible local variant, to be measured separately later.

## Deviations

**V1 — 2026-09-26 — lexicon: the keyword nearest to the figure, not the first in the
sentence.**
- **Why.** A sentence can carry two families ("starts at 45,000 … and ends at 29,943.44").
- **What changes.** The keyword nearest to the figure, within its clause and 8 words
  either side, decides. A count keyword counts only right after the figure ("12
  entries").
- Fixed before any measurement.

**V2 — 2026-09-26 — rules added on the development set (before the freeze).** Every one
is a principle applied to all cases, found by a development failure:

*Units*
- Dates are units, as the protocol said; the first implementation had set them aside.
  Jev has a `place` option: a date that only says where another figure is.
- Masked, not figures: non-breaking hyphens normalised; month-day fragments ("05-16");
  "class 7"; "account (512)"; method parameters ("1.5×IQR"); rank selectors ("top
  three", "Top 10").
- Small integers (≤ 12) are skipped unless a count noun follows.
- "one" is never converted to 1.
- A labelled field whose label names a result column ("Total Amount: 19264.82") gets its
  column and the family `cell` from code; Jev is not asked.

*Scope*
- A coverage claim ("every transaction", "the full ledger") decides `all_data`, and
  beats a size descriptor (truth-set case 4).
- Weak markers are dropped: "overall" is used as a bullet label ("Overall trend:"). Only
  explicit population markers remain ("entire", "whole ledger/period", "in/of the
  ledger", "in the dataset").

*Facts*
- `cell` and `change` look at every numeric column: a value is a value wherever it sits,
  and the result may already hold the changes.
- Changes are compared as magnitudes; the direction is carried by words.
- Prefix sums count only when the sentence says the sum is partial ("top three", "N of
  the M", "combined"). Otherwise a window's running total would pass as "a partial sum"
  of the data, which is the very failure GBAG measures (this was found by the lexicon run
  acquitting "the total debit turnover of the ledger is 289,822.36").
- A date next to an extreme ("the peak in December 2025") is a place, not judged.
- A figure at a named place that equals that row's value in the full result is a true
  point fact, unless end/extreme words ("ends at", "closing", "final", "the highest")
  claim the aggregate.
- Places are read in every format the sentence uses (full dates, day-month,
  month-only).

*Refutability — a mismatch is not a proof when:*
- the sentence names a subset (a short text value of the result: a journal code, a
  document number) and the family aggregates;
- the family is `maximum`/`minimum` and no singular superlative asserts the column's
  extreme;
- the family is `count`, the count concerns a subset the code cannot compute ("the six
  flagged payroll entries"), and no word of the sentence selects a real subset.

*Verdict*
- A selected sentence with no figure but a strong claim ("progressively higher each
  year", "always", "never", "consistently") forbids an acquittal. The answer can only be
  condemned (on another figure) or undecided.
- Found because a false answer was acquitted on a claim nobody checked (v0.5 test-11).

**Development result (dev8, cached translations):**

| mode | undecided | correct on decided |
|---|---|---|
| v0.6-jev | **7/35 = 20 %** (threshold 20 %) | **28/28** |
| v0.6-lex | 12/35 = 34 % | 21/23 |

v0.6-lex misses the threshold, so it is not ready and would be reported as such. As for
v0.5, these are development numbers on cases iterated on: they establish readiness only.

**V3 — 2026-09-26 — accepting a Jev score: median of 3 calls, Jev's `confidence`, and the
"not bearing" threshold (before the freeze).**
- **Why.** Two uncached passes with the step-4 rule (top probability ≥ 0.80, lead ≥ 0.10)
  gave different verdicts on 1 answer in 37. Scores sat on the threshold (0.80 in one
  pass, 0.79 in the other). Criterion 4 requires identical verdicts over five passes.
- **What the sources say.**
  - Jev's probabilities are calibrated in aggregate, not per answer.
  - They vary between calls; TypeSafe advises thresholds on bands, set on one's own
    arbitrated cases.
  - Every choice answer also carries a `confidence` field: how concentrated the
    distribution is. TypeSafe recommends it as a second axis.
  - The order of options is reported to move the probabilities. Here it is fixed by the
    code and fingerprinted at the freeze.
- **What was measured**, replaying cached scores on the development set (no new call):
  - loosening the rule (top ≥ 2× the second, or a lead ≥ 0.30 alone) let 1–2 wrong
    verdicts in;
  - `confidence` ≥ 0.70 with a 0.10 lead gave 0 verdict changes across three
    single-call passes, and no error.
  - A median-of-3 pass under the old rule still changed one verdict between passes:
    condemned "minor" in one pass, "material" in the other. The cause was `on_question`
    at 0.19 vs 0.23, around the 0.20 threshold. `on_question` has no `confidence` field.
- **What changes.**
  1. Each figure is scored by **3 independent calls**. The per-option **median** of the
     probabilities, of `confidence` and of `on_question` is used.
  2. A choice is accepted when its median **`confidence` ≥ 0.70** and the top option
     leads by **≥ 0.10**. This replaces "top probability ≥ 0.80".
  3. A figure is "not bearing on the question" only at `on_question` **≤ 0.10**, instead of
     ≤ 0.20. In doubt, a condemnation stays material.
- **Result (development, two uncached passes `v3a`, `v3b`, plus a cached pass):**
  - **0 verdicts differ** across the three passes (37 answers);
  - **undecided 8/35 = 23 %** (readiness threshold 20 %), **correct 27/27** on the
    decided cases in every pass.
  - 6 of the 8 undecided answers are undecided for reasons in the code, not in Jev's
    scores:
    - a subset the code cannot recompute;
    - a strong claim without a figure.
  - The readiness threshold is therefore **missed by one answer**. This is reported as
    such; no threshold is moved to pass it.
- **Cost:** three times the calls, about 0.08 USD per development pass.

**Secondary configuration on the development set** (from existing J6 outputs, pass `v3a`):
- J6 decides all 8 answers v0.6 leaves undecided and is right on 7, all unproven.
- Its one error is `kimi-k3__ledger-l8-01`: J6 scores it faithful on all 5 passes, but it
  is false. The answer contains the claim "the lows are progressively higher each year",
  the kind of strong claim v0.6 refuses to acquit.
