"""
Convert GBAG questions.jsonl into 3 DeskInsight Benchmark Runner suites
(one per database: sakila, chinook, northwind).

Output: <db>_gbag.json files written directly to Z:\\SampleDB\\, next to
the SQLite files they target. DeskInsight's "Load JSON" dialog already
opens in that folder, so the user just picks the file.

Workflow:
    1. python scripts/export_to_deskinsight_suites.py
       → creates Z:\\SampleDB\\{sakila,chinook,northwind}_gbag.json
    2. In DeskInsight Benchmark Runner: Load JSON → pick <db>_gbag.json
    3. Run benchmark (model = your choice + Use Gold SQL ON + Production)
    4. Copy each resulting benchmark_raw.json into Z:\\gbag-bench\\runs\\
       under a descriptive name like raw_<db>_<model>.json
    5. python scripts/import_from_deskinsight_results.py converts those
       back to GBAG model_answers.jsonl format
    6. python judge/run_judge.py scores it with grok-4.3
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
SAMPLE_DB_DIR = Path(r"Z:\SampleDB")

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

if not SAMPLE_DB_DIR.exists():
    raise SystemExit(f"Target directory does not exist: {SAMPLE_DB_DIR}")

for db, qs in by_db.items():
    suite = {
        "name": f"GBAG-{db} for DeskInsight Runner ({len(qs)} questions)",
        "database": DB_PATHS[db],
        "questions": qs,
    }
    out = SAMPLE_DB_DIR / f"{db}_gbag.json"
    out.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {out}  ({len(qs)} questions)")

print()
print("Next steps:")
print("1. Open DeskInsight Benchmark Runner -> Load JSON")
print(f"   The dialog opens in {SAMPLE_DB_DIR} -- pick <db>_gbag.json")
print("2. Verify model, profile = Production, Use Gold SQL = ON")
print("3. Run benchmark")
print("4. Copy the resulting benchmark_raw.json into Z:\\gbag-bench\\runs\\")
print("   under a descriptive name like raw_<db>_<model>.json")
print("5. python scripts/import_from_deskinsight_results.py")
print("6. python judge/run_judge.py --judge openrouter --model x-ai/grok-4.3")
