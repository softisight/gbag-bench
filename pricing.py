"""Token-pricing helpers for cost estimation in run summaries.

The price table lives in pricing.json at the repo root. Update it whenever
a model's public pricing changes — the rest of the harness reads it lazily.

Cost estimates are best-effort: server-reported tokens are authoritative, but
the per-MTok price reflects what the maintainer verified at `verified_on`.
Mention this caveat when citing costs in a paper.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _pricing_path() -> Path:
    return Path(__file__).parent / "pricing.json"


@lru_cache(maxsize=1)
def _load_pricing() -> dict:
    """Load pricing.json once and cache. Keys starting with `_` are filtered."""
    path = _pricing_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_") and isinstance(v, dict)}


def get_price(provider: str, model: str) -> Optional[dict]:
    """Return {input_per_mtok, output_per_mtok, verified_on} or None if unknown."""
    table = _load_pricing()
    key = f"{provider}:{model}"
    if key in table:
        return table[key]
    # Fallback: match by model id alone (handles provider aliases)
    for k, v in table.items():
        if k.endswith(":" + model):
            return v
    return None


def estimate_cost(provider: str, model: str, input_tokens: int, output_tokens: int) -> Optional[float]:
    """Return estimated USD cost, or None if pricing is unknown.
    Returns 0.0 for free-tier models (explicit zeros in pricing.json)."""
    p = get_price(provider, model)
    if p is None:
        return None
    in_rate = float(p.get("input_per_mtok") or 0)
    out_rate = float(p.get("output_per_mtok") or 0)
    return (input_tokens / 1_000_000.0) * in_rate + (output_tokens / 1_000_000.0) * out_rate


def format_cost(cost: Optional[float]) -> str:
    """Compact display string for a USD cost value."""
    if cost is None:
        return "n/a"
    if cost == 0.0:
        return "free"
    if cost < 0.01:
        return "<$0.01"
    if cost < 0.10:
        return f"${cost:.4f}"
    return f"${cost:.2f}"
