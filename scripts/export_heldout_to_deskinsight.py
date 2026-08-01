"""
Convert the GBAG held-out suite(s) into DeskInsight Benchmark Runner suites
for the ledger database.

Emits two files next to ledger.sqlite (where DeskInsight's Load-JSON dialog
conveniently lands):
    databases/ledger_gbag.json         -> Level 2 = full 15 questions (adds the
                                          extreme l9/l10 tier)
    databases/ledger_gbag_level1.json  -> Level 1 = core 10 questions
                                          (small-model-friendly, no extreme tier)

Deliberately emits NO schema_notes / domain hints: the DeskInsight pipeline
must detect the accounting domain and build its own data dictionary by itself,
exactly as it would in production. Injecting hand-written accounting
conventions here would hand the pipeline an advantage the neutral baseline
runs never got, breaking the comparison.

Workflow:
    1. python scripts/export_heldout_to_deskinsight.py
    2. DeskInsight Benchmark Runner -> Load JSON -> pick the suite you want
       (level1 for small models, the full one to stress-test frontier models)
    3. Run. For apples-to-apples with the neutral baselines, set "Use gold SQL"
       (Utiliser le SQL de reference) = ON. Turn it OFF to test the full
       pipeline including DeskInsight's own NL2SQL.
    4. Copy the resulting benchmark_raw.json into runs/ as raw_ledger_<model>.json
    5. python scripts/import_from_deskinsight_results.py  (converts back)
    6. python judge/run_judge.py --judge openrouter --model x-ai/grok-4.3
"""
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = str((ROOT / "databases" / "ledger.sqlite").resolve())

SUITES = [
    ("questions-heldout.jsonl",        "ledger_gbag.json",        "Level 2 / full"),
    ("questions-heldout-level1.jsonl", "ledger_gbag_level1.json", "Level 1 / core"),
]


def to_suite(dataset_path, label):
    questions = [json.loads(l) for l in dataset_path.open(encoding="utf-8") if l.strip()]
    return {
        "name": "GBAG-ledger held-out (%s) for DeskInsight Runner (%d questions)"
                % (label, len(questions)),
        "database": DB_PATH,
        "questions": [
            {
                "id": q["id"],
                "level": q["difficulty"],
                "question": q["question"],
                "pipeline": "data_analysis",
                "gold_sql": q["gold_sql"],
            }
            for q in questions
        ],
    }, len(questions)


for src, dst, label in SUITES:
    dataset_path = ROOT / "data" / src
    if not dataset_path.exists():
        print("SKIP (missing):", dataset_path)
        continue
    suite, n = to_suite(dataset_path, label)
    out = ROOT / "databases" / dst
    out.write_text(json.dumps(suite, indent=2, ensure_ascii=False), encoding="utf-8")
    print("Wrote %s  (%d questions, %s)" % (out, n, label))

print("Database:", DB_PATH)
