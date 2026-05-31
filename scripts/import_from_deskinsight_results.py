"""
Convert DeskInsight Runner benchmark_raw.json output(s) back to GBAG
model_answers.jsonl format, ready for judge/run_judge.py.

Convention (post-cleanup):
- DeskInsight suites live in Z:\\SampleDB\\<db>_gbag.json (loaded via "Load JSON")
- Raw benchmark outputs are saved into Z:\\gbag-bench\\runs\\raw_<db>_<model>.json
- This script converts those into runs/<model>_gbag.jsonl for the judge

Usage:
    python scripts/import_from_deskinsight_results.py \\
        --raw runs/raw_sakila_gemma4-e4b.json \\
              runs/raw_chinook_gemma4-e4b.json \\
              runs/raw_northwind_gemma4-e4b.json \\
        --model "gemma4:e4b+deskinsight" \\
        --output runs/gemma4-e4b_deskinsight_goldsql.jsonl
"""
import argparse
import json
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", nargs="+", required=True,
                    help="One or more DeskInsight benchmark_raw.json files")
    ap.add_argument("--model", default="qwen3.5:9b+deskinsight",
                    help="Model label written into each output record")
    ap.add_argument("--provider", default="ollama+deskinsight",
                    help="Provider label written into each output record")
    ap.add_argument("--output", required=True,
                    help="GBAG-format model_answers.jsonl output path")
    args = ap.parse_args()

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out.open("w", encoding="utf-8") as f:
        for raw_path in args.raw:
            data = json.loads(Path(raw_path).read_text(encoding="utf-8-sig"))
            for r in data.get("results", []):
                # DeskInsight question_id "L1-01" -> GBAG id "sakila-l1-01" etc.
                # Our suite files preserve the GBAG prefix in id, so it should
                # round-trip cleanly. Lowercase the level digit just in case.
                qid = r["question_id"].lower()
                # If the id lost the db prefix, attempt to recover from file name
                if "-" in qid and not any(qid.startswith(p) for p in ("sakila", "chinook", "northwind")):
                    stem = Path(raw_path).stem.lower()
                    for db in ("sakila", "chinook", "northwind"):
                        if db in stem:
                            qid = f"{db}-{qid}"
                            break

                rec = {
                    "id": qid,
                    "model": args.model,
                    "provider": args.provider,
                    "model_answer": r.get("ai_response", ""),
                    "duration_seconds": r.get("total_duration_ms", 0) / 1000.0,
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1

    print(f"Wrote {n} answers to {out}")
    print(f"\nNext: score with Grok-4.3:")
    print(f"  python judge/run_judge.py \\")
    print(f"    --dataset data/questions.jsonl \\")
    print(f"    --answers {out} \\")
    print(f"    --output {out.with_suffix('.scored-grok43.jsonl')} \\")
    print(f"    --judge openrouter --model x-ai/grok-4.3")


if __name__ == "__main__":
    main()
