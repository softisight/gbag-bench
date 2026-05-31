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

**1. Context engineering > model scale.** The same `qwen3.5:9b` on a consumer RTX 3060 scores **59.6** with a neutral Spider/BIRD-style prompt, but **76.8** wrapped in DeskInsight's context engineering pipeline (data dictionary, domain detection, Pre-Aggregated Context Injection, profile adaptation). **+17.2 points** — placing a 9B local model 12 points above the 480B cloud baseline. **The dominant lever for grounded BI quality is what you feed the model, not how big the model is.** Both rows use identical model weights, hardware, questions, gold SQL, and judge — only the prompt scaffolding differs. See [Methodology — how the DeskInsight pipeline line was obtained](LEADERBOARD.md#methodology--how-the-deskinsight-pipeline-line-was-obtained) for the full reproduction recipe.

**2. Bigger is not (much) better.** Under a uniform strong judge (Grok-4.3), `qwen3.5:9b` (59.6) sits ~3 points below `qwen3-coder-480b` (62.8 on 32 common questions). The earlier v0.1 leaderboard suggested near-parity but was inflated by a lenient judge. The gap reopens — but to **single digits, on a model with ~50× fewer parameters**.

**3. Judge selection matters as much as model selection.** Re-judging the same `qwen3.5:9b` answers with Grok-4.3 dropped the score from **72.7** (deepseek-chat) to **59.6** — 13-point gap on identical model answers. 37.5 % of questions show ≥ 15-point disagreement between the two judges, always in the same direction (deepseek-chat is the more lenient). **Single-judge benchmarks are unreliable.** GBAG ships a dual-judge protocol with Cohen's kappa.

**4. Thinking modes can hurt grounded tasks.** `qwen3-next-80b-thinking` (61.4) barely exceeds the 9B neutral baseline (59.6) and trails the non-thinking `qwen3-coder-480b` (64.6) under the same judge. Hidden reasoning tokens introduce inconsistencies during result interpretation — confirming practitioner reports.

**5. Specific failure modes are concentrated, not universal.** Local models occasionally fabricate aggregates from row samples on top-N queries with large underlying tables (a pattern we call the Post-SQL Aggregation Deficit). Pre-Aggregated Context Injection mitigates most cases. The failures are concentrated on a narrow question type, not spread across the benchmark.

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
