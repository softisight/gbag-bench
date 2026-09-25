"""GBAG v0.5 — the sealed test (PROTOCOL_v0.5_JUDGE.md): run every judge, print NO verdict.

The arbitration of the test set must be blind to judge outputs (PROTOCOL_v0.4.md D9, D12).
This script runs the judges while the arbitration is drafted, so it writes their outputs
to files and prints only progress counters. Nothing here reads a score.

  * v0.5.0 (frozen, local qwen3.8:27b, no cache): 5 passes — criterion 4 (identical verdicts);
  * J6 gemma4:31b (best v0.4 judge on the reserve): 5 ordered passes + isolated pass;
  * J2 deepseek-v4.1-flash (hosted reference): 5 ordered passes + isolated pass.
Local judges run one after the other on the GPU; J2 runs alongside.

Usage (repo root):
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/campaign_v05_test.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from campaign_v04_stage1 import CONFIGS, PROMPT  # the v0.4 configurations, unchanged

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "data" / "sealed" / "test-v05"
Q, A = SEALED / "questions.jsonl", SEALED / "answers.jsonl"
OUT = ROOT / "runs" / "v0.5" / "test"
LOG = OUT / "progress.log"
PASSES = 5
_lock = threading.Lock()


def log(msg: str) -> None:
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    with _lock:
        print(line, flush=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def n_lines(p: Path) -> int:
    return sum(1 for l in p.read_text(encoding="utf-8").splitlines() if l.strip()) if p.exists() else 0


N = n_lines(A)


def quiet(cmd: list[str], out_log: Path) -> int:
    """Run a judge with its stdout (which carries verdicts) sent to a file nobody reads yet."""
    with out_log.open("a", encoding="utf-8") as f:
        return subprocess.run(cmd, stdout=f, stderr=f, cwd=ROOT,
                              env={**os.environ, "PYTHONIOENCODING": "utf-8"}).returncode


def v05() -> None:
    env_ok = os.environ.get("GBAG_V05_NO_CACHE") == "1"
    if not env_ok:
        raise SystemExit("GBAG_V05_NO_CACHE=1 is required for test-set runs (Freeze section)")
    for n in range(1, PASSES + 1):
        out = OUT / f"v05-p{n}.jsonl"
        if n_lines(out) >= N:
            continue
        t0 = time.time()
        rc = quiet([sys.executable, "-m", "judge.v05.run_v05", "--dataset", str(Q), "--answers", str(A),
                    "--output", str(out), "--backend", "ollama", "--model", "qwen3.8:27b"],
                   OUT / "v05-stdout.log")
        log(f"v0.5 pass {n}: {n_lines(out)}/{N} answers written, rc={rc} ({time.time() - t0:.0f}s)")


def v04(cfg: str) -> None:
    args, _, _ = CONFIGS[cfg]
    base = [sys.executable, str(ROOT / "judge" / "run_judge.py"), "--prompt", str(PROMPT), *args]
    for n in range(1, PASSES + 1):
        out = OUT / f"{cfg}-p{n}.jsonl"
        if n_lines(out) >= N:
            continue
        if out.exists():
            out.unlink()
        t0 = time.time()
        rc = quiet(base + ["--dataset", str(Q), "--answers", str(A), "--output", str(out)],
                   OUT / f"{cfg}-stdout.log")
        log(f"{cfg} pass {n}: {n_lines(out)}/{N} scored, rc={rc} ({time.time() - t0:.0f}s)")
    iso = OUT / f"{cfg}-iso.jsonl"
    qs = {json.loads(l)["id"]: l for l in Q.read_text(encoding="utf-8").splitlines() if l.strip()}
    done = {json.loads(l)["id"] for l in iso.read_text(encoding="utf-8").splitlines() if l.strip()} if iso.exists() else set()
    for line in A.read_text(encoding="utf-8").splitlines():
        if not line.strip() or json.loads(line)["id"] in done:
            continue
        with tempfile.TemporaryDirectory() as td:
            dq, da, do = Path(td) / "q.jsonl", Path(td) / "a.jsonl", Path(td) / "o.jsonl"
            dq.write_text(qs[json.loads(line)["id"]] + "\n", encoding="utf-8")
            da.write_text(line + "\n", encoding="utf-8")
            quiet(base + ["--dataset", str(dq), "--answers", str(da), "--output", str(do)],
                  OUT / f"{cfg}-stdout.log")
            if do.exists():
                with iso.open("a", encoding="utf-8") as f:
                    f.write(do.read_text(encoding="utf-8"))
    log(f"{cfg} isolated: {n_lines(iso)}/{N}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    log(f"sealed test: {N} answers; OLLAMA_HOST={os.environ.get('OLLAMA_HOST')}")
    local = threading.Thread(target=lambda: (v05(), v04("J6")))
    hosted = threading.Thread(target=lambda: v04("J2"))
    local.start()
    hosted.start()
    local.join()
    hosted.join()
    log("done — no verdict printed; outputs stay unread until the arbitration is committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
