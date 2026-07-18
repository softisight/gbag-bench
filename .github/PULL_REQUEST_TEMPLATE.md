<!--
Thanks for contributing to GBAG-Bench.

Fill in the section that matches your PR type and delete the others.
-->

## PR type

- [ ] New model result (leaderboard entry)
- [ ] Dataset fix or addition
- [ ] Metric / judge change (must reference a prior discussion Issue)
- [ ] Documentation / tooling

---

## New model result

**Model**: `<exact-model-id>` (e.g. `claude-sonnet-4-6`, `qwen3.5:9b`)

**Provider**: <Anthropic / OpenAI / Ollama / other>

**Hardware**: <e.g. RTX 3060 12GB local, or API cloud>

**Judge**: <Anthropic / OpenAI / DeepSeek / other> — `<judge-model-id>`

**Coverage**: <X> / 35 questions answered

**Reported scores**:
- GBAG: <number>
- Faithfulness: <number>
- Completeness: <number>
- Insight: <number>

**Run files committed**:
- [ ] `runs/<model-id>.jsonl` (raw model answers)
- [ ] `runs/<model-id>.scored.jsonl` (judge scores)
- [ ] `LEADERBOARD.md` updated with my row

**Verification statement**:
- [ ] I ran the official `baseline_runner.py` and `run_judge.py` without modifications
- [ ] I did not use the model under test as its own judge
- [ ] I understand that maintainers may re-run the judge to verify my scores

---

## Dataset fix

**Question id(s) affected**: `<sakila-l3-01>` etc.

**What is wrong**: <e.g. gold_answer reports 5,314 but actual SQL returns 5,315>

**Fix**:
<short description of the change>

**Linked Issue**: #<issue-number>

---

## Metric / judge change

**Linked Issue**: #<issue-number> (required — metric changes must be discussed before PR)

**Summary**: <what changes and why>

---

## Anything else?

<context, screenshots, log snippets, etc.>
