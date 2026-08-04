"""
GBAG Judge — scores model answers against the gold reference.

Usage:
    python judge/run_judge.py \\
        --dataset data/questions.jsonl \\
        --answers path/to/model_answers.jsonl \\
        --output path/to/scores.jsonl \\
        --judge anthropic   # or: openai | nvidia | openrouter | deepseek

Input answers file (JSONL, one per line):
    {"id": "sakila-l1-01", "model_answer": "There are 200 actors..."}

Output (JSONL):
    {"id": "...", "gbag_score": 87.4, "faithfulness": 95, "completeness": 80,
     "insight": 70, "...justifications...",
     "judge_input_tokens": 512, "judge_output_tokens": 128, "judge_cost_usd": 0.002}

Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY environment variable.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

# pricing helpers (repo root)
sys.path.insert(0, str(Path(__file__).parent.parent))
from pricing import estimate_cost, format_cost


JUDGE_PROMPT_PATH = Path(__file__).parent / "prompt.md"


def load_judge_system_prompt() -> str:
    """Extract the System prompt section from prompt.md."""
    text = JUDGE_PROMPT_PATH.read_text(encoding="utf-8")
    marker = "## System prompt"
    idx = text.find(marker)
    if idx == -1:
        raise RuntimeError("Could not locate '## System prompt' in judge/prompt.md")
    return text[idx + len(marker):].strip()


def build_user_message(question: dict, model_answer: str) -> str:
    msg = (
        f"QUESTION:\n{question['question']}\n\n"
        f"SQL:\n{question['gold_sql']}\n\n"
        f"GOLD ANSWER:\n{question['gold_answer']}\n\n"
        f"EXPECTED INSIGHTS:\n"
        + "\n".join(f"- {i}" for i in question.get("expected_insights", []))
    )
    # Deterministic facts computed from the database by
    # scripts/build_verification_facts.py. Present from judge prompt v0.3 onward.
    # Optional on purpose: datasets built before v0.3 still run unchanged.
    facts = question.get("verification_facts")
    if facts:
        msg += f"\n\nVERIFICATION FACTS (computed from the database, authoritative):\n{facts}"
    return msg + f"\n\nMODEL ANSWER:\n{model_answer}\n"


# ---------------------------------------------------------------------------
# Judge callers — return (text, input_tokens, output_tokens)
# ---------------------------------------------------------------------------

def call_anthropic(system: str, user: str, model: str = "claude-sonnet-4-6") -> tuple[str, int | None, int | None]:
    from anthropic import Anthropic
    client = Anthropic()
    resp = client.messages.create(
        model=model,
        max_tokens=1024,
        temperature=0,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text, resp.usage.input_tokens, resp.usage.output_tokens


def call_openai(system: str, user: str, model: str = "gpt-5") -> tuple[str, int | None, int | None]:
    from openai import OpenAI
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    return resp.choices[0].message.content, (usage.prompt_tokens if usage else None), (usage.completion_tokens if usage else None)


def call_nvidia(system: str, user: str, model: str = "nvidia/llama-3.3-nemotron-super-49b-v1") -> tuple[str, int | None, int | None]:
    """NVIDIA NIM API — OpenAI-compatible. Set NVIDIA_API_KEY."""
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["NVIDIA_API_KEY"],
        base_url="https://integrate.api.nvidia.com/v1",
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    return resp.choices[0].message.content, (usage.prompt_tokens if usage else None), (usage.completion_tokens if usage else None)


def call_openrouter(system: str, user: str, model: str = "anthropic/claude-sonnet-4-5") -> tuple[str, int | None, int | None]:
    """OpenRouter API — OpenAI-compatible. Set OPENROUTER_API_KEY."""
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["OPENROUTER_API_KEY"],
        base_url="https://openrouter.ai/api/v1",
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    return resp.choices[0].message.content, (usage.prompt_tokens if usage else None), (usage.completion_tokens if usage else None)


def call_deepseek(system: str, user: str, model: str = "deepseek-chat") -> tuple[str, int | None, int | None]:
    """DeepSeek API is OpenAI-compatible. Set DEEPSEEK_API_KEY."""
    from openai import OpenAI
    client = OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com",
    )
    resp = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    usage = resp.usage
    return resp.choices[0].message.content, (usage.prompt_tokens if usage else None), (usage.completion_tokens if usage else None)


def parse_judge_response(raw: str) -> dict:
    """Extract JSON object from the judge's response (tolerant of fences)."""
    if not raw:
        raise ValueError("judge returned empty response (content filter or rate limit?)")
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("```", 2)[1]
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
        if s.endswith("```"):
            s = s[:-3].strip()
    return json.loads(s)


def _clamp(v) -> int:
    """Clamp a judge score to [0, 100]. Some judges (e.g. DeepSeek v3.2) return
    -1 to mean 'cannot evaluate' — treat that as 0 so it doesn't pollute the
    averages or the JSONL output."""
    try:
        n = int(v)
    except (TypeError, ValueError):
        return 0
    return max(0, min(100, n))


