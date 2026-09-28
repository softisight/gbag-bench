# Experiment "031-B": an AI judge given facts computed by code

GBAG v0.7 judges by code. Many tools still ask an AI judge to score a free-text answer.
This experiment measures one such judge, the judge of the benchmark runner of
DeskInsight (a separate application by the authors of GBAG), before and after one change:

- **before** (`avant`): the judge prompt as it was. It shows the judge a sample of the
  result, and tells it that totals over the whole result exist, without any value.
- **after** (`apres`): the same prompt, plus a table of facts computed by code. Each
  value is given twice: over **all** the rows, and over the **rows shown** to the model
  that wrote the answer.

"031-B" is the name of this experiment in DeskInsight's work plan.

## The answers

47 GBAG answers whose verdict was arbitrated in v0.4 to v0.6: 24 faithful, 23 unfaithful.
They are in [`cases.jsonl`](cases.jsonl), built by `scripts/export_031b_cases.py`.
All of them use the ledger database.

| Result of the question | Answers |
|---|---|
| 200 rows or less: the model saw every row | 19 |
| more than 200 rows: the model saw 200 rows | 28 |

## What is measured

The rules were fixed before the first run. They are in `scripts/eval_031b.py`.

- **Verdict of one call.** The judge lists the claims of the answer and marks each one.
  If no claim is contradicted, the call **acquits** the answer. If one claim or more is
  contradicted, it **condemns** it. A call that returns no score is a **failed** call.
- **Right verdict.** Acquitting a faithful answer, or condemning an unfaithful one. A
  failed call counts as wrong.
- **Self-contradiction.** An answer whose verdict changes from one pass to another.
- **Unverifiable share.** The claims the judge marks `unverifiable`, among all the
  claims it lists.

## Results

### Cloud judge: `deepseek-v4.1-flash`, 47 answers, 3 passes, 282 calls

| | No facts | Facts |
|---|---|---|
| Right verdicts | 58.2 % | 71.6 % |
| Results of 200 rows or less | 55/57 = 96 % | 51/57 = 89 % |
| Results of more than 200 rows | 27/84 = 32 % | 50/84 = 60 % |
| False answers condemned | 21/69 | 43/69 |
| Correct answers acquitted | 61/72 | 58/72 |
| Answers with a self-contradiction | 18 | 18 |
| Unverifiable claims | 24.1 % | 14.9 % |
| Failed calls | 41 | 31 |

By answer, with the verdict of the majority of the three passes: the facts repair 11
answers and break 4.

**72 calls in 282 gave no verdict.** The model reasons before it answers, and the
reasoning used the whole output cap (8,192 tokens, the default of the application). 27 of
these calls were played again with a cap of 16,000 tokens: all 27 gave a verdict. With
these 27 calls in place of the failed ones:

| | No facts | Facts |
|---|---|---|
| Right verdicts | 62.4 % | 81.6 % |
| Results of 200 rows or less | 56/57 = 98 % | 52/57 = 91 % |
| Results of more than 200 rows | 32/84 = 38 % | 63/84 = 75 % |
| Failed calls | 28 | 17 |

### Local judge: `gemma4:31b`, 12 answers, 1 pass, 24 calls

The 12 answers all have a result of more than 200 rows: 5 faithful, 7 unfaithful. The
cloud judge is given for the same 12 answers, pass 1, calls played again included.

| | `gemma4:31b` no facts | `gemma4:31b` facts | `deepseek` no facts | `deepseek` facts |
|---|---|---|---|---|
| Right verdicts | 5/12 | 7/12 | 7/12 | 11/12 |
| False answers condemned | 0/7 | 3/7 | 2/7 | 6/7 |
| Correct answers acquitted | 5/5 | 4/5 | 5/5 | 5/5 |
| Claims marked `supported` | 60/60 | 38/62 | | |

Without the facts, the local judge approves everything: 60 claims in 60, 12 answers in
12. Its 5 right verdicts are the 5 faithful answers.

## What the experiment shows

- **Most errors are on the results that were cut.** On a result of 200 rows or less, the
  cloud judge is right 96 to 98 times in 100 without any fact. On a result of more than
  200 rows, it is right 32 to 38 times in 100.
- **The facts help on the results that were cut**, for both judges: 32 % to 60 % for the
  cloud judge (38 % to 75 % with the calls played again), 5 to 7 answers in 12 for the
  local judge.
- **The facts do not help on a complete result.** The two values are the same there, and
  the cloud judge is slightly lower with them (96 % to 89 %). After this result, the
  application gives the facts only when the result was cut.
- **The facts are not enough for a small judge.** With the same facts, the local judge
  still acquits 4 false answers in 7.

## Limits and deviations

- **One database, 47 answers.** The answers were written for GBAG v0.4 to v0.6.
- **The local judge was measured on 12 answers, in one pass.** One call takes more than
  5 minutes on the test machine, so the set was cut from 28 answers and 3 passes. The
  difference between 5 and 7 answers in 12 is two answers: it is an indication, not a
  proof. Self-contradictions are not measured with one pass. The 12 answers were drawn
  before any verdict of the local judge was read (`scripts/cases_031b_subsets.py`).
- **The cloud judge is an exception to "local models only"**, decided by the owner of
  the project for this measure. The data sent is the synthetic ledger of GBAG.
- **45 calls of the cloud judge still have no verdict.** The replay was stopped at 27
  calls in 72: one call did not answer, and the price set in the measure bench was wrong.
- **The `usd` field of the measure files is wrong.** The bench counted 0.035 and 0.29 USD
  per million tokens. The price listed on 2026-09-28 was 0.025 and 0.60. The 282 calls
  cost about 0.89 USD at the listed price, not the 0.46 USD that the files add up to.
- **"Facts only when the result is cut" was decided after the cloud results**, not before.
- **The rules of the measure were not pushed before the run.** They were written in the
  work plan of DeskInsight, which is a private repository: their date is the authors'
  record, not a third-party timestamp.
- **The measure cannot be run again from this repository alone.** The judge prompt and
  the code that computes the facts belong to DeskInsight. What is here: the answers, every
  raw output of the judges, and the scripts that compute every figure of this page.

## Files

| File | Content |
|---|---|
| `cases.jsonl` | the 47 answers, with question, gold SQL and arbitrated verdict |
| `cases-gt200.jsonl` | the 28 answers whose result has more than 200 rows |
| `cases-gt200-short.jsonl` | the 12 answers of the local judge |
| `measure-deepseek-v41-flash.jsonl` | 282 calls of the cloud judge, raw output included |
| `measure-deepseek-v41-flash-replay16k.jsonl` | 27 calls played again with a cap of 16,000 tokens |
| `measure-gemma4-31b-gt200.jsonl` | 24 calls of the local judge, raw output included |

## Compute the figures again

```bash
python scripts/cases_031b_subsets.py --check
python scripts/eval_031b.py runs/031b/measure-deepseek-v41-flash.jsonl
python scripts/eval_031b.py runs/031b/measure-deepseek-v41-flash.jsonl runs/031b/measure-deepseek-v41-flash-replay16k.jsonl
python scripts/eval_031b.py runs/031b/measure-gemma4-31b-gt200.jsonl
python scripts/compare_031b.py
```
