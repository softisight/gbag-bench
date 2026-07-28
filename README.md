# GBAG-Bench

**Grounded BI Answer Generation** — the first public benchmark for measuring how faithfully an LLM interprets a SQL result into a natural-language answer.

> NL2SQL measures half the problem. GBAG measures the other half.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Status: v0.2](https://img.shields.io/badge/status-v0.2-blue)
![Questions: 35](https://img.shields.io/badge/questions-35-green)
![Databases: 3](https://img.shields.io/badge/databases-3-green)

---

## Why GBAG

Existing benchmarks (Spider, BIRD, WikiSQL) measure whether a model generates correct SQL. They stop there. But in a real BI product, what the user reads is the **natural-language answer** the model writes after the SQL is executed — and that step is where most failures actually happen.

A correct SQL query followed by a hallucinated number, an inverted trend, or a missing key insight is **still a failed product experience**. GBAG isolates and measures that neglected second half.

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

## v0.2 leaderboard — uniform Grok-4.3 judge

> All models re-judged with the same judge to enable apples-to-apples comparison. See [LEADERBOARD.md](LEADERBOARD.md) for the full table, the archived v0.1 mixed-judge results, and inter-judge variance analysis.

| Model | Provider | Config | Coverage | **GBAG** |
|---|---|---|---|---|
| `qwen3.5:9b` | Ollama (local, RTX 3060) | **+ DeskInsight pipeline** | 35/35 | **76.8** |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | NVIDIA NIM | neutral prompt | 35/35 | **67.7** |
| `qwen/qwen3-coder-480b-a35b-instruct` | NVIDIA NIM | neutral prompt | 35/35 | **64.6** |
| `qwen/qwen3-next-80b-a3b-thinking` | NVIDIA NIM | neutral prompt | 35/35 | **61.4** |
| `qwen3.5:9b` | Ollama (local, RTX 3060) | neutral prompt | 32/35 | **59.6** |
| `qwen/qwen3-next-80b-a3b-instruct` | NVIDIA NIM | neutral prompt | 28/35 | **58.9** |

## Five findings

**1. Context engineering > model scale.** The same `qwen3.5:9b` on a consumer RTX 3060 scores **59.6** with a neutral Spider/BIRD-style prompt, but **76.8** wrapped in DeskInsight's context engineering pipeline (data dictionary, domain detection, Pre-Aggregated Context Injection, profile adaptation). Both rows use identical model weights, hardware, questions, gold SQL, and judge; only the prompt scaffolding differs. Restricted to the **32 questions both runs answered**, the paired gap is **+17.2** (76.9 vs 59.6), with a **paired sign test at p = 0.009** (20 wins, 6 ties, 6 losses) and a 95% CI of **[+6.2, +28.3]**. Because the comparison is paired and scored by the same judge, judge leniency cancels in the difference, so the 11-point inter-judge variance does not apply here. The gain concentrates in completeness (+33.1) and faithfulness (+17.5); insight actually drops (-7.2), and the pipeline loses on 6 of 32 questions. **The dominant lever for grounded BI quality is what you feed the model, not how big the model is.** See [Methodology — how the DeskInsight pipeline line was obtained](LEADERBOARD.md#methodology--how-the-deskinsight-pipeline-line-was-obtained) for the full reproduction recipe.

**2. Bigger is not (much) better.** Under a uniform strong judge (Grok-4.3), `qwen3.5:9b` (59.6) sits about 3 points below `qwen3-coder-480b-a35b` (62.8 on the 32 common questions). The earlier v0.1 leaderboard suggested near-parity but was inflated by a lenient judge. The gap reopens, but only to **single digits**. Mind the MoE caveat: `qwen3-coder-480b-a35b` activates roughly 35B parameters per token, not 480B, so the honest framing is a dense 9B sitting within single digits of a **35B-active** model, about 4× its active size. A 3-point gap is also well inside the 11-point inter-judge variance, so read it as a tie, not a ranking.

**3. Judge selection matters as much as model selection.** Re-judging the same `qwen3.5:9b` answers with Grok-4.3 dropped the score from **72.7** (deepseek-chat) to **59.6** — 13-point gap on identical model answers. 37.5 % of questions show ≥ 15-point disagreement between the two judges, always in the same direction (deepseek-chat is the more lenient). **Single-judge benchmarks are unreliable.** GBAG ships a dual-judge protocol with Cohen's kappa.

**4. Thinking mode: no measurable effect (non-result).** The only clean ablation available is `qwen3-next-80b-a3b-thinking` against its non-thinking sibling `qwen3-next-80b-a3b-instruct`: same family, same size, same judge. Restricted to the **28 questions both models answered**, thinking scores **60.6** against **58.9**, a **+1.7** gap in thinking's favour. Faithfulness alone is **+5.4**, also in thinking's favour. Both sit far inside the 11-point inter-judge variance, so **no conclusion can be drawn either way**. An earlier version of this section claimed thinking "can hurt grounded tasks", based on comparisons against *different* models (`qwen3-coder-480b`, `qwen3.5:9b` neutral). Those comparisons are confounded and the claim is **withdrawn**. Settling this needs a matched-coverage re-run of the instruct variant (currently 28/35) plus repeated runs to clear the noise floor.

**5. Specific failure modes are concentrated, not universal.** Local models occasionally fabricate aggregates from row samples on top-N queries with large underlying tables (a pattern we call the Post-SQL Aggregation Deficit). Pre-Aggregated Context Injection mitigates most cases. The failures are concentrated on a narrow question type, not spread across the benchmark.

## Why can an LLM judge another LLM?

The benchmark's scoring rests on LLM-as-judge, so the question deserves a direct answer.

1. **Verifying is easier than producing.** The judge never answers the BI question itself. It checks the candidate answer against material it is handed: the executed SQL, a human-written gold answer, and a checklist of expected insights. Reading-and-matching is a strictly easier task than the open-ended generation being graded.
2. **The judge grades with an answer key, not from its own knowledge.** Every question ships a `gold_answer` and atomic `expected_insights`, both human-curated. Completeness is near-mechanical (insights matched / insights expected). The judge acts as a grader with a rubric, not as an oracle.
3. **The rubric leaves little room for taste.** Anchored score bands per axis, a ±2% numeric tolerance, temperature 0, strict JSON output, and explicit rules against rewarding style or verbosity. The full prompt is published in [judge/prompt.md](judge/prompt.md); challenge it there if you disagree with a band.
4. **Judge error is measured, not assumed away.** Finding #3 above quantifies it: re-judging identical answers moved the score by 13 points between two judges. That is exactly why v0.2 scores the whole leaderboard with one uniform reference judge (Grok-4.3) and why dual-judge submissions with Cohen's kappa are strongly preferred. Judge disagreement is published as data, not hidden.

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
- **3 databases only** — Sakila / Chinook / Northwind are well-known public samples that may appear in some models' training data. We are evaluating whether to introduce held-out databases in v0.3.
- **LLM-as-judge limitations** — see Finding #3. Even with a uniform strong judge, ~11 points of judge-induced variance remain. The dual-judge protocol with Cohen's kappa is the recommended path.
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
