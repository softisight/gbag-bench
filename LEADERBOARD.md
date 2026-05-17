# GBAG Leaderboard

> First public results for the **Grounded BI Answer Generation** benchmark.

Submissions ranked by **GBAG Score** (`0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight`, 0–100).

All runs use **gold-SQL mode**: the reference SQL is executed and only the natural-language interpretation is evaluated. This isolates GBAG from the NL2SQL axis (Spider/BIRD's domain).

## v0.1 results — 35 questions, 3 databases (Sakila / Chinook / Northwind), L1-L10

| Model | Hardware | Judge | Coverage | GBAG | Faithfulness | Completeness | Insight |
|---|---|---|---|---|---|---|---|
| `qwen3.5:9b` | RTX 3060 (local Ollama) | DeepSeek V3 | 32 / 35 (91%) | **72.7** | 75.6 | 73.9 | 63.8 |

*Coverage shows scored questions / dataset size. Three timeouts on the longest queries (large result sets that exceeded the 10-min runner timeout).*

## Observations from v0.1

**1. The metric discriminates.** GBAG scores span 11–100 across the 32 answered questions. No saturation, no flat scoring.

**2. PSAD pattern empirically confirmed.** Faithfulness collapses (F=10) on questions requiring synthesis of derived facts beyond the SQL result:
- **L8-01** *(calendar with gaps)* — model fabricates missing dates
- **L10-02** *(running cumulative total)* — model cannot perform running sums on the row stream
- **L9-01** *(store × category combinations)* — model invents cross-group aggregates

**3. Synthesis beats arithmetic.** L9-02 and L9-03 (multi-row synthesis without numeric reasoning) score 100. Pattern matches the "synthesis vs arithmetic" gap reported in prior work.

**4. Insight axis adds signal.** Models that recite correct numbers without commentary cap at I=30. Models that surface a trend ("revenue peaked in July, then declined") reach I=100.

## How to submit

1. Run `examples/baseline_runner.py` against your model on `data/questions.jsonl`
2. Score with `judge/run_judge.py` using a frontier-class judge (Claude / GPT / DeepSeek V3 class)
3. Open a PR adding your row above with a link to your `runs/*.jsonl` and `runs/*.scored.jsonl`

For inter-judge comparability, dual-judge runs (e.g. Anthropic + DeepSeek) are encouraged.
