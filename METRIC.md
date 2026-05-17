# GBAG Score — Specification v0.1

The **GBAG Score** is a single number from 0 to 100 measuring how well a model interprets a SQL result into a faithful natural-language answer.

## Formula

```
GBAG Score = 0.50 × Faithfulness + 0.30 × Completeness + 0.20 × Insight
```

Each sub-score is rated 0–100 by an LLM judge.

## Sub-scores

### Faithfulness (50%)
Does the answer contain only facts grounded in the SQL result? Penalize any hallucinated number, name, date, or trend.

- 100 = every claim is verifiable from the result set
- 0 = the answer contradicts or invents data

### Completeness (30%)
Does the answer address all parts of the user's question?

- 100 = every sub-question is answered
- 0 = the answer ignores the question

### Insight (20%)
Does the answer go beyond restating numbers? Surface trends, anomalies, or actionable observations.

- 100 = clear, useful business insight
- 0 = raw recitation or empty paraphrase

## Why this weighting

A BI user acts on the answer. A hallucinated number causes real-world damage (wrong invoice, wrong forecast, wrong decision). Faithfulness must dominate. Completeness and Insight matter, but only on top of a faithful answer.

## Judging protocol

- LLM-as-judge using a frontier model (Claude or GPT class)
- Dual-judge for inter-rater agreement (Cohen's kappa reported)
- Temperature = 0
- Prompt and rubric published in `judge/` (coming soon)

## Versioning

This is **v0.1**. The formula and rubric are open to community feedback before v1.0.
