"""GBAG v0.6 — the sealed test (PROTOCOL_v0.6_JUDGE.md): run every judge, print NO verdict.

The arbitration of the test set must be blind to judge outputs (PROTOCOL_v0.4.md D9). This
script runs the judges while the arbitration is drafted, so it writes their outputs to
files and prints only progress counters. Nothing here reads a score.

  * v0.6.0-jev (frozen, Jev via OpenRouter, no cache): 5 passes — criterion 4;
  * v0.6.0-lex (frozen, no model): 5 passes;
  * J2 deepseek-v4.1-flash (hosted, v0.4 configuration): 5 ordered passes + isolated pass;
  * J6 gemma4:31b (local, v0.4 configuration): only with --j6, when the GPU box is up.

Usage (repo root):
    python scripts/campaign_v06_test.py            # cloud judges
    set OLLAMA_HOST=http://<your-ollama-host>:11434
    python scripts/campaign_v06_test.py --j6       # J6 alone, later
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import campaign_v05_test as c5  # the v0.4 judge runner (ordered + isolated passes), unchanged

ROOT = Path(__file__).resolve().parent.parent
SEALED = ROOT / "data" / "sealed" / "test-v06"
Q, A = SEALED / "questions.jsonl", SEALED / "answers.jsonl"
OUT = ROOT / "runs" / "v0.6" / "test"
PASSES = 5

# point the v0.4 runner at this set
c5.Q, c5.A, c5.OUT, c5.LOG = Q, A, OUT, OUT / "progress.log"
c5.N = c5.n_lines(A)
log, n_lines, quiet, N = c5.log, c5.n_lines, c5.quiet, c5.N


def v06(mode: str) -> None:
    if mode == "jev" and os.environ.get("GBAG_V06_NO_CACHE") != "1":
        raise SystemExit("GBAG_V06_NO_CACHE=1 is required for test-set runs (Freeze section)")
    for n in range(1, PASSES + 1):
        out = OUT / f"v06-{mode}-p{n}.jsonl"
        if n_lines(out) >= N:
            continue
        t0 = time.time()
        rc = quiet([sys.executable, "-m", "judge.v06.run_v06", "--dataset", str(Q), "--answers", str(A),
                    "--output", str(out), "--mode", mode], OUT / f"v06-{mode}-stdout.log")
        log(f"v0.6-{mode} pass {n}: {n_lines(out)}/{N} answers written, rc={rc} ({time.time() - t0:.0f}s)")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    if "--j6" in sys.argv:
        log(f"sealed test v06: J6 on {N} answers; OLLAMA_HOST={os.environ.get('OLLAMA_HOST')}")
        c5.v04("J6")
    else:
        log(f"sealed test v06: {N} answers; cloud judges")
        threads = [threading.Thread(target=lambda: (v06("jev"), v06("lex"))),
                   threading.Thread(target=lambda: c5.v04("J2"))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
    log("done — no verdict printed; outputs stay unread until the arbitration is committed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
