# GBAG Leaderboard

> First public results for the **Grounded BI Answer Generation** benchmark.

Submissions ranked by **GBAG Score** (`0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight`, 0–100).

All runs use **gold-SQL mode**: the reference SQL is executed and only the natural-language interpretation is evaluated. This isolates GBAG from the NL2SQL axis (Spider/BIRD's domain).

## v0.1 results — 35 questions, 3 databases (Sakila / Chinook / Northwind), L1-L10

> The table below is **auto-generated** by `scripts/update_leaderboard.py`. Do not edit by hand.

<!-- LEADERBOARD-AUTO-START -->
| Model | Provider | Judge | Coverage | **GBAG** | F | C | I |
|---|---|---|---|---|---|---|---|
| `nvidia/llama-3.3-nemotron-super-49b-v1` | nvidia | qwen3.6 | 35 / 35 | **77.9** | 80.0 | 72.1 | 81.1 |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | nvidia | gemini-2.5 | 34 / 35 | **76.4** | 77.4 | 69.4 | 84.4 |
| `qwen/qwen3-coder-480b-a35b-instruct` | nvidia | deepseek-chat | 35 / 35 | **73.5** | 79.7 | 63.7 | 72.6 |
| `qwen3.5:9b` | ollama | deepseek-chat | 32 / 35 | **72.7** | 75.6 | 73.9 | 63.8 |
| `qwen/qwen3-next-80b-a3b-instruct` | nvidia | deepseek-v3.2 | 5 / 35 | **71.6** | 79.8 | 79.8 | 37.8 |
| `qwen/qwen3-coder-480b-a35b-instruct` | nvidia | deepseek-v3.2 | 35 / 35 | **69.6** | 72.3 | 67.2 | 66.6 |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | nvidia | deepseek-v3.2 | 35 / 35 | **66.6** | 64.8 | 68.3 | 68.5 |
| `qwen/qwen3-next-80b-a3b-thinking` | nvidia | deepseek-v3.2 | 35 / 35 | **56.2** | 63.4 | 52.6 | 43.7 |
<!-- LEADERBOARD-AUTO-END -->

*Coverage = questions answered without timeout / dataset size. Judge column reports the LLM that scored the run; identical models judged by different judges produce different GBAG scores — see "Inter-judge variance" below.*

## Inter-judge variance — `nvidia/llama-3.3-nemotron-super-49b-v1` scored by 3 judges

| Judge | GBAG | F | C | I |
|---|---|---|---|---|
| qwen3.6 | 77.9 | 80.0 | 72.1 | 81.1 |
| gemini-2.5 | 76.4 | 77.4 | 69.4 | 84.4 |
| deepseek-v3.2 | 66.6 | 64.8 | 68.3 | 68.5 |
| **Spread** | **11.3 pts** | **15.2** | **3.8** | **15.9** |

A single model can score 67 to 78 depending on the LLM used as judge. **This is why the GBAG protocol recommends dual-judge runs (two judges from different vendors) and reporting inter-rater agreement (Cohen's kappa).** Faithfulness and Insight axes show the largest sensitivity; Completeness is more stable.

## Observations from v0.1

**1. The metric discriminates.** GBAG scores span 11–100 across answered questions. No saturation, no flat scoring.

**2. Bigger is not better.** A 9B local model (`qwen3.5:9b`, 6.6 GB on consumer GPU) scores within 1 point of a 480B cloud MoE (`qwen3-coder-480b`) when judged by the same judge. **The interpretation phase does not benefit linearly from scale.** This is a finding with direct commercial implications: local BI assistants can match cloud frontier models on the answer-quality axis.

**3. Thinking modes can hurt.** `qwen3-next-80b-a3b-thinking` scores 56.2 — well below `qwen3-coder-480b` (69.6) under the same judge. Hidden reasoning tokens introduce errors during result interpretation. Consistent with practitioner reports that thinking is best disabled for grounded tasks.

**4. PSAD pattern empirically confirmed.** Across multiple models, Faithfulness collapses (F ≤ 10) on questions requiring:
- Synthesis of derived facts beyond the SQL result rows (calendar gaps, running cumulative totals, cross-group aggregates)

**5. Synthesis beats arithmetic.** Multi-row synthesis questions (`L9-02`, `L9-03`) score 100 across most models, while running-arithmetic questions (`L10-02`) collapse. Matches the "synthesis vs arithmetic" gap reported in prior work.

## Submitting your model

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full PR flow. TL;DR:

1. Run `examples/baseline_runner.py` on your model
2. Score with `judge/run_judge.py` using a frontier judge (Claude / GPT / DeepSeek / Gemini / Qwen 3.6 class)
3. Open a PR adding your row + your `runs/*.jsonl` + `runs/*.scored.jsonl`

**Dual-judge submissions strongly preferred.** Single-judge entries are accepted but flagged.
