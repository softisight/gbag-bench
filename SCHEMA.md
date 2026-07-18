# Dataset Schema v0.1

Each question is one line in `data/questions.jsonl`.

## Fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable unique ID encoding database and level: `<db>-l<difficulty>-<nn>`, e.g. `sakila-l6-02` |
| `database` | string | Database name: `sakila`, `chinook`, `northwind` |
| `question` | string | The natural-language question (English) |
| `gold_sql` | string | A reference SQL that correctly answers the question |
| `gold_answer` | string | A reference natural-language answer (faithful, complete, insightful) |
| `difficulty` | int | 1 (trivial) to 10 (extreme: large result sets, multi-step analytical reasoning) |
| `category` | string | One of: `aggregation`, `trend`, `ranking`, `join`, `derived`. (`comparison` and `filter` are reserved in the taxonomy but unused in the current 35-question set.) |
| `expected_insights` | list[string] | Atomic facts the answer MUST contain. Used by the judge for Completeness. |

Current v0.2 dataset: 35 questions (Sakila 15, Chinook 10, Northwind 10). See the "Dataset composition" section of the README for the full breakdown by category and difficulty.

## Example

Illustrative row (shows the field shapes; not an actual dataset entry):

```json
{
  "id": "sakila-l3-07",
  "database": "sakila",
  "question": "What are the top 3 film categories by total rental revenue?",
  "gold_sql": "SELECT c.name, SUM(p.amount) AS revenue FROM payment p JOIN rental r ON p.rental_id = r.rental_id JOIN inventory i ON r.inventory_id = i.inventory_id JOIN film_category fc ON i.film_id = fc.film_id JOIN category c ON fc.category_id = c.category_id GROUP BY c.name ORDER BY revenue DESC LIMIT 3;",
  "gold_answer": "The top 3 categories by rental revenue are Sports ($5,314), Sci-Fi ($4,756), and Animation ($4,656). Sports leads by a margin of about 12% over Sci-Fi.",
  "difficulty": 3,
  "category": "ranking",
  "expected_insights": [
    "Sports is the top category",
    "Sports revenue is approximately $5,314",
    "Top 3 are Sports, Sci-Fi, Animation"
  ]
}
```

## Rules for `expected_insights`

- Each entry is one atomic, verifiable fact
- Keep them short and unambiguous
- The judge marks Completeness based on how many appear in the model's answer
