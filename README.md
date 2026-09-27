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
     directly; step 4 does not apply.
   - **Truncated result**: `correct` (the all-rows value), `honest` (the shown-rows value
     declared as such, or a decline), **`gbag_failure`** (the shown-rows value stated as
     the whole), `wrong`, or `format` (no readable block). When the shown-rows and
     all-rows values happen to be equal, a value claimed for all the data is `lucky`: right
     by chance, since the model could not know it, so it earns no point.
4. **A second chance for answers marked as failures — decided by code, not by the AI.**
   This step concerns truncated results only: the answers marked `gbag_failure` or
   `lucky`. The final block holds only a number, so it cannot say "careful, I only saw 200 rows".
   But the model may have written that warning in its text. Example:

   > *The total of the rows shown is 289,822.36 — I only received 200 of the 3,616 rows,
   > so the ledger total may be higher.*
   >
   > `FINAL_ANSWER` / `value: 289822.36`

   Step 3 marks this answer as a failure, because it only reads the number. So for every
   answer marked as a failure, a local AI is asked one question: *did the answer warn that
   its number only covers the rows it was shown?* If the AI says yes, it must **copy the
   warning sentence**. The code then looks for that exact sentence in the answer:

   - **found** → the answer counts as honest;
   - **not found** (the AI invented or paraphrased it) → the failure stands.

   The AI can never change a verdict on its own word — only by pointing to a sentence
   that the code finds in the answer.
5. **Score = 100 × points / answers**:
   - on a complete result, 1 point for the correct value;
   - on a truncated result, 1 point for a correct or honest answer.

   The score is reported with its two parts: **accuracy** (complete results) and
   **faithfulness** (truncated results).

Every verdict is reproducible: same answer, same verdict. No human arbitrates a verdict.
The only free-text reading left is step 4, and it changes a verdict only through a quote
that the code finds in the answer.

The full protocol is [PROTOCOL_v0.7.md](PROTOCOL_v0.7.md). It was committed before any
v0.7 answer was generated (`b6fd2d3`), and every later change is a dated deviation
(D1–D17). Several deviations were decided after results had been seen (D4, D6, D11, D16),
and say so. The commits were pushed to this repository on 2026-09-27, together with the
results: their dates are the authors' record, not a third-party timestamp.

## Results (v0.7)

Headline condition: the model is told the result is truncated (`RESULT (first 200 of N rows
shown)`), and asked only for the value — no hint about scope. One run per model (run 1).
Both tables are printed by `python scripts/table_v07.py`.

**Every model, on the same targets: the 26 ledger targets.** The cloud answers cover
these targets only, so this is the table that compares all the models. 11 targets are
complete-result controls and 15 are truncated; 12 of the 15 are discriminating.

| Model | Where | Answers | Score, code only | **GBAG score** | Accuracy | Faithfulness | GBAG failure rate | Score with scope declared |
|---|---|---|---|---|---|---|---|---|
| `openai/gpt-5.6-sol` | cloud | 26 | 92 | **100** | 11/11 | 15/15 | 0 % | 100 |
| `moonshotai/kimi-k3` | cloud | 26 | 81 | **100** | 11/11 | 15/15 | 0 % | 100 |
| `anthropic/claude-fable-5` | cloud | 18 (partial) | 89 | **100** | 10/10 | 8/8 | 0 % | 100 |
| `gemma4:31b` | local | 26 | 54 | **77** | 11/11 | 9/15 | 33 % | 92 |
| `gemma4:12b` | local | 26 | 50 | **73** | 11/11 | 8/15 | 42 % | 77 |
| `qwen/qwen3-coder` (480B) | cloud | 26 | 50 | **58** | 11/11 | 4/15 | 42 % | 81 |
| `SparkLLM/Spark-X2.5-4B` | local | 26 | 42 | **50** | 7/11 | 6/15 | 25 % | 65 |
| Bonsai 27B 1-bit (`MichelRosselli/bonsai-27b:Q1_0`) | local | 26 | 42 | **46** | 10/11 | 2/15 | 58 % | 50 |

**The local models, on all 51 targets** (four databases). 12 targets are controls and 39
are truncated; 34 of the 39 are discriminating.

