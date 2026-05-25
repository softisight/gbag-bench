"""
Convert GBAG questions.jsonl into 3 DeskInsight Benchmark Runner suites
(one per database: sakila, chinook, northwind).

Output: gbag_<db>_for_deskinsight.json files in scripts/ folder.

Then the user loads each one via Benchmark Runner "Charger JSON" button,
runs with qwen3.5:9b + Production profile + Use Gold SQL ON.
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent

DB_PATHS = {
    "sakila":    r"Z:\SampleDB\sakila.db",
    "chinook":   r"Z:\SampleDB\Chinook_Sqlite.sqlite",
    "northwind": r"Z:\SampleDB\Northwind_small.sqlite",
}

questions = [json.loads(l) for l in (ROOT / "data" / "questions.jsonl").open(encoding="utf-8") if l.strip()]

# Group by database
by_db: dict[str, list[dict]] = {"sakila": [], "chinook": [], "northwind": []}
for q in questions:
    db = q["database"]
    # GBAG id "sakila-l1-01" -> DeskInsight id "sakila-l1-01" (keep prefix for mapping back)
    by_db[db].append({
        "id": q["id"],
        "level": q["difficulty"],
        "question": q["question"],
        "pipeline": "data_analysis",
        "gold_sql": q["gold_sql"],
    })

for db, qs in by_db.items():
    suite = {
        "name": f"GBAG-{db} for DeskInsight Runner ({len(qs)} questions)",
        "database": DB_PATHS[db],
        "questions": qs,
    }
    out = ROOT / "scripts" / f"gbag_{db}_for_deskinsight.json"
    out.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}  ({len(qs)} questions)")

print()
print("Next steps:")
print("1. Open DeskInsight Benchmark Runner")
print("2. For each of the 3 files:")
print("   - Click 'Charger JSON', pick gbag_<db>_for_deskinsight.json")
print("   - Verify model = qwen3.5:9b (local Ollama)")
print("   - Profile: Production (privacy-first, default)")
print("   - Check 'Utiliser le SQL de reference' (Gold SQL)")
print("   - Run benchmark")
print("   - Save the benchmark_raw.json output to Z:/gbag-bench/scripts/raw_<db>.json")
print("3. Run scripts/import_from_deskinsight_results.py to get GBAG-format answers")
print("4. Score with Grok-4.3 judge")
