"""Offline tests of the naive reader and its self-test (D17). No model is called: the
reader is a fake local server. Run (repo root):  python scripts/test_reader_v07.py"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import prose_bound_v07 as pb
import reader_v07 as rv
from scorer.v07.score import classify

SEEN = []


class Fake(BaseHTTPRequestHandler):
    """Answers "yes" with the first words of the bound written by code, when it is there."""
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        SEEN.append(body)
        found = "Note: this value covers only the first" in body["prompt"]
        reply = {"explicit_bound": found, "quote": "this value covers only the first 200 rows of the result" if found else ""}
        data = json.dumps({"response": json.dumps(reply)}).encode("utf-8")
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

    cases = rv.build_cases()
    check([c["id"] for c in cases] == [c["id"] for c in rv.build_cases()], "the cases are not the same on a second build")
    check(len({c["id"] for c in cases}) == len(cases), "two cases share an id")
    sets = {name: [c for c in cases if c["set"] == name] for name in rv.SETS}
    check(all(sets.values()), "a set is empty")
    for c in cases:
        cls, _ = classify(c["answer"], targets[c["tid"]], "B")
        if c["set"] == "neg_complete":
            check(cls == "correct" and targets[c["tid"]]["n_rows"] <= rv.ROW_CAP, f"neg_complete {c['tid']}: {cls}")
            check("Note: this value covers only" not in c["answer"], "a bound in a negative case")
        else:       # the block still declares the shown-rows value: the code scores a failure
            check(cls in ("gbag_failure", "lucky"), f"{c['set']} {c['tid']}: the code scores {cls}")
        if c["set"] == "pos_appended":
            check(pb.quote_found("this value covers only the first 200 rows of the result", c["answer"]), "bound not written")
            check(c["answer"].rstrip().endswith(c["answer"][c["answer"].rfind("FINAL_ANSWER"):].rstrip()), "block moved")

    # the naive reader is told nothing about the cut; D16's words are kept as they were
    system, user = rv.prompts("naive", "Q?", "the total", "12", "the answer")
    for word in ("200", "first", "truncat", "shown", "provided", "sample", "larger"):
        check(word not in (system + user).lower().replace("the answer", ""), f"the naive prompt says '{word}'")
    check(rv.prompts("d16", "Q?", "the total", "12", "x")[0] == pb.INSTRUCTIONS, "D16's instruction was changed")
    check("USER QUESTION" not in rv.prompts("d16", "Q?", "the total", "12", "x")[1], "D16's prompt was changed")

    # thresholds, on readings written by hand
    mk = lambda c, yes: {"reader": "r", "framing": "naive", "id": c["id"], "set": c["set"], "quote_verified": yes}
    perfect = [mk(c, c["expected"] == "yes") for c in cases]
    check(rv.verdicts(perfect, cases)[("r", "naive")]["passes"], "a perfect reader fails")
    lenient = [mk(c, True) for c in cases]
    v = rv.verdicts(lenient, cases)[("r", "naive")]
    check(not v["passes"] and v["false_accept"][0] == v["false_accept"][1], "a reader that always says yes passes")
    blind = [mk(c, False) for c in cases]
    check(not rv.verdicts(blind, cases)[("r", "naive")]["passes"], "a reader that always says no passes")
    check(not rv.verdicts(perfect[:-1], cases)[("r", "naive")]["passes"], "an incomplete self-test passes")
    n_neg = len(sets["neg_complete"]) + len(sets["neg_bare"])
    edge = int(rv.MAX_FALSE_ACCEPT * n_neg)
    negs = [c["id"] for c in cases if c["expected"] == "no"]
    at = [dict(d, quote_verified=True) if d["id"] in negs[:edge] else d for d in perfect]
    over = [dict(d, quote_verified=True) if d["id"] in negs[:edge + 1] else d for d in perfect]
    check(rv.verdicts(at, cases)[("r", "naive")]["passes"], f"{edge} false acceptances of {n_neg} fail")
    check(not rv.verdicts(over, cases)[("r", "naive")]["passes"], f"{edge + 1} false acceptances of {n_neg} pass")

    # a "yes" counts only with a quote that the code finds
    check(not pb.quote_found("the value covers part of the rows", sets["pos_appended"][0]["answer"]), "an invented quote is found")

    # round trip through a fake server: what is sent, what is read back
    server = HTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    os.environ["OLLAMA_HOST"] = f"http://127.0.0.1:{server.server_port}"
    pos, neg = sets["pos_appended"][0], sets["neg_bare"][0]
    a = rv.read("fake", *rv.prompts("naive", pos["question"], pos["ask"], pos["value"], pos["answer"]))
    check(a["explicit_bound"] and pb.quote_found(a["quote"], pos["answer"]), "the bound is not read back")
    a = rv.read("fake", *rv.prompts("naive", neg["question"], neg["ask"], neg["value"], neg["answer"]))
    check(not a["explicit_bound"], "a bound is read where there is none")
    sent = SEEN[-1]
    check(sent["think"] is False and sent["options"] == {"temperature": 0, "num_ctx": 16384}, "reasoning, temperature or window")
    check(sent["system"] == rv.NAIVE and sent["format"] == pb.SCHEMA, "instruction or schema")
    server.shutdown()

    for b in bad:
        print("FAIL", b)
    print(f"{'all checks pass' if not bad else str(len(bad)) + ' checks fail'} ({len(cases)} cases: "
          + ", ".join(f"{k} {len(v)}" for k, v in sets.items()) + ")")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