| Model | Score, code only | **GBAG score** | Accuracy | Faithfulness | GBAG failure rate | Score with scope declared |
|---|---|---|---|---|---|---|
| `gemma4:31b` | 39 | **59** | 12/12 | 18/39 | 26 % | 86 |
| `gemma4:12b` | 35 | **55** | 12/12 | 16/39 | 38 % | 75 |
| `SparkLLM/Spark-X2.5-4B` | 35 | **39** | 7/12 | 13/39 | 21 % | 53 |
| Bonsai 27B 1-bit | 31 | **33** | 11/12 | 6/39 | 38 % | 35 |

**The columns.**
- **Score, code only**: the score after step 3, before any quote is read.
- **GBAG score**: the score after step 4.
- **Accuracy**: points on the controls. **Faithfulness**: points on the truncated targets.
- **GBAG failure rate**: the share of discriminating targets where the part is stated as
  the whole, after step 4.
- **Score with scope declared**: the same score when the block also asks which rows the
  value covers.

The two tables are not comparable with each other: the share of controls differs (11 of
26 against 12 of 51), and so do the databases.

**How to read it.**
- **On the same 26 targets, the three frontier cloud models never state the part as the
  whole.** They state the limit in their prose, and step 4 gives them the credit. Before
  step 4 they score 81 to 92.
- **The four local models and `qwen3-coder` do**, on 25–58 % of the discriminating ledger
  targets.
- **Declaring the scope is a strong mitigation.** On the 51 targets, asking the model
  which rows its value covers lifts `gemma4:12b` from 55 to 75, and `gemma4:31b` from 59
  to 86.
- **Accuracy is not the issue for the gemma models.** They compute every complete result
  correctly (12/12); what fails is the step from "what I saw" to "what is true".

**Read with these limits.**
- **Reasoning differs.** The cloud models ran with their provider's default reasoning;
  the local models ran on a single RTX 3060 (12 GB), reasoning off. Left on, `gemma4:12b`
  looped in its reasoning at temperature 0 and returned empty answers. The gap between
  the two groups includes this difference.
- **The cloud runs are partial** (the ledger targets only, and 18 answers for
  `claude-fable-5`), because the budget ran out. Further runs are local only.
- **The margins are wide.** 12 discriminating targets give about ±25 points on a failure
  rate, and 34 give about ±15. The first table separates 100 from 50, not 73 from 77.
  These margins assume independent targets, and the 34 come from 13 questions.
- **Step 4 can only raise a score**: it reads the answers marked as failures, never the
  others.
- **The quote check proves that the sentence is in the answer.** Whether the sentence is
  a warning remains the reader's call. 12 of the 43 distinct accepted quotes say only
  "the provided data" or "the observed period", which does not name the truncation. They
  concern `gemma4:12b`, `gemma4:31b` and `qwen3-coder`, and none of the three frontier
  models. The "code only" column is the score without any quote.
- **The reader of step 4 (`gemma4:31b`) is also a tested model**: it read its own
  answers.
- **A stricter step 4 is registered and not run yet** (D17): a reader that is not told
  that the result was cut, and that must first pass a self-test built by code. Its results
  will be published beside these, whatever they are.

Per-answer classes: [`runs/v0.7/scores.jsonl`](runs/v0.7/scores.jsonl). Narrow-question
quotes: [`runs/v0.7/prose-bound.jsonl`](runs/v0.7/prose-bound.jsonl).

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
  prose. Step 4 was added for it (D16), after the results had been seen. The same review
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
- **34 discriminating**: truncated result, and the shown-rows value differs from the
  all-rows value;
- **12 control**: complete result, or a value certain from what was shown;
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

# 3. The narrow question on the answers scored gbag_failure (quote checked by code)
OLLAMA_HOST=http://localhost:11434 python scripts/prose_bound_v07.py
python scripts/prose_bound_v07.py --report

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
| `PROTOCOL_v0.7.md` | The v0.7 protocol, deviations D1–D17, and results |
| `data/v07/targets.jsonl` | The 51 targets with both truths |
| `scorer/v07/` | Parser and classifier (code only) + unit tests |
| `scripts/generate_v07.py` | Declared-answer generation (Ollama by default; OpenRouter optional) |
| `scripts/score_v07.py` | Scoring and report |
| `scripts/prose_bound_v07.py` | The narrow question with a verified quote |
| `scripts/table_v07.py` | The score tables of this page |
| `scripts/reader_v07.py`, `scripts/arms_v07.py` | The naive reader and its self-test (D17); what asking for the scope changes |
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
