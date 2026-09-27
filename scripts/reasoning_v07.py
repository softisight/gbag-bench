"""GBAG v0.7 — the reasoning that the models actually used (PROTOCOL_v0.7.md, D22). Code only.

The cloud models ran with their provider's default reasoning, the local ones with reasoning
off (D10). The answer files record the tokens of reasoning of every cloud answer. This
script counts them, on the controls and on the targets of the trap rate.

Usage (repo root):  python scripts/reasoning_v07.py
"""
from __future__ import annotations

import collections
import statistics
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import double_read_v07 as dr
import reader_v07 as rv


def used(r: dict) -> int | None:
    """Tokens of reasoning of an answer: recorded by the provider for the cloud answers;
    0 for a local answer generated with reasoning off; None when nothing says."""
    if r.get("reasoning_tokens") is not None:
        return r["reasoning_tokens"]
    served = r.get("served") or {}
    if served.get("reasoning_tokens") is not None:
        return served["reasoning_tokens"]
    return 0 if served.get("think") is False else None


def table(arm: str = "B", run: int = 1) -> dict:
    """{model: {"control" | "trap": [tokens of reasoning, one per answer]}}"""
    targets = rv.load_targets()
    out = collections.defaultdict(lambda: collections.defaultdict(list))
    for model, r in dr.answers():
        if r["arm"] == arm and r["run"] == run:
            kind = "control" if targets[r["tid"]]["kind"] == "control" else "trap"
            out[model][kind].append(used(r))
    return out


def main() -> int:
    print("GBAG v0.7 — tokens of reasoning per answer, arm B, run 1")
    print(f"{'model':32} | {'answers':>7} {'mean':>6} {'median':>6} | {'controls without reasoning':>26} | {'trap targets without reasoning':>30}")
    for model, kinds in sorted(table().items(), key=lambda x: -statistics.mean(v or 0 for k in x[1].values() for v in k)):
        every = [v for k in kinds.values() for v in k]
        if any(v is None for v in every):
            print(f"{model:32} | {len(every):>7}   not recorded")
            continue
        none = lambda k: f"{sum(v == 0 for v in kinds[k])}/{len(kinds[k])}"
        print(f"{model:32} | {len(every):>7} {statistics.mean(every):>6.0f} {statistics.median(every):>6.0f} | "
              f"{none('control'):>26} | {none('trap'):>30}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
