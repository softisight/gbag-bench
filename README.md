# GBAG-Bench

**Grounded BI Answer Generation** — a benchmark for faithful natural-language interpretation of SQL results.

> NL2SQL measures half the problem. GBAG measures the other half.

## The gap

NL2SQL benchmarks (Spider, BIRD) stop where the real user experience begins. They measure whether a model produces correct SQL — not whether it correctly **reads** the result and **answers the user's question**.

In practice, a correct SQL query followed by a hallucinated or imprecise natural-language answer is a failure for any BI product. GBAG measures this neglected second half.

## What GBAG evaluates

Given:
- a natural-language question
- the executed SQL
- the full result set
- (optionally) pre-aggregated context

…can the model produce a **faithful**, **complete**, and **insightful** natural-language answer?

## Scope

- Multi-database (Sakila, Chinook, Northwind, more to come)
- Multi-model (local + cloud)
- Multi-axis scoring: faithfulness, completeness, insight
- LLM-as-judge with dual-judge inter-rater agreement

## Status

Early stage. Specification and first dataset coming soon.

## License

MIT
