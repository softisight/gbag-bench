"""Offline tests of the seed trial (D21). No model is called: the box is a fake local
server. Run (repo root):  python scripts/test_seed_trial_v07.py"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import reader_v07 as rv
import seed_trial_v07 as st

SEEN = []


class Fake(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        data = json.dumps({"response": "Some prose.\n\nFINAL_ANSWER\nvalue: NONE", "prompt_eval_count": 3000,
                           "eval_count": 40}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def main() -> int:
    bad = []
    check = lambda ok, what: None if ok else bad.append(what)

    # the targets of the new seed: the same ids as the published ones, other truths
    new, old = st.targets(), rv.load_targets()
    check(len(new) == 16 and set(new) == {tid for tid, t in old.items() if t["qid"] in st.QUESTIONS}, "the 16 targets")
    check(all(t["database"] == st.NAME and t["n_rows"] > st.ROW_CAP for t in new.values()), "database, or a result that is not cut")
    check(all((t["ask"], t["type"], t["op"]) == (old[k]["ask"], old[k]["type"], old[k]["op"]) for k, t in new.items()), "ask, type or op")
    check(sum(t["truth_shown"] != old[k]["truth_shown"] for k, t in new.items()) >= 10, "the numbers did not change")
    check(all(t["kind"] == "control" for t in new.values() if t["op"] == ["count"]), "the header rule (D18)")

    # the prompts: arm B of v0.7, on the rows of the new database
    items = st.prompts()
    check(len(items) == 16, "16 prompts")
    for t, p in items:
        check(f"RESULT (first 200 of {t['n_rows']} rows shown)" in p, f"{t['tid']}: header")
        check(p.rstrip().endswith("Write the answer now.") and "FINAL_ANSWER" in p and "scope:" not in p, f"{t['tid']}: block of arm B")
        check(t["ask"] in p, f"{t['tid']}: value asked")

    # the reading of the result, fixed before the run
    check(st.verdict(40, 44).startswith("the behaviour follows the question"), "40/44")
    check(st.verdict(33, 44).startswith("the behaviour follows the numbers"), "33/44")
    check(st.verdict(36, 44).startswith("between"), "36/44")

    # a round trip through a fake box, in a folder of its own
    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{server.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        st.ANSWERS, st.READ = Path(tmp) / "answers", Path(tmp) / "read.jsonl"
        st.generate(["fake:1b"])
        rows = rv.jsonl(st.ANSWERS / "fake_1b-B-r1.jsonl")
        check(len(rows) == 16 and all(r["seed"] == st.SEED and r["arm"] == "B" and not r["error"] for r in rows), "16 answers written")
        check(all(b["think"] is False and b["options"] == {"temperature": 0, "num_ctx": 16384} for b in SEEN), "reasoning, temperature or window")
        st.generate(["fake:1b"])
        check(len(rv.jsonl(st.ANSWERS / "fake_1b-B-r1.jsonl")) == 16 and len(SEEN) == 16, "an answer was generated twice")
        out = st.outcomes(st.answers(), new, {})
        check({v[1] for k, v in out.items() if v[0] != "control"} == {"safe"}
              and {v[1] for k, v in out.items() if v[0] == "control"} == {"broken"}, "a decline: safe, or broken on a control")
    server.shutdown()

    for b in bad:
        print("FAIL", b)
    print("all checks pass" if not bad else f"{len(bad)} checks fail")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
