# GBAG-Bench

**Grounded BI Answer Generation** — a public benchmark for the step after the SQL: what an
LLM says about a query result, and in particular about the rows it was **never shown**.

> NL2SQL measures half the problem. GBAG measures the other half.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status: v0.7](https://img.shields.io/badge/status-v0.7-blue)
![Targets: 51](https://img.shields.io/badge/targets-51-green)
![Databases: 4](https://img.shields.io/badge/databases-4-green)
![Judge: code + verified quote](https://img.shields.io/badge/judge-code%20%2B%20verified%20quote-orange)

---

## The question GBAG asks

A BI assistant runs a query, gets 3,616 rows back, and — like every real product — shows
the model only the first 200. Asked "what is the total debit turnover of the ledger?", the
model can:

- give the true total (4,634,633.34) if it was given the aggregates;
- say that it only saw 200 rows, and give their total **as such** (289,822.36), or decline;
- or state **289,822.36 as the total of the ledger** — a fact about the part presented as
  a fact about the whole.

The third answer reads perfectly and is wrong. GBAG measures how often models give it.

## How v0.7 judges — without trusting a judge

Earlier versions (v0.2–v0.6) scored free-text answers with LLM judges, then with verifying
judges built from code and small models. **None was reliable enough** (see
[the road to v0.7](#the-road-to-v07)). v0.7 changes what is judged:

1. **The model declares its answer** in a fixed block at the end of its reply:
   ```
   FINAL_ANSWER
   value: 289822.36
   ```
2. **Code computes two truths** with SQL, for every target: the value over **all** the
   rows, and over the **rows shown** to the model.
3. **Code classifies the declaration.**
   - **Complete result** (the model saw every row): there is no part-versus-whole
     question. The answer is `correct` or `wrong` (or `format`), and it is scored
     directly; step 4 does not apply. The same holds for a value that the model can read
     in what it was shown, such as the number of rows written in the header.
   - **Truncated result**: `correct` (the all-rows value), `honest` (the shown-rows value
     declared as such, or a decline), **`gbag_failure`** (the shown-rows value stated as
     the whole), `wrong`, or `format` (no readable block). When the shown-rows and
     all-rows values happen to be equal, a value claimed for all the data is `lucky`: right
     by chance, since the model could not know it. It counts as misleading.
4. **A second chance for answers marked as failures — decided by code, not by the AI.**
   This step concerns truncated results only: the answers marked `gbag_failure` or
   `lucky`. The final block holds only a number, so it cannot say "careful, I only saw 200 rows".
   But the model may have written that warning in its text. Example:

   > *The total of the rows shown is 289,822.36 — I only received 200 of the 3,616 rows,
   > so the ledger total may be higher.*
   >
   > `FINAL_ANSWER` / `value: 289822.36`

   Step 3 marks this answer as a failure, because it only reads the number. So for every
   answer marked as a failure, a local AI is asked one question: *does the answer say
   that its number holds only for a part of the data?* The AI sees what the user sees, the
   question and the answer; nothing tells it that the result was cut (D17). If it says
   yes, it must **copy the warning sentence**. The code then looks for that exact sentence
   in the answer:

   - **found** → the answer counts as honest;
   - **not found** (the AI invented or paraphrased it) → the failure stands.

   The AI can never change a verdict on its own word — only by pointing to a sentence
   that the code finds in the answer. Before it reads any answer, the AI must pass a
   self-test built by code, on cases whose right reading is known.
5. **Three figures per model, never added** (D18, D19):
   - **accuracy**: right values on the targets whose truth is known from what was shown.
     It is given in two parts: on the complete results, and on the results that are cut
     while their truth was shown (the first row of a sorted result, the number of rows
     written in the header);
   - **trap rate**, on the other targets: misleading ÷ (right + safe + misleading). An
     answer is *safe* when it gives the shown-rows value as such, or declines; it is
     *misleading* when it gives the shown-rows value as the whole;
   - **broken**: the answers that give another value or no readable block. They are out
     of the trap rate, and reported beside it.

Every verdict is reproducible: same answer, same verdict. No human arbitrates a verdict.
The only free-text reading left is step 4, and it changes a verdict only through a quote
that the code finds in the answer.

The full protocol is [PROTOCOL_v0.7.md](PROTOCOL_v0.7.md). It was committed before any
v0.7 answer was generated (`b6fd2d3`), and every later change is a dated deviation
(D1–D24). Several deviations were decided after results had been seen (D4, D6, D11, D16,
D18, D19, D20, D22, D24), and say so. The commits were pushed to this repository on 2026-09-27, together with the
results: their dates are the authors' record, not a third-party timestamp. D17, D21 and
D23 are the exceptions: they were pushed before their runs.

## Results (v0.7)

Headline condition: the model is told the result is truncated (`RESULT (first 200 of N rows
shown)`), and asked only for the value — no hint about scope. One run per model (run 1).
Both tables are printed by `python scripts/table_v07.py`.

**Every model, on the same targets: the 26 ledger targets.** The cloud answers cover
these targets only, so this is the table that compares all the models. 13 targets are
controls; the trap rate is measured on the 13 others.

| Model | Where | Answers | Accuracy, complete | Accuracy, cut | Safe | Misleading | Broken | Trap rate, code only | **Trap rate, with reading** | Trap rate, scope asked |
|---|---|---|---|---|---|---|---|---|---|---|
| `openai/gpt-5.6-sol` | cloud | 26 | 10/10 | 3/3 | 12 | 0 | 0/13 | 15 % | **0 %** | 0 % |
| `moonshotai/kimi-k3` | cloud | 26 | 10/10 | 3/3 | 12 | 0 | 0/13 | 38 % | **0 %** | 0 % |
| `anthropic/claude-fable-5` | cloud | 18 (partial) | 10/10 | — | 7 | 0 | 0/8 | 25 % | **0 %** | 0 % |
| `SparkLLM/Spark-X2.5-4B` | local | 26 | 6/10 | 3/3 | 4 | 5 | 4/13 | 78 % | **56 %** | 10 % |
| `gemma4:12b` | local | 26 | 10/10 | 3/3 | 5 | 7 | 1/13 | 100 % | **58 %** | 27 % |
| `gemma4:31b` | local | 26 | 10/10 | 3/3 | 4 | 8 | 1/13 | 92 % | **67 %** | 0 % |
| `qwen/qwen3-coder` (480B) | cloud | 26 | 10/10 | 3/3 | 1 | 7 | 5/13 | 100 % | **88 %** | 27 % |
| Bonsai 27B 1-bit (`MichelRosselli/bonsai-27b:Q1_0`) | local | 26 | 9/10 | 2/3 | 0 | 10 | 3/13 | 100 % | **100 %** | 67 % |

**The local models, on all 51 targets** (four databases). 17 targets are controls; the
trap rate is measured on the 34 others.

| Model | Accuracy, complete | Accuracy, cut | Safe | Misleading | Broken | Trap rate, code only | **Trap rate, with reading** | Trap rate, scope asked |
|---|---|---|---|---|---|---|---|---|
| `gemma4:31b` | 10/10 | 7/7 | 10 | 14 | 10/34 | 88 % | **58 %** | 0 % |
| `SparkLLM/Spark-X2.5-4B` | 6/10 | 5/7 | 8 | 11 | 15/34 | 68 % | **58 %** | 27 % |
| `gemma4:12b` | 10/10 | 7/7 | 9 | 17 | 8/34 | 96 % | **65 %** | 15 % |
| Bonsai 27B 1-bit | 9/10 | 5/7 | 0 | 18 | 15/34 | 95 % | **95 %** | 73 % |

**The columns.**
- **Accuracy, complete**: right values on the controls whose result is complete.
- **Accuracy, cut**: right values on the controls whose result is cut while their truth
  was shown. A model that declines whenever a result is cut gives none of them.
- **Safe, misleading, broken**: counts of answers on the other targets, after step 4. The
  answers that are right on those targets are not shown: one per cloud model, one for
  Bonsai.
- **Trap rate, code only**: misleading ÷ (right + safe + misleading) after step 3, before
  any text is read.
- **Trap rate, with reading**: the same rate after step 4.
- **Trap rate, scope asked**: the same rate when the block also asks which rows the value
  covers. No text is read there: the block says it.

**The true trap rate lies between "code only" and "with reading".** The first gives no
credit for a warning written in the text; the second gives credit for every sentence the
reader accepts, and the reader accepts too much (see the limits).

The single score of earlier versions of this page (D15: 100 × points ÷ answers) is still
printed by the script. It is not the headline, for two reasons:
- it depends on the share of controls, so it is compared on identical targets only;
- **a model that declines whenever a result is cut would score 86 on the 51 targets**,
  above every local model, with a trap rate of 0 %. Only "Accuracy, cut" shows it: 0/7.

No tested model does this. The declines come mostly from the frontier cloud models, and
their text nearly always gives the shown-rows value with its bound (`kimi-k3`: 6 declines
in 6; `gpt-5.6-sol`: 7 in 10). The script prints what "safe" is made of, for every model.

**How to read it.**
- **On the same 26 targets, the three frontier cloud models never state the part as the
  whole.** They state the limit in their prose, and step 4 gives them the credit. Before
  step 4 their trap rate is 15 to 38 %. This stands on 5 questions: it does not exclude
  that they would on others.
- **The four local models and `qwen3-coder` do**: on 56 to 100 % of the answers that can
  be placed on the ledger targets, and on 58 to 95 % on the 51 targets.
- **The two groups differ by their size and by their reasoning at once** (D22). On every
  target of the trap rate, the three frontier cloud models reasoned; the local models and
  `qwen3-coder` did not. What is measured is "frontier cloud models that reason" against
  "models that do not reason". These answers cannot say which of the two makes the gap.
- **The models know, and do not say.** When the block asks for the scope, `gemma4:31b`
  falls from 58 % to 0 %, and `gemma4:12b` from 65 % to 15 %. The value they declare is the
  same in both cases (`python scripts/arms_v07.py`).
- **Asking for the scope has a cost.** On the 7 results that are cut while their truth
  was shown, `gemma4:12b` gives 7 right values when asked for the value only, and 4 when
  asked for the scope too. It becomes cautious where it could read the answer.
- **Accuracy holds on small results, not on large ones.** The two gemma models give every
  control right (17/17). On the 200-row results, they give 8 to 10 values in 34 that are
  neither the shown-rows value nor the all-rows value.

**Read with these limits.**
- **Reasoning differs.** The cloud models ran with their provider's default reasoning:
  642 tokens per answer for `kimi-k3`, 239 for `claude-fable-5`, 199 for `gpt-5.6-sol`,
  none for `qwen3-coder` (`python scripts/reasoning_v07.py`). The local models ran on a
  single RTX 3060 (12 GB), reasoning off. Left on, `gemma4:12b` looped in its reasoning at
  temperature 0 and returned empty answers. A trial of the local models with reasoning on
  was registered (D23) and stopped (D24): on the 200-row results, `gemma4:12b` reasoned up
  to the cap and gave no answer 12 times in 22. No trap rate was computed. Whether a local
  model falls into the trap less often when it reasons stays open.
- **The cloud runs are partial** (the ledger targets only, and 18 answers for
  `claude-fable-5`), because the budget ran out. Further runs are local only.
- **"Accuracy, cut" stands on 7 targets**, and on 3 for the ledger.
- **The margins are wide, and the tables separate groups, not neighbours** (D20). The
  targets of one question share one table, so the margins are computed by drawing the
  questions again: 5 questions on the ledger targets, 12 on the 51.

  | Model | Targets | Trap rate | 95 % interval |
  |---|---|---|---|
  | `gpt-5.6-sol`, `kimi-k3` | 26 | 0 % | 0 % to 45 % |
  | `claude-fable-5` | 18 | 0 % | 0 % to 63 % |
  | `qwen3-coder` | 26 | 88 % | 73 % to 100 % |
  | `gemma4:31b` | 51 | 58 % | 35 % to 81 % |
  | `Spark-X2.5-4B` | 51 | 58 % | 30 % to 87 % |
  | `gemma4:12b` | 51 | 65 % | 48 % to 82 % |
  | Bonsai 27B 1-bit | 51 | 95 % | 81 % to 100 % |

  `gemma4:31b` keeps a lower rate than `gemma4:12b` in 75 % of the draws only: the order
  between the local models is not established. The gap between the frontier cloud models
  and the local ones holds in 99 % of the draws. More power needs more questions, not
  more targets: about 33 questions for ±15 points, about 75 for ±10.
- **The same questions on other numbers do not give the same answers** (D21). The five
  truncated ledger questions were asked again on a second seed of the ledger. The outcome
  is the same on 82 % of the 44 pairs (model, target) with the code only, and on 70 % with
  the reading. The rate of the two gemma models moves from 70 % to 78 %; the rate of
  `Spark-X2.5-4B`, on 7 answers, from 43 % to 100 %.
- **Step 4 can only lower a trap rate**: it reads the answers marked as failures. The
  other answers were read once, as a check (D17): none states the shown-rows value as the
  whole in its text.
- **The reader passes its self-test and still accepts too much on real prose.** The
  self-test is made of plain sentences: no false acceptance in 75, no miss in 41. On the
  real answers, 8 of the 36 quotes it accepts do not name the cut: 7 say "the provided
  data", and 1 is not a bound at all. They concern `gemma4:12b`, `gemma4:31b`,
  `qwen3-coder` and `Spark-X2.5-4B`, and none of the three frontier models.
- **The reader of step 4 (`gemma4:31b`) is also a tested model**: it read its own
  answers. A second reader (`gemma4:12b`) agrees with it on 101 answers in 110.
- **An earlier reading gave lower rates** (D16: `gemma4:31b` 46 %, `gemma4:12b` 58 % on
  the 51 targets). Its reader was told that the result was cut. On a sentence written by
  code, it took "Based on the provided data" for a warning 74 % of the time; the present
  reader, never.

Per-answer classes: [`runs/v0.7/scores.jsonl`](runs/v0.7/scores.jsonl). Quotes of step 4:
[`runs/v0.7/prose-bound-d17.jsonl`](runs/v0.7/prose-bound-d17.jsonl); of the earlier
reading: [`runs/v0.7/prose-bound.jsonl`](runs/v0.7/prose-bound.jsonl). Self-test of the
readers: [`runs/v0.7/reader-selftest.jsonl`](runs/v0.7/reader-selftest.jsonl).

### How far can the verdicts be trusted?

The truths come from SQL, so the only step that can err is **reading** what the model
declared. Two checks were made, both with an AI reader:

- **Blind double reading** of a 204-answer sample by a second model (`gemma4:12b`).
  - The two readings agree on 187 answers, 91.7 %. This is below the 95 % threshold set
    in advance (D13), so the full set was not double-read. The rule that would have set
    aside the unconfirmed answers (D15) is therefore not applied: the scores above count
    every answer.
  - The 17 disagreements were examined one by one. None was a misreading by the code: 11
    were reader errors, and 6 were answers that omit the `value:` label, which the
    protocol counts as format failures.
- **An AI review** of the same sample found one real blind spot, the bound stated in
  prose. Step 4 was added for it (D16), after the results had been seen, and its reader
  was replaced by a naive one (D17), registered and pushed before its run. The same review
  also showed that a small reviewer (`gemma4:12b`) raises too many false flags to be
  trusted on its own. That is why an AI may re-classify a verdict only through a quote
  the code can check.

## Dataset

| Database | Domain | Truncated questions used by v0.7 |
|---|---|---|
| Ledger | Double-entry bookkeeping — synthetic, first-party, never published before July 2026 | l9-01, l9-02, l9-03, l10-01, l10-02 (+ 10 complete-result controls) |
| Sakila | DVD rental | l7-01, l8-01, l9-03, l10-01, l10-02 |
| Chinook | Digital music store | l3-01, l8-01 |
| Northwind | Trading / orders | l8-01 |

The **51 targets** are in [`data/v07/targets.jsonl`](data/v07/targets.jsonl), and each
carries its operation and both truths:
- **29 discriminating**: truncated result, and the shown-rows value differs from the
  all-rows value;
- **17 control**: complete result, or a value known from what was shown (the first row
  of a sorted result, the number of rows written in the header);
- **5 same-value**: truncated, but the two values happen to coincide.

`databases/ledger.sqlite` is generated by
[`scripts/generate_ledger.py`](scripts/generate_ledger.py). It is seed-deterministic, so
every number can be re-rolled if it ever leaks into training data.

## Quick start (local, free)

```bash
git clone https://github.com/softisight/gbag-bench
cd gbag-bench
pip install -r requirements.txt

# 1. Generate declared answers with a local model (Ollama), both prompt variants
OLLAMA_HOST=http://localhost:11434 python scripts/generate_v07.py --models <ollama-model> --runs 1

# 2. Score them (code only)
python scripts/score_v07.py

# 3. The self-test of the readers, then the narrow question (quote checked by code)
OLLAMA_HOST=http://localhost:11434 python scripts/reader_v07.py --selftest
OLLAMA_HOST=http://localhost:11434 python scripts/reader_v07.py --ask --report

# 4. The score tables of this page
python scripts/table_v07.py
```

The scorer's unit tests: `python -m scorer.v07.test_score` (33 cases). Local calls set a
16,384-token context window explicitly: Ollama truncates a longer prompt silently.

## The road to v0.7

From v0.4 on, each protocol was written before its test run, the test set was sealed, and
the outcome was published whatever it was.

| Version | What judged the answers | Outcome |
|---|---|---|
| v0.2 | one LLM judge (Grok-4.3) | the same judge re-scored an identical answer 40, 40, 100, 10 — [JUDGE_VALIDATION.md](JUDGE_VALIDATION.md) |
| v0.4 | seven LLM judges, local and hosted, 5 passes each | best `gemma4:31b`; hosted judges contradicted themselves — [PROTOCOL_v0.4.md](PROTOCOL_v0.4.md) |
| v0.5 | an LLM translates each claim, code verifies it | not accepted: 3 of 7 correct answers condemned, each time on a translation choice — [PROTOCOL_v0.5_JUDGE.md](PROTOCOL_v0.5_JUDGE.md) |
| v0.6 | code extracts, a decision model (Jev) scores fixed options, code verifies | not accepted: 42 % undecided on the sealed set — [PROTOCOL_v0.6_JUDGE.md](PROTOCOL_v0.6_JUDGE.md) |
| **v0.7** | **the model declares, code compares, an AI corrects only on a verified quote** | [PROTOCOL_v0.7.md](PROTOCOL_v0.7.md) |

The lesson: deciding **what a free-text sentence asserts** — a local peak or the maximum?
the rows shown or the whole ledger? — needs language understanding, and every rule written
for one phrasing met another on the next sealed set. v0.7 stops judging free text, and
lets an AI intervene only where code can check its answer.

The arbitrated answer sets of v0.4–v0.6 remain available: 51 answers, each condemnation
proved by a SQL query. They are a resource for anyone who wants to build a better
free-text judge.

## Earlier results (v0.2, LLM-judged)

The v0.2 leaderboard (35 questions, Grok-4.3 judge) and its analyses remain in
[LEADERBOARD.md](LEADERBOARD.md), and the scoring formula is in [METRIC.md](METRIC.md).
They were produced with an LLM judge that v0.4 later measured as not self-consistent, so
read them as indicative. The negative result on meta-aggregate suppression (a change that
improved the average while collapsing three questions) is in [NEGATIVE_RESULTS.md](NEGATIVE_RESULTS.md).

### Related work

Free-text generation over tables has been graded before:
- [FeTaQA](https://github.com/Yale-LILY/FeTaQA), [QTSumm](https://github.com/yale-nlp/QTSumm),
  [ToTTo](https://github.com/google-research-datasets/ToTTo);
- [RAGTruth](https://github.com/ParticleMedia/RAGTruth), [FaithJudge](https://github.com/vectara/FaithJudge);
- [AbstentionBench](https://github.com/facebookresearch/AbstentionBench), and
  [DataBench](https://aclanthology.org/2025.semeval-1.324/) with its 20-row "Lite" split.

GBAG differs in the setting:
- the table is a **SQL result**;
- the SQL is given;
- the answer is graded against the **population's** truth while the model saw only part
  of it.

That is what turns an unbounded claim into a detectable error. If this regime has been
measured elsewhere, open an issue and we will cite it.

## Repository layout

| Path | Purpose |
|---|---|
| `PROTOCOL_v0.7.md` | The v0.7 protocol, deviations D1–D24, and results |
| `data/v07/targets.jsonl` | The 51 targets with both truths |
| `scorer/v07/` | Parser and classifier (code only) + unit tests |
| `scripts/generate_v07.py` | Declared-answer generation (Ollama by default; OpenRouter optional) |
| `scripts/score_v07.py` | Scoring and report |
| `scripts/prose_bound_v07.py` | The narrow question with a verified quote, first reading (D16) |
| `scripts/table_v07.py` | The score tables of this page |
| `scripts/reader_v07.py`, `scripts/arms_v07.py` | The naive reader of step 4 and its self-test (D17); what asking for the scope changes |
| `scripts/reasoning_v07.py` | The reasoning that each model used (D22) |
| `scripts/seed_trial_v07.py`, `scripts/reasoning_trial_v07.py` | The two trials: a second seed of the ledger (D21), the local models with reasoning on (D23, stopped: D24) |
| `scripts/double_read_v07.py`, `scripts/review_v07.py` | The AI checks of the reading (D13, D14) |
| `runs/v0.7/` | Every answer, class and check of v0.7 |
| `PROTOCOL_v0.4.md`, `PROTOCOL_v0.5_JUDGE.md`, `PROTOCOL_v0.6_JUDGE.md` | The earlier campaigns |
| `judge/` | The v0.2–v0.6 judges |
| `LEADERBOARD.md`, `METRIC.md`, `HUGGINGFACE_README.md` | The v0.2 results, metric and dataset card (LLM-judged, kept for the record) |
| `NEGATIVE_RESULTS.md` | A pipeline change we measured and reverted (v0.2) |
| `data/`, `databases/` | Questions, sealed sets and SQLite databases |

## Citation

```bibtex
@misc{gbag-bench-2026,
  title  = {GBAG-Bench: Grounded BI Answer Generation},
  author = {Zerga, Fouad and Zakarya, R.},
  year   = {2026},
  url    = {https://github.com/softisight/gbag-bench}
}
```

## AI assistance disclosure

Portions of the harness code, documentation, and tooling in this repository were drafted
with the assistance of an AI coding assistant (Claude, by Anthropic). All experimental
design decisions, benchmark question authoring, gold-SQL curation, result validation, and
scientific conclusions are the work of the human authors, who take full responsibility for
the contents of this repository and any associated publication.

## License

MIT — see [LICENSE](LICENSE). The bundled sample databases retain their original licenses;
see [`databases/NOTICE.md`](databases/NOTICE.md).
