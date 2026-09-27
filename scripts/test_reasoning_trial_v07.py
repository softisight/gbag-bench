"""Offline tests of the reasoning trial (D23) and of the count of reasoning (D22). No model
is called: the box is a fake local server. Run (repo root):  python scripts/test_reasoning_trial_v07.py"""
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
import reasoning_trial_v07 as rt
import reasoning_v07 as rs

SEEN = []
LOOPS = {"cap"}             # the settings with which the fake model loops: set by the tests


class Fake(BaseHTTPRequestHandler):
    """Loops (empty answer, cut at the cap) when reasoning is on with a setting of LOOPS."""
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        name = next(s["name"] for s in rt.SETTINGS if s["options"] == body["options"])
        loop = body["think"] and name in LOOPS
        reply = {"response": "" if loop else "Some prose.\n\nFINAL_ANSWER\nvalue: NONE",
                 "thinking": "x" * (9000 if loop else 300 if body["think"] else 0),
                 "done_reason": "length" if loop else "stop", "prompt_eval_count": 3000, "eval_count": 4096 if loop else 60}
        data = json.dumps(reply).encode("utf-8")
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
    targets = rv.load_targets()

    # D22: the count of reasoning
    check(rs.used({"reasoning_tokens": 12}) == 12 and rs.used({"served": {"think": False}}) == 0 and rs.used({}) is None, "used")
    t = rs.table()
    check(all(v == 0 for v in t["qwen/qwen3-coder"]["trap"] + t["qwen/qwen3-coder"]["control"]), "qwen3-coder reasoned")
    for m in ("openai/gpt-5.6-sol", "anthropic/claude-fable-5", "moonshotai/kimi-k3"):
        check(all(v > 0 for v in t[m]["trap"]), f"{m}: a trap target without reasoning")
    check(all(v == 0 for m in ("gemma4_12b", "gemma4_31b") for k in t[m].values() for v in k), "a local answer reasoned")

    # D23: the two sets of targets do not meet
    tune, run = rt.tuning_targets(), rt.run_targets()
    check(len(tune) == 10 and len(run) == 41 and not set(tune) & set(run), f"{len(tune)} tuning targets, {len(run)} run targets")
    check(all(targets[x]["kind"] == "control" and targets[x]["n_rows"] <= rt.ROW_CAP for x in tune), "a tuning target is cut")
    check(sum(targets[x]["kind"] != "control" for x in run) == 34 and sum(targets[x]["kind"] == "control" for x in run) == 7, "34 and 7")
    check([s["name"] for s in rt.SETTINGS] == ["cap", "cap+penalty", "cap+temperature"], "the order of the settings")
    check(all(s["options"]["num_ctx"] == 16384 and s["options"]["num_predict"] == rt.CAP for s in rt.SETTINGS), "window or cap")
    check(rt.completes("x\n\nFINAL_ANSWER\nvalue: 12", targets[tune[0]]) and not rt.completes("", targets[tune[0]])
          and not rt.completes("no block", targets[tune[0]]), "completes")

    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{server.server_port}"
    with tempfile.TemporaryDirectory() as tmp:
        rt.OUT = Path(tmp)
        rt.ANSWERS, rt.READ = rt.OUT / "answers", rt.OUT / "read.jsonl"

        # nothing tuned: nothing kept, nothing run
        check(rt.kept("fake:1b") is None, "a setting kept before the tuning")
        rt.generate("fake:1b")
        check(not rt.ANSWERS.exists(), "a run without a setting kept")

        # the witness: one call, of the first setting, on a control
        rt.witness("fake:1b")
        check(len(SEEN) == 1 and SEEN[0]["think"] is True and SEEN[0]["options"] == rt.SETTINGS[0]["options"], "the witness call")
        check(rt.kept("fake:1b") is None, "a setting kept on one answer")

        # the first setting loops, the second passes: it is kept, and the third is not tried
        rt.tune("fake:1b")
        rows = rv.jsonl(rt.tuning_file("fake:1b"))
        names = [r["setting"] for r in rows]
        check(names.count("cap") == 10 and names.count("cap+penalty") == 10 and "cap+temperature" not in names, f"tuning calls {len(rows)}")
        check(rt.kept("fake:1b")["name"] == "cap+penalty", "the setting kept")
        check(all(r["tid"] in tune for r in rows), "a cut result was asked during the tuning")
        n = len(SEEN)
        rt.tune("fake:1b")
        check(len(SEEN) == n, "the tuning was run twice")

        # the run: 41 answers with reasoning, the setting kept; reasoning off is not generated again at temperature 0
        rt.generate("fake:1b")
        on = rv.jsonl(rt.ANSWERS / "fake_1b-B-on.jsonl")
        check(len(on) == 41 and {r["tid"] for r in on} == set(run) and all(r["setting"] == "cap+penalty" for r in on), "41 answers")
        check(all(b["think"] is True for b in SEEN[n:]) and not (rt.ANSWERS / "fake_1b-B-off.jsonl").exists(), "reasoning off generated")
        m = len(SEEN)
        rt.generate("fake:1b")
        check(len(SEEN) == m, "an answer was generated twice")

        # a model that loops with the first two settings: the third changes the sampling, so
        # reasoning off is generated again with the same options
        LOOPS.add("cap+penalty")
        rt.tune("fake:2b")
        check(rt.kept("fake:2b")["name"] == "cap+temperature", "the third setting")
        rt.generate("fake:2b")
        off = rv.jsonl(rt.ANSWERS / "fake_2b-B-off.jsonl")
        check(len(off) == 41 and all(r["served"]["think"] is False and r["served"]["options"] == rt.SETTINGS[2]["options"] for r in off),
              "reasoning off, same options")

        # a model that loops with every setting is not run
        LOOPS.add("cap+temperature")
        rt.tune("fake:3b")
        check(rt.kept("fake:3b") is None and len(rv.jsonl(rt.tuning_file("fake:3b"))) == 30, "every setting tried")
        rt.generate("fake:3b")
        check(not (rt.ANSWERS / "fake_3b-B-on.jsonl").exists(), "a model without a setting was run")

        # the reading of the result: declines everywhere on both sides, no rate to compare against
        rows_on = rt.rows_of(on, {})
        check(rt.tv.shares(rows_on, rt.tv.D17)["safe"] == 34 and rt.tv.accuracy(rows_on, rt.tv.D17, True) == (0, 7), "rows of the run")
    server.shutdown()

    # the verdict, on rows written by hand
    q = lambda i: {"kind": "discriminating", "qid": f"q{i}", "tid": f"q{i}#1", "n_rows": 3616}
    row = lambda i, cls: (q(i), cls, cls, cls, {"declined": False, "text_gives_shown": False})
    bad_rows, good_rows = [row(i, "gbag_failure") for i in range(8)], [row(i, "honest") for i in range(8)]
    check(rt.verdict(good_rows, bad_rows).startswith("reasoning lowers"), rt.verdict(good_rows, bad_rows))
    check(rt.verdict(bad_rows, good_rows).startswith("reasoning raises"), rt.verdict(bad_rows, good_rows))
    check(rt.verdict(good_rows, good_rows).startswith("no established effect"), rt.verdict(good_rows, good_rows))
    broken = [row(i, "wrong") for i in range(6)] + [row(6, "honest"), row(7, "honest")]
    check("UNRELIABLE" in rt.verdict(broken, bad_rows), rt.verdict(broken, bad_rows))

    for b in bad:
        print("FAIL", b)
    print("all checks pass" if not bad else f"{len(bad)} checks fail")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
