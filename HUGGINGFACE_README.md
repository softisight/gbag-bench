---
license: mit
language:
  - en
task_categories:
  - table-question-answering
  - question-answering
  - text2text-generation
  - text-generation
size_categories:
  - n<1K
tags:
  - nl2sql
  - text2sql
  - business-intelligence
  - benchmark
  - llm-evaluation
  - llm-as-a-judge
  - faithfulness
  - grounded-generation
  - hallucination
  - data-analysis
  - sqlite
  - sakila
  - chinook
  - northwind
pretty_name: GBAG-Bench — Grounded BI Answer Generation
configs:
  - config_name: default
    data_files:
      - split: test
        path: data/questions.jsonl
---

# GBAG-Bench — Grounded BI Answer Generation

**A public benchmark for the step after the SQL: how faithfully an LLM interprets a query result into a natural-language answer.**

> NL2SQL measures half the problem. GBAG measures the other half.

- 📂 **GitHub (harness, judge, leaderboard)**: [softisight/gbag-bench](https://github.com/softisight/gbag-bench)
- 📊 **Live leaderboard**: [LEADERBOARD.md](https://github.com/softisight/gbag-bench/blob/main/LEADERBOARD.md)
- 📐 **Metric & rubric**: [METRIC.md](https://github.com/softisight/gbag-bench/blob/main/METRIC.md)
- 🪪 **License**: MIT (questions & harness) — bundled SQLite samples retain their original licenses

---

## Why this benchmark exists

Benchmarks like **Spider**, **BIRD** and **WikiSQL** measure whether a model can generate correct SQL. They stop there. But in a real BI product, what the user reads is the **natural-language answer** the model writes *after* the SQL runs — and that step is where most failures actually happen.

A correct SQL query followed by a hallucinated number, an inverted trend, or a missing key insight is **still a failed product experience**. GBAG isolates and measures that neglected second half.

## What the model is given, and what it must produce

Inputs:
- a natural-language **question**
- the executed **SQL** (gold reference, so the SQL axis is held constant)
- the full **result set** (rows + columns)

Output:
- a **faithful**, **complete**, **insightful** natural-language answer

Scoring is performed by an LLM judge against a hand-crafted gold answer and a list of expected atomic insights:

```
GBAG Score = 0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight
```

Faithfulness dominates because in BI a hallucinated number causes a wrong real-world decision.

## Dataset contents

| File | What it is |
|---|---|
| `data/questions.jsonl` | 35 annotated questions across 3 databases, difficulty L1→L10 |
| `databases/sakila.sqlite` | DVD rental sample (~5 MB) |
| `databases/chinook.sqlite` | Music store sample (~1 MB) |
| `databases/northwind.sqlite` | Wholesale sample (~25 MB) |

### Schema (one JSON object per line)

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable unique ID, e.g. `sakila-l3-02` |
| `database` | string | `sakila` / `chinook` / `northwind` |
| `question` | string | The natural-language question (English) |
| `gold_sql` | string | A reference SQL that correctly answers the question |
| `gold_answer` | string | A reference natural-language answer (faithful, complete, insightful) |
| `difficulty` | int | 1 (trivial) to 10 (multi-step reasoning) |
| `category` | string | One of: `aggregation`, `trend`, `comparison`, `ranking`, `filter`, `join`, `derived` |
| `expected_insights` | list[string] | Atomic facts the answer MUST contain. Used by the judge for Completeness. |

### Example record

```json
{
  "id": "sakila-001",
  "database": "sakila",
  "question": "What are the top 3 film categories by total rental revenue?",
  "gold_sql": "SELECT c.name, SUM(p.amount) AS revenue FROM payment p JOIN rental r ON p.rental_id = r.rental_id JOIN inventory i ON r.inventory_id = i.inventory_id JOIN film_category fc ON i.film_id = fc.film_id JOIN category c ON fc.category_id = c.category_id GROUP BY c.name ORDER BY revenue DESC LIMIT 3;",
  "gold_answer": "The top 3 categories by rental revenue are Sports ($5,314), Sci-Fi ($4,756) and Animation ($4,656). Sports leads by ~12 % over Sci-Fi.",
  "difficulty": 3,
  "category": "ranking",
  "expected_insights": [
    "Sports is the top category",
    "Sports revenue is approximately $5,314",
    "Top 3 are Sports, Sci-Fi, Animation"
  ]
}
```

## Loading the dataset

```python
from datasets import load_dataset

ds = load_dataset("softisight-ai/gbag-bench", split="test")
print(ds[0]["question"])
# > "How many actors are registered in the database?"
```

To execute a question's `gold_sql`, download the corresponding SQLite file from the `databases/` folder of this dataset (or from the [GitHub repo](https://github.com/softisight/gbag-bench/tree/main/databases)) and run it locally — no external service required.

## Can the judge be trusted?

Every score below comes from an LLM judge, so this question decides whether any of them
mean anything. It is answered with measurement, not argument.

Seven cases were built whose correct verdict is settled by a **SQL query** rather than by
an opinion. Six are answers that must be marked unfaithful; one is correct and must be
acquitted, otherwise a judge that condemns everything would score well. Each ships the
query that proves it, and all seven run as written.

They probe one failure. A model shown the first 200 rows of a larger result writes a
sentence that is true about those rows and false about the data — *every*, *the highest*,
*the majority*, *ends at*. The figures are right; the reach of the sentence is not. A judge
that checks figures against the visible rows approves all of them.

| judge | where | score | runs where it contradicted itself |
|---|---|---|---|
| **gemma4-31b** | local, 31B | **7/7** | 0 of 7 |
| **qwen3.6** | local, 36B | **6/7** | 0 of 7 |
| grok-4.3 | hosted | 5.5/7 | **3 of 7** |
| phi4 | local, 15B | 5/7 | 0 of 7 |
| deepseek-v4-pro | hosted | 5/7 | **5 of 7** |
| gemma4-12b | local, 12B | 4/7 | 0 of 7 |
| gemini-2.5-pro | hosted | 3.3/6 | **2 of 6** |

Same prompt, three runs each. Four local judges produced **zero self-contradictions across
28 case-runs**; three hosted judges produced **ten across twenty**. Not a quality gap — a
hosted seed cannot be pinned, so a hosted judge cannot be asked the same question twice.

Under the earlier prompt every judge scored 2 to 4 out of 7, flagships included. What
repaired them was not a larger judge but a procedure: list every quantitative claim, state
its scope, name the fact relied on, and only then score. That is ~150 words longer and took
the best judge from **2/7 to 7/7**.

Two things this does **not** settle, stated in full on the method page: these seven cases
are the ones the rule was written against, so 7/7 shows conformity rather than
generalisation; and batch position flips boundary verdicts, which puts the resolution of
the instrument at about **2 points** — two models closer than that are tied, and the
decimals should not be read.

Full method, the seven cases with their proof queries, and the judge prompts:
**[JUDGE_VALIDATION.md](https://github.com/softisight/gbag-bench/blob/main/JUDGE_VALIDATION.md)**.

## v0.2 leaderboard — uniform Grok-4.3 judge

All models re-judged with the same judge to enable apples-to-apples comparison.

| Model | Provider | Config | Coverage | **GBAG** | F | C | I |
|---|---|---|---|---|---|---|---|
| `google/gemma-4-31b-it` | openrouter | **+ DeskInsight pipeline** | 35/35 | **83.2** | 90.6 | 93.7 | 49.1 |
| `qwen3.5:9b` | ollama (RTX 3060) | **+ DeskInsight pipeline** | 35/35 | **76.8** | 77.1 | 89.8 | 56.3 |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | nvidia NIM | neutral prompt | 35/35 | **67.7** | 61.4 | 70.5 | 79.4 |
| `qwen/qwen3-coder-480b-a35b-instruct` | nvidia NIM | neutral prompt | 35/35 | **64.6** | 64.9 | 56.9 | 75.7 |
| `qwen/qwen3-next-80b-a3b-thinking` | nvidia NIM | neutral prompt | 35/35 | **61.4** | 68.0 | 53.7 | 56.6 |
| `qwen3.5:9b` | ollama (RTX 3060) | neutral prompt | 32/35 | **59.6** | 60.3 | 55.7 | 63.8 |
| `qwen/qwen3-next-80b-a3b-instruct` | nvidia NIM | neutral prompt | 28/35 | **58.9** | 61.1 | 57.4 | 55.7 |

F = Faithfulness · C = Completeness · I = Insight. Full table, v0.1 archive and inter-judge variance analysis: [LEADERBOARD.md on GitHub](https://github.com/softisight/gbag-bench/blob/main/LEADERBOARD.md).

## Five findings worth reading

**1. Context engineering > model scale.** The same `qwen3.5:9b` on a consumer RTX 3060 scores **59.6** with a neutral Spider/BIRD-style prompt, but **76.8** wrapped in a context engineering layer (data dictionary, domain detection, Pre-Aggregated Context Injection, profile adaptation). **The size of the effect is judge-dependent, so read it as a range.** On the **32 questions both runs answered**: **+17.2** under Grok-4.3 (paired sign test p = 0.009, 95% CI [+6.2, +28.3]) but **+7.1** under a second judge, Gemini-2.5-Pro (p = 0.093, 95% CI [-2.7, +16.9]). What survives both judges: the direction (20-6 and 16-7 in wins) and the **completeness gain** (+33.1 and +30.7). What does not: the faithfulness gain (+17.5 vs +1.2) and conventional significance. Insight drops under both (-7.2 and -13.8). Context engineering is still the dominant lever, worth +7 to +17 points on identical weights, but the honest claim is a range, not a point estimate.

**2. Bigger is not (much) better.** Under a uniform strong judge, `qwen3.5:9b` (59.6) sits about 3 points below `qwen3-coder-480b-a35b` (62.8 on the common questions), i.e. **single digits**. Mind the MoE caveat: that model activates roughly 35B parameters per token, not 480B, so this is a dense 9B within single digits of a **35B-active** model, about 4× its active size. A 3-point gap is inside the 11-point inter-judge variance, so read it as a tie.

**3. Judge selection matters as much as model selection.** Re-judging the same `qwen3.5:9b` answers with Grok-4.3 instead of deepseek-chat dropped the score from **72.7** to **59.6** — a 13-point gap on byte-identical answers. **Single-judge benchmarks are unreliable.** GBAG ships a dual-judge protocol with ICC(A,1) and Spearman correlation. A later result sharpens this: a judge does not only disagree with other judges, it disagrees with **itself**. Asked to grade one answer four times, with the answer key in front of it and temperature 0, Grok-4.3 returned **40, 40, 100, 10**. A single run of any judge is a sample, not a measurement — see [JUDGE_VALIDATION.md](https://github.com/softisight/gbag-bench/blob/main/JUDGE_VALIDATION.md).

**4. Thinking mode: no measurable effect (non-result).** The clean ablation is `qwen3-next-80b-a3b-thinking` against its non-thinking sibling `qwen3-next-80b-a3b-instruct`: same family, same size, same judge. On the **28 questions both answered**, thinking scores **60.6** against **58.9**, a +1.7 gap in thinking's favour, far inside the 11-point inter-judge variance. **No conclusion either way.** An earlier version claimed thinking "can hurt grounded tasks" by comparing against *different* models; that comparison was confounded and the claim is **withdrawn**.

**5. Failures are concentrated, not universal.** Small local models occasionally fabricate aggregates from row samples on top-N queries with large underlying tables (a pattern we call the **Post-SQL Aggregation Deficit**). Pre-Aggregated Context Injection mitigates most cases.

## Reproducing a leaderboard entry

The harness, judge, and submission flow live on GitHub:

```bash
git clone https://github.com/softisight/gbag-bench
cd gbag-bench
pip install -r requirements.txt

# 1. Run a model on the 35 questions (gold-SQL mode)
python examples/baseline_runner.py \
    --dataset data/questions.jsonl \
    --db-dir databases/ \
    --output runs/<your-model>.jsonl \
    --provider <anthropic|openai|ollama|nvidia|openrouter> \
    --model <model-id>

# 2a. Score with the v0.2 reference judge, for comparability with the table above
export OPENROUTER_API_KEY=sk-or-...
python judge/run_judge.py \
    --dataset data/questions.jsonl \
    --answers runs/<your-model>.jsonl \
    --output runs/<your-model>.scored-grok43.jsonl \
    --judge openrouter --model x-ai/grok-4.3 \
    --prompt judge/prompt-v041.md

# 2b. And score it again with a local judge, which is free and reproducible
OLLAMA_HOST=http://your-box:11434 python judge/run_judge.py \
    --dataset data/questions.jsonl \
    --answers runs/<your-model>.jsonl \
    --output runs/<your-model>.scored-gemma31.jsonl \
    --judge ollama --model gemma4:31b \
    --prompt judge/prompt-v041.md
```

Reproducing one model costs roughly **$0.40** in judge fees for step 2a, and nothing for
2b. Three points, from the judge validation above:

- **Use `judge/prompt-v041.md`.** Under the older `judge/prompt.md` every judge tested
  scored 2 to 4 out of 7 on cases a SQL query settles.
- **Run each judge at least three times and report all runs.** A single run samples a
  judge; it does not measure one. Grok-4.3 graded one answer 40, 40, 100, 10.
- **A local judge is free, and it is the only kind that can repeat itself** — its seed can
  be pinned. Pin the batch and its order too.

**Dual-judge submissions remain strongly preferred**, one hosted and one local rather than
two hosted, so that at least one side of the comparison is reproducible.

## Limitations

We document them openly:

- **Small dataset** — 35 questions. Statistically informative for spot-checks, not enough for definitive claims. v0.3 will expand.
- **3 databases only** — Sakila / Chinook / Northwind are well-known public samples that may appear in some models' training data. Held-out databases are under evaluation for v0.3.
- **LLM-as-judge variance** — see Finding #3. Even with a uniform strong judge, ~11 points of judge-induced variance remain *between* judges, and a hosted judge is not reproducible against itself either: its seed cannot be pinned. The dual-judge protocol with ICC(A,1) and Spearman correlation is the recommended path, now with several runs per judge. Method, cases and measurements: [JUDGE_VALIDATION.md](https://github.com/softisight/gbag-bench/blob/main/JUDGE_VALIDATION.md).
- **English only** — multilingual extension planned.
- **Faithfulness over Insight** — the 50/30/20 weighting reflects our judgment that hallucinated numbers are worse than missing insights. Alternative weightings are documented in [METRIC.md](https://github.com/softisight/gbag-bench/blob/main/METRIC.md).

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

Portions of the harness code, documentation, and tooling were drafted with the assistance of an AI coding assistant (Claude, by Anthropic). All experimental design, benchmark question authoring, gold-SQL curation, result validation, and scientific conclusions are the work of the human authors, who take full responsibility — consistent with the authorship policies of Nature, Science, ACL, NeurIPS.

## License

**MIT** — see [LICENSE on GitHub](https://github.com/softisight/gbag-bench/blob/main/LICENSE). Bundled sample databases retain their original licenses; see [`databases/NOTICE.md`](https://github.com/softisight/gbag-bench/blob/main/databases/NOTICE.md).
