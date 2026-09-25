# GBAG v0.4 — campaign protocol (pre-registered)

**Status: pre-registration.** This file is committed before the first call of the v0.4
campaign. The commit that adds it is the timestamp. Everything below — judge prompt, cases,
configurations, number of passes, metrics, acceptance thresholds, model list, reporting
rules — is fixed from that commit on.

Anything that changes after that point is logged in [Deviations](#deviations), with the
date, the reason, and the results it could affect. A deviation is allowed, but never silent.

Why pre-register a benchmark this small: the last campaign showed that the judge moves
scores as much as the model does. A protocol written after seeing the numbers would be one
more degree of freedom, and it would be ours.

---

## 1. What this campaign answers

1. **Can a new judge be trusted?** Two candidates: `deepseek-v4.1-flash` (hosted, cheap)
   and `qwen3.8-27b` (open weights, runs locally), measured against the current reference
   `gemma4:31b`.
2. **Is the instability of hosted judges a property of hosting, or of how we called them?**
   [JUDGE_VALIDATION.md](JUDGE_VALIDATION.md) attributes it to the fact that "on a hosted
   API [the seed] cannot" be pinned. Our own hosted callers never sent a seed, and never
   pinned a provider. That explanation is a hypothesis, and this campaign tests it.
3. **Does the rule generalise?** The seven truth-set cases are the ones the rule was written
   against. The 15-case reserve was not seen by it.
4. **Where do current models stand?** The held-out table is scored by a judge and a
   prompt the repository has since shown to be unreliable, and its models date from
   June–July 2026.
5. **Is the held-out suite still held out?** The ledger was published in July 2026. Models
   released after that date may have seen it.

## 2. Frozen inputs

| what | file | SHA-256 |
|---|---|---|
| judge prompt v0.4.1 | `judge/prompt-v041.md` | `db70b3a51aa059b89afcbcf1d4269970490ca97d26bfe4ffddbca7b87259e708` |
| truth set (7 arbitrated cases) | `data/judge-truth-set.jsonl` | `6309cc3fc02dd892b55041f78683c800124460c338531c079a1cae133c223724` |
| truth-set questions | `runs/judge-calibration/t7-q.jsonl` | `c7b4d31c070fdc4d0d1e90af2e5a79c13e82622f4bc0eaee569b66b7123489f8` |
| truth-set answers | `runs/judge-calibration/t7-a.jsonl` | `4512daff3a132695070b655070131ecf6b7a6b2e8e88460e4e9a649e66a18475` |
| reserve questions | `data/questions-reserve.jsonl` | `139f92b7c3af223b7acbb8f9c986995befbb5cb53546124684c1aee6e3e663c1` |
| reserve answers | `data/answers-reserve.jsonl` | `373e809fe0a9bf746c5543de40ba30faff758f86d515433d32ce42562a5f9c4b` |
| public suite (35) | `data/questions.jsonl` | `6e22263744f60fc69ff1ceb4f937966a97abbd4186c1fe38adf2601853a437f6` |
| held-out, level 2 (15) | `data/questions-heldout.jsonl` | `eb591a8d921aa9c0b5efcd0078b6df113cae79a434e6dc400fffb40cae0b93ab` |
| held-out, level 1 (10) | `data/questions-heldout-level1.jsonl` | `113ef182496b35602c084d031005b124d2973fe802e2b394fe5f52b6d9f52d6b` |
| ledger database, seed 20260718 | `databases/ledger.sqlite` | `93a4407485122ea764fd5963af8bfd115ecbf4aa533cdf7365cee96fa50ad7e5` |
| ledger generator | `scripts/generate_ledger.py` | `05e712e31d2e1921dff4224a1b7e9bba7fd218579d398324a49e33949a7baeab` |
| answer runner (neutral prompt) | `examples/baseline_runner.py` | `fe3743c4100a6a7e3f434e6c0640f00e20a411e632d22fa7a350d5988d40bd47` |

Also fixed:

- **The GBAG formula** is unchanged: `0.50 × F + 0.30 × C + 0.20 × I`.
- **The row cap** stays at 200 rows shown to the answering model.
- **The answer prompt** is the neutral system prompt of `baseline_runner.py`, unchanged.
- **The judge prompt is not edited during the campaign.** If a judge fails under v0.4.1, it
  fails, and that is the result.

## 3. Stage 0 — tooling (before any measured call)

Only the changes listed here are allowed. Each one is a separate commit, made before the
first measured call.

1. **Hosted judge callers send what they claim.** `call_openrouter` gains:
   - `seed`, optional, sent only when the configuration says so;
   - provider pinning (`provider.order` plus `allow_fallbacks: false`);
   - reasoning off (`reasoning: {enabled: false}`), matching the local judges
     (`think: false`).
2. **Every scored line records its execution condition, hosted included.** Today
   `judge_config` is written for Ollama only. It gains, for every backend:
   - the backend, model, seed (or `null`), and the requested provider;
   - **the provider that actually served the call**, as returned by the API — the
     requested one is not proof;
   - the quantization when the API reports it, and the reasoning setting.
3. **The ledger seed becomes a parameter** of `generate_ledger.py` (default unchanged,
   `20260718`). Regenerating with the default must reproduce the frozen SHA-256 above
   byte for byte, or the change is reverted.
4. **Answer runs record their generation condition** in the same way (seed, provider,
   quantization, reasoning setting).

Nothing in Stage 0 touches the prompt, the formula, the cases, or any scoring logic.

## 4. Stage 1 — judge qualification on the truth set

### Configurations

| id | judge | where | seed | provider | role |
|---|---|---|---|---|---|
| J1 | `deepseek/deepseek-v4.1-flash` | OpenRouter | none | pinned: DeepSeek | the old hosted condition |
| J2 | `deepseek/deepseek-v4.1-flash` | OpenRouter | 42 | pinned: DeepInfra (fp8) | does a pinned seed stabilise a hosted judge? |
| J3 | `deepseek/deepseek-v4.1-flash` | OpenRouter | 42 | default routing | what a reproducer gets without pinning |
| J4 | `qwen3.8:27b` | Ollama, local | 42 | — | local candidate |
| J5 | `qwen/qwen3.8-27b` | OpenRouter | 42 | pinned (see below) | same weights as J4, hosted |
| J6 | `gemma4:31b` | Ollama, local | 42 | — | control: must reproduce its published 7/7 |
| J7 | `deepseek/deepseek-v4.1-flash` | OpenRouter | 42 | pinned: DeepInfra (fp8) | secondary: same as J2 with **reasoning on** |

For J1, the DeepSeek endpoint does not accept a seed: that is why it reproduces the old
condition.

**Quantization for J4/J5.** The local host runs the highest quantization of `qwen3.8:27b`
that fits entirely in its VRAM (measured and recorded before the run). J5 is pinned to the
hosted provider closest to that precision:
- local `q8_0` pairs with an fp8 provider (Parasail);
- local `q4_K_M` pairs with an fp4 provider (Darkbloom).

If the two precisions differ, J4 against J5 is reported as a comparison of **stability
only**, not of accuracy.

**Local host:** the machine that ran the published qwen3.6 judge (`judge_config.host` in
`t7-qwen36-v041.jsonl`), with `num_ctx` 16384. Its GPU, driver and Ollama version are
recorded with the results.

### Passes

- J1–J6: **5 passes** over the 7 cases, in the fixed file order, one process per pass.
- Plus **1 isolated pass**: each case alone, one process per case (cold first call). This
  measures the batch-position effect instead of hiding it.
- J7: 3 passes, secondary.

### Metrics (definitions identical to JUDGE_VALIDATION.md)

- **Accuracy per pass.** A case is correct if the judge's faithfulness score falls in the
  arbitrated band: `≤ 40` for the six unfaithful cases, `100` for the acquitted one.
- **Score.** The mean of per-pass correct counts, out of 7.
- **Self-contradiction.** A case whose correctness differs between two passes of the same
  configuration.

Also reported:
- the spread of the faithfulness score per case (min, max, standard deviation);
- unparseable judge outputs;
- tokens, cost and latency;
- position flips: the isolated pass against the ordered passes.

### Acceptance — a judge is *qualified* if, and only if

1. its score is ≥ 6/7;
2. it has **0 self-contradictions** across its 5 ordered passes;
3. at most 1 case changes verdict between the isolated and the ordered passes;
4. once Stage 2 is arbitrated, its reserve accuracy is ≥ that of `gemma4:31b` (J6).

A judge that misses any criterion is published as **not qualified**, with its numbers.

If J6 does not reproduce 7/7 with 0 contradictions, the campaign stops and the cause is
investigated before anything else is run. A drifting control invalidates every comparison.

## 5. Stage 2 — the reserve (generalisation)

The 15 reserve cases: 8 `giant`, 4 `l1_36`, 3 `l1_small`
(`data/verdicts-reserve.template.jsonl`).

1. **We prepare the worksheet**: for each case, the contested claim, a `proof_sql`, and
   its result on the frozen database.
2. **The arbiter is not the author of the rule.** Primary arbiter: Zaki. A community
   volunteer may arbitrate as a second, independent arbiter.
3. **The arbitration is blind.** It is done without seeing any judge output on the
   reserve, and committed before reserve judge scores are read.
4. Where two arbiters disagree, the case is reported as disputed and excluded from
   accuracy, not settled by us.
5. Then J2, J4, J5 and J6 run on the reserve: 5 ordered passes plus 1 isolated pass, same
   metrics as Stage 1.

Until the arbitration is committed, reserve results are reported as **inter-judge
agreement only**, and labelled as such.

## 6. Stage 3 — the model campaign

### Suites

| suite | content | what is run |
|---|---|---|
| **HO-A** | held-out ledger, original seed `20260718` (frozen above), levels 1 and 2 | re-judge the 7 existing answer sets, and generate + judge the new models |
| **HO-B** | held-out ledger **re-rolled with seed `20260925`** — same schema, same questions and SQL, new numbers | generate + judge every model |
| **PUB** | public suite, 35 questions | re-judge the existing answer sets behind the v0.2 table; no new generation |

**HO-B construction.**
- `generate_ledger.py --seed 20260925`, then `build_heldout_dataset.py` and
  `build_verification_facts.py` against the new database.
- Every gold SQL is checked for a non-degenerate result.
- The l9/l10 tier must still exceed 200 rows.
- A question that degenerates under the new seed is **reported, not replaced**.
- HO-B is not published until every model in this campaign has answered it.

**Contamination signal.** Each model's GBAG on HO-B minus HO-A. Models released before and
after July 2026 are compared as two groups. The expected drop for an uncontaminated model
is zero, within the instrument's resolution.

### Models

- **Existing held-out models** (answers on HO-A already exist, re-judged only):
  `claude-fable-5`, `gpt-5.6-sol`, `kimi-k3`, `qwen3-coder-480b`, `qwen3.6`,
  `nemotron-3-nano-30b`, `gemma4-12b`.
- **New models:**
  - `deepseek/deepseek-v4.1-flash` — hosted, pinned provider;
  - `qwen/qwen3.8-flash` — hosted, pinned provider;
  - `qwen3.8:27b` — local;
  - `nemotron-3.5-lightning:30b-a3b` — local; successor of `nemotron-3-nano-30b`, same
    lineage;
  - `gpt-oss:20b` — local, the most common local baseline.
- All 12 models answer HO-B.

### Generation

- `baseline_runner.py`, unchanged prompt, 200-row cap.
- Temperature 0, seed 42 where accepted, reasoning off (`think: false` locally).
- One answer per question.
- Local models run at `q4_K_M` unless recorded otherwise.

### Scoring

- **Every answer set is scored by two judges**, both under prompt v0.4.1:
  - `gemma4:31b` (J6 condition);
  - the best qualified judge from Stages 1–2.
- If no new judge qualifies, the second judge is `qwen3.6` (published 6/7, 0
  contradictions), and that is stated.
- One ordered pass, in file order. The batch order is recorded, so any score can be
  replayed exactly.
- `scripts/check_numeric_grounding.py` produces a **separate numeric-grounding column**.
  It is published next to the GBAG score, and **never merged into it**.

### Reporting rules

- **Both judges' scores are published side by side.** A model is ranked above another only
  where both judges agree on the order.
- **Resolution is 2 points.** Gaps under 2 points are ties, and are printed as such.
- **Tables from different judge prompts or protocol versions are never merged.** The v0.2
  grok-4.3 tables are kept as an archive, labelled with their judge and prompt.
- **Coverage is printed on every row.** An unanswered question is shown, never silently
  averaged away.
- **Negative results are published**: an unqualified judge, a contamination drop, a
  control that drifts.

## 7. Stage 4 — the pipeline row, made reproducible

The v0.2 headline row ("+ DeskInsight pipeline", +7 to +17 points) was produced by a
commercial Delphi build nobody else can run. It is re-measured with **DeskInsight v2,
Essential edition** — the free build — so that anyone can reproduce it.

- **Setup:** `qwen3.5:9b` on the same class of consumer GPU, on PUB and HO-A.
- **Recorded:** the app version and the SHA-256 of the executable.
- **Judged** by the same two judges as Stage 3.
- **Labelled** as a system, never ranked among bare models.

This stage runs once the Essential build is final. Its results are published with that
release.

## 8. Budget and stopping

- **Estimated cloud cost:** under 5 USD. **Hard cap: 15 USD.**
- The runner stops at the cap, and the overrun is logged as a deviation.
- Local GPU time is not capped, but it is recorded.

## 9. Publication

When Stages 1–3 are complete:

1. `JUDGE_VALIDATION.md`, `README.md`, `LEADERBOARD.md` and `HUGGINGFACE_README.md` are
   rewritten from the measured numbers.
2. v0.4 runs live under `runs/v0.4/`, with an index file mapping every table cell to its
   file.
3. Older runs move under `runs/v0.2/` and `runs/v0.3/`, unchanged.

Each claim in the rewritten documents cites the file it comes from.

## Deviations

*None yet. Format: date — what changed — why — which results it can affect.*
