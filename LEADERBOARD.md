# GBAG Leaderboard

> First public results for the **Grounded BI Answer Generation** benchmark.

Submissions ranked by **GBAG Score** (`0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight`, 0–100).

All runs use **gold-SQL mode**: the reference SQL is executed and only the natural-language interpretation is evaluated. This isolates GBAG from the NL2SQL axis (Spider/BIRD's domain).

## v0.1 results

| Model | Provider | Judge | Coverage | GBAG | Faithfulness | Completeness | Insight |
|---|---|---|---|---|---|---|---|
| `qwen3.5:9b` | Ollama (local, RTX 2050) | DeepSeek V3 | 4 / 35 (Sakila L1-L5) | **91.0** | 100 | 100 | 55 |

*Coverage shows scored questions / dataset size. Partial coverage = work-in-progress run.*

## How to submit

1. Run `examples/baseline_runner.py` against your model on `data/questions.jsonl`
2. Score with `judge/run_judge.py` using a frontier-class judge (Claude / GPT / DeepSeek V3 class)
3. Open a PR adding your row to this table with a link to your `runs/*.jsonl` and `runs/*.scored.jsonl`

For inter-judge comparability, dual-judge runs (Anthropic + OpenAI, or DeepSeek + Anthropic) are encouraged.

## Notes

- Models with `Insight ≈ 30` produce factually correct but bare answers — the metric is doing its job.
- The `Insight` axis rewards business observation beyond recitation. A correct number alone caps at 30.
