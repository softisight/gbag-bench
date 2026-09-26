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

## Scope and cost

- **Faithfulness only.** Sentences without a figure are not judged, and their share is
  reported.
- **Cost:** about 3 × 10⁻⁵ USD per Jev call (probe). **Hard cap for the whole v0.6
  campaign: 5 USD.**
- **Out of scope for v0.6:** `jaredpalmer/kev-4b` (open weights, same Decisions
  contract). It is a possible local variant, to be measured separately later.

## Deviations

*None yet.*
