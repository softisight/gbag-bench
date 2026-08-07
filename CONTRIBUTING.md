# Contributing to GBAG-Bench

Thanks for considering a contribution. The most valuable contributions are **new model results** added to the leaderboard, but bug reports, dataset fixes, and metric discussions are equally welcome.

## Adding a new model result to the leaderboard

### Step 1 — Clone and install

```bash
git clone https://github.com/softisight/gbag-bench
cd gbag-bench
pip install -r requirements.txt
```

### Step 2 — Run the baseline runner on your model

```bash
python examples/baseline_runner.py \
    --dataset data/questions.jsonl \
    --db-dir databases/ \
    --output runs/<your-model-id>.jsonl \
    --provider <anthropic|openai|ollama> \
    --model <model-name>
```

Use a short, stable model id for the filename — e.g. `claude-sonnet-4-6`, `gpt-5-mini`, `qwen3.5-9b`. No spaces, lowercase preferred.

### Step 3 — Score with a frontier-class judge

```bash
python judge/run_judge.py \
    --dataset data/questions.jsonl \
    --answers runs/<your-model-id>.jsonl \
    --output runs/<your-model-id>.scored.jsonl \
    --judge <anthropic|openai|deepseek|nvidia|openrouter> [--model <judge-model-id>]
```

A frontier judge is required for fair scoring. **Do not judge a model with itself.**

For v0.2 leaderboard comparability, score with the uniform reference judge (Grok-4.3 via OpenRouter — see the README Quick start). Dual-judge submissions are strongly preferred: run a second judge from a different vendor and report both (inter-judge variance is a known factor, see Finding #3 in the README).

**Two additions, from measurements taken after v0.2 was published** — see [JUDGE_VALIDATION.md](JUDGE_VALIDATION.md):

- **Run each judge at least three times and report all runs.** A single run samples a judge, it does not measure one. Grok-4.3 graded the same answer 40, 40, 100, 10 across four runs at temperature 0.
- **Use `judge/prompt-v041.md`, not `judge/prompt.md`.** Under the older prompt every judge tested scored 2 to 4 out of 7 on the validation cases; the newer one takes the best of them to 7 out of 7 and is the best-scoring prompt for every judge measured.

If you can run a judge locally, prefer it: its seed can be pinned, and every local judge tested was perfectly self-consistent. Pin the batch and its order too — position inside a run can flip a boundary verdict.

### Step 4 — Open a Pull Request

Fork the repo, create a branch, commit your two new files (`runs/*.jsonl` + `runs/*.scored.jsonl`), and edit `LEADERBOARD.md` to add your row.

The PR template will ask you to confirm the model name, hardware, judge used, and coverage. Fill it honestly — your results will be re-verified.

### Verification

Any maintainer or third party can reproduce your scores by re-running the judge on your committed `runs/*.jsonl`. Discrepancies between your reported scores and the verification run are grounds for rejection.

## Improving the dataset

If you find a question with an incorrect `gold_sql`, `gold_answer`, or `expected_insights`:

1. Open an **Issue** first to discuss the change (avoids wasted PR work).
2. If agreed, open a PR with the fix and a brief rationale.

Dataset changes are reviewed carefully — they affect every past and future score. Cosmetic changes (typos) are easy; semantic changes (different gold answer) require justification.

## Improving the metric

The 50/30/20 weighting and the 3-axis rubric are explicit design choices. They are **open to challenge** before v1.0.

If you have evidence that a different weighting or a different axis would better capture BI answer quality, open an Issue with:

- A description of the proposed change
- At least 5 concrete examples where the current metric is wrong and yours is right
- A reproducible scoring experiment if possible

Avoid PRs that change the metric without prior discussion — they will be closed.

## Code style

- Python 3.9+
- Use the standard library where possible
- Keep scripts under 300 lines
- No new dependencies without justification

## Code of conduct

Be polite, be precise, be reproducible.
