"""Offline audit of matched questions and actual common-feedback checkpoint history."""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    state = read(args.results / "execution-state.json")
    assert state["status"] == "complete" and state["complete_repeats"]
    cells = [c for c in state["cells"] if c["completed"]
             and c.get("eligible_for_final_comparison") and c["repeat"] in state["complete_repeats"]]
    assert len(cells) == 8 * len(state["complete_repeats"])
    references, audited = {}, []
    for cell in cells:
        key = cell["key"]
        report_path, = (args.results / "cells" / key).glob("metric-*/report.json")
        assert hashlib.sha256(report_path.read_bytes()).hexdigest() == cell["report_sha256"]
        records = read(report_path)["cells"][0]["records"]
        reference = [{k: r[k] for k in ("phase", "task", "metric", "agent", "ask", "question", "gold")}
                     for r in records]
        reference.sort(key=lambda r: (r["phase"], r["task"]))
        encoded = json.dumps(reference, sort_keys=True, ensure_ascii=False).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        ds = cell["dataset"]
        assert references.setdefault(ds, digest) == digest, (key, "Questions or reference answers differ")

        journal = args.results / "memory" / key / "memory-events.jsonl"
        pending, history, snapshot, counts = {}, [], None, Counter()
        for line in journal.read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if event["event"] == "request":
                assert event["index"] not in pending
                pending[event["index"]] = event["request"]
                continue
            req = pending.pop(event["index"])
            response = event["response"]
            assert "error" not in response, (key, event["index"], response)
            op = req["op"]
            counts[op] += 1
            if op == "begin":
                assert response["common_feedback"] == history, (key, "History mismatch")
                block = response["system_prompt"].split("Environment feedback from your own earlier tasks (binary correctness; no reference answers):\n", 1)[1].split("\n", 1)[0]
                assert json.loads(block) == history
                for item in history:
                    assert set(item) == {"question", "own_answer", "correct", "own_sql", "own_observations"}
            elif op == "end":
                observations = [{"tool": e["tool"], "output": e["output"][:350]}
                                for e in req["transcript"] if e.get("kind") == "tool" and e.get("tool") == "run_sql"][-3:]
                history = (history + [{"question": req["question"], "own_answer": req.get("answer"),
                    "correct": bool(req["correct"]), "own_sql": (req.get("sql") or "")[:1800],
                    "own_observations": observations}])[-3:]
            elif op == "checkpoint":
                assert snapshot is None
                snapshot = copy.deepcopy(history)
            elif op == "restore":
                assert snapshot is not None
                history = copy.deepcopy(snapshot)
            else:
                assert op == "close"
        assert not pending
        assert counts["begin"] == counts["end"] == len(records)
        assert counts["checkpoint"] == 1 and counts["restore"] == 11
        audited.append({"cell": key, "tasks": len(records), "operations": dict(counts),
                        "journal_sha256": hashlib.sha256(journal.read_bytes()).hexdigest()})
    result = {"status": "passed", "complete_repeats": state["complete_repeats"],
              "matched_reference_hashes": references, "cells": audited,
              "checks": ["Same questions, parameters and reference values across every arm/repeat within each schema",
                         "Actual bounded own-result feedback matches the memory journal and emitted planner prompt",
                         "All eleven change branches restore the post-held-out common-feedback checkpoint",
                         "No reference values/SQL or hidden phase labels are added to common feedback"]}
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "cells": len(audited), "tasks": sum(c["tasks"] for c in audited)}))


if __name__ == "__main__":
    main()
