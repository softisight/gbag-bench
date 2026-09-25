"""Step 2 — the one question asked of a model: translate a sentence into fact sheets.

The model is never asked whether a claim is true, and never sees the data beyond column
names and two example values. Temperature 0, seed 42, reasoning off, and the output is
constrained by the JSON schema of sheet.py.

Backends: `ollama` (the judge as it will be frozen: local) and `openrouter` (development
only, while the local GPU is busy — PROTOCOL_v0.5_JUDGE.md, deviations).
"""
from __future__ import annotations

import hashlib
import json
import os

from .sheet import Sheet, schema_for

PROMPT = """You translate ONE sentence from an answer about a SQL query result into fact sheets.
You never decide whether a claim is true. You only record what the sentence asserts.

For each factual assertion about the data in the sentence (at most 4), fill one sheet:

span: the exact words of the sentence that carry the assertion, copied verbatim.
scope:
  rows_shown     - the sentence limits itself to the rows shown/displayed/returned/visible,
                   or to "the table above", "the result shown", "the rows I have".
  all_data       - any other factual assertion: about the data, the ledger, the dataset,
                   the account, the period, or a plain fact stated without such a limit.
  interpretation - an opinion, hypothesis, recommendation or explanation with no figure.
type (pick one):
  total      - a sum or the final value of a running total. value = the stated figure.
  count      - a number of rows or items. value = the count; filter_* narrows the rows
               (e.g. filter_column=document_number, filter_op=startswith, filter_value=VAT-).
  extreme    - a maximum or minimum. which=max|min; value = the stated extreme (if any);
               at = the date/label where it occurs (if stated).
  end_value  - where the data starts or ends. which=first|last; value = stated value;
               at = stated date/label. "ends at X on D" -> which=last, value=X, at=D.
  share      - a proportion of rows in a range: low/high = the range as written;
               quantifier = all|almost_all|most|majority|half|few|none, or value = "N%".
  ratio      - "N times", "Nx", "twice": value = the stated ratio ("7x", "twice" -> "2x"
               only if written); reference = second_max|median|mean|min|value, and
               reference_value if a figure is named.
  universal  - every/none of the rows satisfy a comparison: op, value, quantifier=all|none.
  trend      - a direction over the rows' order: direction = up|down|flat.
  other      - a factual assertion none of the above can express.
column: REQUIRED. The result column the assertion is about, chosen from the list ("none"
  only for a count of rows or an interpretation). A debit figure -> the debit column; a
  running total -> the running/cumulative column; a date -> the date column.
value: REQUIRED. The figure the assertion states, copied exactly ("" only if it states none).
answers_question: true if the assertion gives (part of) what the question asks for.
Copy every figure, date and label EXACTLY as written in the sentence (value, at, low, high,
reference_value). Leave a field null when the sentence does not state it.
If the sentence asserts nothing about the data, return {"claims": []}.
"""

PROMPT_SHA = hashlib.sha256(PROMPT.encode("utf-8")).hexdigest()[:16]


def user_message(question: str, columns: str, context: str, sentence: str) -> str:
    return (f"QUESTION:\n{question}\n\nRESULT COLUMNS:\n{columns}\n\n"
            f"PREVIOUS SENTENCE (context only, do not translate):\n{context or '(none)'}\n\n"
            f"SENTENCE TO TRANSLATE:\n{sentence}\n")


def call(backend: str, model: str, user: str, columns: list[str] | None = None) -> tuple[list[dict], dict]:
    """(raw sheet dicts, call metadata)."""
    import requests
    schema = schema_for(columns or [])
    if backend == "ollama":
        host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        payload = {"model": model, "system": PROMPT, "prompt": user, "stream": False,
                   "format": schema, "think": False,
                   "options": {"temperature": 0, "seed": 42, "num_ctx": 8192, "num_predict": 1200}}
        r = requests.post(f"{host}/api/generate", json=payload, timeout=900)
        r.raise_for_status()
        data = r.json()
        text = data.get("response", "")
        meta = {"in": data.get("prompt_eval_count"), "out": data.get("eval_count")}
    elif backend == "openrouter":
        body = {"model": model, "temperature": 0, "seed": 42, "max_tokens": 1200,
                "messages": [{"role": "system", "content": PROMPT}, {"role": "user", "content": user}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "sheets", "strict": False, "schema": schema}},
                "reasoning": {"enabled": False}, "usage": {"include": True}}
        pin = os.environ.get("GBAG_V05_PROVIDER")
        if pin:
            body["provider"] = {"order": [pin], "allow_fallbacks": False}
        data = None
        for attempt in range(3):          # transport retries only: same request, same body
            try:
                r = requests.post("https://openrouter.ai/api/v1/chat/completions",
                                  headers={"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}"},
                                  json=body, timeout=60)
                data = r.json()
                break
            except (requests.RequestException, ValueError):
                if attempt == 2:
                    raise
        if "error" in data:
            raise RuntimeError(f"OpenRouter: {data['error'].get('message', data['error'])}")
        text = data["choices"][0]["message"].get("content") or ""
        u = data.get("usage") or {}
        meta = {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens"),
                "cost": u.get("cost"), "provider": data.get("provider")}
    else:
        raise ValueError(backend)
    # A sheet list fits in a few hundred tokens: an output that hits the cap is a
    # degenerate loop, and is treated as unparseable (every claim of the sentence undecided).
    try:
        parsed = json.loads(text.strip().strip("`").removeprefix("json"))
    except json.JSONDecodeError:
        return [], {**meta, "unparseable": text[:300]}
    return list(parsed.get("claims") or []), meta


def translate(backend: str, model: str, question: str, columns: str, context: str,
              sentence: str, column_names: list[str] | None = None) -> tuple[list[Sheet], dict]:
    raw, meta = call(backend, model, user_message(question, columns, context, sentence), column_names)
    return [Sheet.from_dict(d) for d in raw if isinstance(d, dict)], meta