def clamp_scores(scores: dict) -> dict:
    """Return a copy of the parsed judge response with F/C/I clamped to 0-100."""
    out = dict(scores)
    for k in ("faithfulness", "completeness", "insight"):
        if k in out:
            out[k] = _clamp(out[k])
    return out


def compute_gbag_score(scores: dict) -> float:
    f = _clamp(scores["faithfulness"])
    c = _clamp(scores["completeness"])
    i = _clamp(scores["insight"])
    return round(0.50 * f + 0.30 * c + 0.20 * i, 2)


def _fmt_tokens(n: int | None) -> str:
    return f"{n:,}" if n is not None else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True, help="Path to questions.jsonl")
    ap.add_argument("--answers", required=True, help="Path to model_answers.jsonl")
    ap.add_argument("--output", required=True, help="Where to write scores.jsonl")
    ap.add_argument("--judge", choices=["anthropic", "openai", "nvidia", "openrouter", "deepseek"], default="anthropic")
    ap.add_argument("--model", default=None, help="Override judge model id")
    ap.add_argument("--limit", type=int, default=0, help="Score only first N (debug)")
    ap.add_argument("--resume", action="store_true",
                    help="Skip questions already scored in the output file (retry errors only)")
    args = ap.parse_args()

    dataset = {q["id"]: q for q in (json.loads(l) for l in Path(args.dataset).open(encoding="utf-8") if l.strip())}
    answers = [json.loads(l) for l in Path(args.answers).open(encoding="utf-8") if l.strip()]
    if args.limit:
        answers = answers[: args.limit]

    system = load_judge_system_prompt()
    caller = {"anthropic": call_anthropic, "openai": call_openai, "nvidia": call_nvidia, "openrouter": call_openrouter, "deepseek": call_deepseek}[args.judge]
    kwargs = {"model": args.model} if args.model else {}
    judge_model = args.model or {"anthropic": "claude-sonnet-4-6", "openai": "gpt-5", "nvidia": "nvidia/llama-3.3-nemotron-super-49b-v1", "openrouter": "anthropic/claude-sonnet-4-5", "deepseek": "deepseek-chat"}[args.judge]

    # --resume: load already-scored IDs from existing output file
    done_ids: set[str] = set()
    out_path = Path(args.output)
    if args.resume and out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            if line.strip():
                done_ids.add(json.loads(line)["id"])
        print(f"Resume: {len(done_ids)} already scored, {len(answers) - len(done_ids)} remaining.")

    out = out_path.open("a" if args.resume else "w", encoding="utf-8")

    n_ok = n_err = 0
    total_in: int = 0
    total_out: int = 0
    total_cost: float = 0.0
    tokens_known = False

    for i, ans in enumerate(answers, 1):
        qid = ans["id"]
        if qid in done_ids:
            print(f"[{i}/{len(answers)}] {qid}: skipped (already done)")
            continue
        q = dataset.get(qid)
        if not q:
            print(f"[{i}/{len(answers)}] {qid}: NOT IN DATASET — skipped", file=sys.stderr)
            continue
        user = build_user_message(q, ans["model_answer"])
        try:
            raw, in_tok, out_tok = caller(system, user, **kwargs)
            parsed = clamp_scores(parse_judge_response(raw))
            score = compute_gbag_score(parsed)

            cost = None
            if in_tok is not None and out_tok is not None:
                tokens_known = True
                total_in += in_tok
                total_out += out_tok
                cost = estimate_cost(args.judge, judge_model, in_tok, out_tok)
                if cost is not None:
                    total_cost += cost

            record = {
                "id": qid,
                "gbag_score": score,
                **parsed,
                "judge_input_tokens": in_tok,
                "judge_output_tokens": out_tok,
                "judge_cost_usd": cost,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            n_ok += 1

            tok_info = f"  [{_fmt_tokens(in_tok)} in / {_fmt_tokens(out_tok)} out | {format_cost(cost)}]" if in_tok is not None else ""
            print(f"[{i}/{len(answers)}] {qid}: GBAG={score} (F={parsed['faithfulness']} C={parsed['completeness']} I={parsed['insight']}){tok_info}")
        except Exception as e:
            n_err += 1
            print(f"[{i}/{len(answers)}] {qid}: ERROR — {e}", file=sys.stderr)
            time.sleep(1)

    out.close()

    # Summary
    print(f"\nDone. {n_ok} scored, {n_err} errors.")
    if tokens_known:
        total_tok = total_in + total_out
        cost_display = format_cost(total_cost if total_cost > 0 else estimate_cost(args.judge, judge_model, total_in, total_out))
        print(f"Judge tokens: {total_in:,} in / {total_out:,} out (total: {total_tok:,})")
        print(f"Judge est. cost: {cost_display}")

    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
