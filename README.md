# GBAG-Bench

**Grounded BI Answer Generation** — a public benchmark for the step after the SQL: how faithfully an LLM interprets a query result into a natural-language answer.

> NL2SQL measures half the problem. GBAG measures the other half.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status: v0.2](https://img.shields.io/badge/status-v0.2-blue)
![Questions: 35](https://img.shields.io/badge/questions-35-green)
![Databases: 3](https://img.shields.io/badge/databases-3-green)

---

## Why GBAG

Existing benchmarks (Spider, BIRD, WikiSQL) measure whether a model generates correct SQL. They stop there. But in a real BI product, what the user reads is the **natural-language answer** the model writes after the SQL is executed — and that step is where most failures actually happen.

A correct SQL query followed by a hallucinated number, an inverted trend, or a missing key insight is **still a failed product experience**. GBAG isolates and measures that second half.

### Related work

Grading free-form text generated over tabular data is not new, and GBAG does not claim to be first at it:

- **[FeTaQA](https://github.com/Yale-LILY/FeTaQA)** (TACL 2022) — 10K Wikipedia tables with free-form answers, evaluated on faithfulness and comprehensiveness.
- **[QTSumm](https://github.com/yale-nlp/QTSumm)** (EMNLP 2023) — 7,111 query-summary pairs over 2,934 tables; query-focused table summarization.
- **[ToTTo](https://github.com/google-research-datasets/ToTTo)** (Google) — controlled table-to-text, built around faithfulness to highlighted cells.
- **[RAGTruth](https://github.com/ParticleMedia/RAGTruth)** — word-level hallucination corpus, including a data-to-text task over structured JSON.
- **[FaithJudge](https://github.com/vectara/FaithJudge)** (Vectara) — LLM-as-judge for faithfulness, with a public leaderboard.
- **[AbstentionBench](https://github.com/facebookresearch/AbstentionBench)** (NeurIPS 2025) — 20 datasets on when a model should decline to answer, underspecified context included. Its headline result, that abstention is unsolved and scale barely helps, is the same family of failure GBAG's held-out cliff exposes in a BI setting.
- **[DataBench](https://aclanthology.org/2025.semeval-1.324/)** (SemEval 2025 Task 8) — QA over real tabular datasets, with a "Lite" split capped at 20 sampled rows. Closest published setup to the held-out cliff, and instructive by contrast: Lite carries a separate `sample_answer`, so the model is graded on the sample against the sample's own answer. GBAG grades a 200-row slice against the **population's** answer, which is what turns an unbounded claim into a detectable error rather than a mere omission.

What GBAG adds is the setting rather than the task. The table is a **SQL result from a relational database**, not a curated Wikipedia table, so its shape is whatever the query returns. The **SQL is given**, which isolates interpretation from query generation. And the held-out suite grades answers written over a result the model **only partly received** — what it asserts about the rows it was never shown. We could not find that regime measured elsewhere; if it has been, open an issue and we will cite it.

## What it evaluates

Given:
- a natural-language **question**
- the executed **SQL**
- the full **result set** (rows + columns)

…can the model produce a **faithful**, **complete**, and **insightful** natural-language answer?

Scoring is performed by an LLM judge against a hand-crafted gold answer and a list of expected atomic insights. The single number reported is the **GBAG Score**:

```
GBAG Score = 0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight
```

Faithfulness dominates because in BI, a hallucinated number causes a wrong real-world decision.

See [METRIC.md](METRIC.md) for the full rubric and [SCHEMA.md](SCHEMA.md) for the question format.

## Dataset composition

35 questions across 3 public SQLite databases:

| Database | Domain | Questions | Difficulty range |
|---|---|---|---|
| Sakila | DVD rental | 15 | 1–10 |
| Chinook | Digital music store | 10 | 1–8 |
| Northwind | Trading / order management | 10 | 1–8 |

Each database contributes the same 10-question core ladder: one question per level 1–5, two at level 6, one at level 7, two at level 8. Sakila adds 5 extreme questions (three at level 9, two at level 10) whose result sets reach 16,049 rows.

By category: `aggregation` (11), `trend` (11), `derived` (7), `join` (3), `ranking` (3).

Question ids encode the database and level (`sakila-l6-02` = Sakila, difficulty 6, second question at that level). See [SCHEMA.md](SCHEMA.md) for the per-question format.

### Held-out suite (v0.3)

| Database | Domain | Level 1 (core) | Level 2 (full) | Difficulty |
|---|---|---|---|---|
| Ledger | Double-entry bookkeeping (synthetic, first-party) | 10 questions | 15 questions | 1–10 |

The held-out suite ships in **two levels** so it is fair across model sizes:

- **Level 1** ([`data/questions-heldout-level1.jsonl`](data/questions-heldout-level1.jsonl), 10 questions, difficulty 1-8) is the core ladder. Small local models can show real competence here without being buried by the extreme tier.
- **Level 2** ([`data/questions-heldout.jsonl`](data/questions-heldout.jsonl), 15 questions, difficulty 1-10) adds the 5-question extreme tier (`ledger-l9/l10`) to separate frontier models. Each question in the file carries a `level` field.

`databases/ledger.sqlite` is a fully synthetic double-entry accounting database (a fictional UK trading company: chart of accounts, 7 journals, 3 fiscal years of balanced entries, VAT returns, payroll, and a handful of deliberate unmarked audit anomalies), generated by [`scripts/generate_ledger.py`](scripts/generate_ledger.py). Unlike Sakila/Chinook/Northwind, it had **never been published anywhere** before this repository (first publication: July 2026), so it cannot appear in the training data of any model released before that date. Its 15 questions live in [`data/questions-heldout.jsonl`](data/questions-heldout.jsonl) (same schema and id convention, `ledger-l1-01`, ...), built reproducibly by [`scripts/build_heldout_dataset.py`](scripts/build_heldout_dataset.py). They replicate the public suite's structure, including an **extreme l9/l10 tier** whose gold SQL returns large result sets (up to ~3,600 rows) that exceed the 200-row prompt cap, testing whether a model faithfully reports the result shape or fabricates the requested full-set analysis.

Why a held-out suite:

- **Contamination probe.** The public sample databases (and many of their aggregates) circulate in training corpora. A model whose score drops sharply from the public suite to the held-out suite is likely reciting memorized facts rather than reading the result set.
- **Regenerable.** The generator is seed-deterministic: future benchmark versions can re-roll every number (new seed, same schema), so memorizing a published snapshot has a short shelf life.

The held-out suite is scored separately and does not affect the main 35-question GBAG score (v0.2 comparability preserved). **Status:** eight baseline runs (seven full 15-question runs — claude-fable-5, gpt-5.6-sol, kimi-k3, nemotron-3-nano-30b-a3b, qwen3-coder-480b, qwen3.6, gemma4-12b — plus one partial pipeline run) are published in [`runs/`](runs/) as `*-heldout.jsonl` with their `.scored-grok43.jsonl` judgments, scored under [judge prompt v0.2](judge/prompt.md); per-question scores are recomputable from those files alone. The summary table lives in [LEADERBOARD.md](LEADERBOARD.md); the cliff chart lands with the v0.3 README update. Regenerate the DeskInsight Runner suite for this database with [`scripts/export_heldout_to_deskinsight.py`](scripts/export_heldout_to_deskinsight.py).

## v0.2 leaderboard — uniform Grok-4.3 judge

> Bare models, neutral Spider/BIRD-style prompt, one uniform judge. Every row reproduces for about a dollar (see [Quick start](#quick-start)). Full table, archived v0.1 results and inter-judge variance: [LEADERBOARD.md](LEADERBOARD.md).

| Model | Provider | Coverage | **GBAG** |
|---|---|---|---|
| `nvidia/llama-3.3-nemotron-super-49b-v1` | NVIDIA NIM | 35/35 | **67.7** |
| `qwen/qwen3-coder-480b-a35b-instruct` | NVIDIA NIM | 35/35 | **64.6** |
| `qwen/qwen3-next-80b-a3b-thinking` | NVIDIA NIM | 35/35 | **61.4** |
| `qwen3.5:9b` | Ollama (local, RTX 3060) | 32/35 | **59.6** |
| `qwen/qwen3-next-80b-a3b-instruct` | NVIDIA NIM | 28/35 | **58.9** |

### What context engineering changes (same model, same judge)

The pipeline row is kept out of the ranking above on purpose: it measures a model wrapped in a commercial system, not a bare model.

| Configuration | Coverage | **GBAG** |
|---|---|---|
| `qwen3.5:9b`, neutral prompt | 32/35 | 59.6 |
| `qwen3.5:9b` + DeskInsight pipeline | 35/35 | **76.8** |

Same weights, same GPU, same questions, same judge; only the context changes. Worth +17 points under Grok-4.3 and +7 under a second judge (a range, see finding 1). This pair is the one thing in this repository that needs a commercial tool to reproduce; everything else runs without it.

## Five findings

Each finding below survived our own verification process, including two corrections we publish rather than hide. The paragraphs give you the shape; the links hold the full numbers.

1. **Context beats scale.** The same 9B model, on the same consumer GPU and the same questions, scores 59.6 with a bare prompt and 76.8 wrapped in a context-engineering pipeline. A second judge shrinks the gain from +17 to +7 but keeps its direction, so the honest claim is a range: +7 to +17 points on identical weights. Full dual-judge tables: [Robustness check](LEADERBOARD.md#robustness-check-second-judge-on-the-headline-comparison). Reproduction recipe: [Methodology](LEADERBOARD.md#methodology--how-the-deskinsight-pipeline-line-was-obtained).

2. **Bigger is barely better.** Judged uniformly, the 9B sits about 3 points below a 480B MoE that activates 35B parameters per token. Three points is well inside the judge's own noise, so read it as a tie, not a ranking.

3. **The judge moves scores as much as the model does.** Identical answers scored 72.7 under a lenient judge and 59.6 under a strict one: 13 points apart on the same text. Single-judge benchmarks are unreliable, which is why the board uses one uniform reference judge and publishes judge disagreement as data: [Inter-judge variance](LEADERBOARD.md#inter-judge-variance).

4. **Thinking: no measurable effect (a corrected claim).** We first wrote that thinking modes hurt grounded tasks; that compared different models, which is confounded, and the claim is withdrawn. The clean same-family ablation reads 60.6 vs 58.9 on the 28 questions both variants answered — inside the noise floor. Non-result, either way, until matched re-runs settle it.

5. **Fabrication is concentrated, not universal.** When a query returns a few rows drawn from a large table, small local models sometimes invent the aggregates (we call it the Post-SQL Aggregation Deficit). Injecting pre-computed aggregates removes most of it; the rest of the benchmark barely shows the pattern.

What we would not claim from this table: any ranking inside 3 points, any effect only one judge saw, and any number you cannot recompute yourself — the pipeline row is the single exception, and it is labeled as such.

## Why can an LLM judge another LLM?

The benchmark's scoring rests on LLM-as-judge, so the question deserves a direct answer.

1. **Verifying is easier than producing.** The judge never answers the BI question itself. It checks the candidate answer against material it is handed: the executed SQL, a human-written gold answer, and a checklist of expected insights. Reading-and-matching is a strictly easier task than the open-ended generation being graded.
2. **The judge grades with an answer key, not from its own knowledge.** Every question ships a `gold_answer` and atomic `expected_insights`, both human-curated. Completeness is near-mechanical (insights matched / insights expected). The judge acts as a grader with a rubric, not as an oracle.
3. **The rubric leaves little room for taste.** Anchored score bands per axis, a ±2% numeric tolerance, temperature 0, strict JSON output, and explicit rules against rewarding style or verbosity. The full prompt is published in [judge/prompt.md](judge/prompt.md); challenge it there if you disagree with a band.
4. **Judge error is measured, not assumed away.** Finding #3 above quantifies it: re-judging identical answers moved the score by 13 points between two judges. That is exactly why v0.2 scores the whole leaderboard with one uniform reference judge (Grok-4.3) and why dual-judge submissions with ICC(A,1) and Spearman correlation are strongly preferred. Judge disagreement is published as data, not hidden.

The honest residual: even a uniform strong judge carries ~11 points of judge-induced variance (see [Limitations](#limitations)). LLM-as-judge remains the only scalable way to grade free-form BI prose today; GBAG's stance is to treat the judge as part of the measured system, with its error bars published.

## Quick start

```bash
git clone https://github.com/softisight/gbag-bench
cd gbag-bench
pip install -r requirements.txt

# 1. Run a model on the 35 questions (gold-SQL mode — interpretation only)
python examples/baseline_runner.py \
    --dataset data/questions.jsonl \
    --db-dir databases/ \
    --output runs/<your-model>.jsonl \
    --provider <anthropic|openai|ollama|nvidia|openrouter> \
    --model <model-id>

# 2. Score the answers with the v0.2 reference judge (Grok-4.3 via OpenRouter)
export OPENROUTER_API_KEY=sk-or-...
python judge/run_judge.py \
    --dataset data/questions.jsonl \
    --answers runs/<your-model>.jsonl \
    --output runs/<your-model>.scored-grok43.jsonl \
    --judge openrouter --model x-ai/grok-4.3

# 3. Refresh the leaderboard table
python scripts/update_leaderboard.py
```

Reproducing the v0.2 numbers for one model costs roughly **$0.40** in OpenRouter judge fees. The full dataset, databases, prompts, and judge rubric are in this repo — no external resources required. **Dual-judge submissions (Grok-4.3 + one second judge from a different vendor) are strongly preferred.**

## Contributing

We welcome submissions of new model results. See [CONTRIBUTING.md](CONTRIBUTING.md) for the full PR flow.

In short: fork → run baseline + judge → open a PR with your `runs/*.jsonl` files. The leaderboard regenerates automatically from the scored files.

Dataset improvements, metric discussions, and judge protocol experiments are also welcome — open an Issue first to align on direction.

## Repository layout

| Path | Purpose |
|---|---|
| `data/questions.jsonl` | 35 annotated questions (question + gold SQL + gold answer + expected insights) |
| `databases/` | Sakila, Chinook, Northwind as SQLite (public samples, ~30 MB) |
| `examples/baseline_runner.py` | Neutral reference runner — gold-SQL mode |
| `judge/prompt.md` | The full judge rubric (read this first if you want to challenge the scoring) |
| `judge/run_judge.py` | Judge runner (Anthropic / OpenAI / DeepSeek / NVIDIA / OpenRouter) |
| `scripts/update_leaderboard.py` | Regenerates the LEADERBOARD table from runs |
| `scripts/export_to_deskinsight_suites.py` | Optional — converts `data/questions.jsonl` into the DeskInsight Runner suite format (3 files, one per database) for users who want to evaluate the DeskInsight commercial pipeline on GBAG |
| `scripts/import_from_deskinsight_results.py` | Optional — converts DeskInsight Runner `benchmark_raw.json` outputs back into GBAG `runs/*.jsonl` format ready for `judge/run_judge.py` |
| `runs/` | All published model answers and judge scores |
| `METRIC.md` | Formula, rubric, judging protocol |
| `SCHEMA.md` | Dataset schema |
| `LEADERBOARD.md` | Full leaderboard + analyses |
| `CONTRIBUTING.md` | How to submit a new model result |

## Limitations

GBAG-Bench v0.2 has known limitations we document openly:

- **Small dataset** — 35 questions. Statistically informative for spot-checks; not enough for definitive claims. v0.3 will expand.
- **3 public databases** — Sakila / Chinook / Northwind are well-known public samples that may appear in some models' training data. v0.3 addresses this with a first-party synthetic held-out database (`ledger`); see the [held-out suite](#held-out-suite-v03) section.
- **LLM-as-judge limitations** — see Finding #3. Even with a uniform strong judge, ~11 points of judge-induced variance remain. The dual-judge protocol with ICC(A,1) and Spearman correlation is the recommended path.
- **Single-language** — questions and gold answers are in English. Multilingual extension planned.
- **Faithfulness over Insight** — the 50/30/20 metric weighting reflects our judgment that hallucinated numbers are worse than missing insights. Alternative weightings are documented in [METRIC.md](METRIC.md).

## Negative results — a pipeline change we measured and reverted

We publish the changes that did **not** work, with their run artifacts, because a benchmark is only useful if it can also tell you that your idea was wrong.

**The change.** DeskInsight injects deterministic pre-computed aggregates (PACI) into the interpretation prompt. On `GROUP BY` queries, PACI also emits *meta-aggregates* over an already-aggregated column (a sum of sums, an average of averages). These are mathematically well-defined but off-topic for a "per group" question, and models were reciting them. We tried suppressing them (`groupbypaci`, then `groupbypaci_v2` which also drops the top-K distribution block).

**What the averages said** — Gold-SQL runs, 35 questions, judged by Grok-4.3:

| Run | GBAG | Faithfulness |
|---|---|---|
| `gemma4-31b-it_deskinsight_goldsql` (baseline) | 83.2 | 90.6 |
| `..._groupbypaci` | 84.6 | 92.6 |
| `..._groupbypaci_v2` | **85.6** | **93.7** |
| `qwen35-9b_deskinsight_goldsql` (baseline) | 74.4 | 72.9 |
| `qwen35-9b_deskinsight_goldsql_postfix` | **75.7** | **80.3** |

*Baseline note.* The 9B baseline here is `qwen35-9b_deskinsight_goldsql` (74.4), **not** the `qwen3.5:9b + DeskInsight pipeline` row on the [leaderboard](LEADERBOARD.md) (76.8, run `qwen35-9b_deskinsight_final`). Our three full 35-question 9B pipeline runs sit at 74.0, 74.4 and 76.8. Every delta below compares a run against the baseline it was derived from, never across runs.

*File-naming note.* The 9B variant file is named `qwen35-9b_deskinsight_goldsql_postfix`; its embedded model tag is `qwen3.5:9b+deskinsight+goldsql+groupbypaci` — the same meta-aggregate suppression change as the gemma `_groupbypaci` run, only the filename differs. The separate `gemma4-31b-it_deskinsight_goldsql_postfix` run (tag `...+postfix`) is unrelated to this ablation and not part of the table above.

Both models improved on average. On that evidence alone, the change ships.

**What the per-question data said.** On the 9B, the +1.3 average is the net of **14 questions gaining a cumulative +417 and 13 questions losing a cumulative −373**. Three of those regressions are near-total collapses:

| Question | Type | Before → After |
|---|---|---|
| `sakila-l6-02` | avg rentals per customer, per store | 86 → **11** |
| `chinook-l6-02` | avg invoice total per employee | 86 → **11** |
| `northwind-l6-02` | avg freight per order, per shipper | 92 → **17** |

All three are *average-per-group* questions — exactly the shape the change was meant to help. The 31B absorbed the same change (12 gains / 6 regressions, worst `sakila-l10-02` 92 → 62); the 9B did not.

**Interpretation.** The suppressed aggregates serve two roles at once: a *recitation source* the model copies from (what we wanted to remove) and a *magnitude anchor* the model calibrates against (what we did not). They are the same bytes in the prompt, so no surgical fix separates them. Larger models compose without the anchor; smaller ones fabricate plausibly-shaped numbers instead.

**What we did.** Reverted, and kept the legacy PACI as the production default. A +1.3 average that conceals three near-total failures on a whole question class is not a safe basis for shipping — the mean was hiding the regression, not summarizing it. Note also that +1.3 is smaller than the spread between our own full 9B pipeline runs (74.0 / 74.4 / 76.8), so the gain never clearly cleared run-to-run variation to begin with.

**Reproduce it.** All runs above are in [`runs/`](runs/) with their `.scored-grok43.jsonl` judgments; per-question deltas are recomputable from those files alone. Two partial `qwen35-9b_deskinsight_patched*` runs (3 questions each) are exploratory probes, not a full ablation — do not read averages from them.

**The transferable lesson:** validate any anti-fabrication change on at least two model sizes, and read the per-question distribution, not the mean. A change validated on one model class is not yet validated.

## Citation

If you use GBAG-Bench in your work, please cite:

```bibtex
@misc{gbag-bench-2026,
  title  = {GBAG-Bench: Grounded BI Answer Generation},
  author = {Zerga, Fouad and Zakarya, R.},
  year   = {2026},
  url    = {https://github.com/softisight/gbag-bench}
}
```

## AI assistance disclosure

Portions of the harness code, documentation, and tooling in this repository were drafted with the assistance of an AI coding assistant (Claude, by Anthropic). All experimental design, benchmark question authoring, gold-SQL curation, result validation, and scientific conclusions are the work of the human authors, who take full responsibility for the contents of this repository and any associated publication. The AI was used as a productivity tool, not as a contributor or author — consistent with the authorship policies of major venues (Nature, Science, ACL, NeurIPS), which hold that an AI system cannot assume accountability for research.

## License

MIT — see [LICENSE](LICENSE). The bundled sample databases retain their original licenses; see [`databases/NOTICE.md`](databases/NOTICE.md).
