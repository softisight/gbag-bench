"""
Auto-regenerate the LEADERBOARD.md table from runs/*.scored*.jsonl files.

Behavior:
- Scans every `runs/*.scored*.jsonl` (judge variants supported)
- Matches each scored file with its base `runs/<model>.jsonl` for coverage + provider
- Computes mean GBAG, Faithfulness, Completeness, Insight
- Sorts entries by GBAG descending
- Replaces ONLY the markdown table located between
    <!-- LEADERBOARD-AUTO-START --> and <!-- LEADERBOARD-AUTO-END -->
- Leaves every prose section in LEADERBOARD.md untouched

Usage:
    python scripts/update_leaderboard.py

Exit codes:
    0 — leaderboard updated (or already up to date)
    1 — markers not found in LEADERBOARD.md
    2 — no scored runs found
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = REPO_ROOT / "runs"
LEADERBOARD = REPO_ROOT / "LEADERBOARD.md"
MARKER_START = "<!-- LEADERBOARD-AUTO-START -->"
MARKER_END = "<!-- LEADERBOARD-AUTO-END -->"

# Friendly display name for judge suffixes in the scored filename
JUDGE_LABEL = {
    "": "deepseek-chat",
    "deepseek3.2": "deepseek-v3.2",
    "gemini25": "gemini-2.5",
    "qwen36": "qwen3.6",
}


def parse_scored_filename(p: Path) -> tuple[str, str]:
    """Return (base_model_stem, judge_suffix). Examples:
       qwen35-9b-3060-full.scored.jsonl              -> ('qwen35-9b-3060-full', '')
       nvidia-llama3.scored-deepseek3.2.jsonl        -> ('nvidia-llama3', 'deepseek3.2')
    """
    name = p.name
    m = re.match(r"^(.*?)\.scored(?:-(.+))?\.jsonl$", name)
    if not m:
        raise ValueError(f"unrecognised scored filename: {name}")
    return m.group(1), (m.group(2) or "")


def mean(rows: list[dict], key: str) -> float:
    vals = [r.get(key, 0) for r in rows]
    return sum(vals) / len(vals) if vals else 0.0


def load_jsonl(p: Path) -> list[dict]:
    return [json.loads(l) for l in p.open(encoding="utf-8") if l.strip()]


def main() -> int:
    if not LEADERBOARD.exists():
        print(f"error: {LEADERBOARD} not found", file=sys.stderr)
        return 1

    text = LEADERBOARD.read_text(encoding="utf-8")
    if MARKER_START not in text or MARKER_END not in text:
        print(
            f"error: markers {MARKER_START!r} and {MARKER_END!r} not found in LEADERBOARD.md.\n"
            "Add them around the table you want auto-managed.",
            file=sys.stderr,
        )
        return 1

    scored_files = sorted(RUNS_DIR.glob("*.scored*.jsonl"))
    if not scored_files:
        print("warn: no scored runs found", file=sys.stderr)
        return 2

    entries: list[dict] = []
    for sp in scored_files:
        stem, judge_suffix = parse_scored_filename(sp)
        base = RUNS_DIR / f"{stem}.jsonl"
        if not base.exists():
            print(f"warn: missing base run for {sp.name}, skipping", file=sys.stderr)
            continue

        scored_rows = load_jsonl(sp)
        base_rows = load_jsonl(base)
        if not scored_rows:
            continue

        # extract model + provider from the first base row (they're stable per file)
        first = base_rows[0] if base_rows else {}
        model = first.get("model", stem)
        provider = first.get("provider", "?")

        entries.append({
            "model": model,
            "provider": provider,
            "judge": JUDGE_LABEL.get(judge_suffix, judge_suffix or "deepseek-chat"),
            "coverage": f"{len(scored_rows)} / 35",
            "gbag": round(mean(scored_rows, "gbag_score"), 1),
            "f": round(mean(scored_rows, "faithfulness"), 1),
            "c": round(mean(scored_rows, "completeness"), 1),
            "i": round(mean(scored_rows, "insight"), 1),
        })

    entries.sort(key=lambda e: e["gbag"], reverse=True)

    # build the markdown table
    header = "| Model | Provider | Judge | Coverage | **GBAG** | F | C | I |"
    sep = "|---|---|---|---|---|---|---|---|"
    body = [
        f"| `{e['model']}` | {e['provider']} | {e['judge']} | {e['coverage']} | **{e['gbag']}** | {e['f']} | {e['c']} | {e['i']} |"
        for e in entries
    ]
    table = "\n".join([header, sep, *body])

    # replace content between markers
    pattern = re.compile(
        re.escape(MARKER_START) + r".*?" + re.escape(MARKER_END),
        flags=re.DOTALL,
    )
    new_block = f"{MARKER_START}\n{table}\n{MARKER_END}"
    new_text = pattern.sub(new_block, text)

    if new_text == text:
        print(f"leaderboard already up to date ({len(entries)} entries)")
        return 0

    LEADERBOARD.write_text(new_text, encoding="utf-8")
    print(f"leaderboard updated: {len(entries)} entries written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
