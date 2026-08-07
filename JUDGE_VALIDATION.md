# Judging the judge

GBAG scores an answer written over the result of a SQL query. The scoring is done by an LLM
judge. That raises an obvious question, and for a long time this repository did not answer
it: **can the judge actually tell a good answer from a bad one?**

This page answers it with seven cases whose correct verdict is settled by a SQL query, not
by anyone's opinion. Every claim below ships with the query that proves it. You do not have
to believe the arbitration — you can run it.

Machine-readable version: [`data/judge-truth-set.jsonl`](data/judge-truth-set.jsonl).

## The failure the judge has to catch

A model is shown the first 200 rows of a result. The result has more. The model writes a
sentence that is **true about the 200 rows it saw and false about the data**.

The figure it prints is usually correct. What is wrong is the reach of the sentence: *every*,
*the highest*, *the majority*, *the total*, *ends at*. Nothing looks like an error. There is
no invented number to spot.

That is the whole difficulty. A judge that checks figures against the visible rows will
approve every one of these answers.

## The seven cases

Six are answers that must be marked unfaithful. One is correct and must be acquitted — a
truth set of condemnations only would reward a judge that condemns everything.

| # | model | what it claimed | what the database says |
|---|---|---|---|
| 1 | nemotron-3-nano-30b | 289,822.36 is "the sum of every debit posted in the ledger" | **4,634,633.34** — the figure is the last row of the window |
| 2 | nemotron-3-nano-30b | "the majority of entries sit between 5,000 and 10,000" | **243 of 1,412** — 17.2% |
| 3 | nemotron-3-nano-30b | "absolute changes vary from −7,214 to +12,105" | minimum is **−15,481.40**, a number printed in the model's own table |
| 4 | nemotron-3-nano-30b | "the table above (200 rows) lists **every** transaction on account 512 … ending at 29,943" | account 512 has **684 lines**; the real closing balance is **54,883.50** |
| 5 | claude-fable-5 | "the **vast majority** of entries cluster between €5,250 and €7,400" | **152 of 1,412** — 10.8%; minimum entry 0.01, mean 3,282.32 |
| 6 | qwen3-coder-480b | "the account closed at a running balance of $54,883.50" | **54,883.50 — correct.** This one must be acquitted |
| 7 | qwen3.6 | "5 entries on April 16, 2023 … the highest single-day count **in the dataset**" | maximum is **6**, on 2023-11-28 and 2024-07-08 |

Case 3 deserves a note. Nothing was truncated there: the model received all 36 rows and
printed them. It then summarised its own table with a range that its own table contradicts.
No scope reasoning is needed to catch it — only reading. Three judges out of four missed it
anyway.

Case 4 is the one that gives the benchmark its shape. `(200 rows)` sits in the same sentence
as `every transaction`. The size descriptor is true. The coverage quantifier is not. What
the sentence *asserts* is coverage, and that is what decides its scope.

## How the judges scored

Same seven cases, same judge prompt (`judge/prompt-v041.md`), three runs each — four for
grok, which was the original judge.

| judge | where | score | runs where it contradicted itself |
|---|---|---|---|
| **gemma4-31b** | local, 31B | **7/7** | 0 of 7 |
| **qwen3.6** | local, 36B | **6/7** | 0 of 7 |
| grok-4.3 | hosted | 5.5/7 | **3 of 7** |
| phi4 | local, 15B | 5/7 | 0 of 7 |
| deepseek-v4-pro | hosted | 5/7 | **5 of 7** |
| gemma4-12b | local, 12B | 4/7 | 0 of 7 |
| gemini-2.5-pro | hosted | 3.3/6 | **2 of 6** |

Four local judges: **0 self-contradictions across 28 case-runs.** Three hosted judges:
**10 across 20.**

The cause is not model quality. Locally the sampling seed can be pinned; on a hosted API it
cannot. A judge whose runtime you do not control cannot give you the same answer twice.

Being stable and being right are separate properties. gemma4-12b never contradicts itself
and is the least accurate of the local judges. That combination is the useful one: a stable
judge that is wrong can be fixed by changing the prompt, and you can see immediately whether
the change worked. With an unstable judge you cannot even tell.

## What fixed them

Under the previous prompt (`judge/prompt.md`, v0.3) every judge scored between 2 and 7 —
including the hosted flagships. The repair was not a larger judge. It was replacing "give
three scores" with a procedure:

1. List every quantitative claim first.
2. For each, state its scope: the rows the model saw, or the whole dataset.
3. Name the exact fact you are relying on.
4. **Only then** score, from that list and nothing else.

With one rule at the centre:

> A fact drawn from the rows shown can never support a claim about the whole dataset.

That is ~150 words longer. The same gemma4-31b went from **2/7 to 7/7**, and v0.4.1 is the
best-scoring prompt for every judge tested, not only for the one that ends up on top.

## Reproduce it

```bash
# check the arbitration itself: every case ships with the query that settles it
python -c "import json;[print(json.loads(l)['proof_sql']) for l in open('data/judge-truth-set.jsonl',encoding='utf-8')]"

# re-run a local judge over the seven cases
OLLAMA_HOST=http://your-box:11434 python judge/run_judge.py \
  --dataset runs/judge-calibration/t7-q.jsonl \
  --answers runs/judge-calibration/t7-a.jsonl \
  --output  /tmp/my-run.jsonl \
  --judge ollama --model gemma4:31b --prompt judge/prompt-v041.md
```

Every scored line records its own `judge_config`: host, model, context size, seed, prompt
file and a fingerprint of the prompt text actually sent, plus the batch size and the
position of the case inside the batch. That last pair is not bookkeeping — see below.

## What is not settled

**These seven cases are the ones the rule was written against.** A judge scoring 7/7 has
demonstrated that it follows the rule, not that it generalises. A held-out set exists and is
waiting to be arbitrated by someone other than the author of the rule.

**Batch position changes verdicts.** The same case, judged as the only item of a run, scores
40. Judged after any other case, it scores 100. Same prompt, same seed, same machine, same
3,211 input tokens. The shared system prompt is computed cold on the first request and
served from the prefix cache afterwards, and the numerical difference is enough to flip a
verdict already sitting on a boundary.

Measured: replaying 45 judgments one at a time instead of in a batch changed 2 of them, by 6
and 8 points. The worst case known moves a single question by 30 points, which is 2 points
on a 15-question average.

So the resolution of this instrument is about **2 points**. Two models closer than that are
tied, and the decimals should not be read. Reproducing a score requires replaying the same
list, in the same order, with the same seed — not merely the same seed.
