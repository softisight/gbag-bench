# Dataset Schema v0.1

Each question is one line in `data/questions.jsonl`.

## Fields

| Field | Type | Description |
|---|---|---|
| `id` | string | Stable unique ID, e.g. `sakila-001` |
| `database` | string | Database name: `sakila`, `chinook`, `northwind` |
| `question` | string | The natural-language question (English) |
| `gold_sql` | string | A reference SQL that correctly answers the question |
| `gold_answer` | string | A reference natural-language answer (faithful, complete, insightful) |
| `difficulty` | int | 1 (trivial) to 5 (multi-step reasoning) |
| `category` | string | One of: `aggregation`, `trend`, `comparison`, `ranking`, `filter`, `join`, `derived` |
| `expected_insights` | list[string] | Atomic facts the answer MUST contain. Used by the judge for Completeness. |

## Example

```json
{
  "id": "sakila-001",
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
