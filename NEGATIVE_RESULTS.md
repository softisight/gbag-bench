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

