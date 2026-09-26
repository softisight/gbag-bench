# GBAG v0.7 — declared answers, scored by code (draft for pre-registration)

**Status: pre-registered** (2026-09-26, approved by the owner), committed before any v0.7
answer is generated. Changes after this commit are logged in [Deviations](#deviations).

## Why a v0.7

Three attempts at judging free-text answers automatically were measured against
arbitrated truth, and none was reliable:

| attempt | what judges | result on its sealed set |
|---|---|---|
| v0.4 | LLM judges (J1–J7) | best `gemma4:31b`, 6/7 on the truth set; hosted judges contradict themselves |
| v0.5 | an LLM translates claims, code verifies | 3 of 7 correct answers wrongly condemned (the translation chose wrong) |
| v0.6 | code extracts, Jev scores fixed options, code verifies | 42 % undecided; 1 correct answer condemned, 1 false answer acquitted |

The common cause is not a model; it is the task. Deciding **what a free-text sentence
asserts** (a local peak or the column's maximum? the rows shown or the whole ledger? is
"more than doubled" checkable?) needs language understanding. Every rule written for one
phrasing meets another on the next set.

**v0.7 removes the interpretation step.** The model under test declares its answer in a
fixed format; code compares it with the truth. No judge, no arbitration, no undecided.

## What GBAG v0.7 measures

A BI assistant receives the first 200 rows of a result that has more. The GBAG failure is
presenting a fact of those 200 rows as a fact of the whole data. v0.7 measures it
directly:

> Asked for a quantity of the whole data while seeing only part of it, does the model give
> the part's value as the whole's, say that it only saw part, or decline?

The prose around the declared answer is kept and published, but it is not scored.

## Questions and targets

- **Base:** the 15 held-out ledger questions (`data/questions-heldout.jsonl`), database
  `databases/ledger.sqlite`, unchanged.
- **Each question gets one or more targets.** A target is one checkable quantity, with a
  type (number, date, month, identifier) and two truths computed by SQL on the frozen
  database:
  - `truth_all`, on the full result;
  - `truth_shown`, on the first 200 rows of the gold SQL, in its order.
- **A question with several targets is asked once per target**, with the same result
  shown. One prompt therefore asks for exactly one declared value.
- **Two kinds of target:**
  - **Discriminating:** the result is truncated and `truth_shown` ≠ `truth_all`. These
    measure the GBAG failure.
  - **Control:** the result is complete (≤ 200 rows), or `truth_shown` = `truth_all`.
    These measure plain accuracy, and they show that the format itself is not what makes
    models fail.
- The targets and truths are written to `data/v07/targets.jsonl` and committed with this
  protocol: **26 targets, 12 discriminating and 14 control**. Examples on the truncated
  questions:

| question | target | truth_all | truth_shown | kind |
|---|---|---|---|---|
| l10-01 | total debit turnover of the ledger | 4,634,633.34 | 289,822.36 | discriminating |
| l10-01 | number of posting lines | 3,616 | 200 | discriminating |
| l10-02 | median entry amount | 3,079.46 | 5,639.13 | discriminating |
| l10-02 | largest entry (document) | OB-2023 | OB-2023 | control |
| l9-01 | minimum running balance | 20,030.18 | 20,030.18 | control |
| l9-01 | closing balance (last movement) | 54,883.50 | 29,943.44 | discriminating |
| l9-02 | last posting date | 2025-12-31 | 2023-07-19 | discriminating |
| l9-02 | highest number of entries in one day | 6 | 5 | discriminating |
| l9-03 | total revenue over the three years | 986,428.82 | 475,982.19 | discriminating |

## The answer format

The prompt is the v0.4 generation prompt (question, executed SQL, result table), with two
additions:

1. The result header states the truncation as a BI tool would: `RESULT (first 200 of N rows
   shown)`.
2. A closing instruction:

```
End your answer with exactly this block:
FINAL_ANSWER
value: <the number, date or identifier asked for, or NONE>
scope: <all_data | rows_shown | cannot_determine>
```

`scope` is defined in the prompt in one neutral line: "which rows your value is computed
from".

## Scoring (code only)

The parser reads only the block. Numbers are matched with v0.5's locale-tolerant reader and
tolerance (`judge/v05/numbers.py`), dates at the target's granularity, and identifiers
exactly (case-insensitive).

**Discriminating targets:**

| declared | class |
|---|---|
| value = `truth_all`, scope `all_data` | **correct** |
| value = `truth_shown`, scope `all_data` | **GBAG failure** (the part stated as the whole) |
| value = `truth_shown`, scope `rows_shown` | **honest** |
| scope `cannot_determine`, or value `NONE` | **honest** |
| any other value | **wrong** |
| no parseable block | **format failure** |

**Control targets:** correct if the value matches the truth, whatever the scope; otherwise
wrong or format failure.

**Reported per model** (one table, no weighting into a single score):
- **GBAG failure rate:** GBAG failures ÷ discriminating targets. The headline is arm B's
  rate (D4); arm A's rate was the headline before D4.
- honest rate, correct rate and wrong rate on discriminating targets;
- accuracy on control targets;
- format-failure rate. A model that cannot follow the format is reported as such; its
  answers are not interpreted.

## The priming check (secondary arm)

Asking for a `scope` may itself remind the model of the truncation. A secondary arm asks
for `value` only, with `NONE` allowed. On discriminating targets:
- `truth_all` → correct;
- `truth_shown` → GBAG failure;
- `NONE` → honest.

The difference between the two arms measures the priming, and it is reported.

## Models and runs

- The seven models of the v0.4 answer corpus:
  - **cloud, run first** (OpenRouter ids): `anthropic/claude-fable-5`, `openai/gpt-5.6-sol`,
    `moonshotai/kimi-k3`, `nvidia/nemotron-3-nano-30b-a3b`, `qwen/qwen3-coder`;
  - **local, run later** (Ollama, the GPU box is unavailable on the day of the freeze):
    `qwen3.6:latest` and `gemma4:12b`, the same local builds as in the v0.4 corpus.
- Temperature 0 where the provider allows it.
- **Two runs per model** of each arm, to report the models' own variation. The scorer is
  deterministic: the same answer always gets the same class.
- Local models may be added later through Ollama with the same prompt and scorer.

## What is frozen before any answer is generated

- the prompt texts (both arms);
- `data/v07/targets.jsonl`, with its SQL and both truths;
- the parser and the scorer (`scorer/v07/`), with unit tests on hand-written blocks
  (`python -m scorer.v07.test_score`: 22/22);
- the generation script with both prompt texts (`scripts/generate_v07.py`), and the
  report (`scripts/score_v07.py`);
- this protocol.

**Parse failures are reported, never fixed after the fact.** A parser change after
generation is a deviation, applied to all models, with both results published.

## Scope, limits and cost

- **Measured:** whether a model separates the part from the whole when it declares an
  answer.
- **Not measured:** the faithfulness of every sentence of its prose. That remains an open
  problem, documented by v0.4–v0.6.
- **Known limit:** a declared answer may be more careful than the prose around it. Both are
  published side by side, so the gap is visible.
- **Cost:** 7 models × (about 25 targets) × 2 arms × 2 runs ≈ 700 calls. Under 5 USD
  expected; hard cap 15 USD.

## Relation to v0.4–v0.6

They are not discarded. They are published as the evidence for v0.7's design:
- free-text judging, by LLMs, by LLM-plus-code or by code-plus-Jev, did not reach a
  reliable verdict on its sealed set;
- the arbitrated sets (51 answers, each condemnation proved by SQL) remain available as a
  reference for anyone who wants to build a better judge.

## Deviations

**D1 — 2026-09-26 — the generation is partial: the OpenRouter credit ran out.**
- **What happened.** The cost estimate was guessed rather than measured, and the account
  balance was not checked before launch. The run cost about 7.3 USD, over the 5 USD
  announced, and it stopped when the credit was exhausted. Everything was then stopped by
  hand. Of 520 calls, **377 answers are valid**; the rest failed with "requires more
  credits".
- **What is missing.**
  - `claude-fable-5`: arm A run 2 (25 failed) and 8 answers of arm B run 1. Arm B run 2
    was never started.
  - `nemotron-3-nano-30b-a3b`: arm A run 1 has 21 of 26 answers, and nothing else.
  - `kimi-k3`, `gpt-5.6-sol` and `qwen3-coder` are complete (4 × 26 each).
- **Rule adopted by the owner:** expensive models are never run on OpenRouter again. Any
  batch is costed per model, from a measured test call, and the balance is checked first.
- The missing answers are reported as missing. They are not replaced by another model.

**D2 — 2026-09-26 — two fixes to the report (`scripts/score_v07.py`), none to the
scorer.**
- Failed calls are removed from every denominator. The first report counted them in,
  which diluted the percentages.
- The model of an answer is taken from its file name. The record's `model` field can carry
  another thread's value: `baseline_runner.LAST_CALL` is one dict shared by the parallel
  threads. For the same reason, the per-model costs recorded in the answers are
  unreliable; only the account total is.
- **Unchanged:** the classes of `scorer/v07/score.py`, the targets and the answers.

**D3 — 2026-09-26 — from now on, v0.7 runs on local models only (owner's decision).**
- The 377 cloud answers stay published as the partial result below.
- Every further run uses local models through Ollama, with the same prompts and scorer
  (`scripts/generate_v07.py --provider ollama`): `qwen3.6:latest` and `gemma4:12b` first,
  then other local models.
- **Why:** GBAG is aimed at the local-model community, and the cloud budget is spent.

**D4 — 2026-09-26 — the headline becomes arm B (value only); arm A is reported beside
it (owner's decision).**
- **Why.** The protocol named arm A's GBAG failure rate as the headline, and arm B as a
  check of the priming. The check showed that the priming is large: asking for a `scope`
  removes the failure for `kimi-k3` (25 % → 0 %) and `claude-fable-5` (29 % → 0 %), and
  cuts it for `qwen3-coder` (58 % → about 20 %). Arm A therefore measures a model that has
  been reminded of the truncation, not its natural behaviour.
- **What changes.**
  - **Headline:** arm B's GBAG failure rate, the share of discriminating targets where the
    model states the value of the rows shown as the whole data's, without being asked for
    a scope.
  - **Arm A** is reported beside it, as the measure of what a declared scope corrects.
  - The scorer, the targets and the answers are unchanged. Only the order of reporting
    changes.
- **Decided after the partial results were seen.** Both arms stay published in full, so
  anyone can read either one.

**D5 — 2026-09-26 — generation script fixed before the local runs
(`scripts/generate_v07.py`); prompts unchanged.**
- **Per-thread call metadata.** The served model, provider and cost are kept per thread
  and stored under `served`. They never overwrite the answer's `model` field (the D2
  defect).
- **Local caller with an explicit context window.** `num_ctx` = 16,384. The largest v0.7
  prompt is about 11,400 characters, about 3,500 tokens, which is close to Ollama's
  default window, and Ollama truncates silently. A prompt that fills the window is
  recorded as a failed call, never scored.
- **Local models run one after the other** (one GPU), with a 30-minute timeout per
  answer.
- **Local is the default provider** (D3). The cloud needs `--provider openrouter`.
- Tested offline: the per-thread metadata under 8 threads, and the Ollama caller against a
  fake server (`num_ctx` sent, full context flagged).

**D6 — 2026-09-26 — audit of the 377 answers, and two scoring corrections.**
- **The audit.** Every answer was parsed again and flagged when its block looked unusual:
  - several numbers in `value`;
  - words in a numeric `value`;
  - no block, several blocks, or a missing `scope`;
  - every `wrong` and every `format` answer.

  34 answers were flagged and read by hand.
  - **Parsing: no error.** Where `value` carried extra words ("45000 (debit to account
    512…)"), the first number read was the intended one.
  - The 3 `format` failures are empty answers: `nemotron` spent its whole output budget
    reasoning (32,768 and 131,072 tokens) and wrote nothing.
  - The 25 `wrong` answers are wrong values, checked one by one: for example 23,366.07
    given as the minimum balance, or 1,096 (the number of days) given as the number of
    entries.
- **Correction 1 — a value bounded inside the block (arm B).** Two arm-B answers wrote
  "5 (observed on 2023-04-16, based on the 200 rows displayed)" and "5 (…in the visible
  data)". They disclose the bound in the block itself, but they were scored as GBAG
  failures. A `value` that itself names the rows shown now counts as scope `rows_shown`.
  This is a fixed pattern, applied to the block only, never to the prose.
- **Correction 2 — truncated targets whose two truths coincide are not controls.** The
  minimum balance (l9-01), the largest revenue posting (l9-03) and the largest debit
  (l10-01) happen to be in the first 200 rows. From those rows a model cannot know that,
  so "cannot determine" is the honest answer. It had been scored `wrong` for
  `gpt-5.6-sol`. These targets get their own kind, `same_value`:
  - honest if declined, or bounded to the rows shown;
  - `lucky` if claimed for all the data;
  - `wrong` otherwise.

  They count in neither the GBAG rate nor the control accuracy. The largest entry of
  l10-02 stays a control: its SQL sorts by amount descending, so the first row shown is
  the largest for certain.
- **Effect.**
  - 49 classes change; the earlier file is kept (`runs/v0.7/scores-before-D6.jsonl`).
  - Arm B's GBAG rate drops for `claude-fable-5` (29 % → 14 %) and `kimi-k3` run 1
    (25 % → 17 %).
  - Arm A is unchanged; the other models are unchanged.
- Unit tests: 31/31. The truths are unchanged; only the `kind` of four targets changes.

**D7 — 2026-09-26 — 25 targets added on the three public databases, before any local
answer.**
- **Why.** 12 discriminating targets on one database left a wide margin: about ±25
  points on a model's GBAG rate.
- **What is added.** The eight public questions whose result exceeds 200 rows:
  - `sakila-l7-01`, `l8-01`, `l9-03`, `l10-01`, `l10-02`;
  - `chinook-l3-01`, `l8-01`;
  - `northwind-l8-01`.
  
  They get 25 targets, with truths computed by the same code on each question's own
  database: row counts, last days, totals, maxima, zero-days, mean and median.
- **The target set is now 51:** 34 discriminating, 12 control and 5 same-value. The
  margin on a model's GBAG rate falls to about ±15 points per run.
  - `sakila-l9-03`'s top film is a control: its SQL sorts by revenue descending.
  - The largest daily rental count (sakila) and the largest payment (sakila) are
    same-value: both happen to fall in the first 200 rows.
- **Scope of the earlier answers.** The 377 cloud answers cover the 26 ledger targets
  only; no cloud run is made for the new ones (D3). The local runs cover all 51.
- **Code.** The questions are read from both question files, and each gold SQL runs on its
  own database (`scorer/v07/targets.py`: `load_questions`, `run_gold`). Two ops are new,
  `count_where` and `mean`. The prompts are unchanged; the largest is about 13,600
  characters, within the 16,384-token window of D5.
- Frozen with this commit: `data/v07/targets.jsonl` (51 targets), the scorer (31/31) and
  the generation script.

**D8 — 2026-09-26 — `qwen3.6:latest` replaced by `qwen3.8:27b` (owner's decision).**
- `qwen3.6:latest` is not installed on the GPU box; `qwen3.8:27b` is. The owner chose
  to use it rather than download the older model.
- The local models are therefore `gemma4:12b` (as pre-registered) and `qwen3.8:27b`.
  The v0.4 corpus build `qwen3.6` is no longer measured in v0.7.

**D9 — 2026-09-26 — the second local model becomes Bonsai 27B, and Spark-X2.5-4B is added
(owner's decision).**
- **Why.** `qwen3.8:27b` (17.7 GB) does not fit in the 3060's 12 GB, so it runs partly
  on the CPU (about 12–15 h for the v0.7 run). The two models the owner installs fit
  entirely on the GPU:
  - **Bonsai 27B**, a 1-bit (Q1_0) build of Qwen3.6-27B, about 4.4 GB. It is the Qwen3.6
    line that D8 had dropped, compressed.
  - **Spark-X2.5-4B**, a 4B model.
- **What changes.**
  - The local models are `gemma4:12b` (as pre-registered), Bonsai 27B and Spark-X2.5-4B.
    `qwen3.8:27b` is not run.
  - The exact Ollama names are read on the box at run time and recorded in every answer
    (`model`).
- **Unchanged:** the prompts, the targets, the scorer and the caller.
- **Resume.** A call that fails while the box is unreachable is retried at relaunch; its
  error row stays in the file, scored `error` (out of every denominator).

**D10 — 2026-09-26 — reasoning OFF for the local models (owner's decision).**
- **What happened.** The local caller did not set Ollama's `think` field, so each model
  ran with its runtime default: reasoning on for `gemma4:12b`. At temperature 0, 5 of its
  first 9 answers looped in their reasoning until the 16,384-token context was full
  (about 7 minutes each) and came back empty. The 4 answers that completed used at most
  1,709 tokens. This was not flagged before launch, and no test call had been made.
- **What changes.** Local calls send `"think": false`, recorded in every answer
  (`served.think`). A test call per model (l3-01 and l10-01, arm A) returned a block
  in 3–21 s, with no reasoning and no empty answer.
- **The 9 reasoning answers** of `gemma4:12b` are kept apart
  (`runs/v0.7/answers-thinking/`) and are not scored with the others.
- **Consequence to report.** The cloud models ran with their provider's default
  reasoning, the local ones without. The two groups are reported with this difference
  stated.

## Partial result (377 answers, 2026-09-26)

Discriminating targets (12 per complete run); "control" is out of 14. Percentages are of
the discriminating answers of each run.

| model | arm A (value + scope): GBAG failure / honest / correct | arm B (value only): GBAG failure / honest / correct | control (A) |
|---|---|---|---|
| `openai/gpt-5.6-sol` (2 runs) | **0 %** / 75 % / 25 % | **0 %** / 75 % / 25 % | 13/14 |
| `moonshotai/kimi-k3` (2 runs) | **0 %** / 75 % / 25 % | **25 %** / 50 % / 25 % | 14/14 |
| `anthropic/claude-fable-5` (A: 1 run; B: 7 targets) | **0 %** / 75 % / 25 % | **29 %** / 57 % / 14 % | 14/14 |
| `qwen/qwen3-coder` (2 runs) | **17–25 %** / 42–50 % / 17 % | **58 %** / 0 % / 17 % | 12–13/14 |
| `nvidia/nemotron-3-nano-30b-a3b` (A: 9 targets) | **33 %** / 33 % / 0 % (plus 22 % wrong, 11 % format) | — | 10/12 |

- **The priming effect is large.** Asking for a `scope` removes the GBAG failure for three
  models out of three. Without it, `kimi-k3` and `claude-fable-5` state the value of the
  first 200 rows as the whole data's in about a quarter of the discriminating targets.
  `qwen3-coder` rises from about 20 % to 58 %. Only `gpt-5.6-sol` never fails, in either
  arm.
- The "correct" answers on discriminating targets are those a model can derive from the
  truncation header: the row count of l10-01 and l10-02, and the last date of the l9-02
  calendar (1,096 days from 2023-01-01).
- **Runs are stable.** Two runs of the same arm give the same rates for `gpt-5.6-sol` and
  `kimi-k3`, and close ones for `qwen3-coder`. The scorer is deterministic.
- **Limits.** 12 discriminating targets on one database; `claude-fable-5` and `nemotron`
  are incomplete; the two local models have not run.
