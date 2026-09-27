"""
GBAG Baseline Runner — neutral reference implementation.

Executes the gold_sql of each question against the SQLite database, then asks
a model to produce a natural-language answer. Writes model_answers.jsonl,
which can then be scored with judge/run_judge.py.

This runner is independent from any commercial product. Anyone with an API key
can reproduce GBAG results in a few minutes.

Usage:
    python examples/baseline_runner.py \\
        --dataset data/questions.jsonl \\
        --db-dir databases/ \\
        --output runs/claude-sonnet-4-6.jsonl \\
        --provider anthropic \\
        --model claude-sonnet-4-6

    python examples/baseline_runner.py \\
        --dataset data/questions.jsonl \\
        --db-dir databases/ \\
        --output runs/qwen3-14b.jsonl \\
        --provider ollama \\
        --model qwen3:14b

Expected DB filenames in --db-dir:
    sakila.sqlite, chinook.sqlite, northwind.sqlite

Requires: ANTHROPIC_API_KEY or OPENAI_API_KEY for cloud providers.
Ollama provider needs a local server on http://localhost:11434.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

# pricing helpers (repo root)
sys.path.insert(0, str(Path(__file__).parent.parent))
from pricing import estimate_cost, format_cost


SYSTEM_PROMPT = (
    "You are a business intelligence assistant. The user asked a question, "
    "the SQL was executed for you, and the result is provided. Produce a clear, "
    "faithful natural-language answer in English. Do not invent numbers. "
    "Be concise but include the key figures and any visible trend."
)


def execute_sql(db_path: Path, sql: str, row_cap: int = 200) -> tuple[list[str], list[tuple]]:
    con = sqlite3.connect(str(db_path))
    try:
        cur = con.cursor()
        cur.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchmany(row_cap)
        return cols, rows
    finally:
        con.close()


def format_result_as_markdown(cols: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "(no rows)"
    head = "| " + " | ".join(cols) + " |"
    sep = "| " + " | ".join("---" for _ in cols) + " |"
    body = ["| " + " | ".join("" if v is None else str(v) for v in r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def build_user_prompt(question: str, sql: str, cols: list[str], rows: list[tuple]) -> str:
    return (
        f"USER QUESTION:\n{question}\n\n"
        f"EXECUTED SQL:\n{sql}\n\n"
        f"RESULT ({len(rows)} rows shown):\n{format_result_as_markdown(cols, rows)}\n\n"
        "Write the answer now."
    )


# ---------------------------------------------------------------------------
# Provider callers — return (text, input_tokens, output_tokens)
# tokens are None when the provider doesn't report usage
# ---------------------------------------------------------------------------

def call_anthropic(system: str, user: str, model: str) -> tuple[str, int | None, int | None]:
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


def call_openai(system: str, user: str, model: str) -> tuple[str, int | None, int | None]:
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
    in_tok = usage.prompt_tokens if usage else None
    out_tok = usage.completion_tokens if usage else None
    return resp.choices[0].message.content, in_tok, out_tok


def call_nvidia(system: str, user: str, model: str) -> tuple[str, int | None, int | None]:
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
    in_tok = usage.prompt_tokens if usage else None
    out_tok = usage.completion_tokens if usage else None
    return resp.choices[0].message.content, in_tok, out_tok


# Generation condition, set from the command line. None = not sent, which is how every
# answer set published before v0.4 was produced (PROTOCOL_v0.4.md, deviation D6).
GEN_SEED: int | None = None
GEN_PROVIDER: str | None = None     # OpenRouter endpoint tag, pinned, no fallback
GEN_THINK: bool | None = None       # None = runtime default

# What actually served the last call, and how much it reasoned.
LAST_CALL: dict = {}


def call_openrouter(system: str, user: str, model: str) -> tuple[str, int | None, int | None]:
    """OpenRouter API. Set OPENROUTER_API_KEY.

    Plain HTTP: the endpoint that served the call and the reasoning it produced live
    outside the OpenAI schema, and they are part of the condition.
    """
    import requests
    body: dict = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "usage": {"include": True},
    }
    if GEN_SEED is not None:
        body["seed"] = GEN_SEED
    if GEN_PROVIDER is not None:
        body["provider"] = {"order": [GEN_PROVIDER], "allow_fallbacks": False}
    if GEN_THINK is not None:
        body["reasoning"] = {"enabled": GEN_THINK}
    r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                      headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                      json=body, timeout=900)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"OpenRouter: {data['error'].get('message', data['error'])}")
    usage = data.get("usage") or {}
    LAST_CALL.clear()
    LAST_CALL.update({
        "provider": data.get("provider"),
        "model": data.get("model"),
        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
        "cost_usd": usage.get("cost"),
    })
    msg = data["choices"][0]["message"]
    return msg.get("content") or "", usage.get("prompt_tokens"), usage.get("completion_tokens")


def call_ollama(system: str, user: str, model: str, host: str = "http://localhost:11434") -> tuple[str, int | None, int | None]:
    import urllib.request
    # `think` is a top-level field for Ollama. Until v0.4 it sat inside `options`, where
    # Ollama ignores it: every published local answer was generated with reasoning at
    # the runtime default (on). Measured 2026-09-25, PROTOCOL_v0.4.md deviation D6.
    payload: dict = {
        "model": model,
        "prompt": user,
        "system": system,
        "stream": False,
        "options": {"temperature": 0},
    }
    if GEN_THINK is not None:
        payload["think"] = GEN_THINK
    if GEN_SEED is not None:
        payload["options"]["seed"] = GEN_SEED
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{host.rstrip('/')}/api/generate",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        data = json.loads(r.read().decode("utf-8"))
    in_tok = data.get("prompt_eval_count")
    out_tok = data.get("eval_count")
    LAST_CALL.clear()
    LAST_CALL["thinking_chars"] = len(data.get("thinking") or "")
    return data.get("response", "").strip(), in_tok, out_tok


def ollama_model_info(model: str, host: str) -> dict:
    """Server version, quantization and digest of the local model, read from the host."""
    import urllib.request
    def get(path):
        with urllib.request.urlopen(f"{host.rstrip('/')}{path}", timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    info: dict = {"ollama_version": get("/api/version").get("version")}
    for m in get("/api/tags").get("models", []):
        if m["name"] == model:
            info.update({"quantization": m["details"].get("quantization_level"),
                         "digest": m.get("digest", "")[:16]})
    return info


CALLERS = {
    "anthropic": call_anthropic,
    "openai": call_openai,
    "nvidia": call_nvidia,
    "openrouter": call_openrouter,
    "ollama": call_ollama,
}


def _fmt_tokens(n: int | None) -> str:
    return f"{n:,}" if n is not None else "n/a"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--db-dir", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--provider", choices=list(CALLERS), required=True,
                    help="anthropic | openai | nvidia | openrouter | ollama")
    ap.add_argument("--model", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--resume", action="store_true",
                    help="Skip questions already answered in the output file (retry errors only)")
    ap.add_argument("--ollama-host", default="http://localhost:11434",
                    help="Ollama server URL (default: http://localhost:11434)")
    ap.add_argument("--seed", type=int, default=None,
                    help="ollama/openrouter: send this seed (default: none sent)")
    ap.add_argument("--pin", default=None,
                    help="openrouter: pin this endpoint tag, no fallback (e.g. deepinfra/fp8)")
    ap.add_argument("--think", choices=["default", "on", "off"], default="default",
                    help="reasoning: 'default' sends nothing (the runtime decides)")
    args = ap.parse_args()
    global GEN_SEED, GEN_PROVIDER, GEN_THINK
    if args.provider not in ("ollama", "openrouter") and (args.seed is not None or args.pin or args.think != "default"):
        ap.error("--seed, --pin and --think apply to ollama and openrouter only")
    if args.pin and args.provider != "openrouter":
        ap.error("--pin applies to openrouter only")
    GEN_SEED = args.seed
    GEN_PROVIDER = args.pin
    GEN_THINK = None if args.think == "default" else args.think == "on"

    # Stamped on every answer line: an answer whose condition cannot be read back
    # cannot be compared with another one (PROTOCOL_v0.4.md, Stage 0).
    generation_config: dict = {
        "provider": args.provider,
        "model": args.model,
        "system_prompt_sha256": __import__("hashlib").sha256(SYSTEM_PROMPT.encode("utf-8")).hexdigest()[:16],
        "row_cap": 200,
        "temperature": 0,
        "seed": GEN_SEED,
        "think": args.think,
        "provider_requested": GEN_PROVIDER,
    }
    if args.provider == "ollama":
        generation_config.update({"host": args.ollama_host, **ollama_model_info(args.model, args.ollama_host)})

    dataset = [json.loads(l) for l in Path(args.dataset).open(encoding="utf-8") if l.strip()]
    if args.limit:
        dataset = dataset[: args.limit]

    # --resume: load already-answered IDs from existing output file
    done_ids: set[str] = set()
    out_path = Path(args.output)
    if args.resume and out_path.exists():
        for line in out_path.open(encoding="utf-8"):
            if line.strip():
                done_ids.add(json.loads(line)["id"])
        print(f"Resume: {len(done_ids)} already answered, {len(dataset) - len(done_ids)} remaining.")

    db_dir = Path(args.db_dir)
    caller = CALLERS[args.provider]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out = out_path.open("a" if args.resume else "w", encoding="utf-8")

    n_ok = n_err = 0
    total_in: int = 0
    total_out: int = 0
    total_cost: float = 0.0
    tokens_known = False

    for i, q in enumerate(dataset, 1):
        qid = q["id"]
        if qid in done_ids:
            print(f"[{i}/{len(dataset)}] {qid}: skipped (already done)")
            continue
        db_path = db_dir / f"{q['database']}.sqlite"
        if not db_path.exists():
            print(f"[{i}/{len(dataset)}] {qid}: missing DB {db_path}", file=sys.stderr)
            n_err += 1
            continue
        try:
            cols, rows = execute_sql(db_path, q["gold_sql"])
            user = build_user_prompt(q["question"], q["gold_sql"], cols, rows)
            LAST_CALL.clear()
            t0 = time.time()
            if args.provider == "ollama":
                answer, in_tok, out_tok = caller(SYSTEM_PROMPT, user, args.model, host=args.ollama_host)
            else:
                answer, in_tok, out_tok = caller(SYSTEM_PROMPT, user, args.model)
            dt = round(time.time() - t0, 2)

            cost = None
            if in_tok is not None and out_tok is not None:
                tokens_known = True
                total_in += in_tok
                total_out += out_tok
                cost = LAST_CALL.get("cost_usd")
                if cost is None:
                    cost = estimate_cost(args.provider, args.model, in_tok, out_tok)
                if cost is not None:
                    total_cost += cost

            tok_info = f"  [{_fmt_tokens(in_tok)} in / {_fmt_tokens(out_tok)} out | {format_cost(cost)}]" if in_tok is not None else ""
            print(f"[{i}/{len(dataset)}] {qid}: ok ({dt}s){tok_info}")

            out.write(json.dumps({
                "id": qid,
                "model": args.model,
                "provider": args.provider,
                "model_answer": answer.strip(),
                "duration_seconds": dt,
                "input_tokens": in_tok,
                "output_tokens": out_tok,
                "cost_usd": cost,
                "generation_config": {**generation_config, "batch_position": i},
                "generation_served": dict(LAST_CALL),
            }, ensure_ascii=False) + "\n")
            out.flush()
            n_ok += 1
        except Exception as e:
            n_err += 1
            print(f"[{i}/{len(dataset)}] {qid}: ERROR — {e}", file=sys.stderr)
            time.sleep(2)

    out.close()

    # Summary
    print(f"\nDone. {n_ok} answered, {n_err} errors. Output: {args.output}")
    if tokens_known:
        total_tok = total_in + total_out
        cost_display = format_cost(total_cost if total_cost > 0 else estimate_cost(args.provider, args.model, total_in, total_out))
        print(f"Tokens: {total_in:,} in / {total_out:,} out (total: {total_tok:,})")
        print(f"Est. cost: {cost_display}")

    return 0 if n_err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
