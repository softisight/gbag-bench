# GBAG Leaderboard

> First public results for the **Grounded BI Answer Generation** benchmark.

Submissions ranked by **GBAG Score** (`0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight`, 0–100).

All runs use **gold-SQL mode**: the reference SQL is executed and only the natural-language interpretation is evaluated. This isolates GBAG from the NL2SQL axis (Spider/BIRD's domain).

---

## v0.2 results — uniform judge (Grok-4.3)

> **All models re-judged with the same judge (Grok-4.3 via OpenRouter) to enable apples-to-apples comparison.** Previous v0.1 table (mixed judges) preserved below for transparency.

35 questions, 3 databases (Sakila / Chinook / Northwind), L1-L10.

<!-- LEADERBOARD-V02-START -->
| Model | Provider | Config | Judge | Coverage | **GBAG** | F | C | I |
|---|---|---|---|---|---|---|---|---|
| `google/gemma-4-31b-it` | openrouter | **+ DeskInsight pipeline** | grok-4.3 | 35 / 35 | **83.2** | 90.6 | 93.7 | 49.1 |
| `qwen3.5:9b` | ollama (RTX 3060) | **+ DeskInsight pipeline** | grok-4.3 | 35 / 35 | **76.8** | 77.1 | 89.8 | 56.3 |
| `nvidia/llama-3.3-nemotron-super-49b-v1` | nvidia | neutral prompt | grok-4.3 | 35 / 35 | **67.7** | 61.4 | 70.5 | 79.4 |
| `qwen/qwen3-coder-480b-a35b-instruct` | nvidia | neutral prompt | grok-4.3 | 35 / 35 | **64.6** | 64.9 | 56.9 | 75.7 |
| `qwen/qwen3-next-80b-a3b-thinking` | nvidia | neutral prompt | grok-4.3 | 35 / 35 | **61.4** | 68.0 | 53.7 | 56.6 |
| `qwen3.5:9b` | ollama (RTX 3060) | neutral prompt | grok-4.3 | 32 / 35 | **59.6** | 60.3 | 55.7 | 63.8 |
| `qwen/qwen3-next-80b-a3b-instruct` | nvidia | neutral prompt | grok-4.3 | 28 / 35 | **58.9** | 61.1 | 57.4 | 55.7 |
<!-- LEADERBOARD-V02-END -->

*`deepseek-v4-flash` excluded — only 3/35 questions answered, sample too small to rank.*

### Methodology — how the "DeskInsight pipeline" line was obtained

The `qwen3.5:9b + DeskInsight pipeline` entry is a **submission that uses the same model and the same 35 questions as the neutral baseline**, but feeds the model through a context engineering layer instead of the bare Spider/BIRD-style prompt used by `examples/baseline_runner.py`. The two rows are designed to **isolate the contribution of context engineering** with everything else held constant.

| Variable | Neutral baseline (59.6) | DeskInsight pipeline (76.8) |
|---|---|---|
| Model | qwen3.5:9b @ Ollama | qwen3.5:9b @ Ollama (identical weights) |
| Hardware | RTX 3060 12 GB | RTX 3060 12 GB |
| Questions | 35 (Sakila / Chinook / Northwind) | Same 35 |
| Gold-SQL mode | Yes — reference SQL injected, Phase 3 only | Yes — same gold SQL |
| Judge | Grok-4.3 via OpenRouter | Same — Grok-4.3 via OpenRouter |
| Prompt scaffolding | Schema list + question + result rows | Schema + question + result rows **+ context layer (see below)** |
| Phase 3 prompt length | ~500 tokens | ~1500-3000 tokens |

The **context layer** added by the DeskInsight pipeline consists of:

1. **Auto-generated bilingual data dictionary** — humanized English captions for table and column names (e.g., `cust_amt → Customer Amount`, `inv_dt → Invoice Date`). Helps the model resolve cryptic schema names.
2. **Auto-detected business domain** — one of 9 verticals (sales, accounting, HR, finance, logistics, CRM, inventory, production, project). Each carries vocabulary, business rules, and characteristic question patterns injected into the prompt.
3. **Pre-Aggregated Context Injection (PACI)** — deterministic aggregates (count, distribution, min/max/avg) computed in code over the full result set and injected as authoritative context BEFORE the row sample. Prevents the model from fabricating totals from a truncated view.
4. **User-profile adaptation** — vocabulary and response style adjusted to the configured user profile (technical / analyst / manager / casual). For these benchmarks the "analyst" profile was used.
5. **Anti-fabrication directives** — explicit reminders that any cited number must come from the result table or DATA SUMMARY; no recall from the model's training data.
6. **Strict-dialect directives** in SQL generation (not exercised here since Gold-SQL mode is on).

### How to reproduce the DeskInsight pipeline row

The DeskInsight commercial product is **not open-source**, so external reproduction of this line requires a DeskInsight licence (free trial available). The reproduction flow:

```
1. Open DeskInsight, connect to one of the bundled SQLite DBs
2. Open Benchmark Runner
3. Charger JSON → scripts/export_to_deskinsight_suites.py output
   (the script converts GBAG questions.jsonl into 3 DeskInsight suites,
    one per database)
4. Configure: model = qwen3.5:9b (Ollama), profile = Production
   (privacy-first, default), Use Gold SQL = ON
5. Run all 3 suites, save the resulting benchmark_raw.json files
6. python scripts/import_from_deskinsight_results.py converts them back
   to GBAG runs/*.jsonl format
7. python judge/run_judge.py --judge openrouter --model x-ai/grok-4.3
   scores them with the same judge as every other row
```

The conversion scripts are open-source (this repo). The model, judge, and questions are identical to those used for the neutral baseline. **The only variable that changes between the two rows is the prompt scaffolding fed to the model.** Any reader can verify by inspecting `runs/qwen35-9b-3060-full.jsonl` (baseline answers) vs `runs/qwen35-9b_deskinsight_final.jsonl` (DeskInsight answers) — the questions and SQL are byte-identical, only `model_answer` differs.

### Headline findings (v0.2)

**1. Context engineering > model scale.** The same `qwen3.5:9b` running on a consumer RTX 3060 scores **59.6** with a neutral Spider/BIRD-style prompt, but **76.8** when wrapped in DeskInsight's context engineering pipeline (data dictionary, domain detection, Pre-Aggregated Context Injection, profile adaptation). **The +17.2 gain places a 9B local model 12 points above the 480B cloud baseline.** Under a second judge (Gemini-2.5-Pro) the same paired gain is +7.1 — direction holds, magnitude is judge-dependent; see the robustness check below. The dominant lever for grounded BI quality is the context fed to the model, not the model's parameter count.

**2. Bigger is not (much) better, with a uniform judge.** Compared with a uniform strong judge (Grok-4.3), the 9B local model (59.6) is **3.2 points below** the 480B cloud MoE (62.8 on 32 common questions). The previous v0.1 result that suggested near-parity was partly inflated by the lenient `deepseek-chat` judge used for the 9B run; under Grok-4.3 the gap reopens — but to single digits, on a model with **~50× fewer parameters**.

**3. Judge selection matters as much as model selection.** Re-judging `qwen3.5:9b` with Grok-4.3 dropped the score from **72.7** (deepseek-chat) to **59.6** — a 13-point gap on the same answers. `deepseek-v3.2` produces evaluation failures (`-1` return code) on ~10 % of questions, biasing scores low. **Single-judge benchmarks are unreliable**: 37.5 % of `qwen3.5:9b` questions show ≥ 15-point disagreement between deepseek-chat and grok-4.3.

**4. Thinking was a non-result (corrected 2026-07-28).** An earlier version of this finding claimed thinking modes hurt grounded tasks, based on comparing different models — a confounded comparison, since withdrawn (see the README findings). The clean same-family ablation (`qwen3-next-80b` thinking vs instruct, restricted to the 28 questions both variants answered) gives 60.6 vs 58.9, inside the judge noise floor: no measurable effect either way.

**5. PSAD (Post-SQL Aggregation Deficit) is real but narrowly scoped.** Local models occasionally fabricate aggregates from a row sample — particularly when the SQL returns ≤ 5 rows but underlying tables are large (top-N queries). The DeskInsight pipeline mitigates most cases via Pre-Aggregated Context Injection; one Sakila case (`sakila-l5-01`) remains a partial regression (cross-DB knowledge contamination). The phenomenon is concentrated, not universal.

**6. Pipeline value generalizes to mid-scale cloud (added 2026-05-26).** Adding `google/gemma-4-31b-it` via OpenRouter through the same DeskInsight pipeline reaches **83.2 GBAG** with Faithfulness **90.6** — the highest F on the v0.2 board. Compared to the neutral-prompt baselines (49B → 67.7, 80B-thinking → 61.4, 480B → 64.6), the +15 to +22 gain confirms that context engineering remains the dominant lever even at flagship scale, not just on the smallest local model. The Insight axis (49.1) lags the larger thinking-class models (75-79), consistent with gemma4's known "data-faithful, narratively terse" behavior — a profile DeskInsight users explicitly want for privacy-first BI (less unsolicited speculation).

---

## Held-out suite (ledger) — v0.3

Seven full 15-question runs on the synthetic `ledger` database, all scored by Grok-4.3 under [judge prompt v0.2](judge/prompt.md). Level 1 = 10 questions whose results fit the 200-row window the harness shows the model; Level 2 = 5 questions whose results exceed it (443 to 3,616 rows). Cloud models served via OpenRouter; `qwen3.6` and `gemma4:12b` run locally via Ollama.

| Model | Level 1 (10Q) | Level 2 (5Q) | Drop | Overall (15Q) |
|---|---|---|---|---|
| `moonshotai/kimi-k3` | 97.2 | 78.5 | -18.7 | **91.0** |
| `anthropic/claude-fable-5` | 97.2 | 67.8 | -29.4 | 87.4 |
| `nvidia/nemotron-3-nano-30b-a3b` | 95.0 | 67.3 | -27.7 | 85.8 |
| `openai/gpt-5.6-sol` | 93.6 | 62.2 | -31.4 | 83.1 |
| `qwen3.6` (36B, local) | 92.8 | 41.2 | -51.6 | 75.6 |
| `gemma4:12b` (local) | 85.8 | 51.2 | -34.5 | 74.2 |
| `qwen/qwen3-coder-480b-a35b` | 74.8 | 54.6 | -20.2 | 68.1 |

Reading caveats — they matter more here than on the main board:

- **The drop is the finding, not the ranking.** Five level-2 questions cannot rank models. These same answers were re-scored under three judging configurations while two judging defects were being fixed (see the [judge prompt changelog](judge/prompt.md)): the ordering changed every time; the level-1-to-level-2 drop pattern held every time.
- **Level 2 measures window honesty as much as computation.** The harness shows the first 200 rows of the result. Under judge v0.2, a claim explicitly scoped to the shown rows is faithful; an unscoped global claim that contradicts the gold's full-population facts is not. The most drop-resistant models are the ones that scope their claims — including `nemotron-3-nano-30b-a3b`, a 3B-active MoE whose level-2 faithfulness (85-100) is the highest on this table.
- One partial run (`gemma4-12b_deskinsight_heldout`, level 1 only, pipeline variant) is published in [`runs/`](runs/) but is not comparable to full runs and is not listed above.

---

## v0.1 archive — mixed judges (preserved for transparency)

> Original v0.1 table. Each model judged by whichever judge was available at the time of the run. Now superseded by v0.2 above. Kept here so the published leaderboard history remains intact and to illustrate the inter-judge variance pattern.

<!-- LEADERBOARD-V01-START -->
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
<!-- LEADERBOARD-V01-END -->

---

## Inter-judge variance

Single-judge benchmarks systematically over- or under-estimate. Two examples documented in v0.1 / v0.2:

### `nvidia/llama-3.3-nemotron-super-49b-v1` scored by 3 judges (v0.1)

| Judge | GBAG | F | C | I |
|---|---|---|---|---|
| qwen3.6 | 77.9 | 80.0 | 72.1 | 81.1 |
| gemini-2.5 | 76.4 | 77.4 | 69.4 | 84.4 |
| deepseek-v3.2 | 66.6 | 64.8 | 68.3 | 68.5 |
| grok-4.3 | 67.7 | 61.4 | 70.5 | 79.4 |
| **Spread** | **11.3 pts** | **18.6** | **3.8** | **15.9** |

### `qwen3.5:9b` scored by 2 judges (v0.2)

| Judge | GBAG | F | C | I |
|---|---|---|---|---|
| deepseek-chat | 72.7 | 75.6 | 73.9 | 63.8 |
| grok-4.3 | 59.6 | 60.3 | 55.7 | 63.8 |
| **Delta** | **−13.1** | **−15.3** | **−18.2** | **0.0** |

37.5 % of questions show ≥ 15-point disagreement between the two judges. **All disagreements are in the same direction: deepseek-chat scores higher than grok-4.3, suggesting it is the more lenient judge on this task.**

A single model can score within an 11-point range purely based on judge choice. **The GBAG protocol therefore recommends dual-judge runs (two judges from different vendors) and reporting inter-rater agreement (Cohen's kappa).** Faithfulness and Insight axes show the largest sensitivity; Completeness is moderately stable.

---

## Submitting your model

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the full PR flow. TL;DR:

1. Run `examples/baseline_runner.py` on your model
2. Score with `judge/run_judge.py` using a frontier judge — **for v0.2 leaderboard, Grok-4.3 via OpenRouter is the reference judge** (`--judge openrouter --model x-ai/grok-4.3`)
3. Open a PR adding your row + your `runs/*.jsonl` + `runs/*.scored-grok43.jsonl`

**Dual-judge submissions strongly preferred.** Single-judge entries are accepted but flagged in the table.
